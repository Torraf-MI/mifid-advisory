import pytest
from pydantic import ValidationError

from mifid_advisory.esempi import CLIENTI, questionario
from mifid_advisory.profilazione import CLASSI, profila
from mifid_advisory.questionario import Questionario


def test_clienti_di_esempio(profili):
    assert profili["anna"].classe == 4
    assert profili["giorgio"].classe == 4
    assert profili["lucia"].classe == 2


def test_classe_finale_e_la_componente_piu_prudente(profili):
    for p in profili.values():
        assert p.classe == min(p.componenti.values())
        assert p.componenti[p.vincolo] == p.classe
        assert p.limiti is CLASSI[p.classe]


def test_orizzonte_breve_limita_il_profilo():
    d = CLIENTI["anna"]["questionario"] | {}
    d = {**d, "obiettivi": {**d["obiettivi"], "orizzonte_anni": 2}}
    p = profila(Questionario.model_validate(d))
    assert p.classe == 1 and p.vincolo == "Orizzonte temporale"


def test_certificati_solo_con_conoscenza_verificata(profili):
    assert "certificati" not in profili["lucia"].classi_ammesse  # dichiara di conoscerli ma sbaglia il quiz
    assert any("certificati" in i for i in profili["lucia"].incoerenze)
    assert "derivati" not in profili["anna"].classi_ammesse


def test_eta_avanzata_riduce_la_capacita_di_perdita():
    q = questionario("anna").model_dump()
    giovane = profila(Questionario.model_validate(q)).capacita_perdita
    anziano = profila(Questionario.model_validate({**q, "eta": 80})).capacita_perdita
    assert anziano < giovane


def test_profilo_serializzabile(profili):
    from mifid_advisory.profilazione import Profilo

    for p in profili.values():
        assert Profilo.from_dict(p.to_dict()) == p


@pytest.mark.parametrize("modifica", [
    {"eta": 15},
    {"rischio": {"reazione_ribasso_20": "mantengo", "perdita_massima_annua": 0.9, "scenario_preferito": 2}},
    {"sostenibilita": {"ha_preferenze": False, "quota_minima_sostenibile": 0.3}},
])
def test_questionario_non_valido(modifica):
    with pytest.raises(ValidationError):
        Questionario.model_validate({**CLIENTI["anna"]["questionario"], **modifica})


def test_classi_di_strumenti_duplicate():
    d = CLIENTI["anna"]["questionario"]
    strumenti = d["conoscenza"]["strumenti"]
    with pytest.raises(ValidationError):
        Questionario.model_validate({**d, "conoscenza": {**d["conoscenza"], "strumenti": strumenti + strumenti[:1]}})
