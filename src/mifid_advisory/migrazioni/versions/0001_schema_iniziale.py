"""schema iniziale

Revision ID: 0001
Revises: 
Create Date: 2026-11-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('dati_mercato',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('serie', sa.String(length=60), nullable=False),
    sa.Column('data', sa.Date(), nullable=False),
    sa.Column('valore', sa.Float(), nullable=False),
    sa.Column('fonte', sa.String(length=200), nullable=False),
    sa.Column('aggiornato_il', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('serie', 'data')
    )
    with op.batch_alter_table('dati_mercato', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_dati_mercato_serie'), ['serie'], unique=False)

    op.create_table('eventi_audit',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('momento', sa.DateTime(timezone=True), nullable=False),
    sa.Column('utente', sa.String(length=200), nullable=False),
    sa.Column('azione', sa.String(length=60), nullable=False),
    sa.Column('entita', sa.String(length=60), nullable=False),
    sa.Column('entita_id', sa.Integer(), nullable=True),
    sa.Column('contenuto', sa.JSON(), nullable=False),
    sa.Column('hash_precedente', sa.String(length=64), nullable=False),
    sa.Column('hash', sa.String(length=64), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('hash')
    )
    with op.batch_alter_table('eventi_audit', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_eventi_audit_azione'), ['azione'], unique=False)

    op.create_table('prodotti',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('isin', sa.String(length=12), nullable=False),
    sa.Column('nome', sa.String(length=200), nullable=False),
    sa.Column('classe_strumento', sa.String(length=30), nullable=False),
    sa.Column('categoria', sa.String(length=60), nullable=False),
    sa.Column('sri', sa.Integer(), nullable=False),
    sa.Column('dati', sa.JSON(), nullable=False),
    sa.Column('attivo', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('prodotti', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_prodotti_isin'), ['isin'], unique=True)

    op.create_table('utenti',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=200), nullable=False),
    sa.Column('nome', sa.String(length=200), nullable=False),
    sa.Column('ruolo', sa.String(length=20), nullable=False),
    sa.Column('password_hash', sa.String(length=300), nullable=False),
    sa.Column('attivo', sa.Boolean(), nullable=False),
    sa.Column('creato_il', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('utenti', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_utenti_email'), ['email'], unique=True)

    op.create_table('clienti',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=100), nullable=False),
    sa.Column('cognome', sa.String(length=100), nullable=False),
    sa.Column('data_nascita', sa.Date(), nullable=True),
    sa.Column('email', sa.String(length=200), nullable=True),
    sa.Column('consulente_id', sa.Integer(), nullable=False),
    sa.Column('creato_il', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['consulente_id'], ['utenti.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('clienti', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_clienti_consulente_id'), ['consulente_id'], unique=False)

    op.create_table('rendimenti',
    sa.Column('prodotto_id', sa.Integer(), nullable=False),
    sa.Column('data', sa.Date(), nullable=False),
    sa.Column('valore', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['prodotto_id'], ['prodotti.id'], ),
    sa.PrimaryKeyConstraint('prodotto_id', 'data')
    )
    op.create_table('questionari',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('cliente_id', sa.Integer(), nullable=False),
    sa.Column('risposte', sa.JSON(), nullable=False),
    sa.Column('compilato_il', sa.DateTime(timezone=True), nullable=False),
    sa.Column('versione', sa.String(length=20), nullable=False),
    sa.ForeignKeyConstraint(['cliente_id'], ['clienti.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('questionari', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_questionari_cliente_id'), ['cliente_id'], unique=False)

    op.create_table('profili',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('cliente_id', sa.Integer(), nullable=False),
    sa.Column('questionario_id', sa.Integer(), nullable=False),
    sa.Column('classe_rischio', sa.Integer(), nullable=False),
    sa.Column('dettagli', sa.JSON(), nullable=False),
    sa.Column('creato_il', sa.DateTime(timezone=True), nullable=False),
    sa.Column('valido_fino', sa.Date(), nullable=False),
    sa.ForeignKeyConstraint(['cliente_id'], ['clienti.id'], ),
    sa.ForeignKeyConstraint(['questionario_id'], ['questionari.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('profili', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_profili_cliente_id'), ['cliente_id'], unique=False)

    op.create_table('proposte',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('cliente_id', sa.Integer(), nullable=False),
    sa.Column('profilo_id', sa.Integer(), nullable=False),
    sa.Column('consulente_id', sa.Integer(), nullable=False),
    sa.Column('importo', sa.Float(), nullable=False),
    sa.Column('stato', sa.String(length=30), nullable=False),
    sa.Column('metodo', sa.String(length=20), nullable=False),
    sa.Column('portafoglio_attuale', sa.JSON(), nullable=True),
    sa.Column('creato_il', sa.DateTime(timezone=True), nullable=False),
    sa.Column('decisa_il', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['cliente_id'], ['clienti.id'], ),
    sa.ForeignKeyConstraint(['consulente_id'], ['utenti.id'], ),
    sa.ForeignKeyConstraint(['profilo_id'], ['profili.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('proposte', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_proposte_cliente_id'), ['cliente_id'], unique=False)

    op.create_table('posizioni',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('proposta_id', sa.Integer(), nullable=False),
    sa.Column('isin', sa.String(length=12), nullable=False),
    sa.Column('peso', sa.Float(), nullable=False),
    sa.Column('importo', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['proposta_id'], ['proposte.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('posizioni', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_posizioni_proposta_id'), ['proposta_id'], unique=False)

    op.create_table('verifiche',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('proposta_id', sa.Integer(), nullable=False),
    sa.Column('esito', sa.String(length=30), nullable=False),
    sa.Column('controlli', sa.JSON(), nullable=False),
    sa.Column('metriche', sa.JSON(), nullable=False),
    sa.Column('creato_il', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['proposta_id'], ['proposte.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('proposta_id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('verifiche')
    with op.batch_alter_table('posizioni', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_posizioni_proposta_id'))

    op.drop_table('posizioni')
    with op.batch_alter_table('proposte', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_proposte_cliente_id'))

    op.drop_table('proposte')
    with op.batch_alter_table('profili', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_profili_cliente_id'))

    op.drop_table('profili')
    with op.batch_alter_table('questionari', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_questionari_cliente_id'))

    op.drop_table('questionari')
    op.drop_table('rendimenti')
    with op.batch_alter_table('clienti', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_clienti_consulente_id'))

    op.drop_table('clienti')
    with op.batch_alter_table('utenti', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_utenti_email'))

    op.drop_table('utenti')
    with op.batch_alter_table('prodotti', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_prodotti_isin'))

    op.drop_table('prodotti')
    with op.batch_alter_table('eventi_audit', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_eventi_audit_azione'))

    op.drop_table('eventi_audit')
    with op.batch_alter_table('dati_mercato', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_dati_mercato_serie'))

    op.drop_table('dati_mercato')
