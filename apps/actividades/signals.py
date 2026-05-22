"""Signals para recalcular costos cuando cambian asignaciones de cuadrilla."""
from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from .models import Actividad


@receiver(m2m_changed, sender=Actividad.cuadrillas.through)
def actividad_cuadrillas_changed(sender, instance, action, **kwargs):
    """Recalcula costo_acumulado cuando se agregan/quitan cuadrillas (tipo_costo=FIJO)."""
    if action in ('post_add', 'post_remove', 'post_clear'):
        instance.recalcular_costo()
