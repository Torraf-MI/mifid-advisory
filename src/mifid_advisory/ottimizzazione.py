"""Proposta di allocazione: il portafoglio con il rendimento atteso netto più alto entro i limiti del profilo.

L'ottimizzatore lavora solo sui prodotti adeguati al cliente presi uno per uno (classe di strumento conosciuta,
rischio PRIIPs, periodo di detenzione, obiettivo, preferenze di sostenibilità) e cerca i pesi che massimizzano il
rendimento atteso al netto dei costi rispettando:

- la volatilità massima della classe di rischio (con un margine del 5%);
- la perdita in uno scenario avverso (expected shortfall al 95%) entro il minimo tra il limite della classe e la
  capacità di sostenere perdite del cliente;
- la quota da tenere liquida per le esigenze dei prossimi 12 mesi;
- le quote minime di investimenti sostenibili e allineati alla Tassonomia;
- i limiti di concentrazione per prodotto (25%, nessun limite per la liquidità) e per emittente di titoli
  singoli (20%).

Una piccola penalità quadratica sui pesi evita le soluzioni d'angolo con due soli prodotti. Il problema è risolto
con SLSQP di scipy; i pesi sotto il 2% vengono eliminati e il resto arrotondato all'1%.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize
from scipy.stats import norm

from .prodotti import Catalogo, Prodotto
from .profilazione import CLASSI, Profilo
from .rischio import covarianza_annua, vettori

PESO_MAX_PRODOTTO = 0.25
PESO_MAX_EMITTENTE = 0.20  # per titoli singoli: obbligazioni, azioni, certificati
CLASSI_EMITTENTE = {"obbligazioni", "azioni", "certificati"}
PESO_MIN = 0.02


@dataclass
class EsitoProdotto:
    isin: str
    ammesso: bool
    motivi: list[str]


def adeguatezza_prodotto(p: Prodotto, profilo: Profilo) -> EsitoProdotto:
    """Verifica del singolo prodotto rispetto al profilo (target market e adeguatezza di base)."""
    motivi = []
    if p.classe_strumento not in profilo.classi_ammesse:
        motivi.append("conoscenza ed esperienza insufficienti per questa classe di strumenti")
    if p.sri > profilo.limiti.sri_max:
        motivi.append(f"rischio PRIIPs {p.sri} oltre il massimo {profilo.limiti.sri_max} del profilo")
    if p.orizzonte_min > profilo.orizzonte_anni:
        motivi.append(f"periodo di detenzione raccomandato ({p.orizzonte_min} anni) oltre l'orizzonte del cliente")
    if profilo.obiettivo not in p.obiettivi:
        motivi.append("obiettivo del cliente fuori dal mercato di riferimento del prodotto")
    s = profilo.sostenibilita
    if s.get("ha_preferenze") and s.get("considera_pai") and not p.considera_pai:
        motivi.append("non considera i principali effetti negativi sulla sostenibilità richiesti dal cliente")
    return EsitoProdotto(p.isin, not motivi, motivi)


def prodotti_ammessi(catalogo: Catalogo, profilo: Profilo) -> list[str]:
    return [p.isin for p in catalogo.prodotti if adeguatezza_prodotto(p, profilo).ammesso]


def massimo_prodotto(p: Prodotto) -> float:
    """Peso massimo di un prodotto: la liquidità non ha limite, i titoli singoli quello per emittente."""
    if p.classe_strumento == "liquidita":
        return 1.0
    if p.classe_strumento in CLASSI_EMITTENTE:
        return PESO_MAX_EMITTENTE
    return PESO_MAX_PRODOTTO


class OttimizzazioneFallita(ValueError):
    pass


def ottimizza(catalogo: Catalogo, profilo: Profilo, penalita: float = 0.02) -> dict[str, float]:
    """Pesi del portafoglio proposto (ISIN → peso), che sommano a 1."""
    isin = prodotti_ammessi(catalogo, profilo)
    if not isin:
        raise OttimizzazioneFallita("Nessun prodotto del catalogo è adeguato al profilo del cliente")
    n = len(isin)
    v = vettori(catalogo, isin, profilo.orizzonte_anni)
    idx = [catalogo.isin.index(i) for i in isin]
    cov = covarianza_annua(catalogo.rendimenti)[np.ix_(idx, idx)]
    limiti = CLASSI[profilo.classe]
    vol_max = 0.95 * limiti.volatilita_max
    perdita_max = 0.95 * min(limiti.perdita_max, max(profilo.capacita_perdita, 0.02))
    k_es = norm.pdf(norm.ppf(0.05)) / 0.05
    liquidi = np.array([catalogo[i].classe_strumento == "liquidita" for i in isin], dtype=float)
    s = profilo.sostenibilita

    vincoli = [
        {"type": "eq", "fun": lambda w: w.sum() - 1},
        {"type": "ineq", "fun": lambda w: vol_max**2 - w @ cov @ w},
        {"type": "ineq", "fun": lambda w: perdita_max - (k_es * np.sqrt(w @ cov @ w + 1e-12) - w @ v["mu"])},
    ]
    if profilo.quota_liquida > 0:
        vincoli.append({"type": "ineq", "fun": lambda w: w @ liquidi - profilo.quota_liquida})
    if s.get("ha_preferenze"):
        if s.get("quota_minima_sostenibile", 0) > 0:
            vincoli.append({"type": "ineq", "fun": lambda w: w @ v["sostenibile"] - s["quota_minima_sostenibile"]})
        if s.get("quota_minima_tassonomia", 0) > 0:
            vincoli.append({"type": "ineq", "fun": lambda w: w @ v["tassonomia"] - s["quota_minima_tassonomia"]})
    emittenti = {}
    for j, i in enumerate(isin):
        p = catalogo[i]
        if p.classe_strumento in CLASSI_EMITTENTE:
            emittenti.setdefault(p.emittente, []).append(j)
    for js in emittenti.values():
        vincoli.append({"type": "ineq", "fun": lambda w, js=js: PESO_MAX_EMITTENTE - w[js].sum()})

    def obiettivo(w):
        return -(w @ v["netto"]) + penalita * (w @ w)

    massimo = np.array([massimo_prodotto(catalogo[i]) for i in isin])
    if massimo.sum() < 1:
        raise OttimizzazioneFallita("Troppi pochi prodotti ammessi per rispettare i limiti di concentrazione")
    # Partenza: il portafoglio meno rischioso possibile, dal quale si sale verso il rendimento
    w0 = np.where(liquidi > 0, 1.0, 0.0)
    w0 = w0 / w0.sum() if w0.sum() else np.full(n, 1 / n)
    w0 = np.minimum(w0, massimo)
    w0 = w0 + (1 - w0.sum()) * (massimo - w0) / max((massimo - w0).sum(), 1e-12)
    ris = minimize(obiettivo, w0, method="SLSQP", bounds=list(zip(np.zeros(n), massimo, strict=True)),
                   constraints=vincoli, options={"maxiter": 500, "ftol": 1e-10})
    if not ris.success and max(c["fun"](ris.x) for c in vincoli if c["type"] == "ineq") < -1e-4:
        raise OttimizzazioneFallita(f"Nessun portafoglio rispetta tutti i vincoli del profilo ({ris.message})")
    return _arrotonda(dict(zip(isin, ris.x, strict=True)), massimo=dict(zip(isin, massimo, strict=True)))


def _arrotonda(pesi: dict[str, float], massimo: dict[str, float]) -> dict[str, float]:
    tenuti = {k: w for k, w in pesi.items() if w >= PESO_MIN}
    tot = sum(tenuti.values())
    tenuti = {k: w / tot for k, w in tenuti.items()}
    arrot = {k: np.floor(w * 100) / 100 for k, w in tenuti.items()}
    resto = round(1 - sum(arrot.values()), 2)
    # Il resto va ai prodotti con la parte decimale più grande, senza superare i massimi
    for k in sorted(tenuti, key=lambda k: tenuti[k] * 100 - np.floor(tenuti[k] * 100), reverse=True):
        if resto <= 1e-9:
            break
        if arrot[k] + 0.01 <= massimo[k] + 1e-9:
            arrot[k] = round(arrot[k] + 0.01, 2)
            resto = round(resto - 0.01, 2)
    return {k: float(round(w, 2)) for k, w in sorted(arrot.items(), key=lambda x: -x[1]) if w > 0}
