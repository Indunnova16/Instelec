"""Test #147 Sprint A4 — renombrado labels + regulación dentro de circuito.

Verifica: (a) los textos visibles "OPGW" y "Fase A/B/C" ya NO aparecen (se
renombraron a "Cable de guarda" y "Fase 1/2/3"); (b) los 3 campos
regulacion_flechado_* ya no viven en una sección standalone sino dentro de
los <details> de Circuito 1 (C1 + cable de guarda) / Circuito 2.

Nota: el <details> final "Cable de guarda + regulación final + cuadrilla"
(con tendido_guarda_ok/fecha, regulacion_ok/fecha duplicados) todavía existe
en este punto de la cadena — A5 lo elimina.
"""
import pytest
from django.urls import reverse


@pytest.fixture
def proyecto_i147_a4(db):
    from apps.construccion.models import ProyectoConstruccion
    from apps.contratos.models import Contrato

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo="TEST-I147-A4",
        nombre="Contrato test #147 A4",
        cliente="Cliente #147",
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre="Proyecto tendido #147 A4",
        estado="EJECUCION",
    )


@pytest.fixture
def torre_i147_a4(proyecto_i147_a4):
    from apps.construccion.models import TorreConstruccion

    return TorreConstruccion.objects.create(
        proyecto=proyecto_i147_a4, numero="44", tipo="D6",
    )


def _tendido_url(proyecto, torre):
    return reverse(
        "construccion:tendido_torre",
        kwargs={"proyecto_id": proyecto.id, "torre_id": torre.id},
    )


@pytest.mark.django_db
def test_no_muestra_opgw_ni_fase_abc_como_texto(
    authenticated_client, proyecto_i147_a4, torre_i147_a4
):
    url = _tendido_url(proyecto_i147_a4, torre_i147_a4)
    resp = authenticated_client.get(url)
    assert resp.status_code == 200, resp.content[:800]
    body = resp.content.decode()
    assert "OPGW" not in body, "el label visible 'OPGW' debe renombrarse a 'Cable de guarda'"
    assert "Fase A" not in body
    assert "Fase B" not in body
    assert "Fase C" not in body
    assert "C2 Fase A" not in body
    assert "C2 Fase B" not in body
    assert "C2 Fase C" not in body


@pytest.mark.django_db
def test_muestra_cable_de_guarda_y_fase_123(authenticated_client, proyecto_i147_a4, torre_i147_a4):
    url = _tendido_url(proyecto_i147_a4, torre_i147_a4)
    resp = authenticated_client.get(url)
    body = resp.content.decode()
    assert "Cable de guarda" in body
    assert "Fase 1" in body
    assert "Fase 2" in body
    assert "Fase 3" in body
    assert "C2 Fase 1" in body
    assert "C2 Fase 2" in body
    assert "C2 Fase 3" in body


@pytest.mark.django_db
def test_no_existe_seccion_standalone_regulacion_por_circuito(
    authenticated_client, proyecto_i147_a4, torre_i147_a4
):
    """La sección <details> "Regulación y flechado por circuito" (standalone,
    con las 3 tarjetas Circuito 1/Circuito 2/Cable de guarda una al lado de
    otra) ya no debe existir como bloque independiente."""
    url = _tendido_url(proyecto_i147_a4, torre_i147_a4)
    resp = authenticated_client.get(url)
    body = resp.content.decode()
    assert "Regulación y flechado por circuito" not in body


@pytest.mark.django_db
def test_regulacion_c1_c2_guarda_siguen_siendo_guardables(
    authenticated_client, proyecto_i147_a4, torre_i147_a4
):
    """Los 3 campos regulacion_flechado_* (ahora dentro de Circuito 1/2)
    siguen siendo parte del form y se persisten en POST."""
    from apps.construccion.models import FaseTorre

    url = _tendido_url(proyecto_i147_a4, torre_i147_a4)
    data = {
        "circuito_2_aplica": "on",
        "regulacion_flechado_c1_ok": "on",
        "regulacion_flechado_c1_fecha": "2026-06-30",
        "regulacion_flechado_c2_ok": "on",
        "regulacion_flechado_c2_fecha": "2026-06-30",
        "regulacion_flechado_guarda_ok": "on",
        "regulacion_flechado_guarda_fecha": "2026-06-30",
    }
    resp = authenticated_client.post(url, data)
    assert resp.status_code in (200, 302), resp.content[:800]

    fase = FaseTorre.objects.get(torre=torre_i147_a4)
    assert fase.regulacion_flechado_c1_ok is True
    assert fase.regulacion_flechado_c2_ok is True
    assert fase.regulacion_flechado_guarda_ok is True
