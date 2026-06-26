"""#147: backfill del gate de Tendido.

El cliente marcaba "Entregada para carga" en el detalle de Montaje
(MontajeEstructuraTorreDetalle.entregada_para_carga_ok) pero el gate de Tendido
lee FaseTorre.entrega_carga_ok (otra tabla) → quedaba desincronizado y el letrero
🔒 persistía. El signal post_save ya propaga el flag a futuro; esta migración
sincroniza las torres YA marcadas (sin requerir re-guardar Montaje). Idempotente.
"""
from django.db import migrations


def backfill_entrega_carga(apps, schema_editor):
    FaseTorre = apps.get_model('construccion', 'FaseTorre')
    MontDetalle = apps.get_model('construccion', 'MontajeEstructuraTorreDetalle')
    marcadas = list(
        MontDetalle.objects.filter(entregada_para_carga_ok=True).values_list(
            'torre_id', flat=True
        )
    )
    if marcadas:
        FaseTorre.objects.filter(
            torre_id__in=marcadas, entrega_carga_ok=False
        ).update(entrega_carga_ok=True)


def noop_reverse(apps, schema_editor):
    # No revertimos: el flag refleja un hecho operativo (Montaje entregó la torre).
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('construccion', '0038_issue155_proyecto_coords'),
    ]

    operations = [
        migrations.RunPython(backfill_entrega_carga, noop_reverse),
    ]
