"""Test #147 Sprint A5 — elimina sección standalone final ya redistribuida.

Verifica que el <details> "Cable de guarda + regulación final + cuadrilla"
(con tendido_guarda_ok/fecha, regulacion_ok/fecha, y los duplicados de
cuadrilla/%tendido/%facturación/observaciones) ya NO existe. Los campos que
sí sobreviven (cuadrilla, %tendido, %facturación, observaciones) siguen
presentes pero ÚNICAMENTE dentro de la sección "Tiro" (A3), sin duplicado.

tendido_guarda_ok / tendido_guarda_fecha se eliminan de la UI pero el campo
Python NO se borra de BD (se preserva el histórico) — se valida que el
modelo sigue teniendo el atributo aunque el template ya no lo renderice.
"""
import pytest
from django.urls import reverse


@pytest.fixture
def proyecto_i147_a5(db):
    from apps.construccion.models import ProyectoConstruccion
    from apps.contratos.models import Contrato

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo="TEST-I147-A5",
        nombre="Contrato test #147 A5",
        cliente="Cliente #147",
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre="Proyecto tendido #147 A5",
        estado="EJECUCION",
    )


@pytest.fixture
def torre_i147_a5(proyecto_i147_a5):
    from apps.construccion.models import TorreConstruccion

    return TorreConstruccion.objects.create(
        proyecto=proyecto_i147_a5, numero="45", tipo="D6",
    )


def _tendido_url(proyecto, torre):
    return reverse(
        "construccion:tendido_torre",
        kwargs={"proyecto_id": proyecto.id, "torre_id": torre.id},
    )


@pytest.mark.django_db
def test_no_existe_seccion_standalone_final(authenticated_client, proyecto_i147_a5, torre_i147_a5):
    url = _tendido_url(proyecto_i147_a5, torre_i147_a5)
    resp = authenticated_client.get(url)
    assert resp.status_code == 200, resp.content[:800]
    body = resp.content.decode()
    assert "Cable de guarda + regulación final + cuadrilla" not in body


@pytest.mark.django_db
def test_tendido_guarda_ya_no_se_renderiza(authenticated_client, proyecto_i147_a5, torre_i147_a5):
    """tendido_guarda_ok/fecha desaparecen de la UI (duplicaban las fechas
    izq/der de Cable de guarda que sí se conservan)."""
    url = _tendido_url(proyecto_i147_a5, torre_i147_a5)
    resp = authenticated_client.get(url)
    body = resp.content.decode()
    assert 'name="tendido_guarda_ok"' not in body
    assert 'name="tendido_guarda_fecha"' not in body
    assert 'name="regulacion_ok"' not in body
    assert 'name="regulacion_fecha"' not in body


@pytest.mark.django_db
def test_tendido_guarda_no_se_borra_de_bd(torre_i147_a5):
    """El campo Python tendido_guarda_ok/fecha sigue existiendo en el modelo
    (no se pierde el dato histórico), solo deja de mostrarse en el template."""
    from apps.construccion.models import FaseTorre

    fase = FaseTorre.objects.create(
        torre=torre_i147_a5,
        proyecto=torre_i147_a5.proyecto,
        tendido_guarda_ok=True,
    )
    fase.refresh_from_db()
    assert fase.tendido_guarda_ok is True, "el dato histórico sigue en BD"


@pytest.mark.django_db
def test_cuadrilla_pct_observaciones_solo_una_vez(authenticated_client, proyecto_i147_a5, torre_i147_a5):
    """Los campos que se redistribuyeron a la sección Tiro (A3) ya NO están
    duplicados: cada name= aparece exactamente 1 vez en el render."""
    url = _tendido_url(proyecto_i147_a5, torre_i147_a5)
    resp = authenticated_client.get(url)
    body = resp.content.decode()
    for name in ('cuadrilla_tendido', 'pct_tendido', 'pct_facturacion', 'observaciones'):
        count = body.count(f'name="{name}"')
        assert count == 1, f'{name} debe aparecer exactamente 1 vez, aparece {count}'


@pytest.mark.django_db
def test_post_sigue_guardando_cuadrilla_pct_observaciones(
    authenticated_client, proyecto_i147_a5, torre_i147_a5
):
    from apps.construccion.models import FaseTorre

    url = _tendido_url(proyecto_i147_a5, torre_i147_a5)
    data = {
        "circuito_2_aplica": "on",
        "cuadrilla_tendido": "Instelec",
        "pct_tendido": "85.71",
        "pct_facturacion": "80",
        "observaciones": "torre T-1 tras rediseño",
    }
    resp = authenticated_client.post(url, data)
    assert resp.status_code in (200, 302), resp.content[:800]

    fase = FaseTorre.objects.get(torre=torre_i147_a5)
    assert fase.cuadrilla_tendido == "Instelec"
    assert fase.pct_tendido == 85.71
    assert fase.pct_facturacion == 80
    assert fase.observaciones == "torre T-1 tras rediseño"
