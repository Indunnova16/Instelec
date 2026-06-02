"""
B2 (#122) — Tests pytest para los indicadores del Dashboard Financiero v2.

Cobertura (tests_e2e del BLUEPRINT):
- ``b2_dashboard_render_kpis``    -> los 6 KPIs tecnico-financieros se calculan
  con valores, estados (verde/amarillo/rojo) y progreso correctos.
- ``b2_dashboard_seccion_ans``    -> la seccion ANS arma 9 filas + total
  ponderado reutilizando IndicadorANSContractual (B4).
- ``b2_filtro_anio_recalcula``    -> cambiar el periodo/insumos recalcula los
  indicadores (no hay valores hardcodeados).

Edge cases del dominio:
- Division por cero (ingreso 0, presupuesto 0).
- Margen operativo negativo -> estado rojo.
- Desviacion presupuestal dentro de banda +-5% -> verde; fuera -> amarillo/rojo.
- ANS sin registro del periodo -> placeholder "sin datos", no rompe.

NO se corren aqui (entorno sin Django). El orquestador los ejecuta en F4 Docker.
"""
from datetime import date
from decimal import Decimal

import pytest

from apps.financiero.indicadores_finv2 import (
    calcular_indicadores_tecnico_financieros,
    calcular_resumen_ans,
    _calcular_margen_operativo,
    _calcular_desviacion_presupuestal,
)
from apps.indicadores.models_b4_mantenimiento_detallado import IndicadorANSContractual


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _resumen(ingreso, variables, fijos):
    """Construye un dict resumen como el que arma DashboardFinancieroView."""
    total = Decimal(variables) + Decimal(fijos)
    ingreso = Decimal(ingreso)
    return {
        "ingreso": ingreso,
        "total_variables": Decimal(variables),
        "total_fijos": Decimal(fijos),
        "total_gastos": total,
        "resultado": ingreso - total,
        "utilidad_pct": ((ingreso - total) / ingreso * 100) if ingreso else 0,
        "desglose": [],
    }


def _por_nombre(indicadores, fragmento):
    for ind in indicadores:
        if fragmento.lower() in ind["nombre"].lower():
            return ind
    raise AssertionError(f"No se encontro indicador con '{fragmento}'")


# ---------------------------------------------------------------------------
# b2_dashboard_render_kpis — los 6 KPIs tecnico-financieros
# ---------------------------------------------------------------------------
def test_b2_dashboard_render_kpis():
    """Caso happy: 6 KPIs con valores y estados correctos."""
    # Plan: ingreso 1000, gastos 800.  Real: ingreso 1050, var 500, fijo 250 (800).
    plan = _resumen(1000, 600, 200)   # total_gastos 800
    real = _resumen(1050, 500, 250)   # total_gastos 750
    inds = calcular_indicadores_tecnico_financieros(plan, real)

    # Exactamente 6 indicadores.
    assert len(inds) == 6

    nombres = [i["nombre"] for i in inds]
    assert any("Meta de facturación" in n for n in nombres)
    assert any("Margen Operativo" in n for n in nombres)
    assert any("Desviación Presupuestal" in n for n in nombres)
    assert any("Ejecución presupuestal" in n for n in nombres)
    assert any("Producción cuadrillas" in n for n in nombres)
    assert any("Rentabilidad costo fijo" in n for n in nombres)

    # Meta facturacion: real 1050 / meta_plan 1000 = 105% -> verde.
    meta = _por_nombre(inds, "Meta de facturación")
    assert meta["valor_num"] == Decimal("105.00")
    assert meta["estado"] == "verde"

    # Margen operativo: (1050 - 750)/1050 *100 = 28.57% -> meta 20% -> verde.
    margen = _por_nombre(inds, "Margen Operativo")
    assert margen["valor_num"] == Decimal("28.57")
    assert margen["estado"] == "verde"

    # Cada indicador tiene los campos de display requeridos por el template.
    for ind in inds:
        assert set(["tipo", "nombre", "formula", "meta", "valor", "estado", "progreso"]).issubset(ind.keys())
        assert ind["estado"] in ("verde", "amarillo", "rojo")
        assert 0 <= ind["progreso"] <= 100


def test_b2_kpis_margen_negativo_es_rojo():
    """Edge: gastos > ingresos -> margen negativo -> rojo."""
    plan = _resumen(1000, 600, 200)
    real = _resumen(1000, 800, 400)   # gastos 1200 > ingreso 1000
    inds = calcular_indicadores_tecnico_financieros(plan, real)
    margen = _por_nombre(inds, "Margen Operativo")
    assert margen["valor_num"] < 0
    assert margen["estado"] == "rojo"


def test_b2_kpis_division_por_cero_no_rompe():
    """Edge: ingreso 0 y presupuesto 0 -> sin ZeroDivisionError, valores 0."""
    plan = _resumen(0, 0, 0)
    real = _resumen(0, 0, 0)
    inds = calcular_indicadores_tecnico_financieros(plan, real)
    assert len(inds) == 6
    for ind in inds:
        # ninguno explota; valor numerico definido.
        assert ind["valor_num"] is not None


def test_b2_desviacion_presupuestal_banda():
    """Desviacion dentro de +-5% -> verde; fuera -> amarillo/rojo."""
    # Real == plan -> 0% desviacion -> verde.
    inds_ok = calcular_indicadores_tecnico_financieros(
        _resumen(1000, 600, 200), _resumen(1000, 600, 200)
    )
    desv_ok = _por_nombre(inds_ok, "Desviación Presupuestal")
    assert desv_ok["valor_num"] == Decimal("0.00")
    assert desv_ok["estado"] == "verde"

    # Gasto real +8% -> fuera de banda 5% pero <=10% (2x tolerancia) -> amarillo.
    inds_amarillo = calcular_indicadores_tecnico_financieros(
        _resumen(2000, 600, 200),                 # plan gastos 800
        _resumen(2000, 700, 164),                 # real gastos 864 -> +8%
    )
    desv_a = _por_nombre(inds_amarillo, "Desviación Presupuestal")
    assert desv_a["valor_num"] == Decimal("8.00")
    assert desv_a["estado"] == "amarillo"

    # Gasto real +12% -> fuera de 2x tolerancia (>10%) -> rojo.
    inds_rojo = calcular_indicadores_tecnico_financieros(
        _resumen(2000, 600, 200),                 # plan gastos 800
        _resumen(2000, 700, 196),                 # real gastos 896 -> +12%
    )
    desv_r = _por_nombre(inds_rojo, "Desviación Presupuestal")
    assert desv_r["valor_num"] == Decimal("12.00")
    assert desv_r["estado"] == "rojo"


def test_b2_helpers_formulas():
    """Funciones de calculo puras coinciden con las formulas del issue."""
    assert _calcular_margen_operativo(1000, 600, 200) == Decimal("20")
    assert _calcular_margen_operativo(0, 100, 100) == Decimal("0")  # div0
    assert _calcular_desviacion_presupuestal(1100, 1000) == Decimal("10")
    assert _calcular_desviacion_presupuestal(900, 1000) == Decimal("-10")
    assert _calcular_desviacion_presupuestal(100, 0) == Decimal("0")  # div0


# ---------------------------------------------------------------------------
# b2_dashboard_seccion_ans — 9 filas + total ponderado
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_b2_dashboard_seccion_ans():
    """Con un registro ANS real, la seccion arma 9 filas + total ponderado del modelo."""
    ans = IndicadorANSContractual.objects.create(
        fecha=date(2026, 1, 31),
        anio=2026,
        mes=1,
        cumplimiento_programacion=Decimal("96"),
        cumplimiento_ejecucion=Decimal("98"),
        cumplimiento_informacion_contractual=Decimal("100"),
        cumplimiento_informacion_ambiental=Decimal("100"),
        cumplimiento_disponibilidad_circuitos=Decimal("99"),
    )

    resumen = calcular_resumen_ans(linea=None, anio=2026, mes=1)

    # 9 filas (5 componentes + 4 "Alt" repetidos, segun el screenshot del issue).
    assert len(resumen["filas"]) == 9
    assert resumen["sin_datos"] is False
    # El total ponderado viene de puntaje_total_ans del modelo (fuente unica).
    assert resumen["total_num"] == ans.puntaje_total_ans
    assert resumen["estado_general"] == ans.get_estado_ans_display()
    # Cada fila tiene los campos del template.
    for fila in resumen["filas"]:
        assert set(["ans", "descripcion", "peso", "meta", "valor", "estado"]).issubset(fila.keys())
        assert fila["estado"] in ("verde", "amarillo", "rojo")
    # Numeracion 1..9 consecutiva.
    assert [f["ans"] for f in resumen["filas"]] == list(range(1, 10))


@pytest.mark.django_db
def test_b2_ans_sin_registro_devuelve_placeholder():
    """Edge: sin registro ANS del periodo -> 9 filas placeholder, sin_datos True."""
    resumen = calcular_resumen_ans(linea=None, anio=2099, mes=12)
    assert resumen["sin_datos"] is True
    assert len(resumen["filas"]) == 9
    assert resumen["total_ponderado"] == "—"
    # No explota: estado_general definido.
    assert resumen["estado_general"] == "Sin datos"


# ---------------------------------------------------------------------------
# b2_filtro_anio_recalcula — cambiar periodo recalcula
# ---------------------------------------------------------------------------
def test_b2_filtro_anio_recalcula():
    """Distintos insumos (otro periodo/filtro) producen distintos valores: nada hardcodeado."""
    inds_a = calcular_indicadores_tecnico_financieros(
        _resumen(1000, 600, 200), _resumen(1050, 500, 250)
    )
    inds_b = calcular_indicadores_tecnico_financieros(
        _resumen(2000, 1200, 400), _resumen(1800, 1000, 500)
    )
    meta_a = _por_nombre(inds_a, "Meta de facturación")["valor_num"]
    meta_b = _por_nombre(inds_b, "Meta de facturación")["valor_num"]
    # Periodo A: 1050/1000=105%.  Periodo B: 1800/2000=90%.
    assert meta_a == Decimal("105.00")
    assert meta_b == Decimal("90.00")
    assert meta_a != meta_b


@pytest.mark.django_db
def test_b2_ans_filtro_periodo_recalcula():
    """ANS de distintos meses devuelve distintos totales ponderados."""
    IndicadorANSContractual.objects.create(
        fecha=date(2026, 1, 31), anio=2026, mes=1,
        cumplimiento_programacion=Decimal("100"),
        cumplimiento_ejecucion=Decimal("100"),
        cumplimiento_informacion_contractual=Decimal("100"),
        cumplimiento_informacion_ambiental=Decimal("100"),
        cumplimiento_disponibilidad_circuitos=Decimal("100"),
    )
    IndicadorANSContractual.objects.create(
        fecha=date(2026, 2, 28), anio=2026, mes=2,
        cumplimiento_programacion=Decimal("50"),
        cumplimiento_ejecucion=Decimal("50"),
        cumplimiento_informacion_contractual=Decimal("50"),
        cumplimiento_informacion_ambiental=Decimal("50"),
        cumplimiento_disponibilidad_circuitos=Decimal("50"),
    )
    ene = calcular_resumen_ans(linea=None, anio=2026, mes=1)
    feb = calcular_resumen_ans(linea=None, anio=2026, mes=2)
    assert ene["total_num"] == Decimal("100.00")
    assert feb["total_num"] == Decimal("50.00")
    assert ene["estado_color"] == "verde"
    assert feb["estado_color"] == "rojo"
