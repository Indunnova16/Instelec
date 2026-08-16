"""Consulta de personal disponible para Programación Semanal (#225)."""
from datetime import date

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseBadRequest
from django.shortcuts import render
from django.views import View

from apps.core.mixins import RoleRequiredMixin

from .models import ProyectoConstruccion
from .services_psc_disponibilidad import personal_elegible
from .views_psc_programacion import PSC_ADMIN_ROLES


class PersonalDisponiblePSCView(LoginRequiredMixin, RoleRequiredMixin, View):
    """Renderiza el partial de personas aptas para un proyecto y rango."""

    template_name = 'construccion/programacion_semanal/_personal.html'
    allowed_roles = PSC_ADMIN_ROLES

    def get(self, request, *args, **kwargs):
        proyecto_id = request.GET.get('proyecto_id')
        fecha_inicio = self._fecha(request.GET.get('fecha_inicio'))
        fecha_fin = self._fecha(request.GET.get('fecha_fin'))
        proyecto = ProyectoConstruccion.objects.filter(pk=proyecto_id).first()
        if not proyecto or not fecha_inicio or not fecha_fin:
            return self._error('Seleccione un proyecto y un intervalo de fechas válidos.')
        if fecha_fin < fecha_inicio:
            return self._error('La fecha final no puede ser anterior a la inicial.')

        personal = personal_elegible(proyecto.pk, fecha_inicio, fecha_fin)
        return render(request, self.template_name, {
            'personal_disponible': personal,
            'proyecto': proyecto,
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
            'consulta_exitosa': True,
        })

    def _error(self, message):
        return render(self.request, self.template_name, {'error': message}, status=400)

    @staticmethod
    def _fecha(value):
        try:
            return date.fromisoformat(value) if value else None
        except ValueError:
            return None
