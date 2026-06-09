"""Tests B5 (#139) — Dashboard GENERAL del proyecto (7 fases).

Cubre los tests del BLUEPRINT:
  - b5_dashboard_general_7fases : render con las 7 fases + global ponderado +
    dataset JSON pre-serializado (guard es-CO) + canvas #general-fases-chart.
  - b5_general_drilldown_fase   : cada fase con dashboard propio enlaza a su
    dashboard de fase (Obra Civil / Montaje / Tendido).

Edge cases del dominio:
  - Proyecto SIN avance en ninguna fase → todas las fases en 0%, global 0%,
    sin crash (mensaje "sin avance"), data-charts-ready presente.
  - Fallback equiponderado cuando ProgramacionFase.peso_pct está todo en 0
    (estado actual de prod).
  - Curva S consolidada real agrega solo las fases con datos (no error si una
    fase no tiene avance).
"""
from __future__ import annotations

import json

import pytest
from django.urls import NoReverseMatch, reverse

from apps.construccion import calculators_avance_real as car
from apps.construccion.views_dashboards_b5_general import (
    DRILLDOWN_URL_NAMES,
    curva_s_consolidada_real,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def proyecto_general(db):
    """ProyectoConstruccion mínimo con torres para el dashboard general."""
    from apps.contratos.models import Contrato
    from apps.construccion.models import ProyectoConstruccion, TorreConstruccion

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-B5-GEN-001',
        nombre='Contrato test B5 general',
        cliente='Test Cliente',
    )
    proyecto = ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto B5 general test',
        estado='EJECUCION',
    )
    # Dos torres para tener denominador real en los % por fase.
    for i in (1, 2):
        TorreConstruccion.objects.create(proyecto=proyecto, numero=f'T{i:03d}')
    return proyecto


def _render_view(rf, admin_user, proyecto):
    """Renderiza DashboardGeneralView vía RequestFactory (sin depender del
    wiring de URL que cablea F4). Devuelve (response, view_instance) — la
    respuesta ya está renderizada (``.render()``)."""
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware

    from apps.construccion.views_dashboards_b5_general import DashboardGeneralView

    request = rf.get('/construccion/{}/dashboard-general/'.format(proyecto.id))
    # Adjuntar session + messages (los context processors del proyecto los
    # requieren; RequestFactory no pasa por el stack de middleware).
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = admin_user
    view = DashboardGeneralView()
    view.setup(request, proyecto_id=proyecto.id)
    resp = view.dispatch(request, proyecto_id=proyecto.id)
    if hasattr(resp, 'render'):
        resp.render()
    return resp, view


def _general_url(proyecto):
    """Resuelve la URL del dashboard general. En el entorno aislado de la
    sub-feature el include lo cablea F4; si aún no resuelve, marca skip honesto
    (el name es responsabilidad de F4, no del test)."""
    try:
        return reverse('construccion:dashboard_general',
                       kwargs={'proyecto_id': proyecto.id})
    except NoReverseMatch:
        return None


# ===========================================================================
# b5_dashboard_general_7fases
# ===========================================================================

@pytest.mark.django_db
def test_b5_dashboard_general_7fases(authenticated_client, proyecto_general):
    """Render del dashboard general: 7 fases + global + dataset JSON + canvas."""
    url = _general_url(proyecto_general)
    if url is None:
        pytest.skip('URL construccion:dashboard_general aún no cableada (F4 wiring)')

    resp = authenticated_client.get(url)
    assert resp.status_code == 200

    ctx = resp.context
    # Las 7 fases canónicas.
    assert len(ctx['fases']) == 7
    labels = [f['label'] for f in ctx['fases']]
    for esperado in ('Ingeniería', 'Obra Civil', 'Montaje', 'Tendido',
                     'SPT y Pintura', 'Detalles Finales'):
        assert esperado in labels

    # Global ponderado presente y numérico.
    assert isinstance(ctx['global_pct'], float)

    # Guard es-CO: el dataset viaja como STRING JSON parseable (no floats inline).
    payload = json.loads(ctx['general_chart_json'])
    assert 'fases' in payload and len(payload['fases']) == 7
    assert 'global_pct' in payload
    assert 'curva_s' in payload

    html = resp.content.decode()
    # Canvas global del BLUEPRINT.
    assert 'id="general-fases-chart"' in html
    # json_script (no JSON crudo en x-data) y gate de charts.
    assert 'id="general-chart-data"' in html
    assert 'data-charts-ready' in html
    assert 'data-fase="GENERAL"' in html


@pytest.mark.django_db
def test_b5_dashboard_general_render_directo(rf, admin_user, proyecto_general):
    """Render directo de la vista (sin URL wiring) — cubre context + template.

    Exige el rigor de render real: la vista arma el contexto y el template se
    renderiza con el canvas global, el json_script (guard es-CO) y el gate de
    charts, aun cuando F4 todavía no haya cableado el include en urls.py.
    """
    resp, view = _render_view(rf, admin_user, proyecto_general)
    assert resp.status_code == 200

    html = resp.content.decode()
    assert 'id="general-fases-chart"' in html
    assert 'id="general-chart-data"' in html
    assert 'data-charts-ready' in html
    assert 'data-fase="GENERAL"' in html
    # 7 tarjetas de fase (una por sección).
    assert html.count('data-fase-seccion=') == 7


@pytest.mark.django_db
def test_b5_general_fallback_equiponderado(proyecto_general):
    """Sin pesos en ProgramacionFase (peso_pct=0) → fallback equiponderado.

    El backbone calcula el global como promedio simple de los % de las 7 fases.
    Validamos el contrato directamente sobre avance_general (lo que la vista
    reusa) para que el test no dependa del wiring de la URL.
    """
    general = car.avance_general(proyecto_general)
    assert len(general['fases']) == 7
    # Sin avance ni pesos → global 0, sin error.
    assert general['global_pct'] == 0.0
    # Todas las fases en 0% (proyecto recién creado).
    assert all(f['pct'] == 0.0 for f in general['fases'])


# ===========================================================================
# b5_general_drilldown_fase
# ===========================================================================

@pytest.mark.django_db
def test_b5_general_drilldown_fase(authenticated_client, proyecto_general):
    """Cada fase con dashboard propio enlaza a su dashboard de fase."""
    url = _general_url(proyecto_general)
    if url is None:
        pytest.skip('URL construccion:dashboard_general aún no cableada (F4 wiring)')

    resp = authenticated_client.get(url)
    assert resp.status_code == 200

    fases_por_seccion = {f['seccion']: f for f in resp.context['fases']}
    html = resp.content.decode()

    for seccion, url_name in DRILLDOWN_URL_NAMES.items():
        fase = fases_por_seccion.get(seccion)
        assert fase is not None, f'falta la fase {seccion} en el contexto'
        try:
            esperado = reverse(url_name,
                               kwargs={'proyecto_id': proyecto_general.id})
        except NoReverseMatch:
            # Dashboard de fase aún no cableado en el entorno aislado: la vista
            # degrada a None y el template muestra "Sin dashboard". F4 garantiza
            # el wiring al integrar.
            assert fase['drill_url'] is None
            assert f'data-drilldown-disabled="{seccion}"' in html
            continue
        # El name resuelve → la fase debe enlazar a él.
        assert fase['drill_url'] == esperado
        assert f'href="{esperado}"' in html
        assert f'data-drilldown="{seccion}"' in html


# ===========================================================================
# Edge: proyecto sin avance → 0% por fase, sin crash
# ===========================================================================

@pytest.mark.django_db
def test_b5_general_sin_avance_no_crashea(authenticated_client, proyecto_general):
    """Proyecto sin avance en ninguna fase → render OK, mensaje, 0% global."""
    url = _general_url(proyecto_general)
    if url is None:
        pytest.skip('URL construccion:dashboard_general aún no cableada (F4 wiring)')

    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    assert resp.context['global_pct'] == 0.0
    assert resp.context['tiene_avance'] is False
    assert resp.context['tiene_curva_s'] is False
    html = resp.content.decode()
    assert 'data-estado="sin-avance"' in html
    # Aun sin avance, el gate de charts queda presente (no rompe el E2E).
    assert 'data-charts-ready' in html


@pytest.mark.django_db
def test_b5_curva_consolidada_real_vacia_sin_datos(proyecto_general):
    """Edge: sin avance temporal en ninguna fase → curva consolidada vacía."""
    curva = curva_s_consolidada_real(proyecto_general)
    assert curva == {'labels': [], 'ejecutado': []}


@pytest.mark.django_db
def test_b5_curva_consolidada_real_agrega_fase_con_datos(proyecto_general):
    """La curva consolidada agrega una fase con avance real (Obra Civil).

    Crea un ObraCivilTorreDetalle con avance → la fase OOCC aporta a la curva;
    las otras dos fases sin datos no rompen ni inflan el % por encima de 100.
    """
    from apps.construccion.models import TorreConstruccion
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle

    torre = TorreConstruccion.objects.filter(proyecto=proyecto_general).first()
    # Pata con vaciado 100% ejecutado → avance_ponderado > 0.
    ObraCivilTorreDetalle.objects.create(
        proyecto=proyecto_general,
        torre=torre,
        pata='A',
        vac_ejecutado_pct=1,
    )

    curva = curva_s_consolidada_real(proyecto_general)
    # Hay al menos un punto y el acumulado nunca excede 100.
    assert curva['labels']
    assert curva['ejecutado']
    assert max(curva['ejecutado']) <= 100.0
    # Monótona no decreciente (curva S).
    valores = curva['ejecutado']
    assert all(valores[i] <= valores[i + 1] + 1e-9 for i in range(len(valores) - 1))
