"""
Signals para el módulo de campo.

Agregado: 1 abril 2026
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import RegistroCampo


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
