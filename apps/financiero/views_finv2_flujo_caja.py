"""Pantallas y exportación del flujo de caja proyectado (#251)."""

import csv

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.views.generic import TemplateView

from apps.core.mixins import RoleRequiredMixin

from .forms_finv2_flujo_caja import FlujoCajaFiltroForm
from .services_finv2_conciliacion import resumen_conciliacion
from .services_finv2_flujo_caja import proyectar_flujo_caja


class BaseFlujoCajaView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    allowed_roles = ["admin", "director", "coordinador"]

    def datos(self):
        form = FlujoCajaFiltroForm(self.request.GET or None)
        form.is_valid()
        cleaned = form.cleaned_data if form.is_valid() else {}
        return form, proyectar_flujo_caja(
            contrato=cleaned.get("contrato"),
            horizonte_dias=cleaned.get("horizonte_dias", 90),
            porcentaje_cobro=cleaned.get("porcentaje_cobro", 90),
            escenario=cleaned.get("escenario", "base"),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form, flujo = self.datos()
        context.update(
            {"form": form, "flujo": flujo, "resumen_conciliacion": resumen_conciliacion()}
        )
        return context


class FlujoCajaDashboardView(BaseFlujoCajaView):
    template_name = "financiero/flujo_caja_dashboard.html"


class FlujoCajaCalendarioView(BaseFlujoCajaView):
    template_name = "financiero/flujo_caja_calendario.html"


class FlujoCajaEscenariosView(BaseFlujoCajaView):
    template_name = "financiero/flujo_caja_escenarios.html"


class FlujoCajaAlertasView(BaseFlujoCajaView):
    template_name = "financiero/flujo_caja_alertas.html"


class ExportarFlujoCajaCsvView(BaseFlujoCajaView):
    def get(self, request, *args, **kwargs):
        form, flujo = self.datos()
        if not form.is_valid():
            return HttpResponse("Parámetros inválidos para la proyección.", status=400)
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = "attachment; filename=flujo-caja.csv"
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(["Concepto", "Monto"])
        for key, label in (
            ("saldo_inicial", "Saldo inicial"),
            ("ingresos_proyectados", "Ingresos proyectados"),
            ("gastos_pendientes", "Gastos pendientes"),
            ("egresos_fijos", "Egresos fijos"),
            ("nomina", "Nómina"),
            ("saldo_proyectado", "Saldo proyectado"),
        ):
            writer.writerow([label, flujo[key]])
        return response
