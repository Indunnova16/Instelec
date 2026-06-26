"""Signal B3a — post_save MontajeEstructuraTorreDetalle → recalcula cache
en MontajeEstructuraTorre legacy.

MontajeEstructuraTorre se conserva como cache agregado (4 columnas 0..1) que
alimentan el dashboard B3 y otras vistas. El detalle nuevo (#76) vive en
MontajeEstructuraTorreDetalle con booleans + ~30 campos extra. Este signal
mantiene el cache fresco cada vez que cambia el detalle.

Relación: OneToOne con TorreConstruccion en ambos lados → mapeo 1↔1 vía torre.
"""
from decimal import Decimal

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.construccion.models_b3_mont_detalle import MontajeEstructuraTorreDetalle


@receiver(post_save, sender=MontajeEstructuraTorreDetalle)
def recalcular_montaje_torre(sender, instance, **kwargs):
    """Cache fresco en MontajeEstructuraTorre desde el detalle (OneToOne).

    Mapeo bool → Decimal:
        True  → Decimal('1')
        False → Decimal('0')

    Importación lazy del modelo legacy para evitar ciclos en app loading.
    """
    # Import lazy: el sender vive en models_b3_mont_detalle pero el cache
    # legacy está en models.py — Django ya tiene ambos cargados aquí.
    from apps.construccion.models import MontajeEstructuraTorre

    MontajeEstructuraTorre.objects.update_or_create(
        torre=instance.torre,
        defaults={
            'proyecto': instance.proyecto,
            'avance_estructura_sitio': Decimal('1') if instance.estructura_en_sitio_ok else Decimal('0'),
            'avance_prearamada': Decimal('1') if instance.prearmada_ok else Decimal('0'),
            'avance_torre_montada': Decimal('1') if instance.torre_montada_ok else Decimal('0'),
            'avance_revisada': Decimal('1') if instance.revisada_ok else Decimal('0'),
        },
    )

    # #147: el cliente marca "Entregada para carga" en el detalle de Montaje
    # (instance.entregada_para_carga_ok), pero el gate de Tendido lee
    # FaseTorre.entrega_carga_ok (otra tabla) → quedaba desincronizado y el
    # letrero 🔒 persistía en Tendido. Propagamos el flag (ambos sentidos).
    from datetime import date

    from apps.construccion.models import FaseTorre

    nuevo = bool(instance.entregada_para_carga_ok)
    fase = FaseTorre.objects.filter(torre=instance.torre).first()
    if fase is not None and fase.entrega_carga_ok != nuevo:
        cambios = {'entrega_carga_ok': nuevo}
        if nuevo and not fase.entrega_carga_fecha:
            cambios['entrega_carga_fecha'] = date.today()
        FaseTorre.objects.filter(pk=fase.pk).update(**cambios)
