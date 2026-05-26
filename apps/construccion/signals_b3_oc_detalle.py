"""B2a (#74) — Signal: post_save de ObraCivilTorreDetalle → recalcula cache.

ObraCivilTorre se mantiene como capa agregada por torre (cache para
dashboards rápidos / matrices torre×columna). Cuando se guarda un
ObraCivilTorreDetalle (granularidad torre × pata) este signal promedia las
4 patas y actualiza los `avance_*` de la torre agregada.

Es idempotente: si solo existen 1-3 patas todavía, promedia las que haya.
Si no existe `ObraCivilTorre` se crea para mantener el cache fresco.
"""
from decimal import Decimal

from django.db.models import Avg, Case, DecimalField, Value, When
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle


@receiver(post_save, sender=ObraCivilTorreDetalle)
def recalcular_obra_civil_torre(sender, instance, **kwargs):
    """Promedio sobre las 4 patas → ObraCivilTorre.avance_* (cache)."""
    # Import perezoso para evitar ciclo en import time
    from apps.construccion.models import ObraCivilTorre

    detalles = ObraCivilTorreDetalle.objects.filter(torre_id=instance.torre_id)

    # Para cerr_finalizado_ok (Boolean) lo convertimos a Decimal 0/1 antes
    # de promediar. Para los `_pct` ya es Decimal.
    agg = detalles.aggregate(
        cerr_avg=Avg(
            Case(
                When(cerr_finalizado_ok=True, then=Value(Decimal('1'))),
                default=Value(Decimal('0')),
                output_field=DecimalField(max_digits=5, decimal_places=4),
            )
        ),
        exc_avg=Avg('exc_ejecutada_pct'),
        sol_avg=Avg('sol_ejecutado_pct'),
        ace_avg=Avg('ace_instalacion_pct'),
        vac_avg=Avg('vac_ejecutado_pct'),
        com_avg=Avg('com_finalizada_pct'),
    )

    def _d(v):
        """Coerce aggregate (Decimal|None|float) to Decimal default 0."""
        if v is None:
            return Decimal('0')
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))

    ObraCivilTorre.objects.update_or_create(
        torre_id=instance.torre_id,
        defaults={
            'proyecto_id': instance.proyecto_id,
            'avance_cerramiento': _d(agg['cerr_avg']),
            'avance_excavacion': _d(agg['exc_avg']),
            'avance_solado': _d(agg['sol_avg']),
            'avance_acero': _d(agg['ace_avg']),
            'avance_vaciado': _d(agg['vac_avg']),
            'avance_compactacion': _d(agg['com_avg']),
        },
    )
