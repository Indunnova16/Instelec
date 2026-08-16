"""Formulario de Programación Semanal de Construcción (#225, B2)."""
from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.views.generic import CreateView, DetailView, UpdateView

from apps.core.mixins import RoleRequiredMixin
from apps.construccion.models import (
    ProgramacionSemanalConstruccion,
    ProgramacionSemanalConstruccionPersonal,
    ProgramacionSemanalConstruccionVehiculo,
)
from apps.construccion.services_psc_disponibilidad import personal_elegible
from apps.cuadrillas.models import Vehiculo


PSC_ADMIN_ROLES = [
    'admin', 'director', 'coordinador', 'ing_residente',
    'admin_general', 'coordinador_general', 'admin_construccion',
]


class ProgramacionSemanalConstruccionForm(forms.ModelForm):
    """Valida los campos operativos antes de persistir una programación."""

    class Meta:
        model = ProgramacionSemanalConstruccion
        fields = [
            'proyecto', 'tipo_actividad', 'subactividad',
            'actividad_complementaria', 'fecha_inicio', 'fecha_fin',
            'hora_inicio', 'hora_fin', 'supervisor', 'observaciones',
        ]
        widgets = {
            'fecha_inicio': forms.DateInput(attrs={'type': 'date'}),
            'fecha_fin': forms.DateInput(attrs={'type': 'date'}),
            'hora_inicio': forms.TimeInput(attrs={'type': 'time'}),
            'hora_fin': forms.TimeInput(attrs={'type': 'time'}),
            'actividad_complementaria': forms.Textarea(attrs={'rows': 3}),
            'observaciones': forms.Textarea(attrs={'rows': 3}),
        }

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get('tipo_actividad')
        subactividad = (cleaned.get('subactividad') or '').strip()
        complementaria = (cleaned.get('actividad_complementaria') or '').strip()
        fecha_inicio = cleaned.get('fecha_inicio')
        fecha_fin = cleaned.get('fecha_fin')
        hora_inicio = cleaned.get('hora_inicio')
        hora_fin = cleaned.get('hora_fin')

        if tipo == ProgramacionSemanalConstruccion.TipoActividad.COMPLEMENTARIAS:
            if not complementaria:
                self.add_error(
                    'actividad_complementaria',
                    'Describa la actividad complementaria a realizar.',
                )
        elif not subactividad:
            self.add_error('subactividad', 'Indique la subactividad programada.')

        if fecha_inicio and fecha_fin and fecha_fin < fecha_inicio:
            self.add_error('fecha_fin', 'La fecha final no puede ser anterior a la inicial.')
        if (
            fecha_inicio and fecha_fin and fecha_inicio == fecha_fin
            and hora_inicio and hora_fin and hora_fin <= hora_inicio
        ):
            self.add_error('hora_fin', 'La hora final debe ser posterior a la inicial.')
        return cleaned


class ProgramacionSemanalConstruccionCreateView(
    LoginRequiredMixin, RoleRequiredMixin, CreateView
):
    model = ProgramacionSemanalConstruccion
    form_class = ProgramacionSemanalConstruccionForm
    template_name = 'construccion/programacion_semanal/form.html'
    allowed_roles = PSC_ADMIN_ROLES

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'titulo': 'Nueva programación semanal', 'es_edicion': False})
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'La programación semanal fue creada.')
        return response

    def get_success_url(self):
        return reverse('construccion:psc_programacion_detalle', kwargs={'pk': self.object.pk})


class ProgramacionSemanalConstruccionUpdateView(
    LoginRequiredMixin, RoleRequiredMixin, UpdateView
):
    model = ProgramacionSemanalConstruccion
    form_class = ProgramacionSemanalConstruccionForm
    template_name = 'construccion/programacion_semanal/form.html'
    allowed_roles = PSC_ADMIN_ROLES

    def get_queryset(self):
        return ProgramacionSemanalConstruccion.objects.select_related('proyecto', 'supervisor')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'titulo': 'Editar programación semanal', 'es_edicion': True})
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'La programación semanal fue actualizada.')
        return response

    def get_success_url(self):
        return reverse('construccion:psc_programacion_detalle', kwargs={'pk': self.object.pk})


class ProgramacionSemanalConstruccionDetailView(
    LoginRequiredMixin, RoleRequiredMixin, DetailView
):
    model = ProgramacionSemanalConstruccion
    template_name = 'construccion/programacion_semanal/detalle.html'
    context_object_name = 'programacion'
    # Los supervisores pueden consultar la cuadrilla, pero no cambiarla.
    allowed_roles = [*PSC_ADMIN_ROLES, 'supervisor']

    def get_queryset(self):
        return ProgramacionSemanalConstruccion.objects.select_related('proyecto', 'supervisor')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        programacion = self.object
        personal_asignado = ProgramacionSemanalConstruccionPersonal.objects.filter(
            programacion=programacion,
        ).select_related('personal__rol_cuadrilla').order_by('personal__nombre')
        vehiculos_asignados = ProgramacionSemanalConstruccionVehiculo.objects.filter(
            programacion=programacion,
        ).select_related('vehiculo', 'conductor').order_by('vehiculo__placa')
        context.update({
            # B6 — contrato de contexto para los partials de asignación.
            'personal_asignado': personal_asignado,
            'personal_disponible': personal_elegible(
                programacion.proyecto_id, programacion.fecha_inicio, programacion.fecha_fin,
            ),
            'vehiculos_asignados': vehiculos_asignados,
            'vehiculos_disponibles': Vehiculo.objects.filter(
                estado=Vehiculo.Estado.ACTIVO,
            ).exclude(
                programaciones_semanales_psc__programacion=programacion,
            ).order_by('placa'),
            'puede_gestionar': (
                self.request.user.is_superuser
                or getattr(self.request.user, 'rol', '') in PSC_ADMIN_ROLES
            ),
        })
        return context
