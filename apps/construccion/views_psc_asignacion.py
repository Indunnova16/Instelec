"""Asignación manual de personal y vehículos a una programación PSC (#225, B6)."""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View

from apps.core.mixins import RoleRequiredMixin
from apps.cuadrillas.models import PersonalCuadrilla, Vehiculo

from .models import (
    ProgramacionSemanalConstruccion,
    ProgramacionSemanalConstruccionPersonal,
    ProgramacionSemanalConstruccionVehiculo,
)
from .services_psc_disponibilidad import validar_personal_elegible
from .views_psc_programacion import PSC_ADMIN_ROLES


class _PSCAsignacionAccessMixin(LoginRequiredMixin, RoleRequiredMixin):
    """Las asignaciones manuales solo pueden ser modificadas por PSC admin."""

    allowed_roles = PSC_ADMIN_ROLES
    http_method_names = ['post']

    @staticmethod
    def detalle_url(pk):
        return reverse('construccion:psc_programacion_detalle', kwargs={'pk': pk})

    def http_method_not_allowed(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(['POST'])


class ProgramacionSemanalConstruccionAgregarPersonalView(_PSCAsignacionAccessMixin, View):
    def post(self, request, pk):
        programacion = get_object_or_404(ProgramacionSemanalConstruccion, pk=pk)
        personal_ids = request.POST.getlist('personal_ids')
        categoria = request.POST.get('categoria', ProgramacionSemanalConstruccionPersonal.Categoria.OPERATIVO)
        categorias_validas = set(ProgramacionSemanalConstruccionPersonal.Categoria.values)
        if not personal_ids:
            messages.error(request, 'Seleccione al menos una persona para asignar.')
            return redirect(self.detalle_url(programacion.pk))
        if categoria not in categorias_validas:
            messages.error(request, 'Seleccione una categoría válida para el personal.')
            return redirect(self.detalle_url(programacion.pk))
        try:
            validar_personal_elegible(programacion, personal_ids)
            personas = list(PersonalCuadrilla.objects.filter(pk__in=personal_ids))
            if len(personas) != len(set(map(str, personal_ids))):
                raise ValidationError('Una o más personas seleccionadas no existen.')
            with transaction.atomic():
                # `ignore_conflicts`: un doble clic (o dos pestañas) mandaba
                # dos POST que pasaban ambos la validación previa y el segundo
                # reventaba con IntegrityError 500 contra el UniqueConstraint
                # (programacion, personal). Reasignar a alguien ya asignado es
                # idempotente, no un error que deba ver el usuario.
                ProgramacionSemanalConstruccionPersonal.objects.bulk_create([
                    ProgramacionSemanalConstruccionPersonal(
                        programacion=programacion, personal=persona, categoria=categoria,
                    )
                    for persona in personas
                ], ignore_conflicts=True)
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            messages.success(request, f'{len(personas)} persona(s) asignada(s) a la programación.')
        return redirect(self.detalle_url(programacion.pk))


class ProgramacionSemanalConstruccionQuitarPersonalView(_PSCAsignacionAccessMixin, View):
    def post(self, request, pk, personal_pk):
        programacion = get_object_or_404(ProgramacionSemanalConstruccion, pk=pk)
        eliminados, _ = ProgramacionSemanalConstruccionPersonal.objects.filter(
            programacion=programacion, personal_id=personal_pk,
        ).delete()
        if eliminados:
            messages.success(request, 'La persona fue retirada de la programación.')
        else:
            messages.error(request, 'La persona indicada no está asignada a esta programación.')
        return redirect(self.detalle_url(programacion.pk))


class ProgramacionSemanalConstruccionAgregarVehiculoView(_PSCAsignacionAccessMixin, View):
    def post(self, request, pk):
        programacion = get_object_or_404(ProgramacionSemanalConstruccion, pk=pk)
        vehiculo_id = request.POST.get('vehiculo_id')
        conductor_id = request.POST.get('conductor_id')
        if not vehiculo_id:
            messages.error(request, 'Seleccione un vehículo activo para asignar.')
            return redirect(self.detalle_url(programacion.pk))
        vehiculo = Vehiculo.objects.filter(
            pk=vehiculo_id, estado=Vehiculo.Estado.ACTIVO,
        ).first()
        if not vehiculo:
            messages.error(request, 'El vehículo no existe o no está activo.')
            return redirect(self.detalle_url(programacion.pk))
        if ProgramacionSemanalConstruccionVehiculo.objects.filter(
            programacion=programacion, vehiculo=vehiculo,
        ).exists():
            messages.error(request, 'El vehículo ya está asignado a esta programación.')
            return redirect(self.detalle_url(programacion.pk))
        conductor = None
        if conductor_id:
            conductor = PersonalCuadrilla.objects.filter(
                pk=conductor_id,
                programaciones_semanales_psc__programacion=programacion,
            ).first()
            if not conductor:
                messages.error(request, 'El conductor debe estar asignado previamente a esta programación.')
                return redirect(self.detalle_url(programacion.pk))
        # `get_or_create` en vez de `create`: el `exists()` de arriba deja una
        # ventana para que un doble clic cree dos veces y el segundo POST
        # reviente con IntegrityError 500 contra el UniqueConstraint.
        _, creado = ProgramacionSemanalConstruccionVehiculo.objects.get_or_create(
            programacion=programacion, vehiculo=vehiculo,
            defaults={'conductor': conductor},
        )
        if creado:
            messages.success(request, 'Vehículo asignado a la programación.')
        else:
            messages.error(request, 'El vehículo ya está asignado a esta programación.')
        return redirect(self.detalle_url(programacion.pk))


class ProgramacionSemanalConstruccionQuitarVehiculoView(_PSCAsignacionAccessMixin, View):
    def post(self, request, pk, vehiculo_pk):
        programacion = get_object_or_404(ProgramacionSemanalConstruccion, pk=pk)
        eliminados, _ = ProgramacionSemanalConstruccionVehiculo.objects.filter(
            programacion=programacion, vehiculo_id=vehiculo_pk,
        ).delete()
        if eliminados:
            messages.success(request, 'El vehículo fue retirado de la programación.')
        else:
            messages.error(request, 'El vehículo indicado no está asignado a esta programación.')
        return redirect(self.detalle_url(programacion.pk))
