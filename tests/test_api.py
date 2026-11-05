from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from mifid_advisory import db
from mifid_advisory.esempi import CLIENTI


@pytest.fixture
def client(url_db):
    from mifid_advisory.api.app import crea_app

    with TestClient(crea_app()) as c:
        yield c


def accedi(c, email, password="demo"):
    r = c.post("/auth/token", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


@pytest.fixture
def consulente(client):
    return accedi(client, "consulente@demo.it")


@pytest.fixture
def compliance(client):
    return accedi(client, "compliance@demo.it")


@pytest.fixture
def admin(client):
    return accedi(client, "admin@demo.it")


def test_salute_e_demo(client):
    r = client.get("/salute").json()
    assert r["stato"] == "ok" and r["estr"]["valore"] > 0
    assert client.get("/").status_code == 200


def test_accesso(client):
    assert client.post("/auth/token", data={"username": "consulente@demo.it", "password": "x"}).status_code == 401
    assert client.get("/clienti").status_code == 401
    assert client.get("/clienti", headers={"Authorization": "Bearer non-valido"}).status_code == 401


def test_flusso_completo(client, consulente, compliance):
    r = client.post("/clienti", headers=consulente, json={"nome": "Paolo", "cognome": "Prova",
                                                          "data_nascita": "1980-03-01", "email": "paolo@example.com"})
    assert r.status_code == 201
    cid = r.json()["id"]
    # senza profilo non si può fare una proposta
    assert client.post(f"/clienti/{cid}/proposte", headers=consulente, json={"importo": 10_000}).status_code == 409
    r = client.post(f"/clienti/{cid}/questionari", headers=consulente, json=CLIENTI["giorgio"]["questionario"])
    assert r.status_code == 201 and r.json()["classe_rischio"] == 4
    r = client.post(f"/clienti/{cid}/proposte", headers=consulente, json={"importo": 100_000})
    assert r.status_code == 201
    p = r.json()
    assert p["stato"] == "adeguata" and p["metodo"] == "ottimizzata"
    assert sum(x["peso"] for x in p["posizioni"]) == pytest.approx(1)
    assert sum(x["importo"] for x in p["posizioni"]) == pytest.approx(100_000, abs=1)
    d = client.get(f"/proposte/{p['id']}/dichiarazione", headers=consulente)
    assert d.status_code == 200 and "Dichiarazione di adeguatezza" in d.text and "SHA-256" in d.text
    assert client.post(f"/proposte/{p['id']}/accetta", headers=compliance, json={}).status_code == 403
    r = client.post(f"/proposte/{p['id']}/accetta", headers=consulente, json={"note": "firmata in filiale"})
    assert r.json()["stato"] == "accettata"
    assert client.post(f"/proposte/{p['id']}/rifiuta", headers=consulente, json={}).status_code == 409
    eventi = client.get("/audit", headers=compliance, params={"entita": "proposta", "entita_id": p["id"]}).json()
    assert [e["azione"] for e in eventi] == ["proposta_accettata", "proposta_creata"]
    assert client.get("/audit/verifica", headers=compliance).json()["integro"]


def test_proposta_manuale_non_adeguata_non_accettabile(client, consulente):
    lucia = next(c for c in client.get("/clienti", headers=consulente).json() if c["nome"] == "Lucia")
    prodotti = client.get("/prodotti", headers=consulente).json()
    rischiosi = [p["isin"] for p in prodotti if p["sri"] >= 5][:2]
    r = client.post(f"/clienti/{lucia['id']}/proposte", headers=consulente,
                    json={"importo": 20_000, "pesi": {rischiosi[0]: 0.5, rischiosi[1]: 0.5}})
    assert r.status_code == 201 and r.json()["stato"] == "non_adeguata"
    assert client.post(f"/proposte/{r.json()['id']}/accetta", headers=consulente, json={}).status_code == 409


@pytest.mark.parametrize("corpo", [
    {"importo": -5},
    {"importo": 1000, "pesi": {"XX0000000011": 0.5}},
    {"importo": 1000, "pesi": {"IT0000000000": 1.0}},
])
def test_proposte_non_valide(client, consulente, corpo):
    cid = client.get("/clienti", headers=consulente).json()[0]["id"]
    assert client.post(f"/clienti/{cid}/proposte", headers=consulente, json=corpo).status_code in (409, 422)


def test_questionario_non_valido(client, consulente):
    cid = client.get("/clienti", headers=consulente).json()[0]["id"]
    q = {**CLIENTI["anna"]["questionario"], "eta": 12}
    r = client.post(f"/clienti/{cid}/questionari", headers=consulente, json=q)
    assert r.status_code == 422


def test_profilo_scaduto(client, consulente):
    cid = client.get("/clienti", headers=consulente).json()[0]["id"]
    with db.sessione() as s:
        ieri = date.today() - timedelta(1)
        s.execute(update(db.Profilo).where(db.Profilo.cliente_id == cid).values(valido_fino=ieri))
        s.commit()
    r = client.post(f"/clienti/{cid}/proposte", headers=consulente, json={"importo": 10_000})
    assert r.status_code == 409 and "scaduto" in r.json()["detail"]


def test_ruoli(client, consulente, compliance, admin):
    # un secondo consulente non vede i clienti del primo
    r = client.post("/utenti", headers=admin, json={"email": "altro@demo.it", "nome": "Altro", "ruolo": "consulente",
                                                    "password": "password-lunga"})
    assert r.status_code == 201
    altro = accedi(client, "altro@demo.it", "password-lunga")
    assert client.get("/clienti", headers=altro).json() == []
    cid = client.get("/clienti", headers=consulente).json()[0]["id"]
    assert client.get(f"/clienti/{cid}", headers=altro).status_code == 404
    # compliance legge tutto ma non opera; il consulente non legge il registro
    assert client.get(f"/clienti/{cid}", headers=compliance).status_code == 200
    assert client.post("/clienti", headers=compliance, json={"nome": "X", "cognome": "Y"}).status_code == 403
    assert client.get("/audit", headers=consulente).status_code == 403
    assert client.post("/utenti", headers=consulente, json={}).status_code in (403, 422)
    assert client.post("/mercato/aggiorna", headers=consulente).status_code == 403


def test_dati_di_mercato(client, consulente):
    serie = {d["serie"] for d in client.get("/mercato", headers=consulente).json()}
    assert serie == {"estr", "bce_depositi", "inflazione_it", "inflazione_ea"}
