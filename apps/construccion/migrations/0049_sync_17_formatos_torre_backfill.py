"""#190 (reopen 2026-07-25, bounce=1) — Migration 0049: backfill de los 17
formatos únicos por torre divergentes.

Sucesora de 0048 (`sync_formatos_torre_backfill`), NO la reemplaza. 0048
reconcilió solo 4 de los 17 campos FT reales (`exc_ft023_ok`, `exc_ft058_ok`,
`exc_ft922_ok`, `com_ft914_ok`). El reopen de Indunnova (validado en vivo por
Andrea contra QA#49 Puerta de Oro) pidió la sincronización de los 17 campos
completos — esta migración reconcilia los 13 campos nuevos que 0048 no
cubría (el signal `sincronizar_formatos_unicos_por_torre` ya los sincroniza
HACIA ADELANTE desde el deploy de A1; esta migración reconcilia lo que ya
quedó divergente ANTES de este fix).

Evidencia BD prod (F2, proxy 127.0.0.1:5434, instelec_db): único proyecto
con datos es QA#49 — Puerta de Oro (65 torres); 17 torres tienen divergencia
real HOY entre patas en los 13 campos nuevos (hasta 8 campos divergentes en
una misma torre — ej. Torre E63, pata D tiene 8 de los 13 campos en False
mientras A/B/C están en True).

Política "gana True" (idéntica a 0048): por cada torre y cada uno de los 17
campos, si ALGUNA pata lo tiene en True, se fija ese campo a True en TODAS
las patas de esa torre.

Implementado vía ORM (no SQL crudo), acotado a las torres con divergencia
real. Idempotente: correr esta migración 2 veces no cambia nada la segunda
vez (la segunda corrida no encuentra divergencia -> no actualiza ninguna
fila).

Reversible: noop — igual que 0048, reconciliar datos divergentes hacia
"gana True" no tiene una operación inversa con sentido.
"""
from django.db import migrations

CAMPOS_SYNC_TORRE = [
    # Excavación (11)
    'exc_ft022_ok', 'exc_ft023_ok', 'exc_ft058_ok', 'exc_ft922_ok',
    'exc_ft929_ok', 'exc_ft923_ok', 'exc_ft924_ok', 'exc_ft925_ok',
    'exc_ft926_ok', 'exc_ft927_ok', 'exc_ft928_ok',
    # Acero (2)
    'ace_ft028_ok', 'ace_ft930_ok',
    # Vaciado (3)
    'vac_ft916_ok', 'vac_it380_ok', 'vac_ft056_ok',
    # Compactación (1)
    'com_ft914_ok',
]


def sync_17_formatos_torre_backfill(apps, schema_editor):
    """Reconcilia, por torre, los 17 campos FT con "gana True"."""
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
        ('construccion', '0048_sync_formatos_torre_backfill'),
    ]

    operations = [
        migrations.RunPython(
            sync_17_formatos_torre_backfill, reverse_code=migrations.RunPython.noop,
        ),
    ]
