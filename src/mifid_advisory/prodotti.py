"""Catalogo dei prodotti raccomandabili, con caratteristiche MiFID II, PRIIPs e SFDR, e serie storiche.

Ogni prodotto ha le informazioni che servono alla verifica di adeguatezza: classe di strumento (per la conoscenza
del cliente), complessità, indicatore sintetico di rischio PRIIPs (SRI 1-7), periodo di detenzione raccomandato,
costi correnti e di ingresso, emittente (per il rischio di concentrazione) e caratteristiche di sostenibilità
(articolo SFDR 6, 8 o 9, quota di investimenti sostenibili, quota allineata alla Tassonomia UE, considerazione dei
principali effetti negativi).

Il catalogo dimostrativo è fittizio (codici ISIN che iniziano con ``XX``). I rendimenti mensili sono generati da
un modello a fattori (azionario globale, emergenti, small cap, duration, credito, oro, immobiliare, inflazione)
con code spesse, così rischio e correlazioni tra prodotti sono coerenti; i rendimenti attesi seguono ipotesi di
mercato di lungo periodo (premi per fattore) al netto dei costi.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

FATTORI = ["azionario", "emergenti", "small_cap", "duration", "credito", "oro", "immobiliare", "inflazione"]
VOL_FATTORI = np.array([0.15, 0.10, 0.08, 0.009, 0.06, 0.15, 0.10, 0.02])  # duration: per anno di duration
PREMI = np.array([0.045, 0.010, 0.008, 0.0025, 0.030, 0.015, 0.008, 0.003])
CORRELAZIONI = np.array([
    # az    em    sc    dur   cred  oro   imm   infl
    [1.0, 0.30, 0.20, -0.20, 0.60, 0.10, 0.50, 0.10],
    [0.30, 1.0, 0.10, -0.10, 0.40, 0.15, 0.20, 0.10],
    [0.20, 0.10, 1.0, -0.10, 0.30, 0.00, 0.20, 0.00],
    [-0.20, -0.10, -0.10, 1.0, -0.30, 0.20, 0.10, -0.30],
    [0.60, 0.40, 0.30, -0.30, 1.0, 0.00, 0.40, 0.10],
    [0.10, 0.15, 0.00, 0.20, 0.00, 1.0, 0.05, 0.30],
    [0.50, 0.20, 0.20, 0.10, 0.40, 0.05, 1.0, 0.10],
    [0.10, 0.10, 0.00, -0.30, 0.10, 0.30, 0.10, 1.0],
])
# Bande di volatilità equivalente al VaR (VEV) del Regolamento PRIIPs per il rischio di mercato
BANDE_SRI = [0.005, 0.05, 0.12, 0.20, 0.30, 0.80]


def sri_da_volatilita(vol: float) -> int:
    """Classe di rischio di mercato PRIIPs (1-7) dalla volatilità annua."""
    return 1 + int(np.searchsorted(BANDE_SRI, vol, side="right"))


@dataclass
class Prodotto:
    isin: str
    nome: str
    emittente: str
    classe_strumento: str  # liquidita, obbligazioni, fondi_etf, azioni, certificati, derivati
    categoria: str  # categoria di asset per i grafici
    esposizioni: dict[str, float] = field(repr=False)
    ter: float = 0.002  # costi correnti annui
    costi_ingresso: float = 0.0  # una tantum, sull'importo investito
    complesso: bool = False
    orizzonte_min: int = 1  # periodo di detenzione raccomandato (anni)
    sfdr: int = 6
    quota_sostenibile: float = 0.0
    quota_tassonomia: float = 0.0
    considera_pai: bool = False
    rischio_specifico: float = 0.01  # volatilità annua non spiegata dai fattori
    obiettivi: tuple[str, ...] = ("protezione", "reddito", "crescita_moderata", "crescita")
    # Calcolati dal catalogo
    rendimento_atteso: float = 0.0
    volatilita: float = 0.0
    sri: int = 1

    def to_dict(self) -> dict:
        d = asdict(self)
        d["obiettivi"] = list(self.obiettivi)
        return d


def _p(isin, nome, emittente, classe, categoria, esposizioni, **kw) -> Prodotto:
    return Prodotto(isin, nome, emittente, classe, categoria, esposizioni, **kw)


CATALOGO_BASE = [
    _p("XX0000000011", "Fondo Monetario Euro", "Gestore Alfa", "liquidita", "Liquidità", {"duration": 0.25},
       ter=0.0015, rischio_specifico=0.002, orizzonte_min=1, sfdr=8, quota_sostenibile=0.2, considera_pai=True),
    _p("XX0000000029", "ETF Titoli di Stato Euro 1-3 anni", "Gestore Beta", "fondi_etf", "Obbligazioni governative",
       {"duration": 2.0}, ter=0.0015, rischio_specifico=0.004, orizzonte_min=2),
    _p("XX0000000037", "ETF Titoli di Stato Euro 7-10 anni", "Gestore Beta", "fondi_etf",
       "Obbligazioni governative", {"duration": 8.0}, ter=0.0015, rischio_specifico=0.008, orizzonte_min=5),
    _p("XX0000000045", "ETF Inflazione Euro", "Gestore Gamma", "fondi_etf", "Obbligazioni governative",
       {"duration": 6.0, "inflazione": 1.0}, ter=0.0020, rischio_specifico=0.008, orizzonte_min=4),
    _p("XX0000000052", "BTP 3,5% 2030", "Repubblica Italiana", "obbligazioni", "Obbligazioni governative",
       {"duration": 4.3, "credito": 0.25}, ter=0.0, costi_ingresso=0.002, rischio_specifico=0.01, orizzonte_min=4,
       obiettivi=("protezione", "reddito", "crescita_moderata")),
    _p("XX0000000060", "ETF Obbligazioni Societarie Euro", "Gestore Alfa", "fondi_etf", "Obbligazioni societarie",
       {"duration": 4.5, "credito": 0.3}, ter=0.0012, rischio_specifico=0.006, orizzonte_min=3, sfdr=8,
       quota_sostenibile=0.3, considera_pai=True),
    _p("XX0000000078", "ETF Green Bond Euro", "Gestore Gamma", "fondi_etf", "Obbligazioni societarie",
       {"duration": 6.5, "credito": 0.3}, ter=0.0020, rischio_specifico=0.008, orizzonte_min=4, sfdr=9,
       quota_sostenibile=0.90, quota_tassonomia=0.45, considera_pai=True),
    _p("XX0000000086", "ETF High Yield Euro", "Gestore Beta", "fondi_etf", "Obbligazioni societarie",
       {"duration": 3.0, "credito": 1.0}, ter=0.0040, rischio_specifico=0.015, orizzonte_min=5,
       obiettivi=("reddito", "crescita_moderata", "crescita")),
    _p("XX0000000094", "ETF Obbligazioni Paesi Emergenti", "Gestore Delta", "fondi_etf", "Obbligazioni societarie",
       {"duration": 6.5, "credito": 0.8, "emergenti": 0.25}, ter=0.0040, rischio_specifico=0.02, orizzonte_min=5,
       obiettivi=("reddito", "crescita_moderata", "crescita")),
    _p("XX0000000102", "ETF Azionario Mondo", "Gestore Alfa", "fondi_etf", "Azioni", {"azionario": 1.0},
       ter=0.0020, rischio_specifico=0.01, orizzonte_min=7, obiettivi=("crescita_moderata", "crescita")),
    _p("XX0000000110", "ETF Azionario Mondo ESG", "Gestore Gamma", "fondi_etf", "Azioni",
       {"azionario": 1.0, "small_cap": 0.05}, ter=0.0025, rischio_specifico=0.015, orizzonte_min=7, sfdr=8,
       quota_sostenibile=0.50, quota_tassonomia=0.08, considera_pai=True, obiettivi=("crescita_moderata", "crescita")),
    _p("XX0000000235", "ETF Azionario Stati Uniti ESG", "Gestore Gamma", "fondi_etf", "Azioni",
       {"azionario": 1.05}, ter=0.0012, rischio_specifico=0.045, orizzonte_min=7, sfdr=8, quota_sostenibile=0.40,
       quota_tassonomia=0.05, considera_pai=True, obiettivi=("crescita_moderata", "crescita")),
    _p("XX0000000243", "ETF Azionario Paesi Emergenti ESG", "Gestore Gamma", "fondi_etf", "Azioni",
       {"azionario": 1.0, "emergenti": 1.0}, ter=0.0025, rischio_specifico=0.045, orizzonte_min=8, sfdr=8,
       quota_sostenibile=0.35, quota_tassonomia=0.04, considera_pai=True, obiettivi=("crescita",)),
    _p("XX0000000128", "ETF Azionario Europa", "Gestore Beta", "fondi_etf", "Azioni", {"azionario": 0.95},
       ter=0.0012, rischio_specifico=0.05, orizzonte_min=7, obiettivi=("crescita_moderata", "crescita")),
    _p("XX0000000136", "ETF Azionario Stati Uniti", "Gestore Alfa", "fondi_etf", "Azioni", {"azionario": 1.05},
       ter=0.0007, rischio_specifico=0.04, orizzonte_min=7, obiettivi=("crescita_moderata", "crescita")),
    _p("XX0000000144", "ETF Azionario Paesi Emergenti", "Gestore Delta", "fondi_etf", "Azioni",
       {"azionario": 1.0, "emergenti": 1.0}, ter=0.0018, rischio_specifico=0.04, orizzonte_min=8,
       obiettivi=("crescita",)),
    _p("XX0000000151", "ETF Small Cap Mondo", "Gestore Beta", "fondi_etf", "Azioni",
       {"azionario": 1.1, "small_cap": 1.0}, ter=0.0035, rischio_specifico=0.04, orizzonte_min=8,
       obiettivi=("crescita",)),
    _p("XX0000000169", "Fondo Azionario Transizione Climatica", "Gestore Epsilon", "fondi_etf", "Azioni",
       {"azionario": 1.1, "small_cap": 0.5}, ter=0.0160, costi_ingresso=0.02, rischio_specifico=0.06,
       orizzonte_min=8, sfdr=9, quota_sostenibile=0.85, quota_tassonomia=0.35, considera_pai=True,
       obiettivi=("crescita",)),
    _p("XX0000000177", "ETF Immobiliare Europa", "Gestore Gamma", "fondi_etf", "Immobiliare",
       {"azionario": 0.6, "immobiliare": 1.0, "duration": 3.0}, ter=0.0040, rischio_specifico=0.04,
       orizzonte_min=7, obiettivi=("reddito", "crescita_moderata", "crescita")),
    _p("XX0000000185", "ETC Oro fisico", "Emittente Oro", "fondi_etf", "Materie prime", {"oro": 1.0},
       ter=0.0025, rischio_specifico=0.01, orizzonte_min=5, obiettivi=("crescita_moderata", "crescita")),
    _p("XX0000000193", "Fondo Bilanciato Prudente della banca", "Gestore Epsilon", "fondi_etf", "Bilanciati",
       {"azionario": 0.3, "duration": 4.0, "credito": 0.2}, ter=0.0180, costi_ingresso=0.02,
       rischio_specifico=0.01, orizzonte_min=4, sfdr=8, quota_sostenibile=0.1, considera_pai=True),
    _p("XX0000000201", "Fondo Flessibile Globale", "Gestore Epsilon", "fondi_etf", "Bilanciati",
       {"azionario": 0.6, "duration": 3.0, "credito": 0.3, "emergenti": 0.2}, ter=0.0210, costi_ingresso=0.03,
       rischio_specifico=0.02, orizzonte_min=5, obiettivi=("crescita_moderata", "crescita")),
    _p("XX0000000219", "Certificato Phoenix Memory su indici europei", "Banca Emittente", "certificati",
       "Certificati", {"azionario": 0.7, "duration": 2.0, "credito": 0.3}, ter=0.0, costi_ingresso=0.045,
       complesso=True, rischio_specifico=0.04, orizzonte_min=4, obiettivi=("reddito", "crescita_moderata")),
    _p("XX0000000227", "Azioni Società Energetica", "Società Energetica", "azioni", "Azioni",
       {"azionario": 0.9}, ter=0.0, costi_ingresso=0.002, rischio_specifico=0.22, orizzonte_min=7,
       obiettivi=("reddito", "crescita")),
]


def _covarianza_fattori() -> np.ndarray:
    return np.outer(VOL_FATTORI, VOL_FATTORI) * CORRELAZIONI


def _vettore(esposizioni: dict[str, float]) -> np.ndarray:
    return np.array([esposizioni.get(f, 0.0) for f in FATTORI])


@dataclass
class Catalogo:
    prodotti: list[Prodotto]
    rendimenti: pd.DataFrame  # rendimenti mensili, una colonna per ISIN
    tasso_privo_rischio: float

    def __post_init__(self):
        self._per_isin = {p.isin: p for p in self.prodotti}

    def __getitem__(self, isin: str) -> Prodotto:
        return self._per_isin[isin]

    def __contains__(self, isin: str) -> bool:
        return isin in self._per_isin

    @property
    def isin(self) -> list[str]:
        return [p.isin for p in self.prodotti]

    def tabella(self) -> pd.DataFrame:
        return pd.DataFrame([p.to_dict() for p in self.prodotti]).set_index("isin")


def genera_catalogo(tasso_privo_rischio: float = 0.025, mesi: int = 120, seed: int = 42,
                    prodotti: list[Prodotto] | None = None, fine: str = "2025-12-31") -> Catalogo:
    """Catalogo dimostrativo con rendimenti attesi da premi per fattore e storia mensile simulata."""
    rng = np.random.default_rng(seed)
    prodotti = [Prodotto(**{**asdict(p), "esposizioni": dict(p.esposizioni)}) for p in (prodotti or CATALOGO_BASE)]
    cov_f = _covarianza_fattori()
    # Rendimenti mensili dei fattori con code spesse (t di Student a 5 gradi di libertà, varianza riscalata)
    gl = 5
    z = rng.multivariate_normal(np.zeros(len(FATTORI)), cov_f / 12, size=mesi)
    scala = np.sqrt(rng.chisquare(gl, size=(mesi, 1)) / (gl - 2))
    fattori = z / scala + PREMI / 12
    date = pd.date_range(end=fine, periods=mesi, freq="ME")
    rend = {}
    for p in prodotti:
        b = _vettore(p.esposizioni)
        p.rendimento_atteso = rendimento_atteso(p, tasso_privo_rischio)
        p.volatilita = round(float(np.sqrt(b @ cov_f @ b + p.rischio_specifico**2)), 5)
        p.sri = sri_da_volatilita(p.volatilita)
        specifico = rng.standard_t(gl, size=mesi) * p.rischio_specifico / np.sqrt(12 * gl / (gl - 2))
        rend[p.isin] = tasso_privo_rischio / 12 - p.ter / 12 + fattori @ b + specifico
    return Catalogo(prodotti, pd.DataFrame(rend, index=date), tasso_privo_rischio)


def rendimento_atteso(p: Prodotto, tasso_privo_rischio: float) -> float:
    """Rendimento atteso annuo al netto dei costi correnti: tasso privo di rischio più premi per fattore."""
    return round(float(tasso_privo_rischio + _vettore(p.esposizioni) @ PREMI - p.ter), 5)
