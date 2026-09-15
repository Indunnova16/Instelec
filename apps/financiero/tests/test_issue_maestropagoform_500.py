import pytest

from apps.financiero.models import Banco, MetodoPago


@pytest.mark.django_db
def test_maestros_pago_get_banco_no_crashea(client, admin_user):
    """Hotfix: MaestroPagoForm sin Meta.model tumbaba /financiero/maestros/pagos/
    con un 500 en cuanto la vista instanciaba el form (GET simple, tipo=banco
    por default). Confirmado roto en la revisión promovida por un validador
    adversarial (Instelec#261/#262)."""
    client.force_login(admin_user)
    resp = client.get("/financiero/maestros/pagos/")
    assert resp.status_code == 200
    assert b"Banco" in resp.content or b"banco" in resp.content


@pytest.mark.django_db
def test_maestros_pago_get_metodo_no_crashea(client, admin_user):
    client.force_login(admin_user)
    resp = client.get("/financiero/maestros/pagos/?tipo=metodo")
    assert resp.status_code == 200


@pytest.mark.django_db
def test_maestros_pago_crea_banco(client, admin_user):
    client.force_login(admin_user)
    resp = client.post(
        "/financiero/maestros/pagos/",
        {"tipo": "banco", "nombre": "QA_E2E Banco Hotfix", "activo": "on"},
    )
    assert resp.status_code == 302
    assert Banco.objects.filter(nombre="QA_E2E Banco Hotfix").exists()
    Banco.objects.filter(nombre="QA_E2E Banco Hotfix").delete()


@pytest.mark.django_db
def test_maestros_pago_crea_metodo(client, admin_user):
    client.force_login(admin_user)
    resp = client.post(
        "/financiero/maestros/pagos/",
        {"tipo": "metodo", "nombre": "QA_E2E Metodo Hotfix", "activo": "on"},
    )
    assert resp.status_code == 302
    assert MetodoPago.objects.filter(nombre="QA_E2E Metodo Hotfix").exists()
    MetodoPago.objects.filter(nombre="QA_E2E Metodo Hotfix").delete()
