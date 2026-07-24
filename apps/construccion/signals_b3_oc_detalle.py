"""B2a (#74) — Signal: post_save de ObraCivilTorreDetalle → recalcula cache.

ObraCivilTorre se mantiene como capa agregada por torre (cache para
dashboards rápidos / matrices torre×columna). Cuando se guarda un
ObraCivilTorreDetalle (granularidad torre × pata) este signal promedia las
4 patas y actualiza los `avance_*` de la torre agregada.

Es idempotente: si solo existen 1-3 patas todavía, promedia las que haya.
Si no existe `ObraCivilTorre` se crea para mantener el cache fresco.

#190 — además, un segundo receiver (`sincronizar_formatos_unicos_por_torre`,
abajo) sincroniza entre las 4 patas de la torre los 4 campos que representan
un formato técnico ÚNICO por torre en la realidad (FT-023/058/922 de
Excavación y FT-914 de Compactación) — ver docstring del receiver.
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


# #190 — 4 campos que son un formato técnico ÚNICO por torre en la realidad
# (se diligencia una sola vez para las 4 patas), pero hoy viven en el modelo
# torre×pata sin ningún mecanismo que los mantenga sincronizados entre filas.
CAMPOS_SYNC_TORRE = ['exc_ft023_ok', 'exc_ft058_ok', 'exc_ft922_ok', 'com_ft914_ok']


@receiver(post_save, sender=ObraCivilTorreDetalle)
def sincronizar_formatos_unicos_por_torre(sender, instance, **kwargs):
    """Propaga FT-023/058/922 (Excavación) y FT-914 (Compactación) a las
    otras 3 patas de la misma torre.

    Estos 4 booleanos representan un formato técnico ÚNICO por torre (no por
    pata) — el usuario lo marca en la pata que está viendo en ese momento, y
    sin este signal las otras 3 patas quedaban con el valor previo (bug
    reportado por Gabriel Valencia, ver Instelec#190).

    `form.save()` siempre persiste la fila COMPLETA (todos los campos del
    modelo, no solo los de la sección activa) — así que `instance` ya trae
    el valor vigente de los 4 campos sea cual sea la sección que el usuario
    editó. Propagar siempre es idempotente y barato (1 UPDATE de ≤3 filas).

    `QuerySet.update()` NO dispara señales Django (post_save/pre_save no se
    emiten para updates a nivel de queryset — solo `Model.save()` las
    emite), así que este UPDATE sobre las otras patas no re-entra a este
    mismo receiver ni al de `recalcular_obra_civil_torre`: sin riesgo de
    recursión, no hace falta ningún guard.
    """
    valores = {campo: getattr(instance, campo) for campo in CAMPOS_SYNC_TORRE}
    ObraCivilTorreDetalle.objects.filter(
        torre_id=instance.torre_id,
    ).exclude(pk=instance.pk).update(**valores)
