"""
Signals para el módulo de campo.

Agregado: 1 abril 2026
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import RegistroCampo


# Mapea severidad del registro a inspection_status agregado en Línea/Torre.
_STATUS_DESDE_SEVERIDAD = {
    'CRITICA': 'CRITICA',
    'ALTA': 'CRITICA',
    'MEDIA': 'OK',
    'BAJA': 'OK',
    '': 'OK',
}


@receiver(post_save, sender=RegistroCampo)
def crear_historial_intervencion(sender, instance, created, **kwargs):
    """
    Crea un registro en HistorialIntervencion cuando se sincroniza un RegistroCampo.

    Se ejecuta cuando:
    - Se marca un registro como sincronizado
    - El registro tiene actividad, linea y cuadrilla asociados
    """
    from apps.actividades.models import HistorialIntervencion

    # Solo crear historial si está sincronizado y tiene los datos necesarios
    if not instance.sincronizado:
        return

    if not instance.actividad or not instance.actividad.linea:
        return

    # Evitar duplicados - verificar que no exista ya un historial para este registro
    if HistorialIntervencion.objects.filter(registro_campo=instance).exists():
        return

    # Determinar torre inicio y fin
    torre_inicio = None
    torre_fin = None

    if instance.actividad.torre:
        torre_inicio = instance.actividad.torre

    if instance.actividad.tramo:
        torre_inicio = instance.actividad.tramo.torre_inicio
        torre_fin = instance.actividad.tramo.torre_fin

    # Obtener cuadrilla
    cuadrilla = instance.actividad.cuadrillas.first() if instance.actividad.cuadrillas.exists() else None

    # Crear historial
    HistorialIntervencion.objects.create(
        linea=instance.actividad.linea,
        actividad=instance.actividad,
        registro_campo=instance,
        fecha_intervencion=instance.fecha_inicio,
        tipo_intervencion=instance.actividad.tipo_actividad.nombre if instance.actividad.tipo_actividad else 'N/A',
        cuadrilla=cuadrilla,
        usuario=instance.usuario,
        torre_inicio=torre_inicio,
        torre_fin=torre_fin,
        observaciones=instance.observaciones or '',
    )


@receiver(post_save, sender=RegistroCampo)
def actualizar_inspeccion_linea_torre(sender, instance, created, **kwargs):
    """Mantiene `last_inspection_*` e `inspection_status` en Línea y Torre.

    Toma efecto cuando el registro está sincronizado y tiene actividad/línea.
    Llamado en cada save porque `severidad` puede editarse después.
    """
    if not instance.sincronizado or not instance.actividad or not instance.actividad.linea:
        return

    fecha = instance.fecha_inicio.date() if instance.fecha_inicio else None
    tipo = ''
    if instance.actividad.tipo_actividad:
        tipo = instance.actividad.tipo_actividad.nombre[:50]
    status = _STATUS_DESDE_SEVERIDAD.get(instance.severidad or '', 'OK')

    linea = instance.actividad.linea
    torre = instance.actividad.torre

    # Torre: solo si el registro la tiene asociada.
    if torre is not None and fecha is not None:
        update_torre = {}
        if linea.__class__._meta.get_field('last_inspection_date') and (
            torre.last_inspection_date is None or fecha >= torre.last_inspection_date
        ):
            update_torre['last_inspection_date'] = fecha
            update_torre['last_inspection_type'] = tipo
            update_torre['inspection_status'] = status
        if update_torre:
            type(torre).objects.filter(pk=torre.pk).update(**update_torre)

    # Línea: peor estado entre torres + última fecha.
    if fecha is not None and (
        linea.last_inspection_date is None or fecha >= linea.last_inspection_date
    ):
        # Si la nueva severidad escala el status, lo refleja; si no, conserva el peor.
        nuevo_status = status
        if linea.inspection_status == 'CRITICA':
            nuevo_status = 'CRITICA'
        type(linea).objects.filter(pk=linea.pk).update(
            last_inspection_date=fecha,
            last_inspection_type=tipo,
            inspection_status=nuevo_status,
        )
