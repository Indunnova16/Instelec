# Generated for TransMaint - financiero initial models

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('actividades', '0001_initial'),
        ('lineas', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='CostoRecurso',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creacion')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Fecha de actualizacion')),
                ('tipo', models.CharField(
                    choices=[
                        ('DIA_HOMBRE', 'Dia Hombre'),
                        ('VEHICULO', 'Vehiculo'),
                        ('VIATICO', 'Viatico'),
                        ('HERRAMIENTA', 'Herramienta'),
                        ('MATERIAL', 'Material'),
                        ('OTRO', 'Otro')
                    ],
                    max_length=20,
                    verbose_name='Tipo de recurso'
                )),
                ('descripcion', models.CharField(max_length=200, verbose_name='Descripcion')),
                ('costo_unitario', models.DecimalField(decimal_places=2, max_digits=12, verbose_name='Costo unitario')),
                ('unidad', models.CharField(default='DIA', help_text='DIA, HORA, UNIDAD, etc.', max_length=20, verbose_name='Unidad')),
                ('vigencia_desde', models.DateField(verbose_name='Vigencia desde')),
                ('vigencia_hasta', models.DateField(blank=True, null=True, verbose_name='Vigencia hasta')),
                ('activo', models.BooleanField(default=True, verbose_name='Activo')),
            ],
            options={
                'verbose_name': 'Costo de Recurso',
                'verbose_name_plural': 'Costos de Recursos',
                'db_table': 'costos_recursos',
                'ordering': ['tipo', 'descripcion'],
            },
        ),
        migrations.CreateModel(
            name='Presupuesto',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creacion')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Fecha de actualizacion')),
                ('anio', models.PositiveIntegerField(verbose_name='Ano')),
                ('mes', models.PositiveIntegerField(verbose_name='Mes')),
                ('estado', models.CharField(
                    choices=[
                        ('PROYECTADO', 'Proyectado'),
                        ('APROBADO', 'Aprobado'),
                        ('EN_EJECUCION', 'En Ejecucion'),
                        ('CERRADO', 'Cerrado')
                    ],
                    default='PROYECTADO',
                    max_length=20,
                    verbose_name='Estado'
                )),
                ('dias_hombre_planeados', models.PositiveIntegerField(default=0, verbose_name='Dias hombre planeados')),
                ('costo_dias_hombre', models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name='Costo dias hombre')),
                ('dias_vehiculo_planeados', models.PositiveIntegerField(default=0, verbose_name='Dias vehiculo planeados')),
                ('costo_vehiculos', models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name='Costo vehiculos')),
                ('viaticos_planeados', models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name='Viaticos planeados')),
                ('otros_costos', models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name='Otros costos')),
                ('total_presupuestado', models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name='Total presupuestado')),
                ('total_ejecutado', models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name='Total ejecutado')),
                ('facturacion_esperada', models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name='Facturacion esperada')),
                ('observaciones', models.TextField(blank=True, verbose_name='Observaciones')),
                ('linea', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='presupuestos',
                    to='lineas.linea',
                    verbose_name='Linea'
                )),
            ],
            options={
                'verbose_name': 'Presupuesto',
                'verbose_name_plural': 'Presupuestos',
                'db_table': 'presupuestos',
                'ordering': ['-anio', '-mes', 'linea'],
                'unique_together': {('anio', 'mes', 'linea')},
            },
        ),
        migrations.CreateModel(
            name='EjecucionCosto',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creacion')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Fecha de actualizacion')),
                ('concepto', models.CharField(max_length=200, verbose_name='Concepto')),
                ('tipo_recurso', models.CharField(
                    choices=[
                        ('DIA_HOMBRE', 'Dia Hombre'),
                        ('VEHICULO', 'Vehiculo'),
                        ('VIATICO', 'Viatico'),
                        ('HERRAMIENTA', 'Herramienta'),
                        ('MATERIAL', 'Material'),
                        ('OTRO', 'Otro')
                    ],
                    max_length=20,
                    verbose_name='Tipo de recurso'
                )),
                ('cantidad', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Cantidad')),
                ('costo_unitario', models.DecimalField(decimal_places=2, max_digits=12, verbose_name='Costo unitario')),
                ('costo_total', models.DecimalField(decimal_places=2, max_digits=14, verbose_name='Costo total')),
                ('fecha', models.DateField(verbose_name='Fecha')),
                ('presupuesto', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='ejecuciones',
                    to='financiero.presupuesto',
                    verbose_name='Presupuesto'
                )),
                ('actividad', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='costos',
                    to='actividades.actividad',
                    verbose_name='Actividad'
                )),
            ],
            options={
                'verbose_name': 'Ejecucion de Costo',
                'verbose_name_plural': 'Ejecucion de Costos',
                'db_table': 'ejecucion_costos',
                'ordering': ['-fecha'],
            },
        ),
        migrations.AddIndex(
            model_name='ejecucioncosto',
            index=models.Index(fields=['presupuesto'], name='idx_ejecucion_presupuesto'),
        ),
        migrations.AddIndex(
            model_name='ejecucioncosto',
            index=models.Index(fields=['actividad'], name='idx_ejecucion_actividad'),
        ),
        migrations.AddIndex(
            model_name='ejecucioncosto',
            index=models.Index(fields=['fecha'], name='idx_ejecucion_fecha'),
        ),
        migrations.AddIndex(
            model_name='ejecucioncosto',
            index=models.Index(fields=['tipo_recurso'], name='idx_ejecucion_tipo'),
        ),
        migrations.CreateModel(
            name='CicloFacturacion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creacion')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Fecha de actualizacion')),
                ('estado', models.CharField(
                    choices=[
                        ('INFORME_GENERADO', 'Informe Generado'),
                        ('EN_VALIDACION', 'En Validacion Cliente'),
                        ('ORDEN_ENTREGA', 'Orden de Entrega'),
                        ('FACTURA_EMITIDA', 'Factura Emitida'),
                        ('PAGO_RECIBIDO', 'Pago Recibido')
                    ],
                    default='INFORME_GENERADO',
                    max_length=20,
                    verbose_name='Estado'
                )),
                ('fecha_informe', models.DateField(blank=True, null=True, verbose_name='Fecha informe')),
                ('fecha_validacion', models.DateField(blank=True, null=True, verbose_name='Fecha validacion')),
                ('fecha_orden', models.DateField(blank=True, null=True, verbose_name='Fecha orden entrega')),
                ('fecha_factura', models.DateField(blank=True, null=True, verbose_name='Fecha factura')),
                ('fecha_pago', models.DateField(blank=True, null=True, verbose_name='Fecha pago')),
                ('monto_facturado', models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name='Monto facturado')),
                ('monto_pagado', models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name='Monto pagado')),
                ('numero_factura', models.CharField(blank=True, max_length=50, verbose_name='Numero de factura')),
                ('numero_orden', models.CharField(blank=True, max_length=50, verbose_name='Numero orden de entrega')),
                ('observaciones', models.TextField(blank=True, verbose_name='Observaciones')),
                ('presupuesto', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='ciclos_facturacion',
                    to='financiero.presupuesto',
                    verbose_name='Presupuesto'
                )),
            ],
            options={
                'verbose_name': 'Ciclo de Facturacion',
                'verbose_name_plural': 'Ciclos de Facturacion',
                'db_table': 'ciclos_facturacion',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='ciclofacturacion',
            index=models.Index(fields=['presupuesto'], name='idx_ciclo_presupuesto'),
        ),
        migrations.AddIndex(
            model_name='ciclofacturacion',
            index=models.Index(fields=['estado'], name='idx_ciclo_estado'),
        ),
    ]
