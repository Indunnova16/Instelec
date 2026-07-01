"""Test #147 Sprint A3 — sección "Tiro" única en tendido_torre.html.

Verifica que el formset dinámico de tiros (botón "+ Agregar tiro" y el
bloque Alpine tirosManila) desapareció del template, y que la nueva sección
"Tiro" renderiza el campo N° de tiro como input editable + checks (incl.
FT-931 nuevo).

Nota: en este punto de la cadena (tras A3, antes de A4/A5) el template
todavía tiene las secciones "Circuito 1 + OPGW", "Regulación y flechado por
circuito" (standalone) y "Cable de guarda + regulación final" sin tocar —
esas las cubre A4/A5. Este archivo solo valida el alcance de A3.
"""
import pytest
from django.urls import reverse


@pytest.fixture
def proyecto_i147_a3(db):
    from apps.construccion.models import ProyectoConstruccion
    from apps.contratos.models import Contrato

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo="TEST-I147-A3",
        nombre="Contrato test #147 A3",
        cliente="Cliente #147",
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre="Proyecto tendido #147 A3",
        estado="EJECUCION",
    )


@pytest.fixture
def torre_i147_a3(proyecto_i147_a3):
    from apps.construccion.models import TorreConstruccion

    return TorreConstruccion.objects.create(
        proyecto=proyecto_i147_a3, numero="43", tipo="D6",
    )


def _tendido_url(proyecto, torre):
    return reverse(
        "construccion:tendido_torre",
        kwargs={"proyecto_id": proyecto.id, "torre_id": torre.id},
    )


@pytest.mark.django_db
def test_no_contiene_boton_agregar_tiro(authenticated_client, proyecto_i147_a3, torre_i147_a3):
    url = _tendido_url(proyecto_i147_a3, torre_i147_a3)
    resp = authenticated_client.get(url)
    assert resp.status_code == 200, resp.content[:800]
    body = resp.content.decode()
    assert "data-add-tiro" not in body, "el botón '+ Agregar tiro' debe desaparecer"
    assert "Agregar tiro" not in body
    assert "tirosManila" not in body, "el bloque Alpine del formset dinámico debe desaparecer"
    assert "agregarTiro" not in body
    assert "quitarFila" not in body


@pytest.mark.django_db
def test_contiene_input_numero_tiro(authenticated_client, proyecto_i147_a3, torre_i147_a3):
    url = _tendido_url(proyecto_i147_a3, torre_i147_a3)
    resp = authenticated_client.get(url)
    assert resp.status_code == 200, resp.content[:800]
    body = resp.content.decode()
    assert 'name="numero_tiro"' in body
    assert 'type="number"' in body


@pytest.mark.django_db
def test_seccion_tiro_incluye_checks_y_ft931(authenticated_client, proyecto_i147_a3, torre_i147_a3):
    url = _tendido_url(proyecto_i147_a3, torre_i147_a3)
    resp = authenticated_client.get(url)
    body = resp.content.decode()
    for needle in (
        'name="vestida_torres_ok"',
        'name="riega_manila_ok"',
        'name="riega_guaya_ok"',
        'name="ft046_ok"',
        'name="ft047_ok"',
        'name="ft931_ok"',
        'name="ft932_ok"',
        'name="ft918_ok"',
        'name="grapado_ok"',
        'name="accesorios_ok"',
        'name="placas_senalizacion_ok"',
        'name="cuadrilla_tendido"',
        'name="pct_tendido"',
        'name="pct_facturacion"',
        'name="observaciones"',
    ):
        assert needle in body, f"falta {needle} en la sección Tiro"


@pytest.mark.django_db
def test_post_guarda_numero_tiro_y_ft931_sin_formset(
    authenticated_client, proyecto_i147_a3, torre_i147_a3
):
    from apps.construccion.models import FaseTorre

    url = _tendido_url(proyecto_i147_a3, torre_i147_a3)
    data = {
        "circuito_2_aplica": "on",
        "numero_tiro": "7",
        "ft931_ok": "on",
    }
    resp = authenticated_client.post(url, data)
    assert resp.status_code in (200, 302), resp.content[:800]

    fase = FaseTorre.objects.get(torre=torre_i147_a3)
    assert fase.numero_tiro == 7
    assert fase.ft931_ok is True
