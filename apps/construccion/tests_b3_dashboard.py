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


# ===========================================================================
# #141 — Dashboard Obra Civil: 3 gráficas de seguimiento gerencial
# ===========================================================================
#
# G1 Curva S consolidada · G2 avance por etapa OC · G3 desviación materiales.
# Cubre los calculators puros (calculators.py), el endpoint JSON
# (DashboardGraficasDataView), el render del dashboard OC con los 3 canvas y
# el flag data-charts-ready, más edge cases (proyecto sin torres, torre sin
# vaciado, desviación dentro de umbral = verde).

def _torre_con_patas(proyecto, numero, **pata_flags):
    """Helper: crea una torre con 4 patas (A-D) seteando los booleanos dados
    en TODAS las patas. Devuelve (torre, [patas])."""
    from apps.construccion.models import TorreConstruccion, PataObra
    torre = TorreConstruccion.objects.create(proyecto=proyecto, numero=numero, tipo='D6')
    patas = []
    for letra in ('A', 'B', 'C', 'D'):
        patas.append(PataObra.objects.create(torre=torre, pata=letra, **pata_flags))
    return torre, patas


# ---- Calculators puros ----

@pytest.mark.django_db
def test_141_avance_por_etapa_oc_pct_torres_completas(proyecto_indicadores):
    """G2: 2 torres, 1 con excavación completa en las 4 patas, otra sin →
    50% en EXCAVACION; 0% en las demás etapas. Estructura de 5 etapas siempre."""
    from apps.construccion.calculators import avance_por_etapa_oc
    _torre_con_patas(proyecto_indicadores, 'T1', excavacion_ok=True)
    _torre_con_patas(proyecto_indicadores, 'T2', excavacion_ok=False)

    etapas = avance_por_etapa_oc(proyecto_indicadores)
    # Siempre las 5 etapas, en orden.
    assert [e['etapa'] for e in etapas] == [
        'EXCAVACION', 'SOLADO', 'ACERO', 'VACIADO', 'COMPACTACION']
    exc = next(e for e in etapas if e['etapa'] == 'EXCAVACION')
    assert exc['totales'] == 2
    assert exc['completas'] == 1
    assert exc['pct'] == 50.0
    # Etapa sin avance → 0%.
    sol = next(e for e in etapas if e['etapa'] == 'SOLADO')
    assert sol['completas'] == 0 and sol['pct'] == 0.0


@pytest.mark.django_db
def test_141_avance_etapa_completa_solo_si_todas_las_patas(proyecto_indicadores):
    """G2: una torre cuenta como completa SOLO si las 4 patas tienen la etapa.
    3/4 patas con vaciado → torre NO completa (0%)."""
    from apps.construccion.models import TorreConstruccion, PataObra
    from apps.construccion.calculators import avance_por_etapa_oc
    torre = TorreConstruccion.objects.create(proyecto=proyecto_indicadores, numero='T9', tipo='D6')
    for letra, ok in (('A', True), ('B', True), ('C', True), ('D', False)):
        PataObra.objects.create(torre=torre, pata=letra, vaciado_ok=ok)
    etapas = avance_por_etapa_oc(proyecto_indicadores)
    vac = next(e for e in etapas if e['etapa'] == 'VACIADO')
    assert vac['totales'] == 1
    assert vac['completas'] == 0
    assert vac['pct'] == 0.0


@pytest.mark.django_db
def test_141_avance_por_etapa_acero_y_compactacion_mapean_campo_real(proyecto_indicadores):
    """R3: 'Acero' → acero_refuerzo_ok y 'Compactación' → relleno_compactacion_ok
    (NO acero_ok / compactacion_ok). 1 torre con esos 2 flags en las 4 patas."""
    from apps.construccion.calculators import avance_por_etapa_oc
    _torre_con_patas(proyecto_indicadores, 'T1',
                     acero_refuerzo_ok=True, relleno_compactacion_ok=True)
    etapas = {e['etapa']: e for e in avance_por_etapa_oc(proyecto_indicadores)}
    assert etapas['ACERO']['pct'] == 100.0
    assert etapas['COMPACTACION']['pct'] == 100.0


@pytest.mark.django_db
def test_141_avance_por_etapa_proyecto_sin_torres_no_crashea(proyecto_indicadores):
    """Edge: proyecto sin torres → 5 etapas con totales=0, pct=0.0 (no error)."""
    from apps.construccion.calculators import avance_por_etapa_oc
    etapas = avance_por_etapa_oc(proyecto_indicadores)
    assert len(etapas) == 5
    assert all(e['totales'] == 0 and e['pct'] == 0.0 for e in etapas)


@pytest.mark.django_db
def test_141_desviacion_materiales_calc_real_y_semaforo(proyecto_indicadores):
    """G3: cemento 41 calc / 42 real → desv ~2.44% (verde); agua sobreconsumo
    grande → rojo. Verifica los 4 materiales y el semáforo por umbral."""
    from apps.construccion.models import VaciadoDetalle
    from apps.construccion.calculators import desviacion_materiales_vaciado
    _, patas = _torre_con_patas(proyecto_indicadores, 'T1', vaciado_ok=True)
    # Una sola pata con vaciado para mantener el cálculo claro.
    VaciadoDetalle.objects.create(
        pata=patas[0],
        cemento_calc_bultos=41.0, cemento_util_bultos=42.0,   # +2.44% → verde
        agua_calc_m3=10.0, agua_util_m3=13.0,                 # +30%   → rojo
        arena_calc_m3=5.0, arena_util_m3=5.4,                 # +8%    → amarillo
        grava_calc_m3=8.0, grava_util_m3=8.0,                 # 0%     → verde
    )
    mats = {m['material']: m for m in desviacion_materiales_vaciado(proyecto_indicadores, umbral=10.0)}
    assert mats['cemento']['calc'] == 41.0 and mats['cemento']['real'] == 42.0
    assert round(mats['cemento']['desv_pct'], 2) == 2.44
    assert mats['cemento']['semaforo'] == 'verde'
    assert mats['agua']['semaforo'] == 'rojo'      # 30% > umbral 10%
    assert mats['arena']['semaforo'] == 'amarillo'  # 8% en (5,10]
    assert mats['grava']['semaforo'] == 'verde'     # 0%


@pytest.mark.django_db
def test_141_desviacion_dentro_de_umbral_es_verde(proyecto_indicadores):
    """G3 happy: desviación pequeña (<= umbral/2) → verde, sin alerta roja."""
    from apps.construccion.models import VaciadoDetalle
    from apps.construccion.calculators import desviacion_materiales_vaciado
    _, patas = _torre_con_patas(proyecto_indicadores, 'T1', vaciado_ok=True)
    VaciadoDetalle.objects.create(
        pata=patas[0],
        cemento_calc_bultos=100.0, cemento_util_bultos=102.0,  # +2% → verde
        agua_calc_m3=20.0, agua_util_m3=20.0,
        arena_calc_m3=10.0, arena_util_m3=10.0,
        grava_calc_m3=15.0, grava_util_m3=15.0,
    )
    mats = desviacion_materiales_vaciado(proyecto_indicadores, umbral=10.0)
    assert all(m['semaforo'] in ('verde', 'sin_datos') for m in mats)
    assert not any(m['semaforo'] == 'rojo' for m in mats)


@pytest.mark.django_db
def test_141_desviacion_materiales_proyecto_sin_vaciado(proyecto_indicadores):
    """Edge R4: proyecto con torres pero SIN VaciadoDetalle → materiales en 0,
    desv_pct None, semáforo 'sin_datos'. No rompe."""
    from apps.construccion.calculators import desviacion_materiales_vaciado
    _torre_con_patas(proyecto_indicadores, 'T1', vaciado_ok=False)
    mats = desviacion_materiales_vaciado(proyecto_indicadores)
    assert [m['material'] for m in mats] == ['agua', 'cemento', 'arena', 'grava']
    assert all(m['calc'] == 0 and m['real'] == 0 for m in mats)
    assert all(m['desv_pct'] is None and m['semaforo'] == 'sin_datos' for m in mats)


# ---- #141 reproceso: G3 por etapa (Solado + Vaciado separados) ----

@pytest.mark.django_db
def test_141_desviacion_materiales_solado_calc_real_y_semaforo(proyecto_indicadores):
    """G3 Solado: el agregador desviacion_materiales_solado() lee SoladoDetalle
    (no Vaciado) y calcula calc/real/desv/semaforo por material."""
    from apps.construccion.models import SoladoDetalle
    from apps.construccion.calculators import desviacion_materiales_solado
    _, patas = _torre_con_patas(proyecto_indicadores, 'T1', solado_ok=True)
    SoladoDetalle.objects.create(
        pata=patas[0],
        cemento_calc_bultos=900.0, cemento_util_bultos=906.0,  # +0.67% → verde
        agua_calc_m3=10.0, agua_util_m3=14.0,                  # +40%   → rojo
        arena_calc_m3=5.0, arena_util_m3=5.4,                  # +8%    → amarillo
        grava_calc_m3=8.0, grava_util_m3=8.0,                  # 0%     → verde
    )
    mats = {m['material']: m for m in desviacion_materiales_solado(proyecto_indicadores, umbral=10.0)}
    assert [m for m in mats] == ['agua', 'cemento', 'arena', 'grava']
    assert mats['cemento']['calc'] == 900.0 and mats['cemento']['real'] == 906.0
    assert mats['cemento']['semaforo'] == 'verde'
    assert mats['agua']['semaforo'] == 'rojo'
    assert mats['arena']['semaforo'] == 'amarillo'
    assert mats['grava']['semaforo'] == 'verde'


@pytest.mark.django_db
def test_141_desviacion_materiales_solado_sin_datos(proyecto_indicadores):
    """Edge: proyecto con torres pero SIN SoladoDetalle → materiales en 0,
    desv_pct None, semáforo 'sin_datos' (no rompe)."""
    from apps.construccion.calculators import desviacion_materiales_solado
    _torre_con_patas(proyecto_indicadores, 'T1', solado_ok=False)
    mats = desviacion_materiales_solado(proyecto_indicadores)
    assert [m['material'] for m in mats] == ['agua', 'cemento', 'arena', 'grava']
    assert all(m['calc'] == 0 and m['real'] == 0 for m in mats)
    assert all(m['desv_pct'] is None and m['semaforo'] == 'sin_datos' for m in mats)


@pytest.mark.django_db
def test_141_solado_y_vaciado_se_calculan_independientes(proyecto_indicadores):
    """REPROCESO core: con datos DISTINTOS en Solado y Vaciado, cada agregador
    devuelve SOLO los suyos — Solado no contamina Vaciado ni viceversa."""
    from apps.construccion.models import SoladoDetalle, VaciadoDetalle
    from apps.construccion.calculators import (
        desviacion_materiales_solado, desviacion_materiales_vaciado)
    _, patas = _torre_con_patas(proyecto_indicadores, 'T1', solado_ok=True, vaciado_ok=True)
    SoladoDetalle.objects.create(
        pata=patas[0], cemento_calc_bultos=900.0, cemento_util_bultos=906.0)
    VaciadoDetalle.objects.create(
        pata=patas[0], cemento_calc_bultos=40.0, cemento_util_bultos=60.0)

    sol = {m['material']: m for m in desviacion_materiales_solado(proyecto_indicadores, umbral=10.0)}
    vac = {m['material']: m for m in desviacion_materiales_vaciado(proyecto_indicadores, umbral=10.0)}
    # Solado: 900/906 (verde); Vaciado: 40/60 = +50% (rojo). No se mezclan.
    assert sol['cemento']['calc'] == 900.0 and sol['cemento']['real'] == 906.0
    assert sol['cemento']['semaforo'] == 'verde'
    assert vac['cemento']['calc'] == 40.0 and vac['cemento']['real'] == 60.0
    assert vac['cemento']['semaforo'] == 'rojo'


@pytest.mark.django_db
def test_141_proyecto_solo_solado_muestra_solado_y_vaciado_sin_datos(proyecto_indicadores):
    """Test contra el escenario del cliente: un proyecto con SOLO datos de
    Solado (att_03) muestra Solado con datos y Vaciado 'sin datos'. Cubre el
    rebote: antes el dashboard solo leía Vaciado, así que la data de Solado del
    cliente no aparecía en ningún lado."""
    from apps.construccion.models import SoladoDetalle
    from apps.construccion.calculators import (
        desviacion_materiales_solado, desviacion_materiales_vaciado)
    _, patas = _torre_con_patas(proyecto_indicadores, 'T1', solado_ok=True)
    SoladoDetalle.objects.create(
        pata=patas[0], cemento_calc_bultos=905.25, cemento_util_bultos=906.0,
        agua_calc_m3=0.40, agua_util_m3=0.40)
    sol = desviacion_materiales_solado(proyecto_indicadores, umbral=10.0)
    vac = desviacion_materiales_vaciado(proyecto_indicadores, umbral=10.0)
    # Solado: tiene datos (cemento calc>0).
    cem_sol = next(m for m in sol if m['material'] == 'cemento')
    assert cem_sol['calc'] == 905.25 and cem_sol['real'] == 906.0
    assert cem_sol['semaforo'] != 'sin_datos'
    # Vaciado: sin datos (no hay VaciadoDetalle).
    assert all(m['semaforo'] == 'sin_datos' for m in vac)


# ---- #141 rebote (commit 3): el dashboard lee el modelo que el FORM persiste ----

@pytest.mark.django_db
def test_141_g3_lee_obracivil_torre_detalle_no_solo_detalle_secuencial(proyecto_indicadores):
    """ROOT CAUSE del rebote: el FORMULARIO de captura escribe en
    ``ObraCivilTorreDetalle`` (sol_*/vac_*), pero el dashboard G3 leía SOLO
    ``SoladoDetalle``/``VaciadoDetalle`` (que NO tienen formulario → siempre
    vacíos en prod). Resultado: dashboard en blanco aunque el cliente cargaba
    datos. Este test crea un ObraCivilTorreDetalle (como lo haría el form) y
    verifica que G3 ahora SÍ lo agrega."""
    from apps.construccion.models import TorreConstruccion
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle
    from apps.construccion.calculators import (
        desviacion_materiales_solado, desviacion_materiales_vaciado)
    torre = TorreConstruccion.objects.create(
        proyecto=proyecto_indicadores, numero='T1', tipo='D6')
    # Datos como el formulario de captura del cliente (att_03): Solado.
    ObraCivilTorreDetalle.objects.create(
        proyecto=proyecto_indicadores, torre=torre, pata='A',
        sol_cemento_calc=Decimal('905.25'), sol_cemento_real=Decimal('906.00'),
        sol_agua_calc=Decimal('0.40'), sol_agua_real=Decimal('0.40'),
        vac_cemento_calc=Decimal('40.00'), vac_cemento_real=Decimal('60.00'),  # +50% → rojo
    )
    sol = {m['material']: m for m in desviacion_materiales_solado(proyecto_indicadores, umbral=10.0)}
    vac = {m['material']: m for m in desviacion_materiales_vaciado(proyecto_indicadores, umbral=10.0)}
    # Solado: cemento 905.25/906 → con datos (no 'sin_datos').
    assert sol['cemento']['calc'] == 905.25 and sol['cemento']['real'] == 906.0
    assert sol['cemento']['semaforo'] != 'sin_datos'
    # Vaciado: cemento 40/60 = +50% → rojo. Cada etapa independiente.
    assert vac['cemento']['calc'] == 40.0 and vac['cemento']['real'] == 60.0
    assert vac['cemento']['semaforo'] == 'rojo'


@pytest.mark.django_db
def test_141_g3_une_oc_detalle_y_detalle_secuencial(proyecto_indicadores):
    """Robustez: si hay datos en AMBAS fuentes (ObraCivilTorreDetalle y el
    detalle secuencial), G3 los suma (unión), no descarta ninguna."""
    from apps.construccion.models import TorreConstruccion, PataObra, SoladoDetalle
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle
    from apps.construccion.calculators import desviacion_materiales_solado
    torre = TorreConstruccion.objects.create(
        proyecto=proyecto_indicadores, numero='T1', tipo='D6')
    ObraCivilTorreDetalle.objects.create(
        proyecto=proyecto_indicadores, torre=torre, pata='A',
        sol_agua_calc=Decimal('10.00'), sol_agua_real=Decimal('10.00'))
    pata = PataObra.objects.create(torre=torre, pata='B', solado_ok=True)
    SoladoDetalle.objects.create(pata=pata, agua_calc_m3=5.0, agua_util_m3=5.0)
    sol = {m['material']: m for m in desviacion_materiales_solado(proyecto_indicadores)}
    # agua: 10 (oc_detalle) + 5 (secuencial) = 15 calc y 15 real.
    assert sol['agua']['calc'] == 15.0 and sol['agua']['real'] == 15.0


@pytest.mark.django_db
def test_141_vaciado_detalle_desviacion_pct_property(proyecto_indicadores):
    """La property VaciadoDetalle.desviacion_pct devuelve dict por material."""
    from apps.construccion.models import VaciadoDetalle
    _, patas = _torre_con_patas(proyecto_indicadores, 'T1', vaciado_ok=True)
    v = VaciadoDetalle.objects.create(
        pata=patas[0],
        cemento_calc_bultos=50.0, cemento_util_bultos=55.0,  # +10%
        agua_calc_m3=0.0, agua_util_m3=5.0,                  # calc 0 → None
    )
    desv = v.desviacion_pct
    assert set(desv.keys()) == {'agua', 'cemento', 'arena', 'grava'}
    assert round(desv['cemento'], 2) == 10.0
    assert desv['agua'] is None  # calc 0 → sin base


@pytest.mark.django_db
def test_141_curva_consolidada_une_fases(proyecto_indicadores):
    """G1: la curva consolidada une OOCC + MONTAJE; con 2 fases y 1 torre,
    cada fase al 100% acumulado → consolidada al 50% por fecha (denom = 2 fases)."""
    from datetime import date
    from decimal import Decimal
    from apps.construccion.models import (
        TorreConstruccion, DashboardAvanceSemanal)
    from apps.construccion.calculators import curva_s_consolidada
    TorreConstruccion.objects.create(proyecto=proyecto_indicadores, numero='T1', tipo='D6')

    DashboardAvanceSemanal.objects.create(
        proyecto=proyecto_indicadores, fase='OOCC', semana=date(2026, 1, 5),
        torres_programadas_semana=1, torres_construidas_semana=1,
        torres_programadas_acum=1, torres_construidas_acum=1,
        pct_programado=Decimal('100'), pct_construido=Decimal('100'))
    DashboardAvanceSemanal.objects.create(
        proyecto=proyecto_indicadores, fase='MONTAJE', semana=date(2026, 1, 5),
        torres_programadas_semana=1, torres_construidas_semana=0,
        torres_programadas_acum=1, torres_construidas_acum=0,
        pct_programado=Decimal('100'), pct_construido=Decimal('0'))

    cons = curva_s_consolidada(proyecto_indicadores)
    assert cons['labels'] == ['2026-01-05']
    # denom = total_torres(1) * n_fases(2) = 2.
    # planeado: prog_acum OOCC(1) + MONTAJE(1) = 2 / 2 * 100 = 100
    assert cons['planeado'] == [100.0]
    # ejecutado: cons_acum OOCC(1) + MONTAJE(0) = 1 / 2 * 100 = 50
    assert cons['ejecutado'] == [50.0]


@pytest.mark.django_db
def test_141_curva_consolidada_sin_semanas_vacia(proyecto_indicadores):
    """Edge: proyecto sin semanas capturadas → arreglos vacíos, no error."""
    from apps.construccion.calculators import curva_s_consolidada
    cons = curva_s_consolidada(proyecto_indicadores)
    assert cons == {'labels': [], 'planeado': [], 'ejecutado': []}


# ---- Endpoint JSON DashboardGraficasDataView ----

@pytest.mark.django_db
def test_141_endpoint_datos_graficas_shape(authenticated_client, proyecto_indicadores):
    """El endpoint responde 200 + shape JSON con curva_s/avance_etapas/
    desviacion_materiales. Happy path con torres + vaciado."""
    from apps.construccion.models import VaciadoDetalle
    _, patas = _torre_con_patas(proyecto_indicadores, 'T1', excavacion_ok=True, vaciado_ok=True)
    VaciadoDetalle.objects.create(
        pata=patas[0], cemento_calc_bultos=40.0, cemento_util_bultos=44.0)

    url = reverse('construccion:dashboard_graficas_data',
                  kwargs={'proyecto_id': proyecto_indicadores.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    data = resp.json()
    assert 'curva_s' in data
    assert 'consolidada' in data['curva_s']
    assert len(data['avance_etapas']) == 5
    # #141 — G3 por etapa: el endpoint expone Solado y Vaciado por separado.
    assert [m['material'] for m in data['desviacion_vaciado']] == [
        'agua', 'cemento', 'arena', 'grava']
    assert [m['material'] for m in data['desviacion_solado']] == [
        'agua', 'cemento', 'arena', 'grava']
    assert data['umbral'] == 10.0


@pytest.mark.django_db
def test_141_endpoint_umbral_param_filtra_semaforo(authenticated_client, proyecto_indicadores):
    """?umbral= ajusta el semáforo. desv 15% es rojo con umbral=10 pero verde
    con umbral=40."""
    from apps.construccion.models import VaciadoDetalle
    _, patas = _torre_con_patas(proyecto_indicadores, 'T1', vaciado_ok=True)
    VaciadoDetalle.objects.create(
        pata=patas[0], cemento_calc_bultos=100.0, cemento_util_bultos=115.0)  # +15%

    url = reverse('construccion:dashboard_graficas_data',
                  kwargs={'proyecto_id': proyecto_indicadores.id})
    d10 = authenticated_client.get(url + '?umbral=10').json()
    cem10 = next(m for m in d10['desviacion_vaciado'] if m['material'] == 'cemento')
    assert cem10['semaforo'] == 'rojo'

    d40 = authenticated_client.get(url + '?umbral=40').json()
    cem40 = next(m for m in d40['desviacion_vaciado'] if m['material'] == 'cemento')
    assert cem40['semaforo'] == 'verde'


@pytest.mark.django_db
def test_141_endpoint_umbral_invalido_cae_a_default(authenticated_client, proyecto_indicadores):
    """?umbral=basura → no 500, cae a 10.0."""
    url = reverse('construccion:dashboard_graficas_data',
                  kwargs={'proyecto_id': proyecto_indicadores.id})
    resp = authenticated_client.get(url + '?umbral=foo')
    assert resp.status_code == 200
    assert resp.json()['umbral'] == 10.0


@pytest.mark.django_db
def test_141_endpoint_proyecto_sin_torres_arreglos_vacios(authenticated_client, proyecto_indicadores):
    """Edge: proyecto sin torres → endpoint 200, avance_etapas con 5 etapas en 0,
    materiales en sin_datos, curva consolidada vacía."""
    url = reverse('construccion:dashboard_graficas_data',
                  kwargs={'proyecto_id': proyecto_indicadores.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    data = resp.json()
    assert all(e['totales'] == 0 for e in data['avance_etapas'])
    assert all(m['semaforo'] == 'sin_datos' for m in data['desviacion_vaciado'])
    assert all(m['semaforo'] == 'sin_datos' for m in data['desviacion_solado'])
    assert data['curva_s']['consolidada']['labels'] == []


@pytest.mark.django_db
def test_141_endpoint_login_requerido(client, proyecto_indicadores):
    """Endpoint protegido por LoginRequiredMixin."""
    url = reverse('construccion:dashboard_graficas_data',
                  kwargs={'proyecto_id': proyecto_indicadores.id})
    resp = client.get(url)
    assert resp.status_code in (302, 403)


# ---- Render del dashboard OC con los 3 canvas + ready flag ----

@pytest.mark.django_db
def test_141_dashboard_oc_renderiza_tres_canvas_y_ready_flag(
        authenticated_client, proyecto_indicadores):
    """El dashboard OC renderiza los 3 canvas, las 5 etapas, los 4 materiales,
    el selector Consolidada y el flag data-charts-ready (probe E2E)."""
    from apps.construccion.models import VaciadoDetalle
    _, patas = _torre_con_patas(proyecto_indicadores, 'T1', excavacion_ok=True, vaciado_ok=True)
    VaciadoDetalle.objects.create(
        pata=patas[0], cemento_calc_bultos=40.0, cemento_util_bultos=60.0)  # +50% → rojo

    url = reverse('construccion:dashboard_obra_civil',
                  kwargs={'proyecto_id': proyecto_indicadores.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    body = resp.content.decode()

    # canvas: curva S + avance etapas + G3 por etapa (Solado y Vaciado, #141)
    for cid in ('curva-s-chart', 'avance-etapas-chart',
                'desviacion-solado-chart', 'desviacion-vaciado-chart'):
        assert f'id="{cid}"' in body, f'canvas {cid} faltante'
    # 5 etapas como texto visible (assert_contains del journey)
    for etapa in ('Excavación', 'Solado', 'Acero', 'Vaciado', 'Compactación'):
        assert etapa in body, f'etapa {etapa} faltante'
    # 4 materiales
    for mat in ('Agua', 'Cemento', 'Arena', 'Grava'):
        assert mat in body, f'material {mat} faltante'
    # Selector consolidada
    assert 'Consolidada' in body
    # Flag de probe (Alpine lo bindea; el atributo debe existir en el HTML)
    assert 'data-charts-ready' in body
    # Alerta roja presente (desviación 50% > umbral 10%)
    assert "data-semaforo=\"rojo\"" in body


@pytest.mark.django_db
def test_141_dashboard_montaje_no_muestra_graficas_oc_only(
        authenticated_client, proyecto_indicadores):
    """Tras el bloque dashboards (#139, F4 wiring), ``dashboard_montaje`` abre el
    dashboard REAL de Montaje (``DashboardMontajeRealView`` con su template
    propio ``dashboard_montaje.html``), NO el view del semanal vacío.

    Actualizado en integración F4: antes (#141) este name resolvía a la vista del
    template compartido sin gráficas y el test afirmaba que NO había ``avance-
    etapas-chart``. Ahora el dashboard de Montaje SÍ tiene su Curva S + avance por
    etapa (chart genérico del parcial base + ``#montaje-etapas-chart`` dedicado),
    que es justamente el objetivo de #139. Lo que sigue sin aplicar a Montaje es
    la gráfica de desviación de materiales de vaciado, que es OC-only (#141).
    """
    url = reverse('construccion:dashboard_montaje',
                  kwargs={'proyecto_id': proyecto_indicadores.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    body = resp.content.decode()
    # Montaje real renderiza su propia gráfica de etapas (OK que exista).
    assert 'id="montaje-etapas-chart"' in body
    # La desviación de materiales de vaciado es exclusiva de Obra Civil (#141).
    assert 'id="desviacion-materiales-chart"' not in body
