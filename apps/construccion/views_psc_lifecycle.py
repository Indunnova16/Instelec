"""Listado, duplicación y eliminación de Programación Semanal (#225, B5)."""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import ListView

from apps.core.mixins import RoleRequiredMixin

from .models import (
    ProgramacionSemanalConstruccion,
    ProgramacionSemanalConstruccionPersonal,
    ProgramacionSemanalConstruccionVehiculo,
)
from .views_psc_programacion import PSC_ADMIN_ROLES


PSC_READ_ROLES = [*PSC_ADMIN_ROLES, 'supervisor']


class _PSCReadAccessMixin(LoginRequiredMixin, RoleRequiredMixin):
    """Permite lectura administrativa o la lectura acotada de supervisores."""

    allowed_roles = PSC_READ_ROLES

    def test_func(self):
        """PSC no hereda niveles administrativos de otro módulo por accidente."""
        return (
            self.request.user.is_authenticated
            and (
                self.request.user.is_superuser
                or getattr(self.request.user, 'rol', '') in self.allowed_roles
            )
        )

    @property
    def puede_gestionar(self):
        return getattr(self.request.user, 'rol', '') in PSC_ADMIN_ROLES or self.request.user.is_superuser


class _PSCManageAccessMixin(LoginRequiredMixin, RoleRequiredMixin):
    """Las mutaciones PSC solo se habilitan a los roles operativos definidos."""

    allowed_roles = PSC_ADMIN_ROLES

    def test_func(self):
        return (
            self.request.user.is_authenticated
            and (
                self.request.user.is_superuser
                or getattr(self.request.user, 'rol', '') in self.allowed_roles
            )
        )


class ProgramacionSemanalConstruccionListView(_PSCReadAccessMixin, ListView):
    """Lista PSC; un supervisor ve solo lo que lidera o integra."""

    model = ProgramacionSemanalConstruccion
    context_object_name = 'programaciones'
    template_name = 'construccion/programacion_semanal/_tabla.html'

    def get_queryset(self):
        queryset = ProgramacionSemanalConstruccion.objects.select_related(
            'proyecto', 'supervisor',
        ).prefetch_related('asignaciones_personal__personal')
        if self.puede_gestionar:
            return queryset

        documento = (getattr(self.request.user, 'documento', '') or '').strip()
        visible = Q(supervisor=self.request.user)
        if documento:
            visible |= Q(asignaciones_personal__personal__documento=documento)
        return queryset.filter(visible).distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # B5: contrato de contexto de _tabla.html y _acciones.html.
        context['puede_gestionar'] = self.puede_gestionar
        return context


class ProgramacionSemanalConstruccionDuplicateView(_PSCManageAccessMixin, View):
    """Duplica cabecera y asignaciones sin alterar la programación origen."""

    http_method_names = ['post']

    def post(self, request, pk):
        origen = get_object_or_404(
            ProgramacionSemanalConstruccion.objects.prefetch_related(
                'asignaciones_personal', 'asignaciones_vehiculo',
            ),
            pk=pk,
        )
        with transaction.atomic():
            copia = ProgramacionSemanalConstruccion.objects.create(
                proyecto=origen.proyecto,
                tipo_actividad=origen.tipo_actividad,
                subactividad=origen.subactividad,
                actividad_complementaria=origen.actividad_complementaria,
                fecha_inicio=origen.fecha_inicio,
                fecha_fin=origen.fecha_fin,
                hora_inicio=origen.hora_inicio,
                hora_fin=origen.hora_fin,
                supervisor=origen.supervisor,
                observaciones=origen.observaciones,
            )
            ProgramacionSemanalConstruccionPersonal.objects.bulk_create([
                ProgramacionSemanalConstruccionPersonal(
                    programacion=copia,
                    personal=asignacion.personal,
                    categoria=asignacion.categoria,
                )
                for asignacion in origen.asignaciones_personal.all()
            ])
            ProgramacionSemanalConstruccionVehiculo.objects.bulk_create([
                ProgramacionSemanalConstruccionVehiculo(
                    programacion=copia,
                    vehiculo=asignacion.vehiculo,
                    conductor=asignacion.conductor,
                )
                for asignacion in origen.asignaciones_vehiculo.all()
            ])
        messages.success(request, 'La programación fue duplicada; revise las fechas antes de continuar.')
        return redirect(reverse('construccion:psc_programacion_editar', kwargs={'pk': copia.pk}))


class ProgramacionSemanalConstruccionDeleteView(_PSCManageAccessMixin, View):
    """Elimina una programación y sus asignaciones mediante el cascade del modelo."""

    http_method_names = ['post']

    def post(self, request, pk):
        programacion = get_object_or_404(ProgramacionSemanalConstruccion, pk=pk)
        programacion.delete()
        messages.success(request, 'La programación semanal fue eliminada.')
        return redirect('construccion:psc_programacion_lista')

    def get(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(['POST'])
