"""Altas de personal habilitado por proyecto para Programación Semanal (#225)."""
from __future__ import annotations

from datetime import date

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponseBadRequest
from django.shortcuts import render
from django.views import View

from apps.core.mixins import RoleRequiredMixin
from apps.cuadrillas.models import PersonalCuadrilla

from .models import (
    AsignacionPersonalProyectoConstruccion,
    ProyectoConstruccion,
)


class AprobacionPersonalProyectoView(LoginRequiredMixin, RoleRequiredMixin, View):
    """Lista y registra las ventanas en que una persona puede ser programada.

    La validación se mantiene en la vista porque este submódulo no comparte un
    formulario con las demás sub-features. El modelo admite historia de
    aprobaciones; por eso se rechazan únicamente ventanas que se solapan para
    la misma pareja proyecto-personal.
    """

    template_name = 'construccion/programacion_semanal/aprobaciones.html'

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self._context())

    def post(self, request, *args, **kwargs):
        context = self._context(request.POST)
        proyecto = self._find(ProyectoConstruccion, request.POST.get('proyecto_id'))
        personal = self._find(PersonalCuadrilla, request.POST.get('personal_id'))
        fecha_inicio = self._parse_date(request.POST.get('fecha_inicio'))
        fecha_fin = self._parse_date(request.POST.get('fecha_fin'), optional=True)

        error = self._validation_error(proyecto, personal, fecha_inicio, fecha_fin)
        if error:
            context['error'] = error
            return render(request, self.template_name, context, status=400)

        if self._has_overlap(proyecto, personal, fecha_inicio, fecha_fin):
            context['error'] = (
                'Ya existe una aprobación que se cruza con el intervalo indicado '
                'para esta persona y proyecto.'
            )
            return render(request, self.template_name, context, status=400)

        AsignacionPersonalProyectoConstruccion.objects.create(
            proyecto=proyecto,
            personal=personal,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
        )
        messages.success(
            request,
            f'{personal.nombre} quedó habilitado para {proyecto.nombre} desde '
            f'{fecha_inicio:%d/%m/%Y}.',
        )
        return render(request, self.template_name, self._context())

    @staticmethod
    def _find(model, raw_id):
        if not raw_id:
            return None
        try:
            return model.objects.get(pk=raw_id)
        except (model.DoesNotExist, ValueError, TypeError):
            return None

    @staticmethod
    def _parse_date(raw_value, optional=False):
        if not raw_value:
            return None if optional else False
        try:
            return date.fromisoformat(raw_value)
        except ValueError:
            return False

    @staticmethod
    def _validation_error(proyecto, personal, fecha_inicio, fecha_fin):
        if proyecto is None:
            return 'Seleccione un proyecto válido.'
        if personal is None:
            return 'Seleccione una persona válida.'
        if not personal.activo:
            return 'No se puede habilitar personal inactivo.'
        if not fecha_inicio:
            return 'Ingrese una fecha de inicio válida.'
        if fecha_fin is False:
            return 'Ingrese una fecha de fin válida.'
        if fecha_fin and fecha_fin < fecha_inicio:
            return 'La fecha de fin no puede ser anterior a la fecha de inicio.'
        if personal.fecha_ingreso and fecha_inicio < personal.fecha_ingreso:
            return 'La aprobación no puede iniciar antes del ingreso de la persona.'
        if personal.fecha_salida and (not fecha_fin or fecha_fin > personal.fecha_salida):
            return 'La aprobación no puede extenderse después de la salida de la persona.'
        return None

    @staticmethod
    def _has_overlap(proyecto, personal, fecha_inicio, fecha_fin):
        """Devuelve si una ventana cerrada o abierta interseca el nuevo rango."""
        aprobaciones = AsignacionPersonalProyectoConstruccion.objects.filter(
            proyecto=proyecto,
            personal=personal,
        )
        if fecha_fin:
            aprobaciones = aprobaciones.filter(fecha_inicio__lte=fecha_fin)
        return aprobaciones.filter(
            Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha_inicio)
        ).exists()

    @staticmethod
    def _context(values=None):
        values = values or {}
        return {
            'proyectos': ProyectoConstruccion.objects.order_by('nombre'),
            'personal_disponible': PersonalCuadrilla.objects.filter(activo=True).order_by('nombre'),
            'aprobaciones': AsignacionPersonalProyectoConstruccion.objects.select_related(
                'proyecto', 'personal'
            ).order_by('-fecha_inicio', 'personal__nombre'),
            'values': values,
        }
