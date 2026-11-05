"""Questionario MiFID II: le informazioni che il consulente deve raccogliere prima di raccomandare un investimento.

L'articolo 25(2) della direttiva 2014/65/UE (MiFID II) e gli articoli 54-55 del Regolamento delegato 2017/565
chiedono di conoscere il cliente su cinque aree: conoscenza ed esperienza, situazione finanziaria (compresa la
capacità di sostenere perdite), obiettivi di investimento (compresi orizzonte e tolleranza al rischio) e, dal 2022
(Regolamento delegato 2021/1253), le preferenze di sostenibilità. Gli Orientamenti ESMA sulla valutazione di
adeguatezza (ESMA35-43-3172) aggiungono che le risposte vanno controllate per coerenza.

Ogni area è un modello Pydantic con vincoli di validazione: un questionario incompleto o incoerente nei tipi viene
respinto dall'API con un errore leggibile, prima di arrivare al calcolo del profilo.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class ClasseStrumento(StrEnum):
    liquidita = "liquidita"
    obbligazioni = "obbligazioni"
    fondi_etf = "fondi_etf"
    azioni = "azioni"
    certificati = "certificati"
    derivati = "derivati"


NOMI_CLASSI = {
    "liquidita": "Liquidità e fondi monetari", "obbligazioni": "Obbligazioni", "fondi_etf": "Fondi ed ETF",
    "azioni": "Azioni", "certificati": "Certificati e prodotti strutturati", "derivati": "Derivati e leva",
}
COMPLESSE = {ClasseStrumento.certificati, ClasseStrumento.derivati}


class Frequenza(StrEnum):
    mai = "mai"
    occasionale = "occasionale"  # da 1 a 5 operazioni negli ultimi 3 anni
    frequente = "frequente"  # più di 5 operazioni


class EsperienzaStrumento(BaseModel):
    classe: ClasseStrumento
    conosce: bool = Field(description="Dichiara di conoscere caratteristiche e rischi dello strumento")
    operazioni_3_anni: Frequenza = Frequenza.mai


class Titolo(StrEnum):
    obbligo = "obbligo"
    diploma = "diploma"
    laurea = "laurea"
    laurea_economica = "laurea_economica"


class ConoscenzaEsperienza(BaseModel):
    titolo_studio: Titolo
    professione_finanziaria: bool = False
    strumenti: list[EsperienzaStrumento] = Field(min_length=1)
    # Domande di verifica: la conoscenza dichiarata va controllata, non solo autocertificata
    risposta_tassi_obbligazioni: str = Field(description="Se i tassi salgono, il prezzo di un'obbligazione a tasso "
                                                         "fisso: sale | scende | non cambia")
    risposta_diversificazione: str = Field(description="Un fondo con 500 azioni rispetto a una sola azione è: "
                                                       "più rischioso | meno rischioso | uguale")
    risposta_barriera: str = Field(description="In un certificato con barriera al 60%, se a scadenza il sottostante "
                                               "perde il 50%: rimborso pieno | perdo circa il 50% | perdo tutto")

    @model_validator(mode="after")
    def _classi_uniche(self):
        classi = [s.classe for s in self.strumenti]
        if len(classi) != len(set(classi)):
            raise ValueError("Ogni classe di strumenti va indicata una sola volta")
        return self


class SituazioneFinanziaria(BaseModel):
    reddito_annuo_netto: float = Field(ge=0)
    spese_annue: float = Field(ge=0)
    patrimonio_finanziario: float = Field(ge=0, description="Liquidità e investimenti, compreso l'importo da investire")
    patrimonio_immobiliare: float = Field(ge=0, default=0)
    debiti: float = Field(ge=0, default=0, description="Debito residuo (mutui, prestiti)")
    reddito_stabile: bool = True
    persone_a_carico: int = Field(ge=0, le=15, default=0)


class Obiettivo(StrEnum):
    protezione = "protezione"  # preservare il capitale
    reddito = "reddito"  # flusso di cedole o dividendi
    crescita_moderata = "crescita_moderata"
    crescita = "crescita"


class Obiettivi(BaseModel):
    obiettivo: Obiettivo
    orizzonte_anni: int = Field(ge=1, le=40)
    quota_liquida_12_mesi: float = Field(ge=0, le=1, default=0.0,
                                         description="Quota dell'investimento che potrebbe servire entro 12 mesi")


class Reazione(StrEnum):
    vendo_tutto = "vendo_tutto"
    vendo_parte = "vendo_parte"
    mantengo = "mantengo"
    compro = "compro"


class TolleranzaRischio(BaseModel):
    reazione_ribasso_20: Reazione = Field(description="Che cosa fa se il portafoglio perde il 20% in pochi mesi")
    perdita_massima_annua: float = Field(ge=0, le=0.6, description="Perdita in un anno oltre la quale disinveste")
    scenario_preferito: int = Field(ge=1, le=4, description="1: +2%/0%, 2: +6%/−5%, 3: +12%/−15%, 4: +25%/−30%")


class PreferenzeSostenibilita(BaseModel):
    ha_preferenze: bool = False
    quota_minima_sostenibile: float = Field(ge=0, le=1, default=0.0,
                                            description="Quota minima in investimenti sostenibili (SFDR art. 2.17)")
    quota_minima_tassonomia: float = Field(ge=0, le=1, default=0.0,
                                           description="Quota minima allineata alla Tassonomia UE")
    considera_pai: bool = Field(default=False, description="Considera i principali effetti negativi (PAI)")


class Questionario(BaseModel):
    eta: int = Field(ge=18, le=110)
    conoscenza: ConoscenzaEsperienza
    finanze: SituazioneFinanziaria
    obiettivi: Obiettivi
    rischio: TolleranzaRischio
    sostenibilita: PreferenzeSostenibilita = PreferenzeSostenibilita()

    @model_validator(mode="after")
    def _sostenibilita(self):
        s = self.sostenibilita
        if not s.ha_preferenze and (s.quota_minima_sostenibile or s.quota_minima_tassonomia or s.considera_pai):
            raise ValueError("Preferenze di sostenibilità indicate senza ha_preferenze = true")
        return self
