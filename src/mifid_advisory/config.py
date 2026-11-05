"""Configurazione da variabili d'ambiente (o file ``.env``), con valori di default adatti allo sviluppo."""

from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

CHIAVE_SVILUPPO = "solo-per-sviluppo-e-demo-cambiare-in-produzione"


class Impostazioni(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MIFID_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./mifid.db"
    chiave_segreta: str = CHIAVE_SVILUPPO  # firma dei token JWT
    minuti_token: int = 60
    demo: bool = True  # crea utenti, catalogo e clienti dimostrativi all'avvio
    validita_profilo_mesi: int = 12
    origini_cors: list[str] = ["*"]

    @model_validator(mode="after")
    def _chiave(self):
        if not self.demo and self.chiave_segreta == CHIAVE_SVILUPPO:
            raise ValueError("Con demo disattivata va impostata MIFID_CHIAVE_SEGRETA (almeno 32 caratteri casuali)")
        return self

    @property
    def url_sqlalchemy(self) -> str:
        """I servizi cloud forniscono spesso ``postgres://``: SQLAlchemy con psycopg 3 vuole ``postgresql+psycopg``."""
        url = self.database_url
        for prefisso in ("postgres://", "postgresql://"):
            if url.startswith(prefisso):
                return "postgresql+psycopg://" + url[len(prefisso):]
        return url


@lru_cache
def impostazioni() -> Impostazioni:
    return Impostazioni()
