"""
Instelec#122 — Tooltip de los KPIs técnico-financieros debe incluir la FUENTE
del dato, no solo la fórmula.

El cliente pidió que el tooltip (atributo ``title``) de cada KPI del Dashboard
de Indicadores muestre el formato ``Fórmula: <…> · Fuente: <…>``. El partial
``_indicadores_tecnico_financieros.html`` (y su espejo de construcción) renderiza
``ind.fuente``; este test fija el contrato del helper:
``calcular_indicadores_tecnico_financieros()`` debe entregar la key ``fuente``
no vacía en CADA uno de los 6 dicts (en particular el KPI Margen Operativo).

Tests de cálculo del helper: ``apps/financiero/tests_b2.py``.
"""
from decimal import Decimal

import pytest

from apps.financiero.indicadores_finv2 import (
    FUENTE_TECNICO_FINANCIERA,
    calcular_indicadores_tecnico_financieros,
)


def _resumen(ingreso, variables, fijos):
    """Dict resumen como el que arma DashboardFinancieroView (mismo shape que tests_b2)."""
    total = Decimal(variables) + Decimal(fijos)
    ingreso = Decimal(ingreso)
    return {
        "ingreso": ingreso,
        "total_variables": Decimal(variables),
        "total_fijos": Decimal(fijos),
        "total_gastos": total,
        "resultado": ingreso - total,
        "desglose": [],
    }


def test_issue_122_todos_los_kpis_traen_fuente_no_vacia():
    """Los 6 KPIs técnico-financieros incluyen la key 'fuente' con texto no vacío."""
    plan = _resumen(1000, 600, 200)
    real = _resumen(1050, 500, 250)
    inds = calcular_indicadores_tecnico_financieros(plan, real)

    assert len(inds) == 6
    for ind in inds:
        assert "fuente" in ind, f"KPI sin key 'fuente': {ind['nombre']}"
        assert ind["fuente"], f"KPI con 'fuente' vacía: {ind['nombre']}"
        # La fuente es la del Presupuesto Detallado del módulo Financiero.
        assert "Financiero" in ind["fuente"]
        assert "Presupuesto Detallado" in ind["fuente"]


def test_issue_122_margen_operativo_trae_fuente():
    """Caso explícito pedido por el plan: el KPI Margen Operativo trae 'fuente'."""
    plan = _resumen(1000, 600, 200)
    real = _resumen(1050, 500, 250)
    inds = calcular_indicadores_tecnico_financieros(plan, real)

    margen = next(i for i in inds if "Margen Operativo" in i["nombre"])
    assert margen.get("fuente") == FUENTE_TECNICO_FINANCIERA
    assert margen["fuente"].strip() != ""


def test_issue_122_tooltip_template_incluye_formula_y_fuente():
    """El partial renderiza el title con 'Fórmula:' y 'Fuente:' a partir del dict."""
    from django.template import Context, Template

    plan = _resumen(1000, 600, 200)
    real = _resumen(1050, 500, 250)
    ind = calcular_indicadores_tecnico_financieros(plan, real)[1]  # Margen Operativo

    # Replica la expresión del title del partial (L49) sobre un solo KPI.
    tpl = Template(
        'title="Fórmula: {{ ind.formula }}'
        "{% if ind.fuente %} · Fuente: {{ ind.fuente }}{% endif %}\""
    )
    rendered = tpl.render(Context({"ind": ind}))
    assert "Fórmula:" in rendered
    assert "Fuente:" in rendered
    assert "Presupuesto Detallado" in rendered
