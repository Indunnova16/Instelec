"""Estado, historial, diferencias y exportación de conciliaciones (#250)."""

import csv
from datetime import date

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.utils.timezone import localdate
from django.views.generic import TemplateView

from apps.core.mixins import RoleRequiredMixin

from .models import Banco, ConciliacionBancaria
from .services_finv2_conciliacion import resumen_conciliacion


class BaseConciliacionReporteView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Aplica filtros seguros y comunes a los reportes de conciliación."""

    allowed_roles = ["admin", "director", "coordinador"]

    def filtros(self):
        errores = []
        fecha_inicio = self.request.GET.get("fecha_inicio", "").strip()
        fecha_fin = self.request.GET.get("fecha_fin", "").strip()
        banco_id = self.request.GET.get("banco", "").strip()
        try:
            inicio = date.fromisoformat(fecha_inicio) if fecha_inicio else None
            fin = date.fromisoformat(fecha_fin) if fecha_fin else None
        except ValueError:
            return None, None, None, ["Las fechas deben usar el formato AAAA-MM-DD."]
        if inicio and fin and inicio > fin:
            errores.append("La fecha inicial no puede ser posterior a la fecha final.")
        banco = None
        if banco_id:
            try:
                banco = Banco.objects.get(pk=banco_id, activo=True)
            except (Banco.DoesNotExist, ValidationError, ValueError):
                errores.append("El banco seleccionado no existe o está inactivo.")
        return inicio, fin, banco, errores

    def queryset_filtrado(self):
        inicio, fin, banco, errores = self.filtros()
        queryset = ConciliacionBancaria.objects.select_related(
            "movimiento", "movimiento__banco", "factura_gasto", "ciclo_ingreso", "usuario_override"
        )
        if errores:
            return queryset.none(), inicio, fin, banco, errores
        if inicio:
            queryset = queryset.filter(movimiento__fecha__gte=inicio)
        if fin:
            queryset = queryset.filter(movimiento__fecha__lte=fin)
        if banco:
            queryset = queryset.filter(movimiento__banco=banco)
        return queryset, inicio, fin, banco, errores

    def contexto_filtros(self, **kwargs):
        queryset, inicio, fin, banco, errores = self.queryset_filtrado()
        return {
            "conciliaciones": queryset,
            "bancos": Banco.objects.filter(activo=True).order_by("nombre"),
            "filtros": {
                "fecha_inicio": inicio.isoformat()
                if inicio
                else self.request.GET.get("fecha_inicio", ""),
                "fecha_fin": fin.isoformat() if fin else self.request.GET.get("fecha_fin", ""),
                "banco": str(banco.pk) if banco else self.request.GET.get("banco", ""),
            },
            "errores_filtro": errores,
            **kwargs,
        }


class EstadoConciliacionView(BaseConciliacionReporteView):
    template_name = "financiero/conciliacion_estado.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filtro = self.contexto_filtros()
        context.update(filtro)
        inicio, fin, banco, _ = self.filtros()
        resumen = (
            resumen_conciliacion(
                fecha_inicio=inicio,
                fecha_fin=fin,
                banco_id=banco.pk if banco else None,
            )
            if not filtro["errores_filtro"]
            else {
                "total": 0,
                "conciliadas": 0,
                "pendientes": 0,
                "diferencias": 0,
                "monto_diferencias": 0,
            }
        )
        context["resumen"] = resumen
        context["porcentaje_conciliado"] = (
            (resumen["conciliadas"] * 100 / resumen["total"]) if resumen["total"] else 0
        )
        return context


class HistorialConciliacionView(BaseConciliacionReporteView):
    template_name = "financiero/conciliacion_historial.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.contexto_filtros())
        return context


class DiferenciasConciliacionView(BaseConciliacionReporteView):
    template_name = "financiero/conciliacion_diferencias.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filtro = self.contexto_filtros()
        filtro["conciliaciones"] = filtro["conciliaciones"].filter(
            estado=ConciliacionBancaria.Estado.DIFERENCIA
        )
        context.update(filtro)
        return context


class ExportarConciliacionCsvView(BaseConciliacionReporteView):
    """Entrega exactamente el conjunto filtrado que muestran los reportes."""

    def get(self, request, *args, **kwargs):
        queryset, _, _, _, errores = self.queryset_filtrado()
        if errores:
            return HttpResponse("; ".join(errores), status=400, content_type="text/plain")
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="conciliacion-{localdate().isoformat()}.csv"'
        )
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(
            [
                "Fecha",
                "Referencia",
                "Banco",
                "Monto",
                "Estado",
                "Documento",
                "Diferencia",
                "Override",
            ]
        )
        for conciliacion in queryset.order_by("-movimiento__fecha", "-created_at"):
            documento = conciliacion.factura_gasto or conciliacion.ciclo_ingreso
            writer.writerow(
                [
                    conciliacion.movimiento.fecha.isoformat(),
                    conciliacion.movimiento.referencia,
                    conciliacion.movimiento.banco.nombre,
                    conciliacion.movimiento.monto,
                    conciliacion.get_estado_display(),
                    getattr(documento, "numero_documento", None)
                    or getattr(documento, "numero_factura", ""),
                    conciliacion.diferencia,
                    "Sí" if conciliacion.es_override else "No",
                ]
            )
        return response
