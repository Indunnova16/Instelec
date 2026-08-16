"""Reglas de disponibilidad de personal para Programación Semanal (#225)."""
from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError
from django.db.models import Q

from apps.cuadrillas.models import PersonalCuadrilla

from .models import AsignacionPersonalProyectoConstruccion


def _validar_intervalo(fecha_inicio, fecha_fin):
    if not isinstance(fecha_inicio, date) or not isinstance(fecha_fin, date):
        raise ValidationError('Ingrese un intervalo de fechas válido.')
    if fecha_fin < fecha_inicio:
        raise ValidationError('La fecha final no puede ser anterior a la inicial.')


def personal_elegible(proyecto_id, fecha_inicio, fecha_fin):
    """Devuelve el personal habilitado y libre para proyecto e intervalo.

    Una aprobación abierta sigue vigente; una asignación a otra programación que
    se cruce, incluso en otro proyecto, impide ofrecer a la persona dos veces.
    """
    _validar_intervalo(fecha_inicio, fecha_fin)
    aprobaciones_vigentes = AsignacionPersonalProyectoConstruccion.objects.filter(
        proyecto_id=proyecto_id,
        fecha_inicio__lte=fecha_fin,
    ).filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha_inicio))
    cruza_intervalo = Q(
        programaciones_semanales_psc__programacion__fecha_inicio__lte=fecha_fin,
        programaciones_semanales_psc__programacion__fecha_fin__gte=fecha_inicio,
    ) | Q(
        vehiculos_conducidos_psc__programacion__fecha_inicio__lte=fecha_fin,
        vehiculos_conducidos_psc__programacion__fecha_fin__gte=fecha_inicio,
    )
    ocupados = PersonalCuadrilla.objects.filter(cruza_intervalo)
    return PersonalCuadrilla.objects.filter(
        activo=True,
        aprobaciones_proyecto_construccion__in=aprobaciones_vigentes,
    ).filter(
        Q(fecha_ingreso__isnull=True) | Q(fecha_ingreso__lte=fecha_fin),
        Q(fecha_salida__isnull=True) | Q(fecha_salida__gte=fecha_inicio),
    ).exclude(pk__in=ocupados).select_related('rol_cuadrilla').distinct().order_by('nombre')


def validar_personal_elegible(programacion, personal_ids):
    """Valida la selección antes de persistir integrantes de ``programacion``."""
    if not getattr(programacion, 'pk', None):
        raise ValidationError('La programación debe existir antes de asignar personal.')
    ids = list(personal_ids or [])
    if len(ids) != len(set(map(str, ids))):
        raise ValidationError('No puede seleccionar la misma persona más de una vez.')
    disponibles = personal_elegible(
        programacion.proyecto_id, programacion.fecha_inicio, programacion.fecha_fin,
    )
    disponibles_ids = {str(pk) for pk in disponibles.values_list('pk', flat=True)}
    no_elegibles = [str(personal_id) for personal_id in ids if str(personal_id) not in disponibles_ids]
    if no_elegibles:
        raise ValidationError(
            'Hay personal no habilitado, inactivo, fuera de su vigencia o ya programado: '
            + ', '.join(no_elegibles)
        )
