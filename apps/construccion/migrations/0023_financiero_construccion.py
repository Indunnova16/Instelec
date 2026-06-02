# B3 (#123) — Módulo Financiero de Construcción: 5 modelos nuevos.
# Migración escrita a mano (número 0023 pre-asignado por F1; última real 0022).
import django.db.models.deletion
import django.utils.timezone
import uuid
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('construccion', '0022_dashboard_pendientes'),
    ]

    operations = [
        migrations.CreateModel(
            name='PresupuestoDetalladoConstruccion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creación')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Fecha de actualización')),
                ('anio', models.PositiveIntegerField(verbose_name='Año')),
                ('tipo', models.CharField(choices=[('PLANEADO', 'Planeado'), ('REAL', 'Real')], default='PLANEADO', max_length=10, verbose_name='Tipo')),
                ('datos', models.JSONField(blank=True, default=dict, help_text='Estructura de costos con valores mensuales.', verbose_name='Datos')),
                ('proyecto', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='presupuestos_detallados', to='construccion.proyectoconstruccion', verbose_name='Proyecto')),
            ],
            options={
                'verbose_name': 'Presupuesto Detallado de Construcción',
                'verbose_name_plural': 'Presupuestos Detallados de Construcción',
                'db_table': 'construccion_presupuesto_detallado',
                'ordering': ['-anio', 'tipo'],
                'unique_together': {('proyecto', 'anio', 'tipo')},
            },
        ),
        migrations.CreateModel(
            name='CostosConstruccion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creación')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Fecha de actualización')),
                ('concepto', models.CharField(max_length=300, verbose_name='Concepto')),
                ('tipo_recurso', models.CharField(choices=[('MATERIAL', 'Material'), ('MANO_OBRA', 'Mano de obra'), ('EQUIPOS', 'Equipos'), ('SUBCONTRATA', 'Subcontrata'), ('OTROS', 'Otros')], default='MATERIAL', max_length=20, verbose_name='Tipo de recurso')),
                ('cantidad', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=15, verbose_name='Cantidad')),
                ('costo_unitario', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=15, verbose_name='Costo unitario')),
                ('costo_total', models.DecimalField(decimal_places=2, default=Decimal('0'), help_text='cantidad × costo_unitario. Auto-calculado en save().', max_digits=18, verbose_name='Costo total')),
                ('fecha', models.DateField(default=django.utils.timezone.now, verbose_name='Fecha')),
                ('actividad', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='costos', to='construccion.actividadfinaltorre', verbose_name='Actividad')),
                ('proyecto', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='costos', to='construccion.proyectoconstruccion', verbose_name='Proyecto')),
            ],
            options={
                'verbose_name': 'Costo de Construcción',
                'verbose_name_plural': 'Costos de Construcción',
                'db_table': 'construccion_costos',
                'ordering': ['-fecha', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='CostosActividadConstruccion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creación')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Fecha de actualización')),
                ('costo_materiales', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=18, verbose_name='Costo materiales')),
                ('costo_mano_obra', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=18, verbose_name='Costo mano de obra')),
                ('costo_equipos', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=18, verbose_name='Costo equipos')),
                ('costo_subcontratos', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=18, verbose_name='Costo subcontratos')),
                ('costo_otros', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=18, verbose_name='Costo otros')),
                ('actividad', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='costos_actividad', to='construccion.actividadfinaltorre', verbose_name='Actividad')),
            ],
            options={
                'verbose_name': 'Costo por Actividad de Construcción',
                'verbose_name_plural': 'Costos por Actividad de Construcción',
                'db_table': 'construccion_costos_actividad',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='FacturacionConstruccion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creación')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Fecha de actualización')),
                ('numero_factura', models.CharField(max_length=100, verbose_name='Número de factura')),
                ('fecha_emision', models.DateField(default=django.utils.timezone.now, verbose_name='Fecha de emisión')),
                ('monto_facturado', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=18, verbose_name='Monto facturado')),
                ('monto_pagado', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=18, verbose_name='Monto pagado')),
                ('estado', models.CharField(choices=[('EMITIDA', 'Emitida'), ('EN_VALIDACION', 'En validación'), ('PAGADA', 'Pagada')], default='EMITIDA', max_length=20, verbose_name='Estado')),
                ('observaciones', models.TextField(blank=True, verbose_name='Observaciones')),
                ('proyecto', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='facturacion', to='construccion.proyectoconstruccion', verbose_name='Proyecto')),
            ],
            options={
                'verbose_name': 'Facturación de Construcción',
                'verbose_name_plural': 'Facturación de Construcción',
                'db_table': 'construccion_facturacion',
                'ordering': ['-fecha_emision', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='IndicadorANSConstruccion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creación')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Fecha de actualización')),
                ('nombre', models.CharField(help_text='Ej: "% Cumplimiento Programación".', max_length=200, verbose_name='Nombre')),
                ('descripcion', models.TextField(blank=True, verbose_name='Descripción')),
                ('meta_porcentaje', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=6, verbose_name='Meta (%)')),
                ('peso', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, verbose_name='Peso')),
                ('periodo_anio', models.PositiveIntegerField(verbose_name='Año del período')),
                ('periodo_mes', models.PositiveSmallIntegerField(verbose_name='Mes del período')),
                ('valor_actual', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=6, verbose_name='Valor actual (%)')),
                ('estado', models.CharField(choices=[('cumplido', 'Cumplido'), ('parcial', 'Parcial'), ('incumplido', 'Incumplido')], default='incumplido', max_length=12, verbose_name='Estado')),
                ('proyecto', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='indicadores_ans', to='construccion.proyectoconstruccion', verbose_name='Proyecto')),
            ],
            options={
                'verbose_name': 'Indicador ANS de Construcción',
                'verbose_name_plural': 'Indicadores ANS de Construcción',
                'db_table': 'construccion_indicador_ans',
                'ordering': ['-periodo_anio', '-periodo_mes', 'nombre'],
            },
        ),
    ]
