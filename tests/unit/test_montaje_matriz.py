"""Tests para Montaje matriz CANT MONTAJE (issue #76)."""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.contratos.models import Contrato
from apps.construccion.models import (
    MontajeEstructuraTorre,
    ProyectoConstruccion,
    TorreConstruccion,
)


@pytest.fixture
def proyecto(db):
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo="CT-MON-76",
        nombre="Proyecto Montaje #76",
        cliente="Cliente",
        estado=Contrato.Estado.ACTIVO,
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato, nombre="Proyecto Montaje", estado="EJECUCION",
        # Defaults: 10/20/45/25 = 100
    )


@pytest.fixture
def torres(proyecto):
    return [
        TorreConstruccion.objects.create(proyecto=proyecto, numero=f"E{i}", tipo="A")
        for i in range(1, 4)
    ]


@pytest.fixture
def admin_client(client, admin_user, user_password):
    client.login(username=admin_user.email, password=user_password)
    return client


@pytest.mark.django_db
class TestMontajeEstructuraTorreModel:
    def test_defaults(self, proyecto, torres):
        m = MontajeEstructuraTorre.objects.create(proyecto=proyecto, torre=torres[0])
        assert m.avance_estructura_sitio == 0
        assert m.avance_ponderado_pct == 0.0

    def test_sumproduct_caso_issue(self, proyecto, torres):
        """Ejemplo del issue: estructura=1, prearmada=0.8, montada=1, revisada=1
        Pesos 10/20/45/25 → 0.1*1 + 0.2*0.8 + 0.45*1 + 0.25*1 = 0.96 (96%)."""
        m = MontajeEstructuraTorre.objects.create(
            proyecto=proyecto, torre=torres[0],
            avance_estructura_sitio=Decimal("1.0"),
            avance_prearamada=Decimal("0.8"),
            avance_torre_montada=Decimal("1.0"),
            avance_revisada=Decimal("1.0"),
        )
        assert m.avance_ponderado_pct == pytest.approx(96.0, abs=0.05)

    def test_sumproduct_caso_2(self, proyecto, torres):
        """estructura=1, prearmada=1, montada=1, revisada=0.6
        Pesos 10/20/45/25 → 0.1 + 0.2 + 0.45 + 0.15 = 0.9 (90%)."""
        m = MontajeEstructuraTorre.objects.create(
            proyecto=proyecto, torre=torres[0],
            avance_estructura_sitio=Decimal("1.0"),
            avance_prearamada=Decimal("1.0"),
            avance_torre_montada=Decimal("1.0"),
            avance_revisada=Decimal("0.6"),
        )
        assert m.avance_ponderado_pct == pytest.approx(90.0, abs=0.05)

    def test_avances_dict(self, proyecto, torres):
        m = MontajeEstructuraTorre.objects.create(
            proyecto=proyecto, torre=torres[0],
            avance_estructura_sitio=Decimal("0.5"),
        )
        d = m.avances_dict
        assert d["estructura_sitio"] == Decimal("0.5")
        assert set(d.keys()) == {"estructura_sitio", "prearamada", "torre_montada", "revisada"}


@pytest.mark.django_db
class TestMontajeMatrizView:
    def test_get_responde_200(self, admin_client, proyecto, torres):
        url = reverse("construccion:montaje_lista", kwargs={"proyecto_id": proyecto.id})
        resp = admin_client.get(url)
        assert resp.status_code == 200

    def test_get_crea_filas_idempotente(self, admin_client, proyecto, torres):
        url = reverse("construccion:montaje_lista", kwargs={"proyecto_id": proyecto.id})
        admin_client.get(url)
        assert MontajeEstructuraTorre.objects.filter(proyecto=proyecto).count() == 3
        admin_client.get(url)
        assert MontajeEstructuraTorre.objects.filter(proyecto=proyecto).count() == 3

    def test_contexto_pesos_default(self, admin_client, proyecto, torres):
        url = reverse("construccion:montaje_lista", kwargs={"proyecto_id": proyecto.id})
        resp = admin_client.get(url)
        ctx = resp.context
        assert ctx["pesos"]["estructura_sitio"] == 10
        assert ctx["pesos"]["torre_montada"] == 45
        assert ctx["suma_pesos"] == 100
        assert ctx["suma_pesos_ok"] is True


@pytest.mark.django_db
class TestMontajePesosUpdate:
    def test_pesos_validos(self, admin_client, proyecto):
        url = reverse("construccion:montaje_pesos_update", kwargs={"proyecto_id": proyecto.id})
        resp = admin_client.post(url, {
            "estructura_sitio": "15", "prearamada": "25",
            "torre_montada": "40", "revisada": "20",
        })
        assert resp.status_code == 200
        proyecto.refresh_from_db()
        assert proyecto.peso_mont_estructura_sitio_pct == 15

    def test_pesos_no_suman_100(self, admin_client, proyecto):
        url = reverse("construccion:montaje_pesos_update", kwargs={"proyecto_id": proyecto.id})
        resp = admin_client.post(url, {
            "estructura_sitio": "50", "prearamada": "30",
            "torre_montada": "30", "revisada": "20",  # suma 130
        })
        assert resp.status_code == 400


@pytest.mark.django_db
class TestMontajeAvanceUpdate:
    def test_avance_valido(self, admin_client, proyecto, torres):
        url = reverse("construccion:montaje_avance_update",
                      kwargs={"proyecto_id": proyecto.id, "torre_id": torres[0].id})
        resp = admin_client.post(url, {"columna": "estructura_sitio", "valor": "1.0"})
        assert resp.status_code == 200
        data = resp.json()
        # estructura_sitio=1, otros=0 → ponderado = 10%
        assert data["avance_ponderado_pct"] == pytest.approx(10.0, abs=0.05)

    def test_cascada_prearmada_no_excede_estructura(self, admin_client, proyecto, torres):
        """Prearmada > estructura_sitio → 400."""
        url = reverse("construccion:montaje_avance_update",
                      kwargs={"proyecto_id": proyecto.id, "torre_id": torres[0].id})
        # estructura_sitio queda en 0 por default
        resp = admin_client.post(url, {"columna": "prearamada", "valor": "0.5"})
        assert resp.status_code == 400
        assert "Estructura en sitio" in resp.json()["error"]

    def test_cascada_torre_montada_no_excede_prearmada(self, admin_client, proyecto, torres):
        url = reverse("construccion:montaje_avance_update",
                      kwargs={"proyecto_id": proyecto.id, "torre_id": torres[0].id})
        # Subo estructura primero a 1
        admin_client.post(url, {"columna": "estructura_sitio", "valor": "1"})
        # Sin prearmada, no puedo poner torre_montada
        resp = admin_client.post(url, {"columna": "torre_montada", "valor": "0.5"})
        assert resp.status_code == 400
        assert "Prearmada" in resp.json()["error"]

    def test_cascada_revisada_requiere_torre_montada_100(self, admin_client, proyecto, torres):
        url = reverse("construccion:montaje_avance_update",
                      kwargs={"proyecto_id": proyecto.id, "torre_id": torres[0].id})
        admin_client.post(url, {"columna": "estructura_sitio", "valor": "1"})
        admin_client.post(url, {"columna": "prearamada", "valor": "1"})
        admin_client.post(url, {"columna": "torre_montada", "valor": "0.8"})  # < 1
        resp = admin_client.post(url, {"columna": "revisada", "valor": "0.5"})
        assert resp.status_code == 400
        assert "Torre Montada" in resp.json()["error"]
        # Si subo torre_montada a 1, revisada se habilita:
        admin_client.post(url, {"columna": "torre_montada", "valor": "1"})
        resp = admin_client.post(url, {"columna": "revisada", "valor": "0.5"})
        assert resp.status_code == 200

    def test_columna_invalida(self, admin_client, proyecto, torres):
        url = reverse("construccion:montaje_avance_update",
                      kwargs={"proyecto_id": proyecto.id, "torre_id": torres[0].id})
        resp = admin_client.post(url, {"columna": "xxx", "valor": "0.5"})
        assert resp.status_code == 400

    def test_valor_fuera_de_rango(self, admin_client, proyecto, torres):
        url = reverse("construccion:montaje_avance_update",
                      kwargs={"proyecto_id": proyecto.id, "torre_id": torres[0].id})
        resp = admin_client.post(url, {"columna": "estructura_sitio", "valor": "1.5"})
        assert resp.status_code == 400
