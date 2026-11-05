"""Metriche di rischio, rendimento e costo di un portafoglio di prodotti del catalogo.

- La covarianza è stimata sui rendimenti mensili con lo stimatore di Ledoit e Wolf (shrinkage verso una matrice
  strutturata): con venti prodotti e dieci anni di dati la covarianza campionaria è troppo rumorosa per un
  ottimizzatore.
- Il rischio di perdita è misurato in due modi e si usa il più prudente: expected shortfall al 95% parametrico
  (normale) e storico, sui rendimenti a 12 mesi sovrapposti.
- Gli scenari a orizzonte (sfavorevole, moderato, favorevole) seguono la logica dei documenti PRIIPs: percentili
  10, 50 e 90 di una distribuzione lognormale del capitale.
- I costi sono quelli dell'informativa ex ante MiFID II: costi correnti più costi di ingresso ripartiti
  sull'orizzonte, in percentuale e in euro, ed effetto sul rendimento.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.covariance import LedoitWolf

from .prodotti import Catalogo, sri_da_volatilita


def covarianza_annua(rendimenti: pd.DataFrame) -> np.ndarray:
    return LedoitWolf().fit(rendimenti.to_numpy()).covariance_ * 12


@dataclass
class Metriche:
    rendimento_atteso: float
    volatilita: float
    var_95: float  # perdita annua non superata nel 95% dei casi (positiva = perdita)
    es_95: float  # perdita media nel 5% dei casi peggiori
    massimo_ribasso: float  # peggior ribasso storico (positivo)
    probabilita_perdita: float  # probabilità di chiudere l'orizzonte in perdita
    scenari: dict[str, float]  # capitale a scadenza: sfavorevole, moderato, favorevole
    costo_annuo: float
    costi_totali: float  # euro sull'orizzonte
    sri: int
    quota_sostenibile: float
    quota_tassonomia: float
    quota_pai: float
    orizzonte_anni: int
    importo: float

    def to_dict(self) -> dict:
        return asdict(self)


def vettori(catalogo: Catalogo, isin: list[str], orizzonte: int) -> dict[str, np.ndarray]:
    p = [catalogo[i] for i in isin]
    return {
        "mu": np.array([x.rendimento_atteso for x in p]),
        "ter": np.array([x.ter for x in p]),
        "ingresso": np.array([x.costi_ingresso for x in p]),
        "sostenibile": np.array([x.quota_sostenibile for x in p]),
        "tassonomia": np.array([x.quota_tassonomia for x in p]),
        "pai": np.array([float(x.considera_pai) for x in p]),
        "netto": np.array([x.rendimento_atteso - x.costi_ingresso / max(orizzonte, 1) for x in p]),
    }


def es_parametrico(mu: float, vol: float, livello: float = 0.95) -> float:
    z = norm.ppf(1 - livello)
    return float(-(mu - vol * norm.pdf(z) / (1 - livello)))


def metriche(catalogo: Catalogo, pesi: dict[str, float], importo: float, orizzonte: int) -> Metriche:
    isin = list(pesi)
    w = np.array([pesi[i] for i in isin])
    v = vettori(catalogo, isin, orizzonte)
    r = catalogo.rendimenti[isin]
    cov = covarianza_annua(catalogo.rendimenti)
    idx = [catalogo.isin.index(i) for i in isin]
    cov = cov[np.ix_(idx, idx)]
    mu = float(w @ v["mu"])
    vol = float(np.sqrt(w @ cov @ w))
    # Rischio di perdita a 12 mesi: il più prudente tra stima parametrica e storica
    mensili = r.to_numpy() @ w
    annui = np.exp(pd.Series(np.log1p(mensili)).rolling(12).sum().dropna().to_numpy()) - 1
    coda = np.sort(annui)[: max(1, int(np.ceil(0.05 * len(annui))))]
    var_par = float(-(mu + norm.ppf(0.05) * vol))
    var_95 = max(var_par, float(-np.quantile(annui, 0.05)))
    es_95 = max(es_parametrico(mu, vol), float(-coda.mean()))
    valore = np.cumprod(1 + mensili)
    ribasso = float(1 - (valore / np.maximum.accumulate(valore)).min())
    # Scenari a orizzonte: capitale lognormale con drift netto dei costi di ingresso
    netto = float(w @ v["netto"])
    m_log = (np.log1p(netto) - 0.5 * vol**2) * orizzonte
    s_log = vol * np.sqrt(orizzonte)
    scenari = {nome: float(importo * np.exp(m_log + z * s_log))
               for nome, z in [("sfavorevole", norm.ppf(0.10)), ("moderato", 0.0), ("favorevole", norm.ppf(0.90))]}
    costo_annuo = float(w @ v["ter"] + w @ v["ingresso"] / max(orizzonte, 1))
    costi_totali = float(importo * (w @ v["ingresso"] + w @ v["ter"] * orizzonte))
    return Metriche(
        rendimento_atteso=round(mu, 5), volatilita=round(vol, 5), var_95=round(var_95, 5), es_95=round(es_95, 5),
        massimo_ribasso=round(ribasso, 5), probabilita_perdita=round(float(norm.cdf(-m_log / s_log)), 4),
        scenari={k: round(x, 2) for k, x in scenari.items()}, costo_annuo=round(costo_annuo, 5),
        costi_totali=round(costi_totali, 2), sri=sri_da_volatilita(vol),
        quota_sostenibile=round(float(w @ v["sostenibile"]), 4), quota_tassonomia=round(float(w @ v["tassonomia"]), 4),
        quota_pai=round(float(w @ v["pai"]), 4), orizzonte_anni=orizzonte, importo=importo,
    )
