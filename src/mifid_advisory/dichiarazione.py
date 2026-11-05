"""Dichiarazione di adeguatezza da consegnare al cliente prima dell'operazione.

L'articolo 25(6) di MiFID II e l'articolo 54(12) del Regolamento delegato 2017/565 chiedono di spiegare al cliente
perché la raccomandazione corrisponde ai suoi obiettivi, alla sua tolleranza al rischio e alla sua capacità di
sostenere perdite. Il documento è generato dai dati salvati (profilo, posizioni, verifica) e riporta l'impronta
dell'evento di audit con cui la proposta è stata registrata, così che chiunque possa verificarne l'integrità.
"""

from __future__ import annotations

from jinja2 import Environment, PackageLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import EventoAudit, Prodotto, Proposta, Utente, adesso
from .questionario import NOMI_CLASSI

ambiente = Environment(loader=PackageLoader("mifid_advisory", "templates"), autoescape=select_autoescape())
ambiente.filters["pct"] = lambda x, d=1: f"{x * 100:.{d}f}%".replace(".", ",")
ambiente.filters["eur"] = lambda x: "€ " + f"{x:,.0f}".replace(",", ".")

ESITI = {"adeguato": "Adeguata", "adeguato_con_avvertenze": "Adeguata, con avvertenze", "non_adeguato": "Non adeguata"}
OBIETTIVI = {"protezione": "protezione del capitale", "reddito": "reddito", "crescita_moderata": "crescita moderata",
             "crescita": "crescita del capitale"}


def dati(s: Session, p: Proposta) -> dict:
    prodotti = {x.isin: x for x in s.scalars(select(Prodotto).where(Prodotto.isin.in_([q.isin for q in p.posizioni])))}
    evento = s.scalars(select(EventoAudit).where(EventoAudit.entita == "proposta", EventoAudit.entita_id == p.id,
                                                 EventoAudit.azione == "proposta_creata")).first()
    profilo = p.profilo.dettagli
    return {
        "proposta": p, "cliente": p.cliente, "consulente": s.get(Utente, p.consulente_id), "profilo": profilo,
        "obiettivo": OBIETTIVI.get(profilo["obiettivo"], profilo["obiettivo"]),
        "posizioni": [{"p": q, "prodotto": prodotti[q.isin], "classe": NOMI_CLASSI.get(
            prodotti[q.isin].classe_strumento, prodotti[q.isin].classe_strumento)} for q in p.posizioni],
        "m": p.verifica.metriche, "controlli": p.verifica.controlli, "esito": ESITI[p.verifica.esito],
        "esito_codice": p.verifica.esito, "evento": evento, "generata_il": adesso(),
        "valido_fino": p.profilo.valido_fino,
    }


def dichiarazione_html(s: Session, p: Proposta) -> str:
    return ambiente.get_template("dichiarazione.html.j2").render(**dati(s, p))
