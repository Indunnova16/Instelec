"""#190 — Migration 0048: backfill de formatos únicos por torre divergentes.

Reconcilia datos HISTÓRICOS: antes de este issue, `exc_ft023_ok`,
`exc_ft058_ok`, `exc_ft922_ok` (Excavación) y `com_ft914_ok` (Compactación)
no se sincronizaban entre las 4 patas (A/B/C/D) de una misma torre —
representan un formato técnico ÚNICO por torre, pero el usuario los marcaba
en la pata que estaba viendo en ese momento (bug reportado por Gabriel
Valencia). El signal `sincronizar_formatos_unicos_por_torre`
(`signals_b3_oc_detalle.py`) resuelve esto HACIA ADELANTE (a partir de este
deploy); esta migración reconcilia lo que ya quedó divergente.

Política "gana True": por cada torre y cada uno de los 4 campos, si
`ALGUNA` pata lo tiene en True, se fija ese campo a True en TODAS las patas
de esa torre (consistente con que, en la realidad, el formato ya se
diligenció una vez para la torre completa). Implementado vía ORM (no SQL
crudo), acotado a las torres con divergencia real.

Idempotente: correr esta migración 2 veces no cambia nada la segunda vez
(la segunda corrida no encuentra divergencia → no actualiza ninguna fila).

Reversible: noop — igual que 0019 (`seed_desde_legacy`), reconciliar datos
divergentes hacia "gana True" no tiene una operación inversa con sentido
(no hay forma de reconstruir cuál pata tenía el valor "original").
"""
from django.db import migrations

CAMPOS_SYNC_TORRE = ['exc_ft023_ok', 'exc_ft058_ok', 'exc_ft922_ok', 'com_ft914_ok']


def sync_formatos_torre_backfill(apps, schema_editor):
    """Reconcilia, por torre, los 4 campos FT023/058/922/914 con "gana True"."""
    ObraCivilTorreDetalle = apps.get_model('construccion', 'ObraCivilTorreDetalle')

    torre_ids = (
        ObraCivilTorreDetalle.objects.order_by()
        .values_list('torre_id', flat=True)
        .distinct()
    )
    for torre_id in torre_ids:
        detalles = list(ObraCivilTorreDetalle.objects.filter(torre_id=torre_id))
        if not detalles:
            continue

        valores_ganadores = {}
        hay_divergencia = False
        for campo in CAMPOS_SYNC_TORRE:
            valores_pata = {getattr(d, campo) for d in detalles}
            if len(valores_pata) > 1:
                hay_divergencia = True
            valores_ganadores[campo] = any(getattr(d, campo) for d in detalles)

        # Nada que reconciliar en esta torre — evita un UPDATE no-op.
        if not hay_divergencia:
            continue

        ObraCivilTorreDetalle.objects.filter(torre_id=torre_id).update(
            **valores_ganadores
        )


class Migration(migrations.Migration):

    dependencies = [
        ('construccion', '0047_rename_opgw_a_cable_guarda'),
    ]

    operations = [
        migrations.RunPython(
            sync_formatos_torre_backfill, reverse_code=migrations.RunPython.noop,
        ),
    ]
