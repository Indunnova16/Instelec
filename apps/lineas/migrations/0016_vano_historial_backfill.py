# Generated for Django 5.1.15 on 2026-07-03
# Issue #177 (sub-item A3) — Backfill de historial (SOLO INSERT).
#
# Retro-puebla un VanoHistorialEstado por cada Vano con señal de uso previo
# (estado != 'pendiente' OR observaciones no vacío OR foto presente), con
# los valores AS-IS del Vano (sin remapear ningún estado, incluyendo el dato
# legacy 'no_ejecutado'). CERO UPDATE/DELETE sobre la tabla `vanos` — ver
# Decisión HITL #1 en Instelec/SPRINTS/PLAN_2026-07-03_vanos_historial_modal.md:
# no se migra/reescribe la fila existente del vano legacy en prod.
#
# Idempotente: si el Vano ya tiene >=1 fila de historial (re-run de la
# migración), se salta. La reversa es un no-op documentado — solo crea
# filas nuevas, no hay nada "sucio" que revertir y no tiene sentido borrar
# trazabilidad ya generada al hacer un rollback de esquema.

from django.db import migrations


def _tiene_senal_de_uso_previo(vano) -> bool:
    """True si el Vano tiene algún rastro de haber sido tocado antes de
    existir el historial (estado distinto de pendiente, nota, o foto)."""
    if vano.estado != 'pendiente':
        return True
    if (vano.observaciones or '').strip():
        return True
    if vano.foto:
        return True
    return False


def backfill_historial(apps, schema_editor):
    Vano = apps.get_model('lineas', 'Vano')
    VanoHistorialEstado = apps.get_model('lineas', 'VanoHistorialEstado')
    VanoHistorialFoto = apps.get_model('lineas', 'VanoHistorialFoto')

    for vano in Vano.objects.all().iterator():
        if not _tiene_senal_de_uso_previo(vano):
            continue

        # Idempotencia — no duplicar si ya se corrió antes.
        if VanoHistorialEstado.objects.filter(vano=vano).exists():
            continue

        historial = VanoHistorialEstado.objects.create(
            vano=vano,
            usuario=vano.marcado_por,
            estado=vano.estado,  # AS-IS, sin remapear (incluye 'no_ejecutado')
            nota=vano.observaciones or '',
        )

        # `fecha` es auto_now_add=True — se sobreescribe con la fecha real
        # de marcado (si existe) para que el orden del historial refleje
        # cuándo pasó realmente, no cuándo corrió esta migración.
        if vano.fecha_marcado:
            historial.fecha = vano.fecha_marcado
            historial.save(update_fields=['fecha'])

        if vano.foto:
            # Reusa la misma referencia de storage — NO re-sube el archivo.
            VanoHistorialFoto.objects.create(
                historial=historial,
                imagen=vano.foto.name,
            )


def noop_reverse(apps, schema_editor):
    """Reversa intencional no destructiva: solo se crearon filas nuevas de
    historial, no hay ningún dato de `vanos` que restaurar. Revertir el
    historial generado no aporta nada y sí arriesga borrar trazabilidad
    real si esta migración corrió después de que el modal (A4) ya generó
    historial propio — por eso es un no-op documentado, no un DELETE."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('lineas', '0015_vanohistorialestado_vanohistorialfoto'),
    ]

    operations = [
        migrations.RunPython(backfill_historial, noop_reverse),
    ]
