"""Vista del análisis comparativo de Producción Diaria (#252)."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.views.generic import TemplateView

from apps.core.mixins import RoleRequiredMixin

from .models_pc import ProgramacionSemanalCuadrilla
from .services_produccion_analisis import construir_analisis


class ProduccionDiariaAnalisisView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Muestra varianzas reales contra una programación semanal existente."""

    template_name = "construccion/produccion_diaria/analisis_comparativo.html"
    allowed_roles = ["admin", "director", "coordinador", "supervisor"]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        programacion = get_object_or_404(
            ProgramacionSemanalCuadrilla.objects.select_related("cuadrilla", "proyecto"),
            pk=self.kwargs["pk"],
        )
        context["analisis"] = construir_analisis(programacion)
        return context
