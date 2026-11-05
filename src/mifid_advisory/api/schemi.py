"""Modelli Pydantic di input e output dell'API."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, field_validator

# SQLite non conserva il fuso orario: i momenti salvati sono sempre in UTC
Momento = Annotated[datetime, AfterValidator(lambda d: d if d.tzinfo else d.replace(tzinfo=UTC))]


class Orm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    ruolo: str


class UtenteOut(Orm):
    id: int
    email: str
    nome: str
    ruolo: str


class UtenteIn(BaseModel):
    email: EmailStr
    nome: str = Field(min_length=1, max_length=200)
    ruolo: str = Field(pattern="^(consulente|compliance|admin)$")
    password: str = Field(min_length=8)


class ClienteIn(BaseModel):
    nome: str = Field(min_length=1, max_length=100)
    cognome: str = Field(min_length=1, max_length=100)
    data_nascita: date | None = None
    email: EmailStr | None = None


class ClienteOut(Orm):
    id: int
    nome: str
    cognome: str
    data_nascita: date | None
    email: str | None
    consulente_id: int
    creato_il: Momento


class ProfiloOut(Orm):
    id: int
    cliente_id: int
    questionario_id: int
    classe_rischio: int
    dettagli: dict
    creato_il: Momento
    valido_fino: date


class ClienteDettaglio(ClienteOut):
    profilo: ProfiloOut | None = None
    proposte: list[PropostaSintesi] = []


class ProdottoOut(Orm):
    isin: str
    nome: str
    classe_strumento: str
    categoria: str
    sri: int
    dati: dict


class PropostaIn(BaseModel):
    importo: float = Field(gt=0, le=1e9)
    pesi: dict[str, float] | None = Field(None, description="Assenti: proposta ottimizzata. Presenti: proposta manuale")
    portafoglio_attuale: dict[str, float] | None = Field(None, description="Per la verifica costi-benefici del cambio")
    costi_uscita: float = Field(0.0, ge=0, le=0.2, description="Costi di uscita dal portafoglio attuale, in quota")

    @field_validator("pesi", "portafoglio_attuale")
    @classmethod
    def pesi_positivi(cls, v: dict[str, float] | None) -> dict[str, float] | None:
        if v is not None and any(w <= 0 for w in v.values()):
            raise ValueError("i pesi devono essere positivi")
        return v


class PosizioneOut(Orm):
    isin: str
    peso: float
    importo: float


class VerificaOut(Orm):
    esito: str
    controlli: list[dict]
    metriche: dict


class PropostaSintesi(Orm):
    id: int
    importo: float
    stato: str
    metodo: str
    creato_il: Momento


class PropostaOut(PropostaSintesi):
    cliente_id: int
    profilo_id: int
    consulente_id: int
    portafoglio_attuale: dict | None
    decisa_il: Momento | None
    posizioni: list[PosizioneOut]
    verifica: VerificaOut | None


class Decisione(BaseModel):
    note: str | None = Field(None, max_length=2000)


class EventoOut(Orm):
    id: int
    momento: Momento
    utente: str
    azione: str
    entita: str
    entita_id: int | None
    contenuto: dict
    hash_precedente: str
    hash: str
    note: str | None


class VerificaCatenaOut(BaseModel):
    integro: bool
    eventi: int
    primo_errore: int | None
    motivo: str


class DatoMercatoOut(Orm):
    serie: str
    data: date
    valore: float
    fonte: str


ClienteDettaglio.model_rebuild()
