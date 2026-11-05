"""Logica applicativa: collega database, profilazione, ottimizzazione, adeguatezza e registro di audit.

Le funzioni ricevono una sessione e lasciano il commit al chiamante: ogni richiesta dell'API è una sola
transazione, quindi o si salvano insieme proposta, verifica ed evento di audit, o non si salva nulla.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import date

import pandas as pd
from dateutil.relativedelta import relativedelta
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import audit, mercato
from .adeguatezza import Verifica, verifica
from .config import impostazioni
from .db import (
    Cliente,
    Posizione,
    Prodotto,
    Profilo,
    Proposta,
    Questionario,
    Rendimento,
    Utente,
    VerificaAdeguatezza,
    adesso,
)
from .esempi import CLIENTI
from .ottimizzazione import ottimizza
from .prodotti import Catalogo, genera_catalogo, rendimento_atteso
from .prodotti import Prodotto as ProdottoCatalogo
from .profilazione import Profilo as ProfiloRischio
from .profilazione import profila
from .questionario import Questionario as QuestionarioIn

ITERAZIONI = 200_000


class ErroreServizio(ValueError):
    """Errore di dominio, restituito dall'API come 409 o 422 con il messaggio."""


# ------------------------------------------------------------------------------------------------ utenti
def hash_password(password: str) -> str:
    sale = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(sale), ITERAZIONI).hex()
    return f"pbkdf2_sha256${ITERAZIONI}${sale}${h}"


def verifica_password(password: str, codifica: str) -> bool:
    try:
        _, iterazioni, sale, h = codifica.split("$")
    except ValueError:
        return False
    calcolato = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(sale), int(iterazioni)).hex()
    return hmac.compare_digest(calcolato, h)


def crea_utente(s: Session, email: str, nome: str, ruolo: str, password: str) -> Utente:
    if ruolo not in ("consulente", "compliance", "admin"):
        raise ErroreServizio(f"Ruolo non valido: {ruolo}")
    u = Utente(email=email.lower(), nome=nome, ruolo=ruolo, password_hash=hash_password(password))
    s.add(u)
    s.flush()
    return u


def autentica(s: Session, email: str, password: str) -> Utente | None:
    u = s.scalars(select(Utente).where(Utente.email == email.lower())).first()
    if u and u.attivo and verifica_password(password, u.password_hash):
        return u
    return None


# ---------------------------------------------------------------------------------------------- catalogo
def semina_catalogo(s: Session, seed: int = 42) -> int:
    """Carica il catalogo dimostrativo se la tabella dei prodotti è vuota."""
    if s.scalar(select(func.count(Prodotto.id))):
        return 0
    cat = genera_catalogo(mercato.tasso_privo_rischio(s), seed=seed)
    for p in cat.prodotti:
        riga = Prodotto(isin=p.isin, nome=p.nome, classe_strumento=p.classe_strumento, categoria=p.categoria,
                        sri=p.sri, dati=p.to_dict())
        s.add(riga)
        s.flush()
        s.add_all(Rendimento(prodotto_id=riga.id, data=d.date(), valore=float(v))
                  for d, v in cat.rendimenti[p.isin].items())
    s.flush()
    return len(cat.prodotti)


def carica_catalogo(s: Session) -> Catalogo:
    """Catalogo dal database, con i rendimenti attesi ricalcolati sull'ultimo tasso privo di rischio."""
    rf = mercato.tasso_privo_rischio(s)
    righe = s.scalars(select(Prodotto).where(Prodotto.attivo).order_by(Prodotto.id)).all()
    if not righe:
        raise ErroreServizio("Il catalogo prodotti è vuoto")
    prodotti = []
    for r in righe:
        d = dict(r.dati)
        d["obiettivi"] = tuple(d["obiettivi"])
        p = ProdottoCatalogo(**d)
        p.rendimento_atteso = rendimento_atteso(p, rf)
        prodotti.append(p)
    ids = {r.id: r.isin for r in righe}
    rend = pd.DataFrame(s.execute(select(Rendimento.prodotto_id, Rendimento.data, Rendimento.valore)
                                  .where(Rendimento.prodotto_id.in_(ids))).all(),
                        columns=["prodotto_id", "data", "valore"])
    tabella = rend.pivot(index="data", columns="prodotto_id", values="valore").rename(columns=ids)
    return Catalogo(prodotti, tabella[[p.isin for p in prodotti]].sort_index(), rf)


# ------------------------------------------------------------------------------------- clienti e profili
def crea_cliente(s: Session, consulente: Utente, nome: str, cognome: str, data_nascita: date | None = None,
                 email: str | None = None) -> Cliente:
    c = Cliente(nome=nome, cognome=cognome, data_nascita=data_nascita, email=email, consulente_id=consulente.id)
    s.add(c)
    s.flush()
    audit.registra(s, consulente.email, "cliente_creato", "cliente", c.id,
                   {"nome": nome, "cognome": cognome, "data_nascita": data_nascita, "email": email})
    return c


def salva_questionario(s: Session, utente: Utente, cliente: Cliente, q: QuestionarioIn) -> Profilo:
    risposte = q.model_dump(mode="json")
    qd = Questionario(cliente_id=cliente.id, risposte=risposte)
    s.add(qd)
    s.flush()
    p = profila(q)
    oggi = adesso().date()
    profilo = Profilo(cliente_id=cliente.id, questionario_id=qd.id, classe_rischio=p.classe, dettagli=p.to_dict(),
                      valido_fino=oggi + relativedelta(months=impostazioni().validita_profilo_mesi))
    s.add(profilo)
    s.flush()
    audit.registra(s, utente.email, "questionario_compilato", "questionario", qd.id, risposte)
    audit.registra(s, utente.email, "profilo_calcolato", "profilo", profilo.id,
                   {"cliente_id": cliente.id, "classe": p.classe, "vincolo": p.vincolo, "componenti": p.componenti,
                    "incoerenze": p.incoerenze, "valido_fino": profilo.valido_fino})
    return profilo


def profilo_valido(s: Session, cliente: Cliente) -> Profilo:
    p = s.scalars(select(Profilo).where(Profilo.cliente_id == cliente.id).order_by(Profilo.id.desc())).first()
    if p is None:
        raise ErroreServizio("Il cliente non ha ancora compilato il questionario MiFID")
    if p.valido_fino < adesso().date():
        raise ErroreServizio(f"Il profilo è scaduto il {p.valido_fino:%d/%m/%Y}: il questionario va aggiornato")
    return p


# ----------------------------------------------------------------------------------------------- proposte
def crea_proposta(s: Session, utente: Utente, cliente: Cliente, importo: float, pesi: dict[str, float] | None = None,
                  portafoglio_attuale: dict[str, float] | None = None, costi_uscita: float = 0.0
                  ) -> tuple[Proposta, Verifica]:
    """Proposta ottimizzata (``pesi`` assenti) o manuale, sempre accompagnata dalla verifica di adeguatezza.

    Anche una proposta non adeguata viene salvata e registrata: l'intermediario deve poter dimostrare di averla
    valutata e di non averla raccomandata.
    """
    if importo <= 0:
        raise ErroreServizio("L'importo deve essere positivo")
    profilo = profilo_valido(s, cliente)
    pr = ProfiloRischio.from_dict(profilo.dettagli)
    cat = carica_catalogo(s)
    for nome, insieme in (("proposta", pesi or {}), ("portafoglio attuale", portafoglio_attuale or {})):
        sconosciuti = [i for i in insieme if i not in cat]
        if sconosciuti:
            raise ErroreServizio(f"Prodotti non presenti nel catalogo ({nome}): {', '.join(sconosciuti)}")
        if insieme and abs(sum(insieme.values()) - 1) > 1e-6:
            raise ErroreServizio(f"I pesi del {nome} devono sommare a 1")
    metodo = "manuale" if pesi else "ottimizzata"
    if not pesi:
        pesi = ottimizza(cat, pr)
    v = verifica(cat, pr, pesi, importo, portafoglio_attuale, costi_uscita)
    proposta = Proposta(cliente_id=cliente.id, profilo_id=profilo.id, consulente_id=utente.id, importo=importo,
                        stato="adeguata" if v.adeguata else "non_adeguata", metodo=metodo,
                        portafoglio_attuale=portafoglio_attuale)
    s.add(proposta)
    s.flush()
    s.add_all(Posizione(proposta_id=proposta.id, isin=i, peso=w, importo=round(w * importo, 2))
              for i, w in pesi.items())
    d = v.to_dict()
    s.add(VerificaAdeguatezza(proposta_id=proposta.id, esito=v.esito, controlli=d["controlli"], metriche=d["metriche"]))
    s.flush()
    audit.registra(s, utente.email, "proposta_creata", "proposta", proposta.id,
                   {"cliente_id": cliente.id, "profilo_id": profilo.id, "importo": importo, "metodo": metodo,
                    "pesi": pesi, "portafoglio_attuale": portafoglio_attuale, "esito": v.esito,
                    "controlli_ko": [c["codice"] for c in d["controlli"] if c["esito"] == "ko"],
                    "tasso_privo_rischio": cat.tasso_privo_rischio})
    s.refresh(proposta)
    return proposta, v


def decidi(s: Session, utente: Utente, proposta: Proposta, accetta: bool, note: str | None = None) -> Proposta:
    if proposta.stato not in ("adeguata", "non_adeguata"):
        raise ErroreServizio(f"La proposta è già stata {proposta.stato}")
    if accetta and proposta.stato != "adeguata":
        raise ErroreServizio("Una proposta non adeguata non può essere accettata: va modificata")
    proposta.stato = "accettata" if accetta else "rifiutata"
    proposta.decisa_il = adesso()
    audit.registra(s, utente.email, "proposta_" + proposta.stato, "proposta", proposta.id,
                   {"cliente_id": proposta.cliente_id}, note)
    return proposta


# --------------------------------------------------------------------------------------------------- demo
UTENTI_DEMO = [("consulente@demo.it", "Marco Consulente", "consulente", "demo"),
               ("compliance@demo.it", "Sara Compliance", "compliance", "demo"),
               ("admin@demo.it", "Amministratore", "admin", "demo")]


def semina_demo(s: Session) -> bool:
    """Utenti, dati di mercato, catalogo e tre clienti con questionario e proposta. Solo su database vuoto."""
    if s.scalar(select(func.count(Utente.id))):
        return False
    utenti = {r: crea_utente(s, e, n, r, p) for e, n, r, p in UTENTI_DEMO}
    mercato.aggiorna(s, scaricatore=_non_disponibile)  # valori di esempio; la pipeline notturna li aggiorna
    semina_catalogo(s)
    consulente = utenti["consulente"]
    for dati in CLIENTI.values():
        a = dati["anagrafica"]
        c = crea_cliente(s, consulente, a["nome"], a["cognome"], date.fromisoformat(a["data_nascita"]), a["email"])
        salva_questionario(s, consulente, c, QuestionarioIn.model_validate(dati["questionario"]))
        crea_proposta(s, consulente, c, dati["importo"], portafoglio_attuale=dati.get("portafoglio_attuale"))
    return True


def _non_disponibile(url: str) -> str:
    raise ConnectionError("dati di esempio per la demo")
