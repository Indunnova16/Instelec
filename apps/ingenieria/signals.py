"""Signals para mantener consistencia de Preliminares al crear torres.

`_sincronizar_torres` crea torres masivamente con `bulk_create`, que NO dispara
signals. Este `post_save` cubre la creación unitaria (admin, scripts, tests).
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import TorreContrato


@receiver(post_save, sender=TorreContrato)
def crear_registros_preliminares(sender, instance, created, **kwargs):
    if not created:
        return
    # Import diferido para evitar dependencia circular.
    from apps.preliminares.models import AmbientalTorre, PredialTorre
    PredialTorre.objects.get_or_create(torre=instance)
    AmbientalTorre.objects.get_or_create(torre=instance)
