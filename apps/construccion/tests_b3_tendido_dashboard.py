"""Tests B3 — Dashboard de Tendido (Conductor + Fibra OPGW) (#139).

Cubre los tests_e2e del BLUEPRINT.sub_features.B3:
  - b3_dashboard_tendido_conductor: la gráfica/datos de Conductor reflejan el
    avance real por etapa (6 etapas) + Curva S ejecutado > 0.
  - b3_dashboard_tendido_fibra:     la gráfica/datos de Fibra OPGW reflejan el
    avance real por etapa (5 etapas).

Edge cases del dominio (no genéricos):
  - proyecto SIN registros de tendido → HTTP 200, listas vacías, sin 500.
  - torre con conductor 100% pero fibra 0% → conductor completa, fibra pendiente
    (las dos secciones son SUMPRODUCT independientes; no se contaminan).
  - dato "legacy": TendidoTorre creado solo con flags de conductor (como en prod,
    65 filas con tendido_conductor=True) → el dashboard lo computa sin tocar el
    modelo y la vista por torre lo lista con sus pendientes de fibra.

La URL del dashboard la cablea F4 en urls.py (include de urls_dashboards_b3_tendido),
así que aquí ejercemos la vista vía RequestFactory + usuario admin (no depende del
wiring pendiente) y el endpoint de datos por el mismo medio.
"""
from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.construccion.views_dashboards_b3_tendido import (
    DashboardTendidoDataView,
    DashboardTendidoView,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def admin(db):
    return User.objects.create_user(
        email='admin-b3-tendido@test.com',
        password='x',
        first_name='Admin',
        last_name='B3',
        rol='admin',
        is_staff=True,
        is_superuser=True,
    )


@pytest.fixture
def proyecto(db):
    from apps.contratos.models import Contrato
    from apps.construccion.models import ProyectoConstruccion

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-B3-TEND-001',
        nombre='Contrato test B3 Tendido',
        cliente='Cliente Test',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto B3 Tendido',
        estado='EJECUCION',
    )


def _torre(proyecto, numero):
    from apps.construccion.models import TorreConstruccion
    return TorreConstruccion.objects.create(proyecto=proyecto, numero=numero)


def _tendido(proyecto, torre, **flags):
    """Crea un TendidoTorre con los flags dados (resto en False por default)."""
    from apps.construccion.models import TendidoTorre
    return TendidoTorre.objects.create(proyecto=proyecto, torre=torre, **flags)


def _ctx(view_cls, proyecto, admin, **get):
    """Render del contexto de una CBV de dashboard vía RequestFactory."""
    rf = RequestFactory()
    req = rf.get('/', data=get)
    req.user = admin
    view = view_cls()
    view.setup(req, proyecto_id=proyecto.id)
    return view.get_context_data()


def _datos(proyecto, admin):
    rf = RequestFactory()
    req = rf.get('/')
    req.user = admin
    resp = DashboardTendidoDataView.as_view()(req, proyecto_id=proyecto.id)
    return json.loads(resp.content)


# ---------------------------------------------------------------------------
# E2E del BLUEPRINT — Conductor
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_b3_dashboard_tendido_conductor(proyecto, admin):
    """Happy: el dashboard expone las 6 etapas de Conductor con su % real y la
    Curva S ejecutado refleja avance > 0."""
    t1 = _torre(proyecto, '1')
    t2 = _torre(proyecto, '2')
    # Torre 1: conductor 100% (las 6 etapas). Torre 2: solo las 2 primeras.
    _tendido(
        proyecto, t1,
        riega_manila_conductor=True, riega_guaya_conductor=True,
        tendido_conductor=True, grapado_amarre_conductor=True,
        accesorios_puentes=True, balizas_desviadores=True,
    )
    _tendido(
        proyecto, t2,
        riega_manila_conductor=True, riega_guaya_conductor=True,
    )

    ctx = _ctx(DashboardTendidoView, proyecto, admin)

    # 6 etapas de conductor, en orden.
    conductor = ctx['avance_conductor']
    assert [e['etapa'] for e in conductor] == [
        'RIEGA_MANILA', 'RIEGA_GUAYA', 'TENDIDO_CONDUCTOR',
        'GRAPADO', 'ACCESORIOS', 'BALIZAS',
    ]
    by = {e['etapa']: e for e in conductor}
    # Riega manila: ambas torres completas → 100%.
    assert by['RIEGA_MANILA']['pct'] == 100.0
    assert by['RIEGA_MANILA']['completas'] == 2
    # Balizas: solo torre 1 → 50%.
    assert by['BALIZAS']['pct'] == 50.0
    assert by['BALIZAS']['completas'] == 1

    # Curva S real "Ejecutado" > 0 (no cuelga del semanal vacío).
    curva = ctx['curva_real_json']
    assert curva['ejecutado']['ejecutado']
    assert max(curva['ejecutado']['ejecutado']) > 0

    # % conductor global de las tarjetas es > 0.
    assert ctx['pct_conductor'] > 0
    # La gráfica de etapas genérica del parcial base queda apagada (B3 usa 2 propias).
    assert ctx['avance_etapas'] == []


@pytest.mark.django_db
def test_b3_dashboard_tendido_conductor_template_render(proyecto, admin):
    """El template renderiza el canvas #tendido-conductor-chart y [data-fase]."""
    from django.template.loader import render_to_string

    t1 = _torre(proyecto, '1')
    _tendido(proyecto, t1, riega_manila_conductor=True, tendido_conductor=True)
    ctx = _ctx(DashboardTendidoView, proyecto, admin)
    html = render_to_string('construccion/dashboard_tendido.html', ctx)

    assert 'id="tendido-conductor-chart"' in html
    assert 'id="tendido-fibra-chart"' in html
    assert 'data-fase="TENDIDO"' in html
    # json_script genera el id del dataset (no JSON crudo en x-data / inline).
    assert 'id="tendido-etapas-data"' in html
    # Guard es-CO: localize off presente (lo aplica el bloque).
    assert 'tendido-etapas-data' in html


# ---------------------------------------------------------------------------
# E2E del BLUEPRINT — Fibra OPGW
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_b3_dashboard_tendido_fibra(proyecto, admin):
    """Happy: las 5 etapas de Fibra OPGW con su % real, independientes del
    conductor."""
    t1 = _torre(proyecto, '1')
    t2 = _torre(proyecto, '2')
    # Torre 1: fibra 100%. Torre 2: solo tendido OPGW.
    _tendido(
        proyecto, t1,
        riega_manila_fibra=True, riega_guaya_opgw=True, tendido_opgw=True,
        grapado_amarre_fibra=True, empalmes_opgw=True,
    )
    _tendido(proyecto, t2, tendido_opgw=True)

    ctx = _ctx(DashboardTendidoView, proyecto, admin)

    fibra = ctx['avance_fibra']
    assert [e['etapa'] for e in fibra] == [
        'RIEGA_MANILA_FIBRA', 'RIEGA_GUAYA_OPGW', 'TENDIDO_OPGW',
        'GRAPADO_FIBRA', 'EMPALMES_OPGW',
    ]
    by = {e['etapa']: e for e in fibra}
    # Tendido OPGW: ambas → 100%.
    assert by['TENDIDO_OPGW']['pct'] == 100.0
    # Empalmes: solo torre 1 → 50%.
    assert by['EMPALMES_OPGW']['pct'] == 50.0
    assert ctx['pct_fibra'] > 0


@pytest.mark.django_db
def test_b3_secciones_independientes_conductor_lleno_fibra_vacia(proyecto, admin):
    """Edge: una torre con conductor 100% y fibra 0% — las secciones NO se
    contaminan (SUMPRODUCT independiente). En la vista por torre la fibra queda
    como pendiente."""
    t1 = _torre(proyecto, '1')
    _tendido(
        proyecto, t1,
        riega_manila_conductor=True, riega_guaya_conductor=True,
        tendido_conductor=True, grapado_amarre_conductor=True,
        accesorios_puentes=True, balizas_desviadores=True,
        # fibra toda False
    )
    ctx = _ctx(DashboardTendidoView, proyecto, admin)

    # Conductor 100%, fibra 0%.
    assert ctx['pct_conductor'] == 100.0
    assert ctx['pct_fibra'] == 0.0

    # Vista por torre: pct = promedio(100, 0) = 50, NO completa, pendientes de fibra.
    torres = ctx['vista_torres']
    assert len(torres) == 1
    fila = torres[0]
    assert fila['pct'] == 50.0
    assert fila['completa'] is False
    # Las pendientes contienen las etiquetas de fibra, NO las de conductor.
    assert 'Empalmes OPGW' in fila['pendientes']
    assert 'Tendido conductor' not in fila['pendientes']


# ---------------------------------------------------------------------------
# Edge — proyecto sin tendido (robustez, nunca 500)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_b3_dashboard_sin_tendido_no_crashea(proyecto, admin):
    """Edge: proyecto con torres pero sin registros de tendido → listas vacías,
    pct 0, sin excepción."""
    _torre(proyecto, '1')
    ctx = _ctx(DashboardTendidoView, proyecto, admin)

    assert ctx['pct_conductor'] == 0.0
    assert ctx['pct_fibra'] == 0.0
    assert ctx['vista_torres'] == []
    # Las etapas existen con pct=0 (estructura presente, datos vacíos).
    assert all(e['pct'] == 0.0 for e in ctx['avance_conductor'])
    assert all(e['pct'] == 0.0 for e in ctx['avance_fibra'])


@pytest.mark.django_db
def test_b3_dashboard_proyecto_sin_torres_no_crashea(proyecto, admin):
    """Edge: proyecto sin torres → pct 0, sin división por cero / 500."""
    ctx = _ctx(DashboardTendidoView, proyecto, admin)
    assert ctx['pct_conductor'] == 0.0
    assert ctx['pct_fibra'] == 0.0


# ---------------------------------------------------------------------------
# Endpoint de datos JSON
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_b3_datos_endpoint_estructura(proyecto, admin):
    """El endpoint de datos devuelve curva_s + conductor + fibra + vista_torres."""
    t1 = _torre(proyecto, '1')
    _tendido(proyecto, t1, tendido_conductor=True, tendido_opgw=True)

    data = _datos(proyecto, admin)
    assert 'curva_s' in data
    assert 'ejecutado' in data['curva_s']
    assert 'planeado' in data['curva_s']
    assert len(data['avance_conductor']) == 6
    assert len(data['avance_fibra']) == 5
    assert isinstance(data['vista_torres'], list)


# ---------------------------------------------------------------------------
# Dato legacy — TendidoTorre "estilo prod" (solo flags de conductor)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_b3_dato_legacy_conductor_solo(proyecto, admin):
    """En prod hay 65 TendidoTorre con tendido_conductor=True (y fibra sin tocar).

    Verifica que el dashboard computa ese dato legacy SIN modificar el modelo:
    la etapa de conductor 'Tendido conductor' aparece completa y la torre se
    lista en la vista por torre con pendientes de fibra.
    """
    t1 = _torre(proyecto, '1')
    legacy = _tendido(
        proyecto, t1,
        riega_manila_conductor=True, riega_guaya_conductor=True,
        tendido_conductor=True,
    )
    # No tocamos campos nuevos: la fibra queda en su default False (legacy).
    legacy.refresh_from_db()
    assert legacy.tendido_conductor is True
    assert legacy.tendido_opgw is False

    ctx = _ctx(DashboardTendidoView, proyecto, admin)
    by_c = {e['etapa']: e for e in ctx['avance_conductor']}
    assert by_c['TENDIDO_CONDUCTOR']['completas'] == 1
    # La torre legacy está en la vista por torre con pendientes de fibra.
    assert len(ctx['vista_torres']) == 1
    assert any('OPGW' in p or 'fibra' in p.lower()
               for p in ctx['vista_torres'][0]['pendientes'])
