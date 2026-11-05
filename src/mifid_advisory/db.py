"""Database: tabelle SQLAlchemy 2.0 (PostgreSQL in produzione, SQLite in sviluppo e nei test).

Lo schema segue il flusso della consulenza: un **consulente** segue i suoi **clienti**; ogni cliente compila uno o
più **questionari**, da cui nasce un **profilo** con una scadenza; su un profilo valido si costruiscono le
**proposte**, ciascuna con le sue **posizioni** e la **verifica di adeguatezza**. Il **catalogo** dei prodotti ha
le serie storiche dei rendimenti; i **dati di mercato** (tassi BCE, inflazione) sono aggiornati da una pipeline.
Ogni operazione rilevante finisce nel **registro di audit**.

Le risposte del questionario, i dettagli del profilo e le metriche sono salvati come JSON: il loro contenuto è
validato dai modelli Pydantic e conservato esattamente come era al momento della decisione, come richiede l'obbligo
di registrazione dell'articolo 16(6) di MiFID II.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from .config import impostazioni


def adesso() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {dict: JSON, list: JSON}


class Utente(Base):
    __tablename__ = "utenti"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(200))
    ruolo: Mapped[str] = mapped_column(String(20))  # consulente, compliance, admin
    password_hash: Mapped[str] = mapped_column(String(300))
    attivo: Mapped[bool] = mapped_column(Boolean, default=True)
    creato_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=adesso)


class Cliente(Base):
    __tablename__ = "clienti"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(100))
    cognome: Mapped[str] = mapped_column(String(100))
    data_nascita: Mapped[date | None] = mapped_column(Date)
    email: Mapped[str | None] = mapped_column(String(200))
    consulente_id: Mapped[int] = mapped_column(ForeignKey("utenti.id"), index=True)
    creato_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=adesso)
    consulente: Mapped[Utente] = relationship()
    profili: Mapped[list[Profilo]] = relationship(back_populates="cliente", order_by="Profilo.id")


class Questionario(Base):
    __tablename__ = "questionari"
    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clienti.id"), index=True)
    risposte: Mapped[dict]
    compilato_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=adesso)
    versione: Mapped[str] = mapped_column(String(20), default="2025.1")


class Profilo(Base):
    __tablename__ = "profili"
    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clienti.id"), index=True)
    questionario_id: Mapped[int] = mapped_column(ForeignKey("questionari.id"))
    classe_rischio: Mapped[int] = mapped_column(Integer)
    dettagli: Mapped[dict]
    creato_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=adesso)
    valido_fino: Mapped[date] = mapped_column(Date)
    cliente: Mapped[Cliente] = relationship(back_populates="profili")


class Prodotto(Base):
    __tablename__ = "prodotti"
    id: Mapped[int] = mapped_column(primary_key=True)
    isin: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(200))
    classe_strumento: Mapped[str] = mapped_column(String(30))
    categoria: Mapped[str] = mapped_column(String(60))
    sri: Mapped[int] = mapped_column(Integer)
    dati: Mapped[dict]  # tutte le caratteristiche del prodotto
    attivo: Mapped[bool] = mapped_column(Boolean, default=True)


class Rendimento(Base):
    __tablename__ = "rendimenti"
    prodotto_id: Mapped[int] = mapped_column(ForeignKey("prodotti.id"), primary_key=True)
    data: Mapped[date] = mapped_column(Date, primary_key=True)
    valore: Mapped[float] = mapped_column(Float)


class Proposta(Base):
    __tablename__ = "proposte"
    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clienti.id"), index=True)
    profilo_id: Mapped[int] = mapped_column(ForeignKey("profili.id"))
    consulente_id: Mapped[int] = mapped_column(ForeignKey("utenti.id"))
    importo: Mapped[float] = mapped_column(Float)
    stato: Mapped[str] = mapped_column(String(30))  # adeguata, non_adeguata, accettata, rifiutata
    metodo: Mapped[str] = mapped_column(String(20))  # ottimizzata o manuale
    portafoglio_attuale: Mapped[dict | None]
    creato_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=adesso)
    decisa_il: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posizioni: Mapped[list[Posizione]] = relationship(back_populates="proposta", order_by="Posizione.peso.desc()")
    verifica: Mapped[VerificaAdeguatezza | None] = relationship(back_populates="proposta", uselist=False)
    profilo: Mapped[Profilo] = relationship()
    cliente: Mapped[Cliente] = relationship()


class Posizione(Base):
    __tablename__ = "posizioni"
    id: Mapped[int] = mapped_column(primary_key=True)
    proposta_id: Mapped[int] = mapped_column(ForeignKey("proposte.id"), index=True)
    isin: Mapped[str] = mapped_column(String(12))
    peso: Mapped[float] = mapped_column(Float)
    importo: Mapped[float] = mapped_column(Float)
    proposta: Mapped[Proposta] = relationship(back_populates="posizioni")


class VerificaAdeguatezza(Base):
    __tablename__ = "verifiche"
    id: Mapped[int] = mapped_column(primary_key=True)
    proposta_id: Mapped[int] = mapped_column(ForeignKey("proposte.id"), unique=True)
    esito: Mapped[str] = mapped_column(String(30))
    controlli: Mapped[list]
    metriche: Mapped[dict]
    creato_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=adesso)
    proposta: Mapped[Proposta] = relationship(back_populates="verifica")


class DatoMercato(Base):
    __tablename__ = "dati_mercato"
    __table_args__ = (UniqueConstraint("serie", "data"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    serie: Mapped[str] = mapped_column(String(60), index=True)
    data: Mapped[date] = mapped_column(Date)
    valore: Mapped[float] = mapped_column(Float)
    fonte: Mapped[str] = mapped_column(String(200))
    aggiornato_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=adesso)


class EventoAudit(Base):
    __tablename__ = "eventi_audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    momento: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=adesso)
    utente: Mapped[str] = mapped_column(String(200))
    azione: Mapped[str] = mapped_column(String(60), index=True)
    entita: Mapped[str] = mapped_column(String(60))
    entita_id: Mapped[int | None] = mapped_column(Integer)
    contenuto: Mapped[dict]
    hash_precedente: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)
    note: Mapped[str | None] = mapped_column(Text)


# ------------------------------------------------------------------------------------------- connessione
_motore: Engine | None = None
_sessioni: sessionmaker | None = None


def motore(url: str | None = None) -> Engine:
    global _motore, _sessioni
    if _motore is None or url is not None:
        url = url or impostazioni().url_sqlalchemy
        argomenti = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _motore = create_engine(url, connect_args=argomenti, pool_pre_ping=True)
        if url.startswith("sqlite"):
            event.listen(_motore, "connect", lambda c, _: c.execute("PRAGMA foreign_keys=ON"))
        _sessioni = sessionmaker(_motore, expire_on_commit=False)
    return _motore


def sessione() -> Session:
    motore()
    return _sessioni()


def ottieni_sessione() -> Iterator[Session]:
    """Dipendenza FastAPI: una sessione per richiesta."""
    s = sessione()
    try:
        yield s
    finally:
        s.close()


def crea_tabelle() -> None:
    Base.metadata.create_all(motore())
