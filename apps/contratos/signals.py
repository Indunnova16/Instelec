"""Signals para Contratos (#49)."""
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Contrato


@receiver(post_save, sender=Contrato)
def contrato_auto_proyecto_torres(sender, instance, created, **kwargs):
    """Para contratos de CONSTRUCCION con numero_torres, auto-genera
    ProyectoConstruccion + TorreConstruccion (E1..En). Idempotente.

    Regla de negocio (#49): al guardar 'número de torres', el sistema debe
    generar automáticamente las filas en todos los sub-módulos. Esto cubre
    el primer paso (proyecto + torres); los sub-módulos (PataObra, FaseTorre,
    Sociopredial, Ambiental) se generan lazy al primer acceso.
    """
    if instance.unidad_negocio != Contrato.UnidadNegocio.CONSTRUCCION:
        return
    if not instance.numero_torres:
        return
    try:
        instance.generar_proyecto_y_torres()
    except Exception:
        # No abortar el save por error en cascada; los devs verán el log.
        import logging
        logging.getLogger(__name__).exception(
            f"Error generando proyecto/torres para contrato {instance.codigo}"
        )
