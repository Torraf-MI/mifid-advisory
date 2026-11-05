from sqlalchemy import text

from mifid_advisory import audit


def _eventi(s, n=5):
    for i in range(n):
        audit.registra(s, "test@demo.it", "prova", "cliente", i, {"valore": i, "testo": "àèì"})
    s.commit()


def test_catena_integra(sessione):
    _eventi(sessione)
    e = audit.verifica_catena(sessione)
    assert e.integro and e.eventi == 5


def test_modifica_rilevata(sessione):
    _eventi(sessione)
    sessione.execute(text("update eventi_audit set entita_id = 99 where id = 3"))
    sessione.commit()
    e = audit.verifica_catena(sessione)
    assert not e.integro and e.primo_errore == 3 and "modificato" in e.motivo


def test_cancellazione_rilevata(sessione):
    _eventi(sessione)
    sessione.execute(text("delete from eventi_audit where id = 2"))
    sessione.commit()
    e = audit.verifica_catena(sessione)
    assert not e.integro and e.primo_errore == 3 and "interrotto" in e.motivo


def test_hash_riproducibile_dopo_rilettura(sessione):
    _eventi(sessione, 1)
    sessione.expire_all()  # rilegge dal database: date e JSON come li restituisce il driver
    assert audit.verifica_catena(sessione).integro
