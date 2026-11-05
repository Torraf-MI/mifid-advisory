"""Clienti di esempio (questionari compilati) per la demo, i test e la pagina dimostrativa."""

from __future__ import annotations

from .questionario import Questionario

_STRUMENTI_BASE = [
    {"classe": "liquidita", "conosce": True, "operazioni_3_anni": "frequente"},
    {"classe": "obbligazioni", "conosce": True, "operazioni_3_anni": "occasionale"},
    {"classe": "fondi_etf", "conosce": True, "operazioni_3_anni": "occasionale"},
]

CLIENTI = {
    "anna": {
        "anagrafica": {"nome": "Anna", "cognome": "Esempio", "data_nascita": "1991-05-12",
                       "email": "anna@example.com"},
        "importo": 50_000,
        "questionario": {
            "eta": 34,
            "conoscenza": {"titolo_studio": "laurea", "professione_finanziaria": False,
                           "strumenti": _STRUMENTI_BASE + [{"classe": "azioni", "conosce": True,
                                                             "operazioni_3_anni": "occasionale"}],
                           "risposta_tassi_obbligazioni": "scende", "risposta_diversificazione": "meno rischioso",
                           "risposta_barriera": "rimborso pieno"},
            "finanze": {"reddito_annuo_netto": 38_000, "spese_annue": 24_000, "patrimonio_finanziario": 70_000,
                        "patrimonio_immobiliare": 0, "debiti": 0, "reddito_stabile": True, "persone_a_carico": 0},
            "obiettivi": {"obiettivo": "crescita", "orizzonte_anni": 15, "quota_liquida_12_mesi": 0.0},
            "rischio": {"reazione_ribasso_20": "mantengo", "perdita_massima_annua": 0.25, "scenario_preferito": 3},
            "sostenibilita": {"ha_preferenze": True, "quota_minima_sostenibile": 0.30,
                              "quota_minima_tassonomia": 0.05, "considera_pai": True},
        },
    },
    "giorgio": {
        "anagrafica": {"nome": "Giorgio", "cognome": "Esempio", "data_nascita": "1967-02-03",
                       "email": "giorgio@example.com"},
        "importo": 300_000,
        # Oggi è investito nei fondi della banca: la proposta deve giustificare il cambio
        "portafoglio_attuale": {"XX0000000193": 0.6, "XX0000000201": 0.4},
        "questionario": {
            "eta": 58,
            "conoscenza": {"titolo_studio": "laurea_economica", "professione_finanziaria": False,
                           "strumenti": _STRUMENTI_BASE + [
                               {"classe": "azioni", "conosce": True, "operazioni_3_anni": "frequente"},
                               {"classe": "certificati", "conosce": True, "operazioni_3_anni": "occasionale"}],
                           "risposta_tassi_obbligazioni": "scende", "risposta_diversificazione": "meno rischioso",
                           "risposta_barriera": "perdo circa il 50%"},
            "finanze": {"reddito_annuo_netto": 95_000, "spese_annue": 55_000, "patrimonio_finanziario": 450_000,
                        "patrimonio_immobiliare": 600_000, "debiti": 80_000, "reddito_stabile": True,
                        "persone_a_carico": 1},
            "obiettivi": {"obiettivo": "crescita_moderata", "orizzonte_anni": 8, "quota_liquida_12_mesi": 0.05},
            "rischio": {"reazione_ribasso_20": "mantengo", "perdita_massima_annua": 0.20, "scenario_preferito": 3},
            "sostenibilita": {"ha_preferenze": False},
        },
    },
    "lucia": {
        "anagrafica": {"nome": "Lucia", "cognome": "Esempio", "data_nascita": "1953-09-21",
                       "email": "lucia@example.com"},
        "importo": 80_000,
        "questionario": {
            "eta": 72,
            "conoscenza": {"titolo_studio": "diploma", "professione_finanziaria": False,
                           "strumenti": [{"classe": "liquidita", "conosce": True, "operazioni_3_anni": "frequente"},
                                         {"classe": "obbligazioni", "conosce": True,
                                          "operazioni_3_anni": "occasionale"},
                                         {"classe": "certificati", "conosce": True, "operazioni_3_anni": "mai"}],
                           "risposta_tassi_obbligazioni": "scende", "risposta_diversificazione": "uguale",
                           "risposta_barriera": "rimborso pieno"},
            "finanze": {"reddito_annuo_netto": 22_000, "spese_annue": 19_000, "patrimonio_finanziario": 110_000,
                        "patrimonio_immobiliare": 250_000, "debiti": 0, "reddito_stabile": True,
                        "persone_a_carico": 0},
            "obiettivi": {"obiettivo": "protezione", "orizzonte_anni": 4, "quota_liquida_12_mesi": 0.20},
            "rischio": {"reazione_ribasso_20": "vendo_parte", "perdita_massima_annua": 0.05, "scenario_preferito": 2},
            "sostenibilita": {"ha_preferenze": False},
        },
    },
}


def questionario(nome: str) -> Questionario:
    return Questionario.model_validate(CLIENTI[nome]["questionario"])
