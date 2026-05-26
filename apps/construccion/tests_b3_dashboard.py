"""Tests B3 — Dashboard Indicadores en General (#97).

Cubre:
  - happy: con datos B2 cargados → todos los KPI + 6 canvas + context
  - empty: sin datos B2 → mensaje placeholder, sin crash
  - filtros: ?periodo=trimestre filtra el queryset
  - export PDF: ?export=pdf devuelve Content-Type application/pdf
  - export Excel: ?export=excel devuelve xlsx
  - export JSON: ?export=json devuelve KPIs

B3 depende de B2 (#98) — sus modelos se importan, y los tests crean
datos de prueba directamente vía ORM cuando están disponibles.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse


# ---- Fixture: proyecto de construcción base ----

@pytest.fixture
def proyecto_indicadores(db):
    """ProyectoConstruccion mínimo para colgar indicadores B2."""
    from apps.contratos.models import Contrato
    from apps.construccion.models import ProyectoConstruccion

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-B3-001',
        nombre='Contrato test B3',
        cliente='Test Cliente',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto B3 test',
        estado='EJECUCION',
    )


def _import_b2_models():
    """Helper: importa modelos B2 si están disponibles, None si no."""
    try:
        from apps.construccion.models_b2_indicadores import (
            IndicadorFinancieroConstruccion,
            IndicadorTecnicoConstruccion,
        )
        return IndicadorFinancieroConstruccion, IndicadorTecnicoConstruccion
    except (ImportError, Exception):
        return None, None


# ===========================================================================
# Test E2E del blueprint
# ===========================================================================

@pytest.mark.django_db
def test_b3_dashboard_indicadores_generales_render_con_kpis_y_graficas(
    authenticated_client, proyecto_indicadores
):
    """E2E happy path declarado en BLUEPRINT.sub_features.B3.tests_e2e.

    Carga datos B2 y verifica: HTTP 200, 6 KPI cards en HTML, 6 canvas
    Chart.js, charts_json en context.
    """
    IndFin, IndTec = _import_b2_models()
    if IndFin and IndTec:
        IndFin.objects.create(
            proyecto=proyecto_indicadores,
            fecha=date.today(),
            ingresos_ejecutados=Decimal('100000000'),
            costos_directos=Decimal('60000000'),
            gastos=Decimal('15000000'),
            costo_real=Decimal('75000000'),
            costo_presupuestado=Decimal('80000000'),
        )
        IndTec.objects.create(
            proyecto=proyecto_indicadores,
            fecha=date.today(),
            presupuesto_ejecutado_pct=60.0,
            presupuesto_planeado_pct=70.0,
            obra_ejecutada=Decimal('50'),
            obra_programada=Decimal('60'),
            actividades_completadas=12,
            actividades_planificadas=15,
            cantidad_ejecutada=120.0,
            horas_hombre=80.0,
        )

    url = reverse(
        'construccion:indicadores_financieros',
        kwargs={'proyecto_id': proyecto_indicadores.id},
    )
    resp = authenticated_client.get(url)
    assert resp.status_code == 200, resp.content[:500]

    body = resp.content.decode()

    # Header
    assert 'Indicadores en General' in body
    # 6 KPI cards (chequeo por data-kpi-key)
    for key in ('margen_operativo', 'desviacion_presupuestal',
                'avance_tecnico', 'accidentes',
                'ejecucion_presupuestal', 'capacitaciones'):
        assert f'data-kpi-key="{key}"' in body, f'KPI {key} faltante'

    # 6 canvas Chart.js
    for canvas_id in ('chart-flujo-caja', 'chart-avance-tecnico',
                      'chart-egresos-pie', 'chart-margen-kpi',
                      'chart-seguridad', 'chart-productividad-cuadrillas'):
        assert f'id="{canvas_id}"' in body, f'canvas {canvas_id} faltante'

    # Chart.js CDN cargado
    assert 'cdn.jsdelivr.net/npm/chart.js@4.4.0' in body
    # Data JSON embebida
    assert 'id="b3-charts-data"' in body

    # Filtros
    assert 'name="periodo"' in body
    assert 'name="tipo"' in body
    assert 'name="linea"' in body

    # Context tiene KPIs (vía json export para inspección sin reparsear HTML)
    json_resp = authenticated_client.get(url + '?export=json')
    assert json_resp.status_code == 200
    data = json_resp.json()
    assert len(data['kpis']) == 6
    assert 'flujo_caja' in data['charts']
    assert 'productividad_cuadrillas' in data['charts']


# ===========================================================================
# Edge cases
# ===========================================================================

@pytest.mark.django_db
def test_b3_empty_state_sin_datos_b2_no_crashea(
    authenticated_client, proyecto_indicadores
):
    """Sin indicadores cargados, debe mostrar empty state y NO 500."""
    url = reverse(
        'construccion:indicadores_financieros',
        kwargs={'proyecto_id': proyecto_indicadores.id},
    )
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    body = resp.content.decode()
    assert 'Aún no hay indicadores registrados' in body
    # Los KPI cards SIGUEN render — valores en 0, no crash
    assert 'data-kpi-key="margen_operativo"' in body


@pytest.mark.django_db
def test_b3_filtro_periodo_trimestre_filtra_queryset(
    authenticated_client, proyecto_indicadores
):
    """?periodo=trimestre filtra por fecha (hoy - 90 días)."""
    IndFin, _ = _import_b2_models()
    if IndFin is None:
        pytest.skip('Modelos B2 no disponibles en este worktree (esperado fuera de F4)')

    # 1 indicador hace 200 días (fuera de trimestre)
    viejo = IndFin.objects.create(
        proyecto=proyecto_indicadores,
        fecha=date.today() - timedelta(days=200),
        ingresos_ejecutados=Decimal('50000000'),
        costos_directos=Decimal('40000000'),
    )
    # 1 indicador hace 10 días (dentro de trimestre)
    nuevo = IndFin.objects.create(
        proyecto=proyecto_indicadores,
        fecha=date.today() - timedelta(days=10),
        ingresos_ejecutados=Decimal('80000000'),
        costos_directos=Decimal('50000000'),
    )

    url = reverse(
        'construccion:indicadores_financieros',
        kwargs={'proyecto_id': proyecto_indicadores.id},
    )
    # Sin filtro: ve los 2
    resp_all = authenticated_client.get(url + '?periodo=todo&export=json')
    data_all = resp_all.json()
    assert len(data_all['charts']['flujo_caja']['labels']) == 2

    # Con filtro trimestre: solo el reciente
    resp_q = authenticated_client.get(url + '?periodo=trimestre&export=json')
    data_q = resp_q.json()
    assert len(data_q['charts']['flujo_caja']['labels']) == 1
    assert data_q['charts']['flujo_caja']['labels'][0] == nuevo.fecha.isoformat()


@pytest.mark.django_db
def test_b3_filtro_periodo_invalido_fallback_a_todo(
    authenticated_client, proyecto_indicadores
):
    """?periodo=basura no debe 500 — cae a 'todo'."""
    url = reverse(
        'construccion:indicadores_financieros',
        kwargs={'proyecto_id': proyecto_indicadores.id},
    )
    resp = authenticated_client.get(url + '?periodo=foo_bar_invalido')
    assert resp.status_code == 200


@pytest.mark.django_db
def test_b3_export_pdf_content_type(
    authenticated_client, proyecto_indicadores
):
    """?export=pdf devuelve application/pdf con header de descarga."""
    url = reverse(
        'construccion:indicadores_financieros',
        kwargs={'proyecto_id': proyecto_indicadores.id},
    )
    resp = authenticated_client.get(url + '?export=pdf')
    assert resp.status_code == 200
    assert resp['Content-Type'] == 'application/pdf'
    assert 'attachment' in resp['Content-Disposition']
    assert '.pdf' in resp['Content-Disposition']
    # PDF magic header
    assert resp.content[:4] == b'%PDF'


@pytest.mark.django_db
def test_b3_export_excel_content_type(
    authenticated_client, proyecto_indicadores
):
    """?export=excel devuelve xlsx con header de descarga."""
    IndFin, _ = _import_b2_models()
    if IndFin:
        IndFin.objects.create(
            proyecto=proyecto_indicadores,
            fecha=date.today(),
            ingresos_ejecutados=Decimal('1000'),
            costos_directos=Decimal('500'),
        )

    url = reverse(
        'construccion:indicadores_financieros',
        kwargs={'proyecto_id': proyecto_indicadores.id},
    )
    resp = authenticated_client.get(url + '?export=excel')
    assert resp.status_code == 200
    assert 'spreadsheetml' in resp['Content-Type']
    assert '.xlsx' in resp['Content-Disposition']
    # XLSX magic header (zip signature)
    assert resp.content[:2] == b'PK'


@pytest.mark.django_db
def test_b3_login_requerido(client, proyecto_indicadores):
    """Sin autenticar redirige al login (LoginRequiredMixin)."""
    url = reverse(
        'construccion:indicadores_financieros',
        kwargs={'proyecto_id': proyecto_indicadores.id},
    )
    resp = client.get(url)
    assert resp.status_code in (302, 403)
