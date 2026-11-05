import numpy as np
import pytest

from mifid_advisory.adeguatezza import verifica
from mifid_advisory.esempi import CLIENTI
from mifid_advisory.ottimizzazione import PESO_MAX_EMITTENTE, massimo_prodotto, ottimizza, prodotti_ammessi
from mifid_advisory.prodotti import BANDE_SRI, sri_da_volatilita
from mifid_advisory.rischio import es_parametrico, metriche


def test_bande_sri():
    assert sri_da_volatilita(0.003) == 1
    assert sri_da_volatilita(0.10) == 3
    assert sri_da_volatilita(0.15) == 4
    assert sri_da_volatilita(0.50) == 6
    assert sri_da_volatilita(0.90) == 7
    assert len(BANDE_SRI) == 6


def test_expected_shortfall_normale():
    # ES al 95% di una normale standard: phi(1,645) / 0,05 = 2,063
    assert es_parametrico(0.0, 1.0) == pytest.approx(2.0627, abs=1e-3)


@pytest.mark.parametrize("nome", list(CLIENTI))
def test_proposta_ottimizzata_rispetta_il_profilo(catalogo, profili, nome):
    p = profili[nome]
    pesi = ottimizza(catalogo, p)
    assert sum(pesi.values()) == pytest.approx(1.0)
    ammessi = set(prodotti_ammessi(catalogo, p))
    assert set(pesi) <= ammessi
    for isin, w in pesi.items():
        assert w <= massimo_prodotto(catalogo[isin]) + 1e-9
    m = metriche(catalogo, pesi, CLIENTI[nome]["importo"], p.orizzonte_anni)
    assert m.volatilita <= p.limiti.volatilita_max
    v = verifica(catalogo, p, pesi, CLIENTI[nome]["importo"])
    assert v.adeguata


def test_portafoglio_troppo_rischioso_non_adeguato(catalogo, profili):
    azionari = [x.isin for x in catalogo.prodotti if x.classe_strumento == "fondi_etf" and x.volatilita > 0.14][:4]
    pesi = {i: 0.25 for i in azionari}
    v = verifica(catalogo, profili["lucia"], pesi, 30_000)
    assert v.esito == "non_adeguato"
    ko = {c.codice for c in v.controlli if c.esito == "ko"}
    assert "rischio_portafoglio" in ko


def test_concentrazione_emittente(catalogo, profili):
    pesi = ottimizza(catalogo, profili["giorgio"])
    emittenti = {}
    for isin, w in pesi.items():
        if catalogo[isin].classe_strumento in ("obbligazioni", "certificati", "azioni"):
            emittenti[catalogo[isin].emittente] = emittenti.get(catalogo[isin].emittente, 0) + w
    assert all(w <= PESO_MAX_EMITTENTE + 1e-9 for w in emittenti.values())


def test_cambio_di_portafoglio_con_costi_benefici(catalogo, profili):
    g = CLIENTI["giorgio"]
    pesi = ottimizza(catalogo, profili["giorgio"])
    v = verifica(catalogo, profili["giorgio"], pesi, g["importo"], g["portafoglio_attuale"], costi_uscita=0.01)
    codici = {c.codice: c for c in v.controlli}
    assert "costi_benefici_cambio" in codici
    assert codici["costi_benefici_cambio"].esito == "ok"


def test_metriche_coerenti(catalogo):
    pesi = {catalogo.prodotti[0].isin: 1.0}
    m = metriche(catalogo, pesi, 10_000, 5)
    assert m.es_95 >= m.var_95 - 1e-9
    assert m.scenari["sfavorevole"] < m.scenari["moderato"] < m.scenari["favorevole"]
    assert np.isfinite(m.costi_totali)
