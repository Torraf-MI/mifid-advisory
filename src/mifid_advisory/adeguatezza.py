"""Verifica di adeguatezza di una proposta: ogni controllo con esito, motivazione e riferimento normativo.

La verifica si fa su due livelli, come richiesto dagli Orientamenti ESMA sull'adeguatezza:

- **singolo prodotto**: conoscenza ed esperienza, rischio PRIIPs, periodo di detenzione, mercato di riferimento,
  preferenze di sostenibilità;
- **portafoglio**: rischio complessivo rispetto alla classe del cliente, perdita in uno scenario avverso rispetto
  alla capacità di sostenere perdite, liquidità, concentrazione, sostenibilità, costi e, se la proposta sostituisce
  investimenti esistenti, l'analisi costi-benefici del cambio (articolo 54(11) del Regolamento delegato 2017/565).

Ogni controllo è ``ok``, ``attenzione`` (da motivare al cliente) o ``ko`` (la proposta non può essere fatta).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .ottimizzazione import CLASSI_EMITTENTE, PESO_MAX_EMITTENTE, adeguatezza_prodotto, massimo_prodotto
from .prodotti import Catalogo
from .profilazione import Profilo
from .rischio import Metriche, metriche

OK, ATTENZIONE, KO = "ok", "attenzione", "ko"


@dataclass
class Controllo:
    codice: str
    area: str
    descrizione: str
    esito: str
    dettaglio: str
    riferimento: str = ""


@dataclass
class Verifica:
    esito: str  # adeguato, adeguato_con_avvertenze, non_adeguato
    controlli: list[Controllo]
    metriche: Metriche

    @property
    def adeguata(self) -> bool:
        return self.esito != "non_adeguato"

    def to_dict(self) -> dict:
        return {"esito": self.esito, "controlli": [asdict(c) for c in self.controlli],
                "metriche": self.metriche.to_dict()}


def _pct(x: float, dec: int = 1) -> str:
    return f"{100 * x:.{dec}f}%".replace(".", ",")


def _eur(x: float) -> str:
    return f"€ {x:,.0f}".replace(",", ".")


def verifica(catalogo: Catalogo, profilo: Profilo, pesi: dict[str, float], importo: float,
             portafoglio_attuale: dict[str, float] | None = None, costi_uscita: float = 0.0) -> Verifica:
    m = metriche(catalogo, pesi, importo, profilo.orizzonte_anni)
    lim = profilo.limiti
    c: list[Controllo] = []

    # Coerenza del profilo
    if profilo.incoerenze:
        c.append(Controllo("coerenza_questionario", "Profilo", "Coerenza delle risposte del questionario",
                           ATTENZIONE, " ".join(profilo.incoerenze), "Orientamenti ESMA 35-43-3172, n. 4"))
    else:
        c.append(Controllo("coerenza_questionario", "Profilo", "Coerenza delle risposte del questionario", OK,
                           "Nessuna incoerenza rilevata", "Orientamenti ESMA 35-43-3172, n. 4"))

    # Singoli prodotti
    for isin, w in pesi.items():
        p = catalogo[isin]
        e = adeguatezza_prodotto(p, profilo)
        c.append(Controllo(f"prodotto_{isin}", "Prodotto", f"{p.nome} ({_pct(w, 0)})", OK if e.ammesso else KO,
                           "Adeguato al profilo" if e.ammesso else "; ".join(e.motivi).capitalize(),
                           "Dir. 2014/65/UE, art. 25(2); Reg. delegato 2017/565, art. 54"))

    # Portafoglio
    c.append(Controllo("rischio_portafoglio", "Portafoglio", "Volatilità del portafoglio entro il profilo",
                       OK if m.volatilita <= lim.volatilita_max else KO,
                       f"Volatilità {_pct(m.volatilita)} su un massimo di {_pct(lim.volatilita_max)} per il "
                       f"profilo {lim.nome.lower()}", "Reg. delegato 2017/565, art. 54(2)"))
    perdita_max = min(lim.perdita_max, profilo.capacita_perdita)
    c.append(Controllo("capacita_perdita", "Portafoglio", "Perdita in uno scenario avverso sostenibile dal cliente",
                       OK if m.es_95 <= perdita_max + 1e-4 else KO,
                       f"Perdita media nel 5% dei casi peggiori a un anno {_pct(m.es_95)}, pari a "
                       f"{_eur(m.es_95 * importo)}; massimo sostenibile {_pct(perdita_max)}",
                       "Reg. delegato 2017/565, art. 54(5)"))
    liquido = sum(w for i, w in pesi.items() if catalogo[i].classe_strumento == "liquidita")
    if profilo.quota_liquida > 0:
        c.append(Controllo("liquidita", "Portafoglio", "Liquidità per le esigenze dei prossimi 12 mesi",
                           OK if liquido >= profilo.quota_liquida - 1e-6 else KO,
                           f"Investito in liquidità {_pct(liquido, 0)}, richiesto {_pct(profilo.quota_liquida, 0)}",
                           "Reg. delegato 2017/565, art. 54(2)"))
    eccessi = [(catalogo[i].nome, w) for i, w in pesi.items() if w > massimo_prodotto(catalogo[i]) + 1e-6]
    non_liquidi = [w for i, w in pesi.items() if catalogo[i].classe_strumento != "liquidita"] or [0.0]
    c.append(Controllo("concentrazione_prodotto", "Portafoglio", "Concentrazione sul singolo prodotto",
                       ATTENZIONE if eccessi else OK,
                       "; ".join(f"{n}: {_pct(w, 0)}" for n, w in eccessi) if eccessi else
                       f"Peso massimo di un prodotto non monetario {_pct(max(non_liquidi), 0)}",
                       "Orientamenti ESMA 35-43-3172, n. 7"))
    emittenti: dict[str, float] = {}
    for i, w in pesi.items():
        if catalogo[i].classe_strumento in CLASSI_EMITTENTE:
            emittenti[catalogo[i].emittente] = emittenti.get(catalogo[i].emittente, 0) + w
    if emittenti:
        nome, peso = max(emittenti.items(), key=lambda x: x[1])
        c.append(Controllo("concentrazione_emittente", "Portafoglio", "Rischio di credito verso un singolo emittente",
                           OK if peso <= PESO_MAX_EMITTENTE + 1e-6 else KO,
                           f"{nome}: {_pct(peso, 0)} (limite {_pct(PESO_MAX_EMITTENTE, 0)})",
                           "Orientamenti ESMA 35-43-3172, n. 7"))
    s = profilo.sostenibilita
    if s.get("ha_preferenze"):
        for chiave, valore, nome in [("quota_minima_sostenibile", m.quota_sostenibile, "investimenti sostenibili"),
                                     ("quota_minima_tassonomia", m.quota_tassonomia, "allineata alla Tassonomia")]:
            richiesto = s.get(chiave, 0)
            if richiesto > 0:
                c.append(Controllo(chiave, "Sostenibilità", f"Quota {nome}",
                                   OK if valore >= richiesto - 1e-6 else KO,
                                   f"{_pct(valore, 0)} contro un minimo richiesto di {_pct(richiesto, 0)}",
                                   "Reg. delegato 2021/1253"))
    c.append(Controllo("costi", "Costi", "Costi complessivi ragionevoli per il profilo",
                       OK if m.costo_annuo <= lim.costo_max else ATTENZIONE,
                       f"Costo annuo {_pct(m.costo_annuo, 2)} (riferimento {_pct(lim.costo_max, 2)}), "
                       f"{_eur(m.costi_totali)} sull'orizzonte di {m.orizzonte_anni} anni",
                       "Dir. 2014/65/UE, art. 24(4); Orientamenti ESMA 35-43-3172, n. 8"))
    if portafoglio_attuale:
        att = metriche(catalogo, portafoglio_attuale, importo, profilo.orizzonte_anni)
        ingresso = importo * sum(w * catalogo[i].costi_ingresso for i, w in pesi.items())
        ter_prop = sum(w * catalogo[i].ter for i, w in pesi.items())
        # I rendimenti attesi del catalogo sono già al netto dei costi correnti: si confrontano direttamente
        h = profilo.orizzonte_anni
        beneficio = importo * ((1 + m.rendimento_atteso) ** h - (1 + att.rendimento_atteso) ** h)
        costo = ingresso + importo * costi_uscita
        risparmio = importo * h * (sum(w * catalogo[i].ter for i, w in portafoglio_attuale.items()) - ter_prop)
        c.append(Controllo(
            "costi_benefici_cambio", "Costi", "Analisi costi-benefici della sostituzione degli investimenti",
            OK if beneficio >= costo else KO,
            f"Maggior rendimento atteso netto sull'orizzonte {_eur(beneficio)} (di cui risparmio di costi correnti "
            f"{_eur(risparmio)}) contro costi del cambio {_eur(costo)}",
            "Reg. delegato 2017/565, art. 54(11)"))

    if any(x.esito == KO for x in c):
        esito = "non_adeguato"
    elif any(x.esito == ATTENZIONE for x in c):
        esito = "adeguato_con_avvertenze"
    else:
        esito = "adeguato"
    return Verifica(esito, c, m)
