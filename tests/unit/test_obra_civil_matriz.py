"""Tests para Obra Civil — matriz torre×columna (issue #74)."""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.contratos.models import Contrato
from apps.construccion.models import (
    ObraCivilTorre,
    ProyectoConstruccion,
    TorreConstruccion,
)


@pytest.fixture
def proyecto(db):
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo="CT-OC-74",
        nombre="Proyecto OC #74",
        cliente="Cliente OC",
        estado=Contrato.Estado.ACTIVO,
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre="Proyecto OC matriz",
        estado="EJECUCION",
        # pesos por defecto del modelo: 5/30/5/15/30/15 = 100
    )


@pytest.fixture
def torres(proyecto):
    return [
        TorreConstruccion.objects.create(
            proyecto=proyecto, numero=f"T-{i:03d}", tipo="A"
        )
        for i in range(1, 4)
    ]


@pytest.fixture
def admin_client(client, admin_user, user_password):
    client.login(username=admin_user.email, password=user_password)
    return client


# ============================================================================
# Modelo ObraCivilTorre
# ============================================================================

@pytest.mark.django_db
class TestObraCivilTorreModel:
    """El modelo persiste 6 avances 0-1 y expone avance_ponderado SUMPRODUCT."""

    def test_create_defaults_son_cero(self, proyecto, torres):
        oc = ObraCivilTorre.objects.create(proyecto=proyecto, torre=torres[0])
        assert oc.avance_cerramiento == 0
        assert oc.avance_excavacion == 0
        assert oc.avance_solado == 0
        assert oc.avance_acero == 0
        assert oc.avance_vaciado == 0
        assert oc.avance_compactacion == 0
        assert oc.avance_ponderado == 0

    def test_avance_ponderado_sumproduct_caso_perfecto(self, proyecto, torres):
        """Todos los avances al 100% → ponderado debe ser 1.0 sin importar pesos."""
        oc = ObraCivilTorre.objects.create(
            proyecto=proyecto, torre=torres[0],
            avance_cerramiento=Decimal("1.0"),
            avance_excavacion=Decimal("1.0"),
            avance_solado=Decimal("1.0"),
            avance_acero=Decimal("1.0"),
            avance_vaciado=Decimal("1.0"),
            avance_compactacion=Decimal("1.0"),
        )
        assert oc.avance_ponderado == Decimal("1")
        assert oc.avance_ponderado_pct == 100.0

    def test_avance_ponderado_sumproduct_caso_mixto(self, proyecto, torres):
        """Pesos 5/30/5/15/30/15, avances 1/1/0/0.5/0/0 → 5+30+0+7.5+0+0 = 42.5%."""
        oc = ObraCivilTorre.objects.create(
            proyecto=proyecto, torre=torres[0],
            avance_cerramiento=Decimal("1.0"),
            avance_excavacion=Decimal("1.0"),
            avance_solado=Decimal("0"),
            avance_acero=Decimal("0.5"),
            avance_vaciado=Decimal("0"),
            avance_compactacion=Decimal("0"),
        )
        # SUMPRODUCT([5,30,5,15,30,15],[1,1,0,0.5,0,0]) / 100 = 42.5 / 100 = 0.425
        assert oc.avance_ponderado_pct == pytest.approx(42.5, abs=0.05)

    def test_avance_ponderado_respeta_cambio_de_pesos_del_proyecto(self, proyecto, torres):
        """Si el cliente cambia los pesos del proyecto, el ponderado se actualiza."""
        oc = ObraCivilTorre.objects.create(
            proyecto=proyecto, torre=torres[0],
            avance_cerramiento=Decimal("1.0"),  # demás en 0
        )
        # Defaults: cerramiento=5% → ponderado=5%
        assert oc.avance_ponderado_pct == pytest.approx(5.0, abs=0.05)
        # Si subo cerramiento a 40% y otros para sumar 100, ponderado debe ser 40%.
        proyecto.peso_cerramiento_pct = 40
        proyecto.peso_excavacion_pct = 30
        proyecto.peso_solado_pct = 5
        proyecto.peso_acero_pct = 15
        proyecto.peso_vaciado_pct = 10
        proyecto.peso_compactacion_pct = 0
        proyecto.save()
        oc.refresh_from_db()
        assert oc.avance_ponderado_pct == pytest.approx(40.0, abs=0.05)

    def test_one_to_one_torre(self, proyecto, torres):
        ObraCivilTorre.objects.create(proyecto=proyecto, torre=torres[0])
        with pytest.raises(Exception):
            # OneToOne torre → no se puede crear segunda fila para la misma torre.
            ObraCivilTorre.objects.create(proyecto=proyecto, torre=torres[0])

    def test_avances_dict(self, proyecto, torres):
        oc = ObraCivilTorre.objects.create(
            proyecto=proyecto, torre=torres[0],
            avance_cerramiento=Decimal("0.5"),
        )
        d = oc.avances_dict
        assert d["cerramiento"] == Decimal("0.5")
        assert set(d.keys()) == {"cerramiento", "excavacion", "solado", "acero", "vaciado", "compactacion"}


# ============================================================================
# Vista matriz GET
# ============================================================================

@pytest.mark.django_db
class TestObraCivilMatrizView:
    """GET /construccion/<p>/obra-civil/ renderiza matriz, idempotente."""

    def test_get_responde_200(self, admin_client, proyecto, torres):
        url = reverse("construccion:obra_civil_lista", kwargs={"proyecto_id": proyecto.id})
        resp = admin_client.get(url)
        assert resp.status_code == 200

    def test_get_crea_filas_idempotente(self, admin_client, proyecto, torres):
        """La primera visita crea ObraCivilTorre para cada torre. La segunda no duplica."""
        assert ObraCivilTorre.objects.filter(proyecto=proyecto).count() == 0
        url = reverse("construccion:obra_civil_lista", kwargs={"proyecto_id": proyecto.id})
        admin_client.get(url)
        assert ObraCivilTorre.objects.filter(proyecto=proyecto).count() == 3
        admin_client.get(url)
        assert ObraCivilTorre.objects.filter(proyecto=proyecto).count() == 3

    def test_get_contexto_incluye_pesos_y_totales(self, admin_client, proyecto, torres):
        url = reverse("construccion:obra_civil_lista", kwargs={"proyecto_id": proyecto.id})
        resp = admin_client.get(url)
        ctx = resp.context
        assert ctx["pesos"]["cerramiento"] == 5
        assert ctx["pesos"]["excavacion"] == 30
        assert ctx["suma_pesos"] == 100
        assert ctx["suma_pesos_ok"] is True
        assert len(ctx["filas"]) == 3
        # Sin avances aún → totales = 0
        assert ctx["totales"]["cerramiento"] == 0
        assert ctx["avance_general"] == 0


# ============================================================================
# AJAX endpoints
# ============================================================================

@pytest.mark.django_db
class TestPesosUpdate:
    """POST /obra-civil/pesos/ valida suma=100 y persiste."""

    def test_post_pesos_validos_guarda(self, admin_client, proyecto):
        url = reverse("construccion:obra_civil_pesos_update", kwargs={"proyecto_id": proyecto.id})
        resp = admin_client.post(url, {
            "cerramiento": "40", "excavacion": "30", "solado": "5",
            "acero": "15", "vaciado": "10", "compactacion": "0",
        })
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        proyecto.refresh_from_db()
        assert proyecto.peso_cerramiento_pct == 40
        assert proyecto.peso_compactacion_pct == 0

    def test_post_pesos_no_suman_100_rechaza(self, admin_client, proyecto):
        url = reverse("construccion:obra_civil_pesos_update", kwargs={"proyecto_id": proyecto.id})
        resp = admin_client.post(url, {
            "cerramiento": "50", "excavacion": "30", "solado": "5",
            "acero": "15", "vaciado": "10", "compactacion": "0",  # suma 110
        })
        assert resp.status_code == 400
        assert "100" in resp.json()["error"]

    def test_post_pesos_fuera_de_rango_rechaza(self, admin_client, proyecto):
        url = reverse("construccion:obra_civil_pesos_update", kwargs={"proyecto_id": proyecto.id})
        resp = admin_client.post(url, {
            "cerramiento": "150", "excavacion": "0", "solado": "0",
            "acero": "0", "vaciado": "0", "compactacion": "0",
        })
        assert resp.status_code == 400

    def test_post_pesos_no_enteros_rechaza(self, admin_client, proyecto):
        url = reverse("construccion:obra_civil_pesos_update", kwargs={"proyecto_id": proyecto.id})
        resp = admin_client.post(url, {
            "cerramiento": "abc",
        })
        assert resp.status_code == 400


@pytest.mark.django_db
class TestAvanceUpdate:
    """POST /obra-civil/torres/<id>/avance/ actualiza una celda."""

    def test_post_avance_valido_persiste(self, admin_client, proyecto, torres):
        url = reverse("construccion:obra_civil_avance_update",
                      kwargs={"proyecto_id": proyecto.id, "torre_id": torres[0].id})
        resp = admin_client.post(url, {"columna": "cerramiento", "valor": "0.8"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["avance_ponderado_pct"] == pytest.approx(4.0, abs=0.05)  # 0.8 × 5% = 4%
        oc = ObraCivilTorre.objects.get(proyecto=proyecto, torre=torres[0])
        assert oc.avance_cerramiento == Decimal("0.8")

    def test_post_columna_invalida_rechaza(self, admin_client, proyecto, torres):
        url = reverse("construccion:obra_civil_avance_update",
                      kwargs={"proyecto_id": proyecto.id, "torre_id": torres[0].id})
        resp = admin_client.post(url, {"columna": "fantasma", "valor": "0.5"})
        assert resp.status_code == 400

    def test_post_valor_fuera_de_rango_rechaza(self, admin_client, proyecto, torres):
        url = reverse("construccion:obra_civil_avance_update",
                      kwargs={"proyecto_id": proyecto.id, "torre_id": torres[0].id})
        resp = admin_client.post(url, {"columna": "cerramiento", "valor": "1.5"})
        assert resp.status_code == 400

    def test_post_valor_negativo_rechaza(self, admin_client, proyecto, torres):
        url = reverse("construccion:obra_civil_avance_update",
                      kwargs={"proyecto_id": proyecto.id, "torre_id": torres[0].id})
        resp = admin_client.post(url, {"columna": "cerramiento", "valor": "-0.1"})
        assert resp.status_code == 400

    def test_post_torre_de_otro_proyecto_404(self, admin_client, proyecto, torres):
        # Crear otro proyecto y torre.
        contrato2 = Contrato.objects.create(
            unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
            codigo="CT-OTRO", nombre="Otro", cliente="X",
            estado=Contrato.Estado.ACTIVO,
        )
        proyecto2 = ProyectoConstruccion.objects.create(
            contrato=contrato2, nombre="Otro", estado="EJECUCION",
        )
        torre_otro = TorreConstruccion.objects.create(
            proyecto=proyecto2, numero="X-001", tipo="A",
        )
        url = reverse("construccion:obra_civil_avance_update",
                      kwargs={"proyecto_id": proyecto.id, "torre_id": torre_otro.id})
        resp = admin_client.post(url, {"columna": "cerramiento", "valor": "0.5"})
        assert resp.status_code == 404

    def test_post_get_or_create_torre_sin_oc(self, admin_client, proyecto, torres):
        """Si la torre no tiene ObraCivilTorre todavía, el POST debe crearla."""
        assert not ObraCivilTorre.objects.filter(torre=torres[0]).exists()
        url = reverse("construccion:obra_civil_avance_update",
                      kwargs={"proyecto_id": proyecto.id, "torre_id": torres[0].id})
        resp = admin_client.post(url, {"columna": "excavacion", "valor": "0.5"})
        assert resp.status_code == 200
        assert ObraCivilTorre.objects.filter(torre=torres[0]).exists()
