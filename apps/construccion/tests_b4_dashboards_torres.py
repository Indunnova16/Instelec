"""Tests B4 — Vista por torre consolidada (cross-fase) + drill-down (#139).

Cubre los dos tests del BLUEPRINT:
  - ``b4_vista_torres_consolidada``  → tabla torre × fase con % y estado.
  - ``b4_drilldown_punto_bajo``      → endpoint detalle de lo atrasado.

Más edge cases del dominio:
  - Torre con avance en una fase pero NO en otra → celda registrada=False,
    pendiente, sin error (edge crítico del scope).
  - Drill-down de fase inválida → HTTP 400.
  - Drill-down de torre sin registro → registrada=False, pendientes=[].
  - Dato legacy: torre OC con patas parcialmente avanzadas (como prod) preservada.

Las vistas se ejercitan con ``RequestFactory`` llamando directo al ``.get`` /
``get_context_data`` para no depender de que F4 ya haya cableado el ``include``
en ``urls.py`` (el wiring se aplica en integración). Las funciones puras del
módulo se testean directo contra el ORM.
"""
from __future__ import annotations

import json
from decimal import Decimal

import pytest
from django.test import RequestFactory

from apps.construccion import views_dashboards_b4_torres as b4
from apps.construccion import calculators_avance_real as car


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def proyecto_b4(db):
    """ProyectoConstruccion mínimo para la vista consolidada B4."""
    from apps.contratos.models import Contrato
    from apps.construccion.models import ProyectoConstruccion
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-B4-VT-001',
        nombre='Contrato test B4 vista torres',
        cliente='Cliente B4',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto B4 vista torres',
        estado='EJECUCION',
    )


@pytest.fixture
def torres_b4(proyecto_b4):
    """Dos torres: T1 (avance mixto) y T2 (sin avance en algunas fases)."""
    from apps.construccion.models import TorreConstruccion
    t1 = TorreConstruccion.objects.create(proyecto=proyecto_b4, numero='01', tipo='D6')
    t2 = TorreConstruccion.objects.create(proyecto=proyecto_b4, numero='02', tipo='D6')
    return t1, t2


@pytest.fixture
def avance_mixto(proyecto_b4, torres_b4):
    """Carga avance:
      - T1: OC completa (1 pata 100%), Montaje a medias, sin Tendido.
      - T2: solo Tendido (conductor+fibra completos), sin OC ni Montaje.
    Refleja el edge "torre sin avance en una fase".
    """
    t1, t2 = torres_b4
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle
    from apps.construccion.models_b3_mont_detalle import MontajeEstructuraTorreDetalle
    from apps.construccion.models import TendidoTorre

    # T1 — Obra Civil 100% (todas las etapas de la pata al máximo).
    ObraCivilTorreDetalle.objects.create(
        proyecto=proyecto_b4, torre=t1, pata='A',
        cerr_finalizado_ok=True,
        exc_ejecutada_pct=Decimal('1'),
        sol_ejecutado_pct=Decimal('1'),
        ace_instalacion_pct=Decimal('1'),
        vac_ejecutado_pct=Decimal('1'),
        com_finalizada_pct=Decimal('1'),
    )
    # T1 — Montaje parcial (solo estructura en sitio).
    MontajeEstructuraTorreDetalle.objects.create(
        proyecto=proyecto_b4, torre=t1,
        estructura_en_sitio_ok=True,
        prearmada_ok=False, torre_montada_ok=False, revisada_ok=False,
    )
    # T2 — Tendido completo (conductor + fibra).
    TendidoTorre.objects.create(
        proyecto=proyecto_b4, torre=t2,
        riega_manila_conductor=True, riega_guaya_conductor=True,
        tendido_conductor=True, grapado_amarre_conductor=True,
        accesorios_puentes=True, balizas_desviadores=True,
        riega_manila_fibra=True, riega_guaya_opgw=True,
        tendido_opgw=True, grapado_amarre_fibra=True, empalmes_opgw=True,
    )
    return t1, t2


@pytest.fixture
def b4_urls_registradas():
    """Registra temporalmente las URLs de B4 en el urlconf de ``construccion``.

    En integración (F4) el ``include`` de ``urls_dashboards_b4_torres`` se agrega
    a ``urls.py`` de forma permanente. En el worktree aislado aún NO está, así
    que para que ``reverse('construccion:dashboard_drilldown_torre')`` resuelva
    dentro del test, inyectamos los patterns y limpiamos los caches del resolver.
    """
    from django.urls import clear_url_caches
    from apps.construccion import urls as construccion_urls
    from apps.construccion.urls_dashboards_b4_torres import urlpatterns as b4_urls

    originales = list(construccion_urls.urlpatterns)
    construccion_urls.urlpatterns += b4_urls
    clear_url_caches()
    try:
        yield
    finally:
        construccion_urls.urlpatterns = originales
        clear_url_caches()


def _rf_get(view_cls, proyecto, admin_user, **get):
    """Helper: instancia la CBV con un GET autenticado vía RequestFactory.

    Adjunta una sesión vacía: el render del parcial (?format=html) pasa por los
    context processors del proyecto, que leen ``request.session``.
    """
    from importlib import import_module
    from django.conf import settings
    rf = RequestFactory()
    req = rf.get('/x', data=get)
    req.user = admin_user
    engine = import_module(settings.SESSION_ENGINE)
    req.session = engine.SessionStore()
    view = view_cls()
    view.setup(req, proyecto_id=proyecto.id)
    return view, req


# ===========================================================================
# 1. b4_vista_torres_consolidada — happy path
# ===========================================================================

@pytest.mark.django_db
def test_b4_vista_torres_consolidada(proyecto_b4, avance_mixto):
    """La matriz consolidada pivota las 3 fases por torre con % y estado."""
    consolidado = b4.construir_vista_torres_consolidada(proyecto_b4)

    # 3 columnas de fase, en orden OC/Montaje/Tendido.
    assert [f['codigo'] for f in consolidado['fases']] == [
        car.FASE_OOCC, car.FASE_MONTAJE, car.FASE_TENDIDO]

    # Ambas torres aparecen (cada una con avance en al menos una fase).
    numeros = {t['numero'] for t in consolidado['torres']}
    assert numeros == {'01', '02'}

    porn = {t['numero']: t for t in consolidado['torres']}

    # T1: OC completa (celda registrada + completa), Montaje registrado no completo,
    # Tendido NO registrado.
    t1 = porn['01']
    assert t1['celdas'][car.FASE_OOCC]['registrada'] is True
    assert t1['celdas'][car.FASE_OOCC]['completa'] is True
    assert t1['celdas'][car.FASE_OOCC]['pct'] == 100.0
    assert t1['celdas'][car.FASE_MONTAJE]['registrada'] is True
    assert t1['celdas'][car.FASE_MONTAJE]['completa'] is False
    assert t1['celdas'][car.FASE_TENDIDO]['registrada'] is False
    assert t1['celdas'][car.FASE_TENDIDO]['pct'] == 0.0
    # global = promedio de fases CON avance (OC 100 + Montaje parcial) / 2.
    assert t1['completa_global'] is False

    # T2: solo Tendido.
    t2 = porn['02']
    assert t2['celdas'][car.FASE_TENDIDO]['registrada'] is True
    assert t2['celdas'][car.FASE_TENDIDO]['completa'] is True
    assert t2['celdas'][car.FASE_OOCC]['registrada'] is False
    assert t2['celdas'][car.FASE_MONTAJE]['registrada'] is False


@pytest.mark.django_db
def test_b4_vista_consolidada_view_context(
        proyecto_b4, avance_mixto, admin_user, b4_urls_registradas):
    """La view arma el contexto completo + drilldown_cfg pre-serializado."""
    view, _req = _rf_get(b4.DashboardVistaTorresView, proyecto_b4, admin_user)
    ctx = view.get_context_data()

    assert ctx['proyecto'] == proyecto_b4
    assert len(ctx['fases']) == 3
    assert len(ctx['torres']) == 2
    assert ctx['total_torres'] == 2
    assert ctx['torres_con_avance'] == 2
    # resumen por fase presente para las 3.
    assert {r['codigo'] for r in ctx['resumen_fases']} == {
        car.FASE_OOCC, car.FASE_MONTAJE, car.FASE_TENDIDO}
    # Guard es-CO: la config es un STRING JSON (no dict crudo en template).
    assert isinstance(ctx['drilldown_cfg'], str)
    cfg = json.loads(ctx['drilldown_cfg'])
    assert 'drilldown_url' in cfg and str(proyecto_b4.id) in cfg['drilldown_url']


# ===========================================================================
# 2. b4_drilldown_punto_bajo — endpoint detalle de lo atrasado
# ===========================================================================

@pytest.mark.django_db
def test_b4_drilldown_punto_bajo(proyecto_b4, avance_mixto):
    """El drill-down de Montaje de T1 lista las etapas atrasadas (lo bajo)."""
    t1, _t2 = avance_mixto
    detalle = b4.detalle_drilldown_torre(proyecto_b4, t1.id, car.FASE_MONTAJE)

    assert detalle['registrada'] is True
    assert detalle['completa'] is False
    assert detalle['fase'] == car.FASE_MONTAJE
    # Montaje: solo estructura_en_sitio_ok → faltan Prearmada/Torre montada/Revisada.
    assert 'Prearmada' in detalle['pendientes']
    assert 'Torre montada' in detalle['pendientes']
    assert 'Revisada' in detalle['pendientes']
    assert detalle['total_pendientes'] == len(detalle['pendientes']) == 3


@pytest.mark.django_db
def test_b4_drilldown_endpoint_json(proyecto_b4, avance_mixto, admin_user):
    """El endpoint JSON responde ok=True con el detalle (Content-Type json)."""
    t1, _t2 = avance_mixto
    view, _req = _rf_get(
        b4.DrilldownTorreFaseView, proyecto_b4, admin_user,
        torre=t1.id, fase=car.FASE_MONTAJE)
    resp = view.get(_req, proyecto_id=proyecto_b4.id)
    assert resp.status_code == 200
    assert resp['Content-Type'] == 'application/json'
    payload = json.loads(resp.content)
    assert payload['ok'] is True
    assert payload['detalle']['fase'] == car.FASE_MONTAJE
    assert payload['detalle']['total_pendientes'] == 3


@pytest.mark.django_db
def test_b4_drilldown_endpoint_html_format(proyecto_b4, avance_mixto, admin_user):
    """?format=html renderiza el parcial _drilldown_torre.html con las pendientes."""
    t1, _t2 = avance_mixto
    view, _req = _rf_get(
        b4.DrilldownTorreFaseView, proyecto_b4, admin_user,
        torre=t1.id, fase=car.FASE_MONTAJE, format='html')
    resp = view.get(_req, proyecto_id=proyecto_b4.id)
    assert resp.status_code == 200
    body = resp.content.decode()
    assert 'data-drilldown-torre' in body
    assert 'data-dd-pendientes' in body
    assert 'Prearmada' in body


# ===========================================================================
# 3. Edge cases del dominio
# ===========================================================================

@pytest.mark.django_db
def test_b4_torre_sin_avance_en_fase_no_es_error(proyecto_b4, avance_mixto):
    """Edge: T1 NO tiene Tendido → drill-down devuelve registrada=False, [],
    NO lanza error."""
    t1, _t2 = avance_mixto
    detalle = b4.detalle_drilldown_torre(proyecto_b4, t1.id, car.FASE_TENDIDO)
    assert detalle['registrada'] is False
    assert detalle['pendientes'] == []
    assert detalle['total_pendientes'] == 0
    assert detalle['pct'] == 0.0
    # El número de torre se resuelve aunque no haya registro de la fase.
    assert detalle['numero'] == '01'


@pytest.mark.django_db
def test_b4_drilldown_fase_invalida_raise(proyecto_b4, torres_b4):
    """Fase inválida → ValueError (la view la traduce a HTTP 400)."""
    t1, _t2 = torres_b4
    with pytest.raises(ValueError):
        b4.detalle_drilldown_torre(proyecto_b4, t1.id, 'NO_EXISTE')


@pytest.mark.django_db
def test_b4_drilldown_endpoint_400_sin_torre(proyecto_b4, admin_user):
    """Falta ?torre → HTTP 400 ok=False."""
    view, _req = _rf_get(
        b4.DrilldownTorreFaseView, proyecto_b4, admin_user, fase=car.FASE_OOCC)
    resp = view.get(_req, proyecto_id=proyecto_b4.id)
    assert resp.status_code == 400
    assert json.loads(resp.content)['ok'] is False


@pytest.mark.django_db
def test_b4_drilldown_endpoint_400_fase_invalida(proyecto_b4, torres_b4, admin_user):
    """?fase inválida → HTTP 400."""
    t1, _t2 = torres_b4
    view, _req = _rf_get(
        b4.DrilldownTorreFaseView, proyecto_b4, admin_user,
        torre=t1.id, fase='ZZZ')
    resp = view.get(_req, proyecto_id=proyecto_b4.id)
    assert resp.status_code == 400


@pytest.mark.django_db
def test_b4_proyecto_sin_torres_consolidado_vacio(proyecto_b4):
    """Proyecto sin torres → consolidado con 3 fases pero 0 filas (no crash)."""
    consolidado = b4.construir_vista_torres_consolidada(proyecto_b4)
    assert len(consolidado['fases']) == 3
    assert consolidado['torres'] == []


# ===========================================================================
# 4. Dato legacy — torre OC con patas parciales (como prod)
# ===========================================================================

@pytest.mark.django_db
def test_b4_dato_legacy_oc_patas_parciales(proyecto_b4, torres_b4):
    """Como en prod: una torre con 2 patas a distinto avance → la celda OC
    refleja el promedio y lista las etapas pendientes en el drill-down."""
    t1, _t2 = torres_b4
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle
    # Pata A: excavación 100%; Pata B: nada. Promedio < 100 → pendiente.
    ObraCivilTorreDetalle.objects.create(
        proyecto=proyecto_b4, torre=t1, pata='A',
        exc_ejecutada_pct=Decimal('1'),
    )
    ObraCivilTorreDetalle.objects.create(
        proyecto=proyecto_b4, torre=t1, pata='B',
    )
    consolidado = b4.construir_vista_torres_consolidada(proyecto_b4)
    fila = next(t for t in consolidado['torres'] if t['numero'] == '01')
    celda_oc = fila['celdas'][car.FASE_OOCC]
    assert celda_oc['registrada'] is True
    assert celda_oc['completa'] is False
    assert 0.0 < celda_oc['pct'] < 100.0

    detalle = b4.detalle_drilldown_torre(proyecto_b4, t1.id, car.FASE_OOCC)
    # Vaciado/Acero/etc siguen pendientes (no todas las patas al 100%).
    assert detalle['total_pendientes'] > 0
    assert 'Vaciado' in detalle['pendientes']
