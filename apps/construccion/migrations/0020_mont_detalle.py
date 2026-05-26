"""B3a — MontajeEstructuraTorreDetalle (paridad CANT MONTAJE Excel #76).

CreateModel + RunPython seed que propaga 1 detalle por torre desde el cache
legacy `MontajeEstructuraTorre.avance_*` y `FaseTorre.entrega_carga_ok`.

NÚMERO PRE-ASIGNADO (0020). NO depende de B2a/0019 — el merge 0021 los une
para evitar el conflicto multiple-leaf-nodes (lección
feedback_modulo_f3_migration_conflict).
"""
from decimal import Decimal
import uuid

import django.db.models.deletion
from django.db import migrations, models


def seed_desde_legacy(apps, schema_editor):
    """Crea 1 MontajeEstructuraTorreDetalle por cada MontajeEstructuraTorre
    existente, propagando los 4 avances legacy (0..1) a sus booleans
    equivalentes (>=0.99 → True) y leyendo entrega_carga_ok desde FaseTorre
    si existe la fase asociada a la misma torre.
    """
    MontajeEstructuraTorre = apps.get_model('construccion', 'MontajeEstructuraTorre')
    MontajeEstructuraTorreDetalle = apps.get_model(
        'construccion', 'MontajeEstructuraTorreDetalle'
    )
    FaseTorre = apps.get_model('construccion', 'FaseTorre')

    UMBRAL = Decimal('0.99')

    for legacy in MontajeEstructuraTorre.objects.select_related('torre', 'proyecto').all():
        # Mapear avances legacy (Decimal 0..1) → booleans del detalle.
        defaults = {
            'proyecto': legacy.proyecto,
            'estructura_en_sitio_ok': (legacy.avance_estructura_sitio or Decimal('0')) >= UMBRAL,
            'prearmada_ok': (legacy.avance_prearamada or Decimal('0')) >= UMBRAL,
            'torre_montada_ok': (legacy.avance_torre_montada or Decimal('0')) >= UMBRAL,
            'revisada_ok': (legacy.avance_revisada or Decimal('0')) >= UMBRAL,
        }

        # entregada_para_carga_ok se lee de FaseTorre (si existe la fase).
        fase = FaseTorre.objects.filter(torre=legacy.torre).first()
        if fase is not None:
            defaults['entregada_para_carga_ok'] = bool(
                getattr(fase, 'entrega_carga_ok', False)
            )

        # update_or_create por si una corrida previa ya seeded esta torre
        # (idempotencia ante re-run del RunPython en CI).
        MontajeEstructuraTorreDetalle.objects.update_or_create(
            torre=legacy.torre,
            defaults=defaults,
        )


class Migration(migrations.Migration):

    dependencies = [
        # IMPORTANTE: NO depender de 0019 (B2a). El merge 0021 los une.
        ('construccion', '0018_merge_b1_b2_0017'),
    ]

    operations = [
        migrations.CreateModel(
            name='MontajeEstructuraTorreDetalle',
            fields=[
                ('id', models.UUIDField(
                    default=uuid.uuid4, editable=False,
                    primary_key=True, serialize=False, verbose_name='ID',
                )),
                ('created_at', models.DateTimeField(
                    auto_now_add=True, verbose_name='Fecha de creación',
                )),
                ('updated_at', models.DateTimeField(
                    auto_now=True, verbose_name='Fecha de actualización',
                )),
                ('tipo_torre', models.CharField(
                    blank=True, max_length=10,
                    choices=[
                        ('A', 'A — Suspensión'),
                        ('A_esp', 'A especial — Suspensión'),
                        ('B', 'B — Retención'),
                        ('C', 'C — Retención'),
                        ('D', 'D — Retención'),
                        ('portico', 'Pórtico — Retención'),
                    ],
                    verbose_name='Tipo de torre',
                )),
                ('cuerpo', models.CharField(
                    blank=True, max_length=30,
                    help_text='Identificador del cuerpo según planos del proyecto',
                    verbose_name='Cuerpo / tramo',
                )),
                ('fecha_recibida_patio', models.DateField(
                    blank=True, null=True,
                    verbose_name='Fecha de recepción en patio',
                )),
                ('recepcion_sin_pendientes_ok', models.BooleanField(
                    default=False, verbose_name='Recibida sin pendientes',
                )),
                ('recepcion_observaciones', models.TextField(
                    blank=True, verbose_name='Observaciones de recepción',
                )),
                ('prearmado_encargado', models.CharField(
                    blank=True, max_length=100,
                    verbose_name='Encargado pre-armado',
                )),
                ('estructura_en_sitio_ok', models.BooleanField(
                    default=False, verbose_name='Estructura en sitio (peso 10%)',
                )),
                ('prearmado_fecha_inicio', models.DateField(
                    blank=True, null=True,
                    verbose_name='Pre-armado — fecha inicio',
                )),
                ('prearmado_fecha_fin', models.DateField(
                    blank=True, null=True,
                    verbose_name='Pre-armado — fecha fin',
                )),
                ('prearmada_ok', models.BooleanField(
                    default=False, verbose_name='Prearmada (peso 20%)',
                )),
                ('prearmado_pct', models.DecimalField(
                    decimal_places=2, default=Decimal('0'), max_digits=5,
                    help_text='0..100 (avance granular si la torre no está 100% prearmada)',
                    verbose_name='% avance pre-armado',
                )),
                ('montaje_encargado', models.CharField(
                    blank=True, max_length=100,
                    verbose_name='Encargado montaje',
                )),
                ('montaje_fecha_inicio', models.DateField(
                    blank=True, null=True,
                    verbose_name='Montaje — fecha inicio',
                )),
                ('montaje_fecha_fin', models.DateField(
                    blank=True, null=True,
                    verbose_name='Montaje — fecha fin',
                )),
                ('torre_montada_ok', models.BooleanField(
                    default=False, verbose_name='Torre montada (peso 45%)',
                )),
                ('montaje_observaciones', models.TextField(
                    blank=True, verbose_name='Observaciones de montaje',
                )),
                ('ft032_control_montaje_ok', models.BooleanField(
                    default=False, verbose_name='FT-032 Control montaje',
                )),
                ('ft913_verticalidad_torsion_ok', models.BooleanField(
                    default=False, verbose_name='FT-913 Verticalidad y torsión',
                )),
                ('ft920_recepcion_montaje_ok', models.BooleanField(
                    default=False, verbose_name='FT-920 Recepción de montaje',
                )),
                ('revisada_ok', models.BooleanField(
                    default=False, verbose_name='Revisada (peso 25%)',
                )),
                ('entregada_para_carga_ok', models.BooleanField(
                    default=False,
                    verbose_name='Entregada para carga (habilita Tendido)',
                )),
                ('peso_diseno_kl', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=10, null=True,
                    help_text='Peso teórico según planos, en kilo-libras (kL)',
                    verbose_name='Peso diseño (kL)',
                )),
                ('peso_instalado_kl', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=10, null=True,
                    help_text='Peso real montado, en kilo-libras (kL)',
                    verbose_name='Peso instalado (kL)',
                )),
                ('facturada_a_dueno_ok', models.BooleanField(
                    default=False, verbose_name='Facturada al dueño',
                )),
                ('facturada_por_contratista', models.CharField(
                    blank=True, max_length=100,
                    help_text='Nombre del contratista que facturó (ej. Cruz, Higuita, Instelec)',
                    verbose_name='Facturada por contratista',
                )),
                ('proyecto', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='mont_detalles',
                    to='construccion.proyectoconstruccion',
                    verbose_name='Proyecto',
                )),
                ('torre', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='mont_detalle',
                    to='construccion.torreconstruccion',
                    verbose_name='Torre',
                )),
            ],
            options={
                'verbose_name': 'Montaje — Detalle por torre',
                'verbose_name_plural': 'Montaje — Detalle por torre',
                'db_table': 'construccion_mont_detalle',
                'ordering': ['torre__numero'],
            },
        ),
        migrations.RunPython(seed_desde_legacy, reverse_code=migrations.RunPython.noop),
    ]
