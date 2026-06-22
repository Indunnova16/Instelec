"""#122 (rebote): los 6 KPIs técnico-financieros + ANS deben aparecer en el
Dashboard de Indicadores (/indicadores/), no solo en /financiero/."""

import pytest
from django.urls import reverse


@pytest.mark.django_db
class Test122IndicadoresKPIs:
    def test_helper_devuelve_6_kpis_y_ans(self):
        from apps.financiero.indicadores_finv2 import contexto_indicadores_finv2

        ctx = contexto_indicadores_finv2(anio=2026, mes=0)
        assert len(ctx["indicadores_tecnico_financieros"]) == 6
        assert len(ctx["indicadores_ans"]) == 9
        assert "resumen_ans" in ctx

    def test_dashboard_indicadores_expone_kpis(self, client, admin_user, user_password):
        client.force_login(admin_user)
        resp = client.get(reverse("indicadores:dashboard"))
        assert resp.status_code == 200
        # #122: el dashboard que ve el cliente ahora trae las 2 tablas nuevas.
        assert len(resp.context["indicadores_tecnico_financieros"]) == 6
        assert len(resp.context["indicadores_ans"]) == 9


@pytest.mark.django_db
class Test122VentanaMesAgregaElAnio:
    """#122 (rebote, FIX_INCOMPLETO): el bug del 0.00% era la VENTANA de mes.

    DashboardView pasaba mes=hoy.month (el mes actual) a
    contexto_indicadores_finv2, ventaneando los 6 KPIs a un solo mes. El
    presupuesto REAL del año puede vivir íntegramente en OTRO mes (en prod 2026:
    los $57M están en MARZO, junio = $0) → los KPIs daban 0.00% aunque el año sí
    tuviera datos. El fix: pasar mes=0 (agregación anual, paridad con
    /financiero/). Estos tests reproducen ese escenario con la MISMA forma de
    dato legacy de prod: ``costos_variables.MO.'Nómina operación'`` cargado en
    marzo, no en el mes corriente.
    """

    MONTO_MARZO = 54_122_992  # == 'Nómina operación' REAL marzo 2026 en prod
    INGRESO_MARZO = 80_000_000  # ingreso del mismo mes para margen != -100%

    def _crear_presupuesto_real_en_marzo(self, anio):
        """Crea un PresupuestoDetallado REAL con el gasto+ingreso SOLO en marzo,
        replicando la forma de los datos legacy de prod (todo en un mes que no es
        el corriente)."""
        from apps.financiero.models_base import PresupuestoDetallado
        from apps.financiero.views import _build_empty_datos

        datos = _build_empty_datos()
        # El gasto REAL del año vive enteramente en marzo (idx 2), igual que prod.
        datos["costos_variables"]["MO"]["Nómina operación"]["marzo"] = self.MONTO_MARZO
        datos["ingreso_proyectado"]["marzo"] = self.INGRESO_MARZO
        return PresupuestoDetallado.objects.create(
            anio=anio,
            tipo="REAL",
            contrato=None,
            datos=datos,
        )

    def _margen_operativo(self, ctx):
        """Devuelve el valor_num del KPI 'Margen Operativo del Proyecto'."""
        for kpi in ctx["indicadores_tecnico_financieros"]:
            if "Margen Operativo" in kpi["nombre"]:
                return kpi["valor_num"]
        raise AssertionError("No se encontró el KPI Margen Operativo")

    def test_mes0_agrega_el_anio_y_da_kpi_no_cero(self):
        """Con el fix (mes=0) los KPIs agregan el año completo → capturan marzo
        → el Margen Operativo es != 0.00% (antes daba 0.00% por ventanear)."""
        from apps.financiero.indicadores_finv2 import contexto_indicadores_finv2

        anio = 2026
        self._crear_presupuesto_real_en_marzo(anio)

        ctx = contexto_indicadores_finv2(anio=anio, mes=0, contrato=None)
        margen = self._margen_operativo(ctx)
        assert margen != 0, (
            "mes=0 debe agregar el año completo y capturar el gasto de marzo; "
            f"el Margen Operativo salió {margen} (esperado != 0)"
        )

    def test_mes_corriente_vacio_reproduce_el_bug_cero(self):
        """Contra-prueba: el comportamiento VIEJO (ventana al mes corriente,
        que está vacío) reproduce el bug 0.00%. Esto confirma que el fix (mes=0),
        no otro cambio, es lo que mueve el KPI de 0 a != 0."""
        from django.utils import timezone

        from apps.financiero.indicadores_finv2 import contexto_indicadores_finv2

        anio = 2026
        self._crear_presupuesto_real_en_marzo(anio)

        mes_corriente = timezone.now().month
        if mes_corriente == 3:
            pytest.skip("El mes corriente es marzo: no hay 'mes vacío' que reproduzca el bug")

        ctx_viejo = contexto_indicadores_finv2(anio=anio, mes=mes_corriente, contrato=None)
        margen_viejo = self._margen_operativo(ctx_viejo)
        assert margen_viejo == 0, (
            f"Ventanear al mes corriente vacío debe dar 0.00% (el bug); salió {margen_viejo}"
        )

    def test_dashboard_view_usa_mes0_y_expone_kpi_no_cero(self, client, admin_user):
        """E2E de vista: GET /indicadores/ default (sin ?mes) — DashboardView ya
        NO ventanea al mes actual, pasa mes=0 → el Margen Operativo en el contexto
        del dashboard que ve el cliente es != 0 aunque el dato esté en marzo."""
        from datetime import date

        anio = date.today().year
        # Cargamos el dato en marzo del año corriente para que el GET default
        # (anio=hoy.year) lo lea con la agregación anual del fix.
        self._crear_presupuesto_real_en_marzo(anio)

        client.force_login(admin_user)
        resp = client.get(reverse("indicadores:dashboard"))
        assert resp.status_code == 200
        margen = self._margen_operativo(
            {"indicadores_tecnico_financieros": resp.context["indicadores_tecnico_financieros"]}
        )
        if date.today().month == 3:
            # En marzo el viejo comportamiento también lo captaría; el fix igual
            # debe dar != 0.
            assert margen != 0
        else:
            assert margen != 0, (
                "El dashboard /indicadores/ debe agregar el año (mes=0) y exponer "
                f"el Margen Operativo != 0; salió {margen}"
            )
