"""Signals para el módulo construccion (#69, #61)."""
from django.db.models.signals import pre_save
from django.dispatch import receiver

from .models import MovimientoFinanciero, PeriodoFinanciero


class PresupuestoBloqueadoError(Exception):
    """Se intentó modificar un movimiento PRESUPUESTO ya establecido."""


@receiver(pre_save, sender=MovimientoFinanciero)
def bloquear_modificacion_presupuesto(sender, instance, **kwargs):
    """#69: el PRESUPUESTO es editable una sola vez. Después solo admins
    pueden cambiarlo y solo si el período NO está cerrado.

    Reglas:
    - Si tipo=REAL → permitir siempre (salvo período cerrado).
    - Si tipo=PRESUPUESTO Y es UPDATE Y valor previo != 0 → bloquear
      (a menos que se setee `instance._override_presupuesto = True` desde
      una vista admin que confirme la edición).
    - Si período.cerrado=True → bloquear REAL también.
    """
    # Período cerrado bloquea cualquier escritura (excepto admin override)
    try:
        periodo = instance.periodo
    except PeriodoFinanciero.DoesNotExist:
        return
    if periodo and periodo.cerrado and not getattr(instance, '_override_cierre', False):
        raise PresupuestoBloqueadoError(
            f'Período {periodo} está cerrado — no acepta nuevos movimientos.'
        )

    # Bloqueo edición PRESUPUESTO (solo first-write)
    if instance.tipo != MovimientoFinanciero.Tipo.PRESUPUESTO:
        return
    if not instance.pk:
        return  # creación = primera edición, OK
    if getattr(instance, '_override_presupuesto', False):
        return  # admin confirmó la edición
    try:
        previo = MovimientoFinanciero.objects.get(pk=instance.pk)
    except MovimientoFinanciero.DoesNotExist:
        return
    if previo.valor and previo.valor != 0:
        # Ya tenía valor presupuestado → no permitir
        raise PresupuestoBloqueadoError(
            f'El PRESUPUESTO de "{previo.categoria.nombre}" para {periodo} '
            f'ya está establecido en ${previo.valor:,.0f} y no puede modificarse '
            f'(regla #69). Setear instance._override_presupuesto=True para confirmar.'
        )
