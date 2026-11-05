"""Migrazioni dello schema con Alembic.

Lo schema del database evolve solo tramite migrazioni versionate (``migrazioni/versions``), applicate all'avvio
dell'API o con ``mifid-advisory migra``. Per crearne una nuova dopo aver modificato ``db.py``::

    mifid-advisory nuova-migrazione "descrizione"
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

CARTELLA = Path(__file__).parent


def configurazione(url: str | None = None) -> Config:
    from ..config import impostazioni

    cfg = Config()
    cfg.set_main_option("script_location", str(CARTELLA))
    cfg.set_main_option("url", url or impostazioni().url_sqlalchemy)
    return cfg


def migra(url: str | None = None, revisione: str = "head") -> None:
    command.upgrade(configurazione(url), revisione)


def nuova(messaggio: str, url: str | None = None) -> None:
    command.revision(configurazione(url), message=messaggio, autogenerate=True)
