"""Autenticazione con token JWT e autorizzazione per ruolo.

- **consulente**: vede e gestisce solo i propri clienti;
- **compliance**: legge tutto (clienti, proposte, registro di audit) ma non crea né decide proposte;
- **admin**: tutto, compresa la gestione degli utenti e l'aggiornamento dei dati di mercato.
"""

from __future__ import annotations

from datetime import timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .config import impostazioni
from .db import Cliente, Utente, adesso, ottieni_sessione

ALGORITMO = "HS256"
schema_oauth = OAuth2PasswordBearer(tokenUrl="/auth/token")


def crea_token(utente: Utente) -> str:
    imp = impostazioni()
    dati = {"sub": str(utente.id), "ruolo": utente.ruolo, "iat": adesso(),
            "exp": adesso() + timedelta(minutes=imp.minuti_token)}
    return jwt.encode(dati, imp.chiave_segreta, algorithm=ALGORITMO)


def utente_corrente(token: str = Depends(schema_oauth), s: Session = Depends(ottieni_sessione)) -> Utente:
    non_autorizzato = HTTPException(status.HTTP_401_UNAUTHORIZED, "Token non valido o scaduto",
                                    headers={"WWW-Authenticate": "Bearer"})
    try:
        dati = jwt.decode(token, impostazioni().chiave_segreta, algorithms=[ALGORITMO])
    except jwt.PyJWTError as e:
        raise non_autorizzato from e
    u = s.get(Utente, int(dati["sub"]))
    if u is None or not u.attivo:
        raise non_autorizzato
    return u


def richiede(*ruoli: str):
    """Dipendenza che ammette solo i ruoli indicati."""

    def controllo(u: Utente = Depends(utente_corrente)) -> Utente:
        if u.ruolo not in ruoli:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Operazione riservata a: {', '.join(ruoli)}")
        return u

    return controllo


def puo_vedere(u: Utente, c: Cliente) -> bool:
    return u.ruolo in ("compliance", "admin") or c.consulente_id == u.id


def puo_operare(u: Utente, c: Cliente) -> bool:
    return u.ruolo == "admin" or (u.ruolo == "consulente" and c.consulente_id == u.id)
