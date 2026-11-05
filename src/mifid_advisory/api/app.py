"""Applicazione FastAPI. Documentazione interattiva su ``/docs``, pagina dimostrativa su ``/``."""

from __future__ import annotations

from contextlib import asynccontextmanager
from importlib import resources

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import __version__, mercato, servizi
from ..config import impostazioni
from ..db import ottieni_sessione, sessione
from ..migrazioni import migra
from .rotte import auth, catalogo, clienti, proposte, registro

STATICI = resources.files("mifid_advisory") / "static"


@asynccontextmanager
async def avvio(app: FastAPI):
    migra()
    if impostazioni().demo:
        with sessione() as s:
            if servizi.semina_demo(s):
                s.commit()
    yield


DESCRIZIONE = """
Piattaforma di consulenza finanziaria conforme a MiFID II: questionario di profilatura, profilo di rischio,
proposta di portafoglio ottimizzata, verifica di adeguatezza, dichiarazione per il cliente e registro di audit
a prova di manomissione.

**Demo**: `consulente@demo.it`, `compliance@demo.it`, `admin@demo.it`, password `demo`
(pulsante *Authorize* in alto a destra).

Dati di prodotto e rendimenti sono **simulati** a scopo dimostrativo.
"""


def crea_app() -> FastAPI:
    app = FastAPI(title="MiFID II Advisory API", version=__version__, description=DESCRIZIONE, lifespan=avvio)
    app.add_middleware(CORSMiddleware, allow_origins=impostazioni().origini_cors, allow_methods=["*"],
                       allow_headers=["*"])
    for r in (auth, clienti, proposte, catalogo, registro):
        app.include_router(r)

    @app.get("/salute", tags=["sistema"])
    def salute(s: Session = Depends(ottieni_sessione)):
        s.execute(text("select 1"))
        estr = mercato.ultimo(s, "estr")
        return {"stato": "ok", "versione": __version__, "database": s.bind.dialect.name,
                "estr": {"data": estr.data, "valore": estr.valore} if estr else None}

    @app.get("/", include_in_schema=False)
    def pagina_demo():
        return FileResponse(str(STATICI / "index.html"))

    app.mount("/static", StaticFiles(directory=str(STATICI)), name="static")
    return app


app = crea_app()
