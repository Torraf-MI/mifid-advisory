"""Fixture condivise. I test sul database girano su SQLite e, se ``MIFID_TEST_POSTGRES`` è impostata, anche su
PostgreSQL (in CI con un servizio Postgres 16)."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text

from mifid_advisory import config, db
from mifid_advisory.esempi import CLIENTI, questionario
from mifid_advisory.prodotti import genera_catalogo
from mifid_advisory.profilazione import profila

URL_POSTGRES = os.environ.get("MIFID_TEST_POSTGRES")
DATABASE = ["sqlite"] + (["postgres"] if URL_POSTGRES else [])


@pytest.fixture(scope="session")
def catalogo():
    return genera_catalogo()


@pytest.fixture(scope="session")
def profili():
    return {nome: profila(questionario(nome)) for nome in CLIENTI}


def _pulisci_postgres(url: str) -> None:
    m = create_engine(url.replace("postgresql://", "postgresql+psycopg://"))
    with m.begin() as c:
        c.execute(text("drop schema public cascade; create schema public"))
    m.dispose()


@pytest.fixture(params=DATABASE)
def url_db(request, tmp_path, monkeypatch):
    """Database vuoto, configurato come lo vedrebbe l'applicazione."""
    if request.param == "sqlite":
        url = f"sqlite:///{tmp_path / 'test.db'}"
    else:
        url = URL_POSTGRES
        _pulisci_postgres(url)
    monkeypatch.setenv("MIFID_DATABASE_URL", url)
    monkeypatch.setenv("MIFID_DEMO", "true")
    config.impostazioni.cache_clear()
    db.motore(config.impostazioni().url_sqlalchemy)
    yield url
    db.motore().dispose()
    config.impostazioni.cache_clear()


@pytest.fixture
def sessione(url_db):
    from mifid_advisory.migrazioni import migra

    migra()
    with db.sessione() as s:
        yield s
