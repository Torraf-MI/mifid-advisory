"""Pipeline dei dati di mercato: tassi della BCE e inflazione Eurostat, aggiornati ogni notte.

Fonti pubbliche, senza chiavi di accesso:

- **€STR** (tasso a breve dell'area euro) e **tasso sui depositi presso la BCE** dal portale dati della BCE
  (API SDMX, formato CSV);
- **inflazione armonizzata (HICP)** di Italia e area euro da Eurostat (API di diffusione, formato JSON-stat).

Il tasso privo di rischio usato per i rendimenti attesi dei prodotti è l'ultimo €STR disponibile; l'inflazione
serve a mostrare al cliente il rendimento reale atteso. Se una fonte non risponde l'aggiornamento registra
l'errore e si continua a usare l'ultimo valore salvato (o, al primo avvio, i valori di esempio inclusi nel
pacchetto). L'aggiornamento è idempotente: rieseguirlo non duplica le osservazioni.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from importlib import resources

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import DatoMercato, adesso

BCE = "https://data-api.ecb.europa.eu/service/data"
EUROSTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"


@dataclass(frozen=True)
class Serie:
    codice: str
    descrizione: str
    url: str
    formato: str  # sdmx_csv o jsonstat
    scala: float = 0.01  # da percentuale a decimale


SERIE = [
    Serie("estr", "€STR, tasso overnight dell'area euro",
          f"{BCE}/EST/B.EU000A2X2A25.WT?format=csvdata&lastNObservations=60", "sdmx_csv"),
    Serie("bce_depositi", "Tasso sui depositi presso la BCE", f"{BCE}/FM/D.U2.EUR.4F.KR.DFR.LEV?format=csvdata"
          "&lastNObservations=30", "sdmx_csv"),
    Serie("inflazione_it", "Inflazione armonizzata Italia (HICP, variazione annua)",
          f"{EUROSTAT}/prc_hicp_manr?geo=IT&coicop=CP00&lastTimePeriod=24", "jsonstat"),
    Serie("inflazione_ea", "Inflazione armonizzata area euro (HICP, variazione annua)",
          f"{EUROSTAT}/prc_hicp_manr?geo=EA&coicop=CP00&lastTimePeriod=24", "jsonstat"),
]


def _data(periodo: str) -> date:
    """Date SDMX ed Eurostat: 2025-11-03, 2025-11, 2025M11."""
    p = periodo.strip().replace("M", "-")
    parti = [int(x) for x in p.split("-")]
    return date(parti[0], parti[1] if len(parti) > 1 else 12, parti[2] if len(parti) > 2 else 1)


def leggi_sdmx_csv(testo: str) -> list[tuple[date, float]]:
    """Osservazioni da una risposta SDMX in CSV (colonne TIME_PERIOD e OBS_VALUE)."""
    righe = csv.DictReader(io.StringIO(testo))
    out = []
    for r in righe:
        if r.get("OBS_VALUE") not in (None, "", "NaN"):
            out.append((_data(r["TIME_PERIOD"]), float(r["OBS_VALUE"])))
    return sorted(out)


def leggi_jsonstat(testo: str) -> list[tuple[date, float]]:
    """Osservazioni da una risposta JSON-stat 2.0 di Eurostat con una sola serie (dimensione tempo variabile)."""
    j = json.loads(testo)
    tempi = j["dimension"]["time"]["category"]["index"]
    valori = j["value"]
    # Con una sola serie l'indice del valore coincide con la posizione del periodo
    dimensioni = j["size"]
    passo = 1
    for nome, n in zip(reversed(j["id"]), reversed(dimensioni), strict=True):
        if nome == "time":
            break
        passo *= n
    out = []
    for periodo, pos in tempi.items():
        v = valori.get(str(pos * passo)) if isinstance(valori, dict) else valori[pos * passo]
        if v is not None:
            out.append((_data(periodo), float(v)))
    return sorted(out)


def esempio() -> dict[str, list[tuple[date, float]]]:
    """Valori di esempio inclusi nel pacchetto, usati se le fonti non sono raggiungibili al primo avvio."""
    j = json.loads(resources.files("mifid_advisory").joinpath("dati/mercato_esempio.json").read_text("utf-8"))
    return {k: [(_data(d), v) for d, v in osservazioni] for k, osservazioni in j["serie"].items()}


Scaricatore = Callable[[str], str]


def scarica(url: str, timeout: float = 20.0) -> str:
    r = httpx.get(url, timeout=timeout, headers={"Accept": "text/csv, application/json"}, follow_redirects=True)
    r.raise_for_status()
    return r.text


def salva(s: Session, serie: str, osservazioni: list[tuple[date, float]], fonte: str, scala: float = 0.01) -> int:
    """Inserisce o aggiorna le osservazioni; restituisce quante sono nuove."""
    esistenti = {d.data: d for d in s.scalars(select(DatoMercato).where(DatoMercato.serie == serie))}
    nuove = 0
    for d, v in osservazioni:
        valore = round(v * scala, 6)
        if d in esistenti:
            if abs(esistenti[d].valore - valore) > 1e-9:
                esistenti[d].valore, esistenti[d].aggiornato_il = valore, adesso()
        else:
            s.add(DatoMercato(serie=serie, data=d, valore=valore, fonte=fonte))
            nuove += 1
    return nuove


def aggiorna(s: Session, scaricatore: Scaricatore = scarica, usa_esempio: bool = True) -> dict[str, dict]:
    """Scarica tutte le serie e le salva. Restituisce, per serie, osservazioni nuove o errore."""
    esito = {}
    for serie in SERIE:
        try:
            testo = scaricatore(serie.url)
            oss = leggi_sdmx_csv(testo) if serie.formato == "sdmx_csv" else leggi_jsonstat(testo)
            if not oss:
                raise ValueError("risposta senza osservazioni")
            esito[serie.codice] = {"nuove": salva(s, serie.codice, oss, serie.url, serie.scala),
                                   "ultima": oss[-1][0].isoformat()}
        except Exception as e:  # noqa: BLE001 - una fonte che non risponde non deve fermare le altre
            esito[serie.codice] = {"errore": f"{type(e).__name__}: {e}"[:300]}
            vuota = s.scalars(select(DatoMercato).where(DatoMercato.serie == serie.codice).limit(1)).first() is None
            if usa_esempio and vuota:
                salva(s, serie.codice, esempio()[serie.codice], "valori di esempio inclusi nel pacchetto")
                esito[serie.codice]["esempio"] = True
    s.flush()
    return esito


def ultimo(s: Session, serie: str) -> DatoMercato | None:
    return s.scalars(select(DatoMercato).where(DatoMercato.serie == serie)
                     .order_by(DatoMercato.data.desc()).limit(1)).first()


def tasso_privo_rischio(s: Session, default: float = 0.02) -> float:
    d = ultimo(s, "estr")
    return d.valore if d else default
