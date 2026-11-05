from datetime import date
from pathlib import Path

from sqlalchemy import func, select

from mifid_advisory import mercato
from mifid_advisory.db import DatoMercato

DATI = Path(__file__).parent / "dati"


def test_sdmx_csv():
    oss = mercato.leggi_sdmx_csv((DATI / "estr.csv").read_text())
    assert oss[0] == (date(2025, 10, 30), 1.926) and len(oss) == 3


def test_jsonstat():
    oss = mercato.leggi_jsonstat((DATI / "hicp.json").read_text())
    assert oss == [(date(2025, 7, 1), 1.7), (date(2025, 8, 1), 1.6), (date(2025, 9, 1), 1.8)]


def _finto(url: str) -> str:
    return (DATI / ("estr.csv" if "csvdata" in url else "hicp.json")).read_text()


def test_aggiornamento_idempotente(sessione):
    e1 = mercato.aggiorna(sessione, _finto)
    assert e1["estr"]["nuove"] == 3 and all("errore" not in v for v in e1.values())
    e2 = mercato.aggiorna(sessione, _finto)
    assert all(v["nuove"] == 0 for v in e2.values())
    sessione.commit()
    assert sessione.scalar(select(func.count(DatoMercato.id))) == 3 * 4
    assert mercato.tasso_privo_rischio(sessione) == 0.01929


def test_fonte_non_raggiungibile_usa_valori_di_esempio(sessione):
    def giu(url):
        raise ConnectionError("rete assente")

    esito = mercato.aggiorna(sessione, giu)
    assert all(v.get("esempio") for v in esito.values())
    assert 0 < mercato.tasso_privo_rischio(sessione) < 0.05
    # al giro successivo, con dati già presenti, non si aggiungono altri valori di esempio
    assert not any(v.get("esempio") for v in mercato.aggiorna(sessione, giu).values())
