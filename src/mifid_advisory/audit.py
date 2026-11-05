"""Registro di audit a prova di manomissione: ogni evento contiene l'impronta (SHA-256) del precedente.

MiFID II (articolo 16(6) della direttiva e articolo 72 del Regolamento delegato 2017/565) obbliga a conservare le
registrazioni dei servizi prestati in modo che non possano essere alterate senza lasciare traccia. Il registro è una
catena di hash, lo stesso principio di un registro distribuito: ogni evento salva il proprio contenuto e l'hash
dell'evento precedente, e il proprio hash è calcolato su entrambi. Se qualcuno modifica o cancella un evento
direttamente nel database, la verifica della catena indica il primo evento non più coerente.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import EventoAudit, adesso

GENESI = "0" * 64


def _canonico(dati: dict) -> str:
    return json.dumps(dati, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def impronta(precedente: str, momento: datetime, utente: str, azione: str, entita: str, entita_id: int | None,
             contenuto: dict) -> str:
    if momento.tzinfo is not None:  # PostgreSQL restituisce l'ora nel fuso della sessione, SQLite senza fuso
        momento = momento.astimezone(UTC).replace(tzinfo=None)
    momento = momento.isoformat(timespec="microseconds")
    testo = _canonico({"precedente": precedente, "momento": momento, "utente": utente, "azione": azione,
                       "entita": entita, "entita_id": entita_id, "contenuto": contenuto})
    return hashlib.sha256(testo.encode("utf-8")).hexdigest()


def registra(s: Session, utente: str, azione: str, entita: str, entita_id: int | None, contenuto: dict,
             note: str | None = None) -> EventoAudit:
    """Aggiunge un evento in coda alla catena (nella transazione corrente: il commit è del chiamante)."""
    ultimo = s.scalars(select(EventoAudit).order_by(EventoAudit.id.desc()).limit(1).with_for_update()).first()
    precedente = ultimo.hash if ultimo else GENESI
    contenuto = json.loads(_canonico(contenuto))  # solo tipi JSON, come saranno riletti dal database
    momento = adesso()
    e = EventoAudit(momento=momento, utente=utente, azione=azione, entita=entita, entita_id=entita_id,
                    contenuto=contenuto, hash_precedente=precedente, note=note,
                    hash=impronta(precedente, momento, utente, azione, entita, entita_id, contenuto))
    s.add(e)
    s.flush()
    return e


@dataclass
class EsitoVerifica:
    integro: bool
    eventi: int
    primo_errore: int | None = None
    motivo: str = ""


def verifica_catena(s: Session) -> EsitoVerifica:
    precedente = GENESI
    n = 0
    for e in s.scalars(select(EventoAudit).order_by(EventoAudit.id)):
        n += 1
        if e.hash_precedente != precedente:
            return EsitoVerifica(False, n, e.id, "collegamento con l'evento precedente interrotto (evento cancellato "
                                                  "o inserito fuori sequenza)")
        atteso = impronta(e.hash_precedente, e.momento, e.utente, e.azione, e.entita, e.entita_id, e.contenuto)
        if atteso != e.hash:
            return EsitoVerifica(False, n, e.id, "contenuto modificato dopo la registrazione")
        precedente = e.hash
    return EsitoVerifica(True, n)
