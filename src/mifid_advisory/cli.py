"""Riga di comando: migrazioni, dati dimostrativi, pipeline dei dati di mercato, verifica del registro, server."""

from __future__ import annotations

import argparse
import json
import sys

from . import audit, mercato, migrazioni, servizi
from .db import sessione


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mifid-advisory", description=__doc__)
    sub = ap.add_subparsers(dest="comando", required=True)
    sub.add_parser("migra", help="applica le migrazioni del database (alembic upgrade head)")
    n = sub.add_parser("nuova-migrazione", help="genera una migrazione dalle differenze con db.py")
    n.add_argument("messaggio")
    sub.add_parser("demo", help="crea utenti, catalogo e clienti dimostrativi (solo su database vuoto)")
    m = sub.add_parser("aggiorna-mercato", help="scarica €STR, tasso BCE e inflazione Eurostat")
    m.add_argument("--senza-esempio", action="store_true",
                   help="non usare i valori di esempio se una fonte non risponde")
    m.add_argument("--rigoroso", action="store_true", help="esce con errore se una fonte non risponde")
    sub.add_parser("verifica-audit", help="ricalcola la catena di hash del registro di audit")
    s = sub.add_parser("serve", help="avvia l'API con uvicorn")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--reload", action="store_true")
    a = ap.parse_args(argv)

    if a.comando == "migra":
        migrazioni.migra()
        print("Database aggiornato all'ultima migrazione")
    elif a.comando == "nuova-migrazione":
        migrazioni.nuova(a.messaggio)
    elif a.comando == "demo":
        migrazioni.migra()
        with sessione() as ss:
            creati = servizi.semina_demo(ss)
            ss.commit()
        print("Dati dimostrativi creati" if creati else "Database non vuoto: nessun dato dimostrativo aggiunto")
    elif a.comando == "aggiorna-mercato":
        migrazioni.migra()
        with sessione() as ss:
            esito = mercato.aggiorna(ss, usa_esempio=not a.senza_esempio)
            audit.registra(ss, "pipeline", "mercato_aggiornato", "dati_mercato", None, esito)
            ss.commit()
        print(json.dumps(esito, indent=2, ensure_ascii=False))
        if a.rigoroso and any("errore" in e for e in esito.values()):
            return 1
    elif a.comando == "verifica-audit":
        migrazioni.migra()
        with sessione() as ss:
            e = audit.verifica_catena(ss)
        print(json.dumps(e.__dict__, ensure_ascii=False))
        return 0 if e.integro else 2
    elif a.comando == "serve":
        import uvicorn

        uvicorn.run("mifid_advisory.api.app:app", host=a.host, port=a.port, reload=a.reload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
