"""Endpoint REST, divisi per area. Ogni richiesta che modifica dati è una sola transazione."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, mercato, servizi
from ..db import Cliente, DatoMercato, EventoAudit, Prodotto, Proposta, Utente, ottieni_sessione
from ..dichiarazione import dichiarazione_html
from ..ottimizzazione import OttimizzazioneFallita
from ..questionario import Questionario
from ..sicurezza import crea_token, puo_operare, puo_vedere, richiede, utente_corrente
from . import schemi

TUTTI = ("consulente", "compliance", "admin")


def _errore(e: Exception) -> HTTPException:
    codice = status.HTTP_422_UNPROCESSABLE_ENTITY if isinstance(e, OttimizzazioneFallita) else status.HTTP_409_CONFLICT
    return HTTPException(codice, str(e))


def _cliente(s: Session, u: Utente, cliente_id: int, operare: bool = False) -> Cliente:
    c = s.get(Cliente, cliente_id)
    if c is None or not puo_vedere(u, c):  # 404 anche se esiste ma non è suo: non rivela l'esistenza
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente non trovato")
    if operare and not puo_operare(u, c):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo il consulente del cliente può operare")
    return c


def _proposta(s: Session, u: Utente, proposta_id: int, operare: bool = False) -> Proposta:
    p = s.get(Proposta, proposta_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proposta non trovata")
    _cliente(s, u, p.cliente_id, operare)
    return p


# ------------------------------------------------------------------------------------------- autenticazione
auth = APIRouter(tags=["autenticazione"])


@auth.post("/auth/token", response_model=schemi.Token)
def login(form: OAuth2PasswordRequestForm = Depends(), s: Session = Depends(ottieni_sessione)):
    u = servizi.autentica(s, form.username, form.password)
    if u is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenziali non valide",
                            headers={"WWW-Authenticate": "Bearer"})
    return schemi.Token(access_token=crea_token(u), ruolo=u.ruolo)


@auth.get("/utenti/me", response_model=schemi.UtenteOut)
def io(u: Utente = Depends(utente_corrente)):
    return u


@auth.post("/utenti", response_model=schemi.UtenteOut, status_code=201)
def nuovo_utente(dati: schemi.UtenteIn, u: Utente = Depends(richiede("admin")), s: Session = Depends(ottieni_sessione)):
    if s.scalars(select(Utente).where(Utente.email == dati.email.lower())).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email già registrata")
    nuovo = servizi.crea_utente(s, dati.email, dati.nome, dati.ruolo, dati.password)
    audit.registra(s, u.email, "utente_creato", "utente", nuovo.id, {"email": nuovo.email, "ruolo": nuovo.ruolo})
    s.commit()
    return nuovo


# ---------------------------------------------------------------------------------------------------- clienti
clienti = APIRouter(prefix="/clienti", tags=["clienti"])


@clienti.get("", response_model=list[schemi.ClienteOut])
def elenco_clienti(u: Utente = Depends(utente_corrente), s: Session = Depends(ottieni_sessione)):
    q = select(Cliente).order_by(Cliente.cognome, Cliente.nome)
    if u.ruolo == "consulente":
        q = q.where(Cliente.consulente_id == u.id)
    return s.scalars(q).all()


@clienti.post("", response_model=schemi.ClienteOut, status_code=201)
def nuovo_cliente(dati: schemi.ClienteIn, u: Utente = Depends(richiede("consulente", "admin")),
                  s: Session = Depends(ottieni_sessione)):
    c = servizi.crea_cliente(s, u, dati.nome, dati.cognome, dati.data_nascita, dati.email)
    s.commit()
    return c


@clienti.get("/{cliente_id}", response_model=schemi.ClienteDettaglio)
def scheda_cliente(cliente_id: int, u: Utente = Depends(utente_corrente), s: Session = Depends(ottieni_sessione)):
    c = _cliente(s, u, cliente_id)
    proposte = s.scalars(select(Proposta).where(Proposta.cliente_id == c.id).order_by(Proposta.id.desc())).all()
    return schemi.ClienteDettaglio.model_validate(c).model_copy(
        update={"profilo": c.profili[-1] if c.profili else None, "proposte": proposte})


@clienti.post("/{cliente_id}/questionari", response_model=schemi.ProfiloOut, status_code=201)
def compila_questionario(cliente_id: int, q: Questionario, u: Utente = Depends(utente_corrente),
                         s: Session = Depends(ottieni_sessione)):
    """Salva il questionario MiFID e restituisce il profilo calcolato (valido 12 mesi)."""
    c = _cliente(s, u, cliente_id, operare=True)
    p = servizi.salva_questionario(s, u, c, q)
    s.commit()
    return p


@clienti.get("/{cliente_id}/profilo", response_model=schemi.ProfiloOut)
def profilo(cliente_id: int, u: Utente = Depends(utente_corrente), s: Session = Depends(ottieni_sessione)):
    c = _cliente(s, u, cliente_id)
    try:
        return servizi.profilo_valido(s, c)
    except servizi.ErroreServizio as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e


@clienti.post("/{cliente_id}/proposte", response_model=schemi.PropostaOut, status_code=201)
def nuova_proposta(cliente_id: int, dati: schemi.PropostaIn, u: Utente = Depends(utente_corrente),
                   s: Session = Depends(ottieni_sessione)):
    """Proposta ottimizzata sul profilo (senza ``pesi``) o manuale, sempre con la verifica di adeguatezza."""
    c = _cliente(s, u, cliente_id, operare=True)
    try:
        p, _ = servizi.crea_proposta(s, u, c, dati.importo, dati.pesi, dati.portafoglio_attuale, dati.costi_uscita)
    except (servizi.ErroreServizio, OttimizzazioneFallita) as e:
        s.rollback()
        raise _errore(e) from e
    s.commit()
    return p


# --------------------------------------------------------------------------------------------------- proposte
proposte = APIRouter(prefix="/proposte", tags=["proposte"])


@proposte.get("/{proposta_id}", response_model=schemi.PropostaOut)
def leggi_proposta(proposta_id: int, u: Utente = Depends(utente_corrente), s: Session = Depends(ottieni_sessione)):
    return _proposta(s, u, proposta_id)


@proposte.get("/{proposta_id}/dichiarazione", response_class=HTMLResponse)
def dichiarazione(proposta_id: int, u: Utente = Depends(utente_corrente), s: Session = Depends(ottieni_sessione)):
    """Dichiarazione di adeguatezza da consegnare al cliente (art. 25(6) MiFID II), in HTML stampabile."""
    p = _proposta(s, u, proposta_id)
    return dichiarazione_html(s, p)


def _decidi(proposta_id: int, accetta: bool, dati: schemi.Decisione, u: Utente, s: Session) -> Proposta:
    p = _proposta(s, u, proposta_id, operare=True)
    try:
        servizi.decidi(s, u, p, accetta, dati.note)
    except servizi.ErroreServizio as e:
        raise _errore(e) from e
    s.commit()
    return p


@proposte.post("/{proposta_id}/accetta", response_model=schemi.PropostaOut)
def accetta(proposta_id: int, dati: schemi.Decisione = schemi.Decisione(), u: Utente = Depends(utente_corrente),
            s: Session = Depends(ottieni_sessione)):
    return _decidi(proposta_id, True, dati, u, s)


@proposte.post("/{proposta_id}/rifiuta", response_model=schemi.PropostaOut)
def rifiuta(proposta_id: int, dati: schemi.Decisione = schemi.Decisione(), u: Utente = Depends(utente_corrente),
            s: Session = Depends(ottieni_sessione)):
    return _decidi(proposta_id, False, dati, u, s)


# ---------------------------------------------------------------------------------------------- catalogo e dati
catalogo = APIRouter(tags=["catalogo e mercato"])


@catalogo.get("/prodotti", response_model=list[schemi.ProdottoOut])
def prodotti(_: Utente = Depends(utente_corrente), s: Session = Depends(ottieni_sessione)):
    return s.scalars(select(Prodotto).where(Prodotto.attivo).order_by(Prodotto.sri, Prodotto.nome)).all()


@catalogo.get("/mercato", response_model=list[schemi.DatoMercatoOut])
def dati_mercato(serie: str | None = None, limite: int = Query(24, ge=1, le=500),
                 _: Utente = Depends(utente_corrente), s: Session = Depends(ottieni_sessione)):
    nomi = [serie] if serie else [x.codice for x in mercato.SERIE]
    out = []
    for n in nomi:
        out += s.scalars(select(DatoMercato).where(DatoMercato.serie == n)
                         .order_by(DatoMercato.data.desc()).limit(limite)).all()
    return out


@catalogo.post("/mercato/aggiorna")
def aggiorna_mercato(u: Utente = Depends(richiede("admin")), s: Session = Depends(ottieni_sessione)):
    esito = mercato.aggiorna(s)
    audit.registra(s, u.email, "mercato_aggiornato", "dati_mercato", None, esito)
    s.commit()
    return esito


# ---------------------------------------------------------------------------------------------------- audit
registro = APIRouter(prefix="/audit", tags=["audit"])


@registro.get("", response_model=list[schemi.EventoOut])
def eventi(entita: str | None = None, entita_id: int | None = None, limite: int = Query(100, ge=1, le=1000),
           _: Utente = Depends(richiede("compliance", "admin")), s: Session = Depends(ottieni_sessione)):
    q = select(EventoAudit).order_by(EventoAudit.id.desc()).limit(limite)
    if entita:
        q = q.where(EventoAudit.entita == entita)
    if entita_id is not None:
        q = q.where(EventoAudit.entita_id == entita_id)
    return s.scalars(q).all()


@registro.get("/verifica", response_model=schemi.VerificaCatenaOut)
def verifica_registro(_: Utente = Depends(richiede("compliance", "admin")), s: Session = Depends(ottieni_sessione)):
    """Ricalcola l'intera catena di hash e indica il primo evento alterato, se c'è."""
    return audit.verifica_catena(s).__dict__
