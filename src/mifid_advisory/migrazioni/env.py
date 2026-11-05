"""Ambiente Alembic: usa i metadati di ``db.py`` e l'URL passato dalla configurazione."""

from alembic import context
from sqlalchemy import create_engine, pool

from mifid_advisory.db import Base

cfg = context.config
url = cfg.get_main_option("url")
argomenti = {"render_as_batch": url.startswith("sqlite"), "compare_type": True}


def offline() -> None:
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True, **argomenti)
    with context.begin_transaction():
        context.run_migrations()


def online() -> None:
    motore = create_engine(url, poolclass=pool.NullPool)
    with motore.connect() as conn:
        context.configure(connection=conn, target_metadata=Base.metadata, **argomenti)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    offline()
else:
    online()
