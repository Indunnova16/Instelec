# Backfill de la curva de avance REAL para los Dashboards de fase (#139 · S4).
#
# El Dashboard de Obra Civil sale en 0% porque la Curva S cuelga de
# `construccion_dashboard_semanal` (2 filas en prod) y `construccion_snapshot_avance`
# está VACÍA (0 filas) — sin snapshots no hay curva real histórica.
#
# Esta migración genera UN snapshot "hoy" por proyecto (semilla de la curva real)
# usando `SnapshotAvance.capturar`, que lee el avance real ya calculado
# (`porcentaje_avance_civil_ponderado`, montaje, tendido). Es IDEMPOTENTE: si ya
# existe un snapshot para (proyecto, hoy) hace update_or_create (no duplica) y la
# reversa es no-op (no borra datos del cliente). NO toca pesos del cronograma
# (`construccion_programacion_fase`).
#
# Nota: se usa el modelo REAL (no el histórico de `apps.get_model`) dentro de la
# RunPython porque `SnapshotAvance.capturar` depende de properties calculadas que
# no existen en el modelo histórico. Es seguro: solo genera/actualiza snapshots,
# no altera el esquema.

from datetime import date

from django.db import migrations


def backfill_snapshot_hoy(apps, schema_editor):
    """Forward: genera SnapshotAvance 'hoy' por proyecto (idempotente)."""
    try:
        from apps.construccion.models import ProyectoConstruccion, SnapshotAvance
    except Exception:
        # Si el import falla en un entorno de prueba reducido, no romper migrate.
        return

    hoy = date.today()
    for proyecto in ProyectoConstruccion.objects.all():
        try:
            SnapshotAvance.capturar(proyecto, fecha=hoy)
        except Exception:
            # Un proyecto sin torres/datos no debe abortar el backfill del resto.
            continue


def revertir_noop(apps, schema_editor):
    """Reverse: no-op — no borramos snapshots (son datos del cliente)."""
    return


class Migration(migrations.Migration):

    dependencies = [
        ('construccion', '0026_oc_clase_cimentacion'),
    ]

    operations = [
        migrations.RunPython(backfill_snapshot_hoy, revertir_noop),
    ]
