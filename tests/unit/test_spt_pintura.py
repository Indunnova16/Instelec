"""Tests para SPT y Pintura (issue #78)."""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.contratos.models import Contrato
from apps.construccion.models import (
    PinturaAeronauticaTorre,
    PinturaFranja,
    PinturaPatasTorre,
    ProyectoConstruccion,
    SPTTorre,
    TorreConstruccion,
)


@pytest.fixture
def proyecto(db):
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo="CT-SPT-78", nombre="Proyecto SPT #78", cliente="C",
        estado=Contrato.Estado.ACTIVO,
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato, nombre="Proyecto SPT", estado="EJECUCION",
    )


@pytest.fixture
def torres(proyecto):
    return [
        TorreConstruccion.objects.create(proyecto=proyecto, numero=f"T-{i}", tipo="A")
        for i in range(1, 3)
    ]


@pytest.fixture
def admin_client(client, admin_user, user_password):
    client.login(username=admin_user.email, password=user_password)
    return client


@pytest.mark.django_db
class TestSPTTorreModel:
    def test_diferencia_cable(self, proyecto, torres):
        spt = SPTTorre.objects.create(
            proyecto=proyecto, torre=torres[0],
            cable_planos_m=Decimal("100.5"), cable_instalado_m=Decimal("98.3"),
        )
        assert spt.diferencia_cable == Decimal("2.2")

    def test_diferencia_cable_none_si_faltan_datos(self, proyecto, torres):
        spt = SPTTorre.objects.create(proyecto=proyecto, torre=torres[0])
        assert spt.diferencia_cable is None

    def test_diferencia_polvora(self, proyecto, torres):
        spt = SPTTorre.objects.create(
            proyecto=proyecto, torre=torres[0],
            polvora_teorica_cajas=Decimal("20"), polvora_real_kg=Decimal("18.5"),
        )
        assert spt.diferencia_polvora == Decimal("1.5")


@pytest.mark.django_db
class TestPinturaAeroSignal:
    """El signal crea 7 franjas con colores alternando al crear PinturaAeronauticaTorre."""

    def test_signal_crea_7_franjas(self, proyecto, torres):
        aero = PinturaAeronauticaTorre.objects.create(proyecto=proyecto, torre=torres[0])
        franjas = list(aero.franjas.order_by('numero_franja'))
        assert len(franjas) == 7
        # Colores alternando: 1,3,5,7 NARANJA · 2,4,6 BLANCO
        for f in franjas:
            esperado = PinturaFranja.Color.NARANJA if f.numero_franja % 2 == 1 else PinturaFranja.Color.BLANCO
            assert f.color == esperado, f"Franja {f.numero_franja} debería ser {esperado}, es {f.color}"

    def test_franjas_no_se_duplican(self, proyecto, torres):
        """El signal idempotente: re-guardar no crea franjas extras."""
        aero = PinturaAeronauticaTorre.objects.create(proyecto=proyecto, torre=torres[0])
        aero.save()  # disparar post_save de nuevo (created=False)
        assert aero.franjas.count() == 7

    def test_franja_diferencia(self, proyecto, torres):
        aero = PinturaAeronauticaTorre.objects.create(proyecto=proyecto, torre=torres[0])
        f = aero.franjas.get(numero_franja=1)
        f.cantidad_base_proyectada = Decimal("10")
        f.cantidad_base_consumida = Decimal("9.8")
        f.save()
        assert f.diferencia_base == Decimal("0.2")


@pytest.mark.django_db
class TestSPTPinturaIndexView:
    def test_get_responde_200(self, admin_client, proyecto, torres):
        url = reverse("construccion:spt_pintura", kwargs={"proyecto_id": proyecto.id})
        resp = admin_client.get(url)
        assert resp.status_code == 200


@pytest.mark.django_db
class TestSPTPinturaTorreView:
    def test_get_crea_estructuras(self, admin_client, proyecto, torres):
        """La primera visita crea SPTTorre, PinturaPatasTorre, PinturaAeronauticaTorre + 7 franjas."""
        url = reverse("construccion:spt_pintura_torre",
                      kwargs={"proyecto_id": proyecto.id, "torre_id": torres[0].id})
        resp = admin_client.get(url)
        assert resp.status_code == 200
        assert SPTTorre.objects.filter(torre=torres[0]).exists()
        assert PinturaPatasTorre.objects.filter(torre=torres[0]).exists()
        assert PinturaAeronauticaTorre.objects.filter(torre=torres[0]).exists()
        assert PinturaFranja.objects.filter(
            pintura_aeronautica__torre=torres[0]).count() == 7

    def test_get_navegacion_prev_next(self, admin_client, proyecto, torres):
        url = reverse("construccion:spt_pintura_torre",
                      kwargs={"proyecto_id": proyecto.id, "torre_id": torres[0].id})
        resp = admin_client.get(url)
        ctx = resp.context
        assert ctx["prev_torre"] is None  # primera torre
        assert ctx["next_torre"].id == torres[1].id
        assert ctx["posicion"] == 1
        assert ctx["total_torres"] == 2


@pytest.mark.django_db
class TestSPTPinturaUpdateView:
    def _url(self, proyecto, torre):
        return reverse("construccion:spt_pintura_update",
                       kwargs={"proyecto_id": proyecto.id, "torre_id": torre.id})

    def test_update_spt(self, admin_client, proyecto, torres):
        resp = admin_client.post(self._url(proyecto, torres[0]), {
            "seccion": "spt",
            "cable_planos_m": "100.5",
            "cable_instalado_m": "98.3",
            "porcentaje_avance": "75",
            "control_compensacion": "1",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["diferencia_cable"] == pytest.approx(2.2)
        spt = SPTTorre.objects.get(torre=torres[0])
        assert spt.porcentaje_avance == 75
        assert spt.control_compensacion is True

    def test_update_spt_avance_fuera_de_rango(self, admin_client, proyecto, torres):
        resp = admin_client.post(self._url(proyecto, torres[0]), {
            "seccion": "spt", "porcentaje_avance": "150",
        })
        assert resp.status_code == 400

    def test_update_patas(self, admin_client, proyecto, torres):
        resp = admin_client.post(self._url(proyecto, torres[0]), {
            "seccion": "patas",
            "control_espesor": "1",
            "torres_pintadas": "1",
            "cuadrilla": "Cruz",
        })
        assert resp.status_code == 200
        patas = PinturaPatasTorre.objects.get(torre=torres[0])
        assert patas.cuadrilla == "Cruz"
        assert patas.control_espesor is True

    def test_update_aero(self, admin_client, proyecto, torres):
        resp = admin_client.post(self._url(proyecto, torres[0]), {
            "seccion": "aero",
            "revision_espesor_micras": "1",
        })
        assert resp.status_code == 200
        aero = PinturaAeronauticaTorre.objects.get(torre=torres[0])
        assert aero.revision_espesor_micras is True

    def test_update_franja(self, admin_client, proyecto, torres):
        # Trigger creación de aero+franjas
        admin_client.get(reverse("construccion:spt_pintura_torre",
                                 kwargs={"proyecto_id": proyecto.id, "torre_id": torres[0].id}))
        resp = admin_client.post(self._url(proyecto, torres[0]), {
            "seccion": "franja_1",
            "porcentaje_base": "100",
            "cantidad_base_proyectada": "10.0",
            "cantidad_base_consumida": "9.8",
            "porcentaje_color": "80",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["diferencia_base"] == pytest.approx(0.2, abs=0.01)
        franja = PinturaFranja.objects.get(
            pintura_aeronautica__torre=torres[0], numero_franja=1,
        )
        assert franja.porcentaje_base == 100
        assert franja.porcentaje_color == 80

    def test_update_franja_numero_invalido(self, admin_client, proyecto, torres):
        resp = admin_client.post(self._url(proyecto, torres[0]), {
            "seccion": "franja_9",
        })
        assert resp.status_code == 400

    def test_update_seccion_invalida(self, admin_client, proyecto, torres):
        resp = admin_client.post(self._url(proyecto, torres[0]), {
            "seccion": "loquesea",
        })
        assert resp.status_code == 400

    def test_update_franja_porcentaje_fuera_de_rango(self, admin_client, proyecto, torres):
        admin_client.get(reverse("construccion:spt_pintura_torre",
                                 kwargs={"proyecto_id": proyecto.id, "torre_id": torres[0].id}))
        resp = admin_client.post(self._url(proyecto, torres[0]), {
            "seccion": "franja_2",
            "porcentaje_base": "120",
        })
        assert resp.status_code == 400
