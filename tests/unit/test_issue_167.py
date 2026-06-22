"""#167: el filtro de mes/contrato del Dashboard de Indicadores (/indicadores/)
ahora SÍ ventanea los 6 KPIs técnico-financieros.

Devolución del cliente: "no pasa nada cuando hago los filtros". Causa raíz
(F2): DashboardView.get_context_data hardcodeaba ``mes=0`` al llamar a
``contexto_indicadores_finv2`` → cualquier ?mes=N era ignorado y los KPIs no
cambiaban. El fix desambigua: default anual (preserva #122) pero ?mes=N
ventanea al mes N.

Test contra dato LEGACY: usa la MISMA forma de presupuesto REAL de marzo 2026
que ya existía en prod (``costos_variables.MO.'Nómina operación'`` + ingreso,
todo en marzo) — replica la fixture de #122 — y verifica que el contexto del
dashboard con ?mes=3 difiere del default anual (?mes vacío / mes=0). Es decir:
el filtro AHORA mueve el KPI.
"""

import pytest
from django.urls import reverse

# Mismas cifras "legacy" que el corpus de #122: el presupuesto REAL del año vive
# íntegramente en marzo (idx 2), igual que en prod 2026.
MONTO_MARZO = 54_122_992  # 'Nómina operación' REAL marzo 2026 en prod
INGRESO_MARZO = 80_000_000


def _crear_presupuesto_real_en_marzo(anio):
    """Crea un PresupuestoDetallado REAL con gasto+ingreso SOLO en marzo,
    replicando la forma del dato legacy de prod."""
    from apps.financiero.models_base import PresupuestoDetallado
    from apps.financiero.views import _build_empty_datos

    datos = _build_empty_datos()
    datos["costos_variables"]["MO"]["Nómina operación"]["marzo"] = MONTO_MARZO
    datos["ingreso_proyectado"]["marzo"] = INGRESO_MARZO
    return PresupuestoDetallado.objects.create(
        anio=anio,
        tipo="REAL",
        contrato=None,
        datos=datos,
    )


def _margen_operativo(indicadores):
    for kpi in indicadores:
        if "Margen Operativo" in kpi["nombre"]:
            return kpi["valor_num"]
    raise AssertionError("No se encontró el KPI Margen Operativo")


@pytest.mark.django_db
class TestIssue167FiltroMesVentanea:
    def test_mes3_ventanea_distinto_del_anual_en_el_dashboard(self, client, admin_user):
        """Con el dato legacy de marzo cargado, el contexto del dashboard con
        ?mes=3 (ventana a marzo) debe ser DISTINTO del default anual (?mes=0 /
        sin mes), donde junio (mes corriente del bug) está vacío.

        Antes del fix mes estaba hardcodeado a 0 → ambos GET devolvían el MISMO
        Margen Operativo (el filtro no movía nada). Tras el fix, ?mes=3 captura
        marzo (!= 0) y un mes vacío da 0 → el filtro mueve el KPI.
        """
        anio = 2026
        _crear_presupuesto_real_en_marzo(anio)
        client.force_login(admin_user)

        # Default anual (mes=0): agrega los 12 meses → captura marzo → != 0.
        resp_anual = client.get(reverse("indicadores:dashboard"), {"anio": anio, "mes": 0})
        assert resp_anual.status_code == 200
        margen_anual = _margen_operativo(resp_anual.context["indicadores_tecnico_financieros"])
        assert margen_anual != 0  # el anual captura el gasto de marzo

        # Ventana a marzo (?mes=3): captura marzo → != 0.
        resp_marzo = client.get(reverse("indicadores:dashboard"), {"anio": anio, "mes": 3})
        assert resp_marzo.status_code == 200
        margen_marzo = _margen_operativo(resp_marzo.context["indicadores_tecnico_financieros"])

        # Ventana a un mes vacío (?mes=6, junio) → 0.00% (no hay dato ahí).
        resp_vacio = client.get(reverse("indicadores:dashboard"), {"anio": anio, "mes": 6})
        assert resp_vacio.status_code == 200
        margen_vacio = _margen_operativo(resp_vacio.context["indicadores_tecnico_financieros"])

        # El dato legacy de marzo SÍ se ve (anual y marzo capturan el gasto).
        assert margen_marzo != 0, (
            f"?mes=3 debe ventanear a marzo y capturar el gasto legacy; salió {margen_marzo}"
        )
        # El núcleo de #167: el filtro AHORA MUEVE el KPI. Un mes vacío difiere
        # del mes con dato → el filtro tiene efecto (antes eran idénticos).
        assert margen_vacio != margen_marzo, (
            "El filtro de mes NO mueve el KPI: ?mes=6 (vacío) y ?mes=3 (con dato) "
            f"dieron el mismo valor {margen_marzo} (bug #167 sin corregir)"
        )
        assert margen_vacio == 0, f"Un mes sin dato debe dar 0.00%; salió {margen_vacio}"

    def test_default_sin_filtro_sigue_anual_no_regresa_a_cero(self, client, admin_user):
        """Guard de no-regresión de #122: el default (sin ?mes ni ?periodo)
        DEBE seguir siendo la agregación anual (mes_kpi=0), NO ventanear al mes
        corriente (junio vacío → 0.00%). El dato vive en marzo; el default anual
        lo captura → Margen != 0."""
        from datetime import date

        anio = date.today().year
        _crear_presupuesto_real_en_marzo(anio)
        client.force_login(admin_user)

        resp = client.get(reverse("indicadores:dashboard"))
        assert resp.status_code == 200
        # El fix expone mes_kpi al template: default = anual.
        assert resp.context["mes_kpi"] == 0, (
            "Sin filtros, el default debe ser anual (mes_kpi=0) para preservar "
            f"#122; salió mes_kpi={resp.context['mes_kpi']}"
        )
        margen = _margen_operativo(resp.context["indicadores_tecnico_financieros"])
        assert margen != 0, (
            "El default anual debe capturar el gasto de marzo y dar != 0 "
            f"(preserva #122); salió {margen}"
        )
