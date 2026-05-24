"""Tests para CANT TENDIDO matriz (issue #79)."""

import pytest
from django.urls import reverse

from apps.contratos.models import Contrato
from apps.construccion.models import (
    ProyectoConstruccion,
    TendidoTorre,
    TorreConstruccion,
)


@pytest.fixture
def proyecto(db):
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo="CT-TEND-79", nombre="Tendido", cliente="C",
        estado=Contrato.Estado.ACTIVO,
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato, nombre="Tendido", estado="EJECUCION",
    )


@pytest.fixture
def torres(proyecto):
    return [
        TorreConstruccion.objects.create(proyecto=proyecto, numero="E1", tipo="A"),
        TorreConstruccion.objects.create(proyecto=proyecto, numero="E2", tipo="B"),
    ]


@pytest.fixture
def admin_client(client, admin_user, user_password):
    client.login(username=admin_user.email, password=user_password)
    return client


@pytest.mark.django_db
class TestTendidoTorreModel:
    def test_defaults(self, proyecto, torres):
        t = TendidoTorre.objects.create(proyecto=proyecto, torre=torres[0])
        assert t.avance_conductor == 0
        assert t.avance_fibra == 0
        assert t.funcion == "Suspensión"  # tipo='A'

    def test_funcion_retencion(self, proyecto, torres):
        t = TendidoTorre.objects.create(proyecto=proyecto, torre=torres[1])
        assert t.funcion == "Retención"  # tipo='B' (no A ni A especial)

    def test_sumproduct_conductor_caso_issue(self, proyecto, torres):
        """Issue #79 ejemplo: F=1,G=1,H=1,I=1,J=1,K=0 con pesos 10/30/30/10/10/10
        → 0.1+0.3+0.3+0.1+0.1+0 = 0.9 (90%)."""
        t = TendidoTorre.objects.create(
            proyecto=proyecto, torre=torres[0],
            riega_manila_conductor=True, riega_guaya_conductor=True,
            tendido_conductor=True, grapado_amarre_conductor=True,
            accesorios_puentes=True, balizas_desviadores=False,
        )
        assert t.avance_conductor_pct == pytest.approx(90.0, abs=0.05)

    def test_sumproduct_fibra_caso_issue(self, proyecto, torres):
        """Pesos fibra 10/20/40/20/10. Si solo tendido_opgw=True → 40%."""
        t = TendidoTorre.objects.create(
            proyecto=proyecto, torre=torres[0],
            tendido_opgw=True,
        )
        assert t.avance_fibra_pct == pytest.approx(40.0, abs=0.05)

    def test_sumproduct_fibra_completa(self, proyecto, torres):
        t = TendidoTorre.objects.create(
            proyecto=proyecto, torre=torres[0],
            riega_manila_fibra=True, riega_guaya_opgw=True,
            tendido_opgw=True, grapado_amarre_fibra=True, empalmes_opgw=True,
        )
        assert t.avance_fibra_pct == pytest.approx(100.0, abs=0.05)


@pytest.mark.django_db
class TestTendidoMatrizView:
    def test_get_200(self, admin_client, proyecto, torres):
        url = reverse("construccion:tendido_lista", kwargs={"proyecto_id": proyecto.id})
        resp = admin_client.get(url)
        assert resp.status_code == 200

    def test_crea_filas_idempotente(self, admin_client, proyecto, torres):
        url = reverse("construccion:tendido_lista", kwargs={"proyecto_id": proyecto.id})
        admin_client.get(url)
        assert TendidoTorre.objects.filter(proyecto=proyecto).count() == 2
        admin_client.get(url)
        assert TendidoTorre.objects.filter(proyecto=proyecto).count() == 2

    def test_pesos_default(self, admin_client, proyecto, torres):
        url = reverse("construccion:tendido_lista", kwargs={"proyecto_id": proyecto.id})
        resp = admin_client.get(url)
        ctx = resp.context
        assert ctx["pesos_conductor"]["riega_guaya_conductor"] == 30
        assert ctx["pesos_fibra"]["tendido_opgw"] == 40
        assert ctx["suma_conductor"] == 100
        assert ctx["suma_fibra"] == 100


@pytest.mark.django_db
class TestTendidoPesosUpdate:
    def _url(self, p):
        return reverse("construccion:tendido_pesos_update", kwargs={"proyecto_id": p.id})

    def test_pesos_conductor_validos(self, admin_client, proyecto):
        resp = admin_client.post(self._url(proyecto), {
            "seccion": "conductor",
            "riega_manila": "15", "riega_guaya": "25", "tendido": "30",
            "grapado": "10", "accesorios": "10", "balizas": "10",
        })
        assert resp.status_code == 200
        proyecto.refresh_from_db()
        assert proyecto.peso_tend_riega_manila_pct == 15

    def test_pesos_conductor_no_suman_100(self, admin_client, proyecto):
        resp = admin_client.post(self._url(proyecto), {
            "seccion": "conductor",
            "riega_manila": "20", "riega_guaya": "30", "tendido": "30",
            "grapado": "10", "accesorios": "10", "balizas": "10",  # suma 110
        })
        assert resp.status_code == 400

    def test_pesos_fibra_validos(self, admin_client, proyecto):
        resp = admin_client.post(self._url(proyecto), {
            "seccion": "fibra",
            "riega_manila_fibra": "5", "riega_guaya_opgw": "25",
            "tendido_opgw": "40", "grapado_fibra": "20", "empalmes_opgw": "10",
        })
        assert resp.status_code == 200

    def test_seccion_invalida(self, admin_client, proyecto):
        resp = admin_client.post(self._url(proyecto), {"seccion": "xxx"})
        assert resp.status_code == 400


@pytest.mark.django_db
class TestTendidoToggle:
    def _url(self, p, t):
        return reverse("construccion:tendido_toggle", kwargs={"proyecto_id": p.id, "torre_id": t.id})

    def test_toggle_actividad(self, admin_client, proyecto, torres):
        resp = admin_client.post(self._url(proyecto, torres[0]), {
            "campo": "tendido_conductor", "valor": "1",
        })
        assert resp.status_code == 200
        data = resp.json()
        # tendido pesa 30% → 30%
        assert data["avance_conductor_pct"] == pytest.approx(30.0, abs=0.05)
        t = TendidoTorre.objects.get(torre=torres[0])
        assert t.tendido_conductor is True

    def test_toggle_campo_invalido(self, admin_client, proyecto, torres):
        resp = admin_client.post(self._url(proyecto, torres[0]), {
            "campo": "fantasma", "valor": "1",
        })
        assert resp.status_code == 400


@pytest.mark.django_db
class TestTendidoRealizo:
    def _url(self, p, t):
        return reverse("construccion:tendido_realizo_update", kwargs={"proyecto_id": p.id, "torre_id": t.id})

    def test_realizo_conductor(self, admin_client, proyecto, torres):
        resp = admin_client.post(self._url(proyecto, torres[0]), {
            "seccion": "conductor", "valor": "Cuadrilla Cruz",
        })
        assert resp.status_code == 200
        t = TendidoTorre.objects.get(torre=torres[0])
        assert t.realizo_conductor == "Cuadrilla Cruz"

    def test_realizo_seccion_invalida(self, admin_client, proyecto, torres):
        resp = admin_client.post(self._url(proyecto, torres[0]), {"seccion": "xxx"})
        assert resp.status_code == 400
