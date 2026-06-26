"""Tests #122 Fase 2 — Curvas S por FECHAS REALES + Gantt de Obra Civil.

Decisión de Miguel (#122): las series de los dashboards de Obra Civil y Montaje
se anclan en las FECHAS REALES por torre (2025), NO en la cascada updated_at
(que cae a 2026) ni en el cronograma project-level (vacío en QA). La métrica es
CONTEO de torres acumulado, normalizado a % sobre el total de torres aplica=True.

Cubre el backbone ``calculators_avance_real``:
- serie_planeado_oc_fechas        (acum por ObraCivilTorre.fecha_esperada)
- serie_ejecutado_oc_fechas       (acum por ObraCivilTorre.fecha_final)
- serie_ejecutado_montaje_fechas  (acum por MontajeEstructuraTorreDetalle.montaje_fecha_fin)
- gantt_oc                        (barra por torre [inicio, esperada, final])

Punto crítico del root cause: las etiquetas de fecha deben ser 2025 (de las
fechas reales), NO 2026 (de updated_at). Por eso las fixtures crean los registros
HOY (updated_at = 2026) pero con fechas reales en 2025.
"""
from datetime import date

import pytest

from apps.construccion import calculators_avance_real as car

# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def proyecto_122(db):
    from apps.construccion.models import ProyectoConstruccion
    from apps.contratos.models import Contrato

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-I122-001',
        nombre='Contrato test #122',
        cliente='Cliente #122',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto curvas #122',
        estado='EJECUCION',
    )


@pytest.fixture
def oc_torres_122(proyecto_122):
    """4 torres aplica=True con fechas reales 2025 + 1 torre no-aplica (excluida).

    Fechas (todas 2025; updated_at queda en 2026 por crearse hoy):
      T1: esperada 2025-01-10, final 2025-01-15
      T2: esperada 2025-02-10, final 2025-02-20
      T3: esperada 2025-03-05, final 2025-03-10
      T4: esperada 2025-04-01, final NULL (planeada, no ejecutada)
      T5: NO aplica → excluida del conteo y del denominador
    """
    from apps.construccion.models import ObraCivilTorre, TorreConstruccion

    def _torre(numero, aplica=True):
        return TorreConstruccion.objects.create(
            proyecto=proyecto_122, numero=numero, tipo='D6', aplica=aplica,
        )

    t1, t2, t3, t4 = _torre('1'), _torre('2'), _torre('3'), _torre('4')
    t5 = _torre('5', aplica=False)

    ObraCivilTorre.objects.create(
        proyecto=proyecto_122, torre=t1,
        fecha_inicio=date(2025, 1, 2), fecha_esperada=date(2025, 1, 10), fecha_final=date(2025, 1, 15),
    )
    ObraCivilTorre.objects.create(
        proyecto=proyecto_122, torre=t2,
        fecha_inicio=date(2025, 2, 1), fecha_esperada=date(2025, 2, 10), fecha_final=date(2025, 2, 20),
    )
    ObraCivilTorre.objects.create(
        proyecto=proyecto_122, torre=t3,
        fecha_inicio=date(2025, 3, 1), fecha_esperada=date(2025, 3, 5), fecha_final=date(2025, 3, 10),
    )
    ObraCivilTorre.objects.create(
        proyecto=proyecto_122, torre=t4,
        fecha_inicio=date(2025, 3, 25), fecha_esperada=date(2025, 4, 1), fecha_final=None,
    )
    # No-aplica: con fechas 2025 pero NO debe entrar al conteo ni al denominador.
    ObraCivilTorre.objects.create(
        proyecto=proyecto_122, torre=t5,
        fecha_inicio=date(2025, 1, 1), fecha_esperada=date(2025, 1, 1), fecha_final=date(2025, 1, 1),
    )
    return proyecto_122


@pytest.fixture
def montaje_torres_122(proyecto_122):
    """3 torres aplica=True con montaje_fecha_fin en 2025 (1 sin fecha)."""
    from apps.construccion.models import TorreConstruccion
    from apps.construccion.models_b3_mont_detalle import MontajeEstructuraTorreDetalle

    def _torre(numero, aplica=True):
        return TorreConstruccion.objects.create(
            proyecto=proyecto_122, numero=numero, tipo='D6', aplica=aplica,
        )

    t1, t2, t3 = _torre('1'), _torre('2'), _torre('3')
    MontajeEstructuraTorreDetalle.objects.create(
        proyecto=proyecto_122, torre=t1, montaje_fecha_fin=date(2025, 5, 10),
    )
    MontajeEstructuraTorreDetalle.objects.create(
        proyecto=proyecto_122, torre=t2, montaje_fecha_fin=date(2025, 6, 15),
    )
    # Sin montaje_fecha_fin → no aporta a la serie ejecutada.
    MontajeEstructuraTorreDetalle.objects.create(
        proyecto=proyecto_122, torre=t3, montaje_fecha_fin=None,
    )
    return proyecto_122


# ===========================================================================
# 1. serie_planeado_oc_fechas — acumula por fecha_esperada
# ===========================================================================

@pytest.mark.django_db
def test_planeado_oc_acumula_por_fecha_esperada(oc_torres_122):
    s = car.serie_planeado_oc_fechas(oc_torres_122)
    # 4 torres aplica con fecha_esperada → 4 puntos ordenados por fecha.
    assert s['labels'] == ['2025-01-10', '2025-02-10', '2025-03-05', '2025-04-01']
    # Denominador = 4 torres aplica (la no-aplica NO cuenta). Acum 1,2,3,4 → 25/50/75/100.
    assert s['planeado'] == [25.0, 50.0, 75.0, 100.0]


@pytest.mark.django_db
def test_planeado_oc_etiquetas_son_2025_no_2026(oc_torres_122):
    """Root cause #122: las etiquetas vienen de fecha_esperada (2025), NO de
    updated_at (2026, por crearse hoy)."""
    s = car.serie_planeado_oc_fechas(oc_torres_122)
    anios = {lab[:4] for lab in s['labels']}
    assert anios == {'2025'}
    assert '2026' not in anios


# ===========================================================================
# 2. serie_ejecutado_oc_fechas — acumula por fecha_final, refleja cerradas
# ===========================================================================

@pytest.mark.django_db
def test_ejecutado_oc_acumula_por_fecha_final(oc_torres_122):
    s = car.serie_ejecutado_oc_fechas(oc_torres_122)
    # 3 torres aplica con fecha_final (T4 tiene final NULL → no aporta).
    assert s['labels'] == ['2025-01-15', '2025-02-20', '2025-03-10']
    # Denominador = 4 torres aplica → acum 1,2,3 sobre 4 = 25/50/75.
    assert s['ejecutado'] == [25.0, 50.0, 75.0]


@pytest.mark.django_db
def test_ejecutado_oc_ultimo_punto_refleja_torres_cerradas(oc_torres_122):
    """El último punto = nº de torres con fecha_final / total aplica * 100.

    3 cerradas / 4 aplica = 75.0 (NO 100 — T4 sigue abierta)."""
    s = car.serie_ejecutado_oc_fechas(oc_torres_122)
    assert s['ejecutado'][-1] == 75.0


@pytest.mark.django_db
def test_ejecutado_oc_etiquetas_son_2025_no_2026(oc_torres_122):
    """Las etiquetas de la serie ejecutada son 2025 (fecha_final), no 2026."""
    s = car.serie_ejecutado_oc_fechas(oc_torres_122)
    anios = {lab[:4] for lab in s['labels']}
    assert anios == {'2025'}
    assert '2026' not in anios


# ===========================================================================
# 3. serie_ejecutado_montaje_fechas — acumula por montaje_fecha_fin
# ===========================================================================

@pytest.mark.django_db
def test_ejecutado_montaje_acumula_por_fecha_fin(montaje_torres_122):
    s = car.serie_ejecutado_montaje_fechas(montaje_torres_122)
    # 2 torres con montaje_fecha_fin (la 3ª es NULL → no aporta).
    assert s['labels'] == ['2025-05-10', '2025-06-15']
    # Denominador = 3 torres aplica → acum 1,2 sobre 3 ≈ 33.33 / 66.67.
    assert s['ejecutado'] == [33.33, 66.67]


@pytest.mark.django_db
def test_ejecutado_montaje_etiquetas_son_2025(montaje_torres_122):
    s = car.serie_ejecutado_montaje_fechas(montaje_torres_122)
    anios = {lab[:4] for lab in s['labels']}
    assert anios == {'2025'}
    assert '2026' not in anios


# ===========================================================================
# 4. gantt_oc — barra por torre, ordenada, solo con fecha_inicio
# ===========================================================================

@pytest.mark.django_db
def test_gantt_oc_una_fila_por_torre_con_inicio(oc_torres_122):
    g = car.gantt_oc(oc_torres_122)
    # 4 torres aplica con fecha_inicio (la no-aplica se excluye).
    assert len(g) == 4
    torres = [f['torre'] for f in g]
    # Orden numérico natural T-1, T-2, T-3, T-4.
    assert torres == ['T-1', 'T-2', 'T-3', 'T-4']


@pytest.mark.django_db
def test_gantt_oc_fechas_iso_y_final_nullable(oc_torres_122):
    g = car.gantt_oc(oc_torres_122)
    primera = g[0]
    assert primera['inicio'] == '2025-01-02'
    assert primera['esperada'] == '2025-01-10'
    assert primera['final'] == '2025-01-15'
    # T4 (última) tiene fecha_final None → debe quedar None en el Gantt.
    ultima = g[-1]
    assert ultima['torre'] == 'T-4'
    assert ultima['final'] is None


@pytest.mark.django_db
def test_gantt_oc_excluye_torre_no_aplica(oc_torres_122):
    g = car.gantt_oc(oc_torres_122)
    assert 'T-5' not in [f['torre'] for f in g]


# ===========================================================================
# 5. Edge cases — proyecto sin datos no revienta
# ===========================================================================

@pytest.mark.django_db
def test_series_vacias_proyecto_sin_datos(proyecto_122):
    assert car.serie_planeado_oc_fechas(proyecto_122) == {'labels': [], 'planeado': []}
    assert car.serie_ejecutado_oc_fechas(proyecto_122) == {'labels': [], 'ejecutado': []}
    assert car.serie_ejecutado_montaje_fechas(proyecto_122) == {'labels': [], 'ejecutado': []}
    assert car.gantt_oc(proyecto_122) == []
