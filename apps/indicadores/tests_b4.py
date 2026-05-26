"""
B4 — Tests pytest para Indicadores Mantenimiento detallado + ANS Contractual.

Cobertura:
- Test E2E ``b4_dashboard_ans_y_calc_ponderado`` (blueprint).
- IndicadorANSContractual: puntaje ponderado auto-calculado en save().
- IndicadorANSContractual: clasificacion CUMPLE / PARCIAL / NO_CUMPLE.
- IndicadorMantenimientoFinanciero: margen + desviacion auto.
- IndicadorMantenimientoTecnico: 4 indicadores auto.
- Edge: cumple_margen / cumple_desviacion / cumple_ejecucion thresholds.
- Edge: division por cero (insumos 0).
- Calculators: tendencia_ans_6_meses incluye None para periodos sin dato.
- Forms validacion.
"""
from datetime import date
from decimal import Decimal

import pytest

from apps.indicadores.calculators_b4 import (
    resumen_mensual,
    tendencia_ans_6_meses,
)
from apps.indicadores.forms_b4 import (
    IndicadorANSContractualForm,
    IndicadorMantenimientoFinancieroForm,
)
from apps.indicadores.models_b4_mantenimiento_detallado import (
    IndicadorANSContractual,
    IndicadorMantenimientoFinanciero,
    IndicadorMantenimientoTecnico,
)


# ---------------------------------------------------------------------------
# Modelo: IndicadorANSContractual
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_ans_crear_con_5_componentes_calcula_puntaje():
    """5 componentes -> puntaje ponderado correcto."""
    ans = IndicadorANSContractual.objects.create(
        fecha=date(2026, 1, 15),
        anio=2026,
        mes=1,
        cumplimiento_programacion=Decimal("100"),
        cumplimiento_ejecucion=Decimal("100"),
        cumplimiento_informacion_contractual=Decimal("100"),
        cumplimiento_informacion_ambiental=Decimal("100"),
        cumplimiento_disponibilidad_circuitos=Decimal("100"),
    )
    assert ans.puntaje_total_ans == Decimal("100.00")
    assert ans.estado_ans == IndicadorANSContractual.Estado.CUMPLE


@pytest.mark.django_db
def test_ans_puntaje_ponderado_formula_pesos():
    """Pesos: 30+30+15+15+10. Verificar suma ponderada explicita."""
    ans = IndicadorANSContractual.objects.create(
        fecha=date(2026, 2, 28),
        anio=2026,
        mes=2,
        cumplimiento_programacion=Decimal("90"),    # 90*0.30 = 27
        cumplimiento_ejecucion=Decimal("80"),       # 80*0.30 = 24
        cumplimiento_informacion_contractual=Decimal("100"),  # 100*0.15 = 15
        cumplimiento_informacion_ambiental=Decimal("100"),    # 100*0.15 = 15
        cumplimiento_disponibilidad_circuitos=Decimal("95"),  # 95*0.10 = 9.5
    )
    # Total esperado: 27 + 24 + 15 + 15 + 9.5 = 90.5
    assert ans.puntaje_total_ans == Decimal("90.50")
    assert ans.estado_ans == IndicadorANSContractual.Estado.CUMPLE


@pytest.mark.django_db
def test_ans_estado_clasificacion_parcial():
    """75 <= puntaje < 90 -> PARCIAL."""
    ans = IndicadorANSContractual.objects.create(
        fecha=date(2026, 3, 31),
        anio=2026,
        mes=3,
        cumplimiento_programacion=Decimal("80"),     # 24
        cumplimiento_ejecucion=Decimal("80"),        # 24
        cumplimiento_informacion_contractual=Decimal("80"),  # 12
        cumplimiento_informacion_ambiental=Decimal("80"),    # 12
        cumplimiento_disponibilidad_circuitos=Decimal("80"), # 8
    )
    # Total: 24+24+12+12+8 = 80
    assert ans.puntaje_total_ans == Decimal("80.00")
    assert ans.estado_ans == IndicadorANSContractual.Estado.PARCIAL


@pytest.mark.django_db
def test_ans_estado_clasificacion_no_cumple():
    """puntaje < 75 -> NO_CUMPLE."""
    ans = IndicadorANSContractual.objects.create(
        fecha=date(2026, 4, 30),
        anio=2026,
        mes=4,
        cumplimiento_programacion=Decimal("50"),
        cumplimiento_ejecucion=Decimal("50"),
        cumplimiento_informacion_contractual=Decimal("50"),
        cumplimiento_informacion_ambiental=Decimal("50"),
        cumplimiento_disponibilidad_circuitos=Decimal("50"),
    )
    # Total: 50
    assert ans.puntaje_total_ans == Decimal("50.00")
    assert ans.estado_ans == IndicadorANSContractual.Estado.NO_CUMPLE


@pytest.mark.django_db
def test_ans_recalcula_al_actualizar():
    """Edge: cambiar un componente recalcula puntaje + estado en save()."""
    ans = IndicadorANSContractual.objects.create(
        fecha=date(2026, 5, 31),
        anio=2026,
        mes=5,
        cumplimiento_programacion=Decimal("100"),
        cumplimiento_ejecucion=Decimal("100"),
        cumplimiento_informacion_contractual=Decimal("100"),
        cumplimiento_informacion_ambiental=Decimal("100"),
        cumplimiento_disponibilidad_circuitos=Decimal("100"),
    )
    assert ans.estado_ans == IndicadorANSContractual.Estado.CUMPLE

    # Bajar Programacion a 0 -> impacto 30 puntos -> 70 -> NO_CUMPLE
    ans.cumplimiento_programacion = Decimal("0")
    ans.save()
    assert ans.puntaje_total_ans == Decimal("70.00")
    assert ans.estado_ans == IndicadorANSContractual.Estado.NO_CUMPLE


@pytest.mark.django_db
def test_ans_componentes_property_render_dashboard():
    """El property componentes devuelve los 5 con la metadata para el dashboard."""
    ans = IndicadorANSContractual.objects.create(
        fecha=date(2026, 6, 30),
        anio=2026,
        mes=6,
        cumplimiento_programacion=Decimal("95"),
        cumplimiento_ejecucion=Decimal("96"),
        cumplimiento_informacion_contractual=Decimal("100"),
        cumplimiento_informacion_ambiental=Decimal("100"),
        cumplimiento_disponibilidad_circuitos=Decimal("99"),
    )
    comps = ans.componentes
    assert len(comps) == 5
    keys = [c["key"] for c in comps]
    assert keys == [
        "programacion",
        "ejecucion",
        "info_contractual",
        "info_ambiental",
        "disponibilidad",
    ]
    pesos_total = sum(c["peso"] for c in comps)
    assert pesos_total == Decimal("100")


# ---------------------------------------------------------------------------
# Modelo: IndicadorMantenimientoFinanciero
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_financiero_margen_y_desviacion_auto():
    """save() calcula margen y desviacion a partir de insumos."""
    fin = IndicadorMantenimientoFinanciero.objects.create(
        fecha=date(2026, 1, 31),
        anio=2026,
        mes=1,
        ingresos_ejecutados=Decimal("1000000"),
        costos_directos=Decimal("600000"),
        gastos=Decimal("200000"),
        costo_real=Decimal("750000"),
        costo_presupuestado=Decimal("700000"),
    )
    # Margen = (1000000 - 800000) / 1000000 = 20%
    assert fin.margen_operativo == Decimal("20.00")
    assert fin.cumple_margen is True
    # Desviacion = (750000 - 700000) / 700000 = 7.14%
    assert fin.desviacion_presupuestal == Decimal("7.14")
    assert fin.cumple_desviacion is True


@pytest.mark.django_db
def test_financiero_division_por_cero_no_revienta():
    """Edge: ingresos=0 y costo_presupuestado=0 -> indicadores en 0, no crash."""
    fin = IndicadorMantenimientoFinanciero.objects.create(
        fecha=date(2026, 1, 31),
        anio=2026,
        mes=1,
        ingresos_ejecutados=Decimal("0"),
        costo_presupuestado=Decimal("0"),
        costos_directos=Decimal("0"),
        gastos=Decimal("0"),
        costo_real=Decimal("0"),
    )
    assert fin.margen_operativo == Decimal("0")
    assert fin.desviacion_presupuestal == Decimal("0")


@pytest.mark.django_db
def test_financiero_carga_historica_preserva_percentajes():
    """Edge: si todos los insumos son 0, conservar los % enviados manualmente."""
    fin = IndicadorMantenimientoFinanciero(
        fecha=date(2025, 12, 31),
        anio=2025,
        mes=12,
        margen_operativo=Decimal("25.00"),
        desviacion_presupuestal=Decimal("15.00"),
    )
    fin.save()
    fin.refresh_from_db()
    assert fin.margen_operativo == Decimal("25.00")
    assert fin.desviacion_presupuestal == Decimal("15.00")


# ---------------------------------------------------------------------------
# Modelo: IndicadorMantenimientoTecnico
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_tecnico_calcula_4_indicadores():
    """save() calcula los 4 indicadores tecnicos."""
    tec = IndicadorMantenimientoTecnico.objects.create(
        fecha=date(2026, 1, 31),
        anio=2026,
        mes=1,
        facturacion_real=Decimal("295000"),
        meta_facturacion=Decimal("10000000"),
        produccion_real=Decimal("300"),
        meta_produccion=Decimal("10000"),
        valor_facturado=Decimal("1500000"),
        costo_cuadrilla=Decimal("100000"),
    )
    # ejecucion = 295000/10000000 * 100 = 2.95%
    assert tec.ejecucion_presupuestal == Decimal("2.9500")
    assert tec.cumple_ejecucion is True
    # produccion = 300/10000 * 100 = 3%
    assert tec.produccion_cuadrillas == Decimal("3.0000")
    assert tec.cumple_produccion is True
    # rentabilidad = 1500000/100000 = 15
    assert tec.rentabilidad_costo_fijo == Decimal("15.0000")
    assert tec.cumple_rentabilidad is True
    # meta_facturacion_general = ejecucion = 2.95 (FUERA por meta >= 100)
    assert tec.meta_facturacion_general == Decimal("2.9500")
    assert tec.cumple_meta_facturacion is False


@pytest.mark.django_db
def test_tecnico_meta_facturacion_cero_no_crash():
    """Edge: meta_facturacion=0 -> los 3 % son 0, no division error."""
    tec = IndicadorMantenimientoTecnico.objects.create(
        fecha=date(2026, 2, 28),
        anio=2026,
        mes=2,
        facturacion_real=Decimal("100000"),
        meta_facturacion=Decimal("0"),
        produccion_real=Decimal("100"),
        meta_produccion=Decimal("0"),
        valor_facturado=Decimal("100"),
        costo_cuadrilla=Decimal("0"),
    )
    assert tec.ejecucion_presupuestal == Decimal("0")
    assert tec.produccion_cuadrillas == Decimal("0")
    assert tec.rentabilidad_costo_fijo == Decimal("0")
    assert tec.meta_facturacion_general == Decimal("0")


# ---------------------------------------------------------------------------
# Calculadores
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_tendencia_ans_6_meses_incluye_none_para_huecos():
    """Edge: si falta el dato de un mes, la serie inyecta None."""
    # Solo creamos el dato actual; los 5 meses anteriores -> None.
    IndicadorANSContractual.objects.create(
        fecha=date(2026, 5, 1),
        anio=2026,
        mes=5,
        cumplimiento_programacion=Decimal("95"),
        cumplimiento_ejecucion=Decimal("95"),
        cumplimiento_informacion_contractual=Decimal("100"),
        cumplimiento_informacion_ambiental=Decimal("100"),
        cumplimiento_disponibilidad_circuitos=Decimal("98"),
    )
    data = tendencia_ans_6_meses(linea=None, hasta=date(2026, 5, 1))
    assert len(data["labels"]) == 6
    assert data["labels"][-1] == "05/2026"
    # El ultimo periodo tiene puntaje; los anteriores deben ser None.
    assert data["puntaje_total"][-1] is not None
    assert data["puntaje_total"][0] is None


@pytest.mark.django_db
def test_resumen_mensual_sin_datos_no_crash():
    """Sin datos del periodo, has_data=False y secciones=None."""
    res = resumen_mensual(linea=None, anio=2020, mes=1)
    assert res["financiero"] is None
    assert res["tecnico"] is None
    assert res["ans"] is None
    assert res["has_data"] is False


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_form_financiero_mes_invalido():
    form = IndicadorMantenimientoFinancieroForm(
        data={
            "fecha": "2026-01-01",
            "anio": 2026,
            "mes": 13,
            "ingresos_ejecutados": "1000",
            "costos_directos": "500",
            "gastos": "100",
            "costo_real": "600",
            "costo_presupuestado": "700",
            "observaciones": "",
        }
    )
    assert form.is_valid() is False
    # Django reporta el error a nivel field validator OR clean_mes.
    assert "mes" in form.errors


@pytest.mark.django_db
def test_form_ans_aplica_max_atributo_widget():
    """Los 5 widgets de % tienen min/max/step en attrs."""
    form = IndicadorANSContractualForm()
    f = form.fields["cumplimiento_programacion"]
    assert f.widget.attrs.get("min") == 0
    assert f.widget.attrs.get("max") == 100


# ---------------------------------------------------------------------------
# E2E del BLUEPRINT
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_b4_dashboard_ans_y_calc_ponderado(client, admin_user, user_password):
    """E2E: dashboard responde 200 y muestra puntaje ponderado correcto."""
    # 1) Crear ANS del mes con valores conocidos.
    ans = IndicadorANSContractual.objects.create(
        fecha=date(2026, 1, 31),
        anio=2026,
        mes=1,
        cumplimiento_programacion=Decimal("95"),    # 28.5
        cumplimiento_ejecucion=Decimal("95"),       # 28.5
        cumplimiento_informacion_contractual=Decimal("100"),  # 15
        cumplimiento_informacion_ambiental=Decimal("100"),    # 15
        cumplimiento_disponibilidad_circuitos=Decimal("98"),  # 9.8
    )
    # Total: 28.5+28.5+15+15+9.8 = 96.8
    assert ans.puntaje_total_ans == Decimal("96.80")
    assert ans.estado_ans == IndicadorANSContractual.Estado.CUMPLE

    # 2) Crear Financiero y Tecnico del mismo periodo.
    IndicadorMantenimientoFinanciero.objects.create(
        fecha=date(2026, 1, 31),
        anio=2026,
        mes=1,
        ingresos_ejecutados=Decimal("1000000"),
        costos_directos=Decimal("600000"),
        gastos=Decimal("200000"),
        costo_real=Decimal("750000"),
        costo_presupuestado=Decimal("700000"),
    )
    IndicadorMantenimientoTecnico.objects.create(
        fecha=date(2026, 1, 31),
        anio=2026,
        mes=1,
        facturacion_real=Decimal("295000"),
        meta_facturacion=Decimal("10000000"),
        produccion_real=Decimal("300"),
        meta_produccion=Decimal("10000"),
        valor_facturado=Decimal("1500000"),
        costo_cuadrilla=Decimal("100000"),
    )

    # 3) Login admin y GET dashboard.
    client.login(username=admin_user.email, password=user_password)
    resp = client.get("/indicadores/mantenimiento-v2/?anio=2026&mes=1")
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    # 4) Puntaje prominente aparece (locale es_CO usa coma).
    assert ("96.80" in body) or ("96,80" in body)
    # 5) Estado CUMPLE aparece (es el display upper en el template).
    assert "CUMPLE" in body
    # 6) Las 4 secciones titulares.
    assert "Financiero" in body
    assert "Tecnico" in body or "Técnico" in body
    assert "ANS Contractual" in body
    # 7) Margen 20% (locale-agnostic check).
    assert ("20.00" in body) or ("20,00" in body)
    # 8) Chart.js tendencia incluida.
    assert "chart-tendencia-ans" in body


@pytest.mark.django_db
def test_b4_dashboard_sin_datos_muestra_placeholder(client, admin_user, user_password):
    """Edge UI: sin medicion ANS, dashboard muestra placeholder con CTA."""
    client.login(username=admin_user.email, password=user_password)
    resp = client.get("/indicadores/mantenimiento-v2/?anio=2099&mes=12")
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    assert "Sin medicion ANS" in body


@pytest.mark.django_db
def test_b4_crud_ans_create_flow(client, admin_user, user_password):
    """E2E: GET create form -> POST crea registro -> redirect a list."""
    client.login(username=admin_user.email, password=user_password)
    # GET form
    resp = client.get("/indicadores/mantenimiento-v2/ans/nuevo/")
    assert resp.status_code == 200

    # POST submit
    resp = client.post(
        "/indicadores/mantenimiento-v2/ans/nuevo/",
        data={
            "fecha": "2026-07-01",
            "anio": 2026,
            "mes": 7,
            "cumplimiento_programacion": "95.00",
            "cumplimiento_ejecucion": "95.00",
            "cumplimiento_informacion_contractual": "100.00",
            "cumplimiento_informacion_ambiental": "100.00",
            "cumplimiento_disponibilidad_circuitos": "98.00",
            "observaciones": "Test E2E",
        },
    )
    # 302 redirect to list (success)
    assert resp.status_code == 302
    # Modelo creado y puntaje correcto
    obj = IndicadorANSContractual.objects.get(anio=2026, mes=7)
    assert obj.estado_ans == IndicadorANSContractual.Estado.CUMPLE
    assert obj.actualizado_por_id == admin_user.id
