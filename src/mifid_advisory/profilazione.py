"""Dal questionario al profilo di rischio del cliente.

Il profilo combina quattro componenti, ognuna tradotta in una classe da 1 (prudente) a 5 (aggressivo):

- **tolleranza al rischio**: reazione a un ribasso, perdita massima accettabile, scelta tra scenari;
- **capacità di sostenere perdite**: quanta parte del patrimonio finanziario il cliente può perdere senza
  compromettere il tenore di vita (riserva di emergenza, risparmio, debiti, persone a carico, età);
- **orizzonte temporale**;
- **obiettivo di investimento**.

La classe finale è la **più bassa** delle quattro: un cliente molto tollerante ma con poco patrimonio libero, o con
un orizzonte di due anni, non può avere un profilo aggressivo. La componente che vincola il profilo viene
registrata, perché è la prima cosa da spiegare al cliente.

La conoscenza ed esperienza non sposta la classe di rischio ma decide **quali classi di strumenti** possono essere
raccomandate: gli strumenti complessi (certificati, derivati) richiedono esperienza e la risposta corretta alla
domanda di verifica. Le risposte incoerenti vengono segnalate, come chiedono gli Orientamenti ESMA.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .questionario import COMPLESSE, ClasseStrumento, Frequenza, Obiettivo, Questionario, Reazione, Titolo


@dataclass(frozen=True)
class ClasseRischio:
    livello: int
    nome: str
    volatilita_max: float  # volatilità annua massima del portafoglio
    perdita_max: float  # perdita annua in uno scenario avverso (expected shortfall al 95%)
    sri_max: int  # indicatore sintetico di rischio PRIIPs massimo del singolo prodotto
    costo_max: float  # costo annuo massimo ritenuto ragionevole per il portafoglio


CLASSI = {
    1: ClasseRischio(1, "Prudente", 0.04, 0.05, 2, 0.008),
    2: ClasseRischio(2, "Moderato", 0.07, 0.10, 3, 0.010),
    3: ClasseRischio(3, "Bilanciato", 0.11, 0.18, 4, 0.012),
    4: ClasseRischio(4, "Dinamico", 0.16, 0.27, 5, 0.014),
    5: ClasseRischio(5, "Aggressivo", 0.22, 0.38, 6, 0.016),
}
CLASSE_OBIETTIVO = {Obiettivo.protezione: 2, Obiettivo.reddito: 3, Obiettivo.crescita_moderata: 4,
                    Obiettivo.crescita: 5}
PUNTI_REAZIONE = {Reazione.vendo_tutto: 0, Reazione.vendo_parte: 1, Reazione.mantengo: 2, Reazione.compro: 3}
RISPOSTE_CORRETTE = {"risposta_tassi_obbligazioni": "scende", "risposta_diversificazione": "meno rischioso",
                     "risposta_barriera": "perdo circa il 50%"}


@dataclass
class Profilo:
    classe: int
    nome: str
    componenti: dict[str, int]  # classe di ogni componente
    vincolo: str  # componente che determina la classe finale
    tolleranza_punteggio: float  # 0-100
    capacita_perdita: float  # quota del patrimonio finanziario che si può perdere
    orizzonte_anni: int
    obiettivo: str
    quota_liquida: float
    conoscenza: dict[str, int]  # livello 0-3 per classe di strumenti
    quiz_corrette: int
    classi_ammesse: list[str]
    sostenibilita: dict
    incoerenze: list[str] = field(default_factory=list)

    @property
    def limiti(self) -> ClasseRischio:
        return CLASSI[self.classe]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["limiti"] = asdict(self.limiti)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Profilo:
        return cls(**{k: v for k, v in d.items() if k != "limiti"})


def _classe_da_soglie(valore: float, soglie: list[float]) -> int:
    """1 + numero di soglie superate (soglie crescenti, quattro valori per cinque classi)."""
    return 1 + sum(valore >= s for s in soglie)


def tolleranza(q: Questionario) -> float:
    """Punteggio 0-100 dalle tre domande sulla tolleranza al rischio."""
    r = q.rischio
    reazione = PUNTI_REAZIONE[r.reazione_ribasso_20] / 3
    perdita = min(r.perdita_massima_annua / 0.40, 1.0)
    scenario = (r.scenario_preferito - 1) / 3
    return round(100 * (0.35 * reazione + 0.40 * perdita + 0.25 * scenario), 1)


def capacita_perdita(q: Questionario) -> float:
    """Quota del patrimonio finanziario che il cliente può perdere senza cambiare tenore di vita.

    Si toglie dal patrimonio finanziario una riserva di emergenza (6 mesi di spese, 12 se il reddito non è
    stabile) e i debiti che il patrimonio non immobiliare dovrebbe coprire; sulla parte libera si applicano
    correzioni per capacità di risparmio, persone a carico, peso dei debiti ed età.
    """
    f = q.finanze
    if f.patrimonio_finanziario <= 0:
        return 0.0
    riserva = f.spese_annue * (0.5 if f.reddito_stabile else 1.0)
    debiti_scoperti = max(0.0, f.debiti - 0.6 * f.patrimonio_immobiliare)
    libero = max(0.0, f.patrimonio_finanziario - riserva - debiti_scoperti)
    quota_libera = libero / f.patrimonio_finanziario
    risparmio = (f.reddito_annuo_netto - f.spese_annue) / max(f.reddito_annuo_netto, 1.0)
    c = 0.45 * quota_libera
    c += 0.10 if risparmio >= 0.20 else (-0.10 if risparmio < 0 else 0.0)
    c -= min(0.05 * f.persone_a_carico, 0.15)
    patrimonio_totale = f.patrimonio_finanziario + f.patrimonio_immobiliare
    if patrimonio_totale > 0 and f.debiti > 0.5 * patrimonio_totale:
        c -= 0.10
    if q.eta >= 75:
        c -= 0.20
    elif q.eta >= 65:
        c -= 0.10
    return round(min(max(c, 0.0), 0.50), 3)


def conoscenza(q: Questionario) -> tuple[dict[str, int], int, list[str]]:
    """Livello 0-3 per classe di strumenti, risposte corrette al quiz e classi ammesse."""
    k = q.conoscenza
    corrette = sum(getattr(k, campo).strip().lower() == giusta for campo, giusta in RISPOSTE_CORRETTE.items())
    bonus = 1 if (k.professione_finanziaria or k.titolo_studio == Titolo.laurea_economica) else 0
    livelli = {c.value: 0 for c in ClasseStrumento}
    for s in k.strumenti:
        esperienza = {Frequenza.mai: 0, Frequenza.occasionale: 1, Frequenza.frequente: 2}[s.operazioni_3_anni]
        livelli[s.classe.value] = min(3, int(s.conosce) + esperienza + (bonus if s.conosce else 0))
    livelli["liquidita"] = max(livelli["liquidita"], 1)  # la liquidità è sempre ammessa
    barriera_ok = k.risposta_barriera.strip().lower() == RISPOSTE_CORRETTE["risposta_barriera"]
    ammesse = []
    for c in ClasseStrumento:
        lv = livelli[c.value]
        if c in COMPLESSE:
            ok = lv >= (3 if c == ClasseStrumento.derivati else 2) and barriera_ok
        else:
            ok = lv >= 1 or (corrette >= 2 and c in (ClasseStrumento.obbligazioni, ClasseStrumento.fondi_etf))
        if ok:
            ammesse.append(c.value)
    return livelli, corrette, ammesse


def incoerenze(q: Questionario, livelli: dict[str, int]) -> list[str]:
    out = []
    dichiarati = {s.classe for s in q.conoscenza.strumenti if s.conosce}
    if ClasseStrumento.certificati in dichiarati and \
            q.conoscenza.risposta_barriera.strip().lower() != RISPOSTE_CORRETTE["risposta_barriera"]:
        out.append("Dichiara di conoscere i certificati ma sbaglia la domanda sulla barriera: i certificati non "
                   "possono essere raccomandati finché la conoscenza non è verificata.")
    if q.obiettivi.obiettivo == Obiettivo.crescita and q.rischio.perdita_massima_annua <= 0.05:
        out.append("Chiede crescita del capitale ma non accetta perdite oltre il 5% in un anno: obiettivo e "
                   "tolleranza vanno chiariti con il cliente.")
    if q.obiettivi.orizzonte_anni >= 10 and q.rischio.reazione_ribasso_20 == Reazione.vendo_tutto:
        out.append("Orizzonte lungo ma vende tutto dopo un ribasso del 20%: rischio di disinvestire nel momento "
                   "peggiore.")
    if q.obiettivi.quota_liquida_12_mesi > 0.5 and q.obiettivi.orizzonte_anni > 5:
        out.append("Più di metà dell'importo potrebbe servire entro un anno, ma l'orizzonte dichiarato supera i "
                   "cinque anni.")
    if q.finanze.spese_annue > q.finanze.reddito_annuo_netto and q.rischio.scenario_preferito >= 3:
        out.append("Spende più di quanto guadagna ma sceglie scenari ad alto rischio.")
    if q.rischio.scenario_preferito == 4 and q.rischio.reazione_ribasso_20 in (Reazione.vendo_tutto,
                                                                               Reazione.vendo_parte):
        out.append("Sceglie lo scenario più rischioso ma venderebbe dopo un ribasso del 20%.")
    return out


def profila(q: Questionario) -> Profilo:
    punteggio = tolleranza(q)
    capacita = capacita_perdita(q)
    componenti = {
        "Tolleranza al rischio": _classe_da_soglie(punteggio, [20, 40, 60, 80]),
        "Capacità di sostenere perdite": 1 + sum(capacita >= CLASSI[c].perdita_max for c in (2, 3, 4, 5)),
        "Orizzonte temporale": _classe_da_soglie(q.obiettivi.orizzonte_anni, [3, 5, 8, 11]),
        "Obiettivo di investimento": CLASSE_OBIETTIVO[q.obiettivi.obiettivo],
    }
    classe = min(componenti.values())
    vincolo = min(componenti, key=lambda k: (componenti[k], list(componenti).index(k)))
    livelli, corrette, ammesse = conoscenza(q)
    return Profilo(
        classe=classe, nome=CLASSI[classe].nome, componenti=componenti, vincolo=vincolo,
        tolleranza_punteggio=punteggio, capacita_perdita=capacita, orizzonte_anni=q.obiettivi.orizzonte_anni,
        obiettivo=q.obiettivi.obiettivo.value, quota_liquida=q.obiettivi.quota_liquida_12_mesi,
        conoscenza=livelli, quiz_corrette=corrette, classi_ammesse=ammesse,
        sostenibilita=q.sostenibilita.model_dump(), incoerenze=incoerenze(q, livelli),
    )
