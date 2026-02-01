# Generated for TransMaint - InformeDiario model for daily activity reports

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('cuadrillas', '0003_cuadrillamiembro_extended_roles'),
        ('lineas', '0003_linea_transelca_fields'),
        ('actividades', '0003_actividad_sap_consignacion'),
    ]

    operations = [
        migrations.CreateModel(
            name='InformeDiario',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creacion')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Fecha de actualizacion')),
                ('fecha', models.DateField(help_text='Fecha del informe', verbose_name='Fecha')),
                ('vanos_ejecutados', models.PositiveIntegerField(default=0, help_text='Numero de vanos completados en el dia', verbose_name='Vanos ejecutados')),
                ('personal_presente', models.JSONField(blank=True, default=list, help_text='Lista de personal presente con roles [{usuario_id, nombre, rol, cargo}]', verbose_name='Personal presente')),
                ('total_personas', models.PositiveIntegerField(default=0, verbose_name='Total personas')),
                ('condicion_climatica', models.CharField(
                    choices=[
                        ('SOLEADO', 'Soleado'),
                        ('NUBLADO', 'Nublado'),
                        ('LLUVIOSO', 'Lluvioso'),
                        ('TORMENTA', 'Tormenta Electrica')
                    ],
                    default='SOLEADO',
                    max_length=20,
                    verbose_name='Condicion climatica'
                )),
                ('hora_inicio_jornada', models.TimeField(blank=True, null=True, verbose_name='Hora inicio jornada')),
                ('hora_fin_jornada', models.TimeField(blank=True, null=True, verbose_name='Hora fin jornada')),
                ('resumen_trabajo', models.TextField(blank=True, help_text='Descripcion detallada del trabajo realizado', verbose_name='Resumen del trabajo')),
                ('novedades', models.TextField(blank=True, help_text='Novedades o incidentes del dia', verbose_name='Novedades')),
                ('observaciones', models.TextField(blank=True, verbose_name='Observaciones')),
                ('estado', models.CharField(
                    choices=[
                        ('BORRADOR', 'Borrador'),
                        ('ENVIADO', 'Enviado'),
                        ('APROBADO', 'Aprobado'),
                        ('RECHAZADO', 'Rechazado')
                    ],
                    default='BORRADOR',
                    max_length=20,
                    verbose_name='Estado'
                )),
                ('fecha_envio', models.DateTimeField(blank=True, null=True, verbose_name='Fecha de envio')),
                ('fecha_aprobacion', models.DateTimeField(blank=True, null=True, verbose_name='Fecha de aprobacion')),
                ('cuadrilla', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='informes_diarios',
                    to='cuadrillas.cuadrilla',
                    verbose_name='Cuadrilla'
                )),
                ('linea', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='informes_diarios',
                    to='lineas.linea',
                    verbose_name='Linea'
                )),
                ('tramo', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='informes_diarios',
                    to='lineas.tramo',
                    verbose_name='Tramo'
                )),
                ('torre_inicio', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='informes_inicio',
                    to='lineas.torre',
                    verbose_name='Torre inicio del dia'
                )),
                ('torre_fin', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='informes_fin',
                    to='lineas.torre',
                    verbose_name='Torre fin del dia'
                )),
                ('actividades_realizadas', models.ManyToManyField(
                    blank=True,
                    related_name='informes_diarios',
                    to='actividades.actividad',
                    verbose_name='Actividades realizadas'
                )),
                ('enviado_por', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='informes_enviados',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Enviado por'
                )),
                ('aprobado_por', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='informes_aprobados',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Aprobado por'
                )),
            ],
            options={
                'verbose_name': 'Informe Diario',
                'verbose_name_plural': 'Informes Diarios',
                'db_table': 'informes_diarios',
                'ordering': ['-fecha', 'cuadrilla'],
            },
        ),
        migrations.AddConstraint(
            model_name='informediario',
            constraint=models.UniqueConstraint(
                fields=['fecha', 'cuadrilla'],
                name='unique_informe_fecha_cuadrilla'
            ),
        ),
        migrations.AddIndex(
            model_name='informediario',
            index=models.Index(fields=['fecha'], name='informes_di_fecha_3b9c2f_idx'),
        ),
        migrations.AddIndex(
            model_name='informediario',
            index=models.Index(fields=['cuadrilla', 'fecha'], name='informes_di_cuadril_a8e721_idx'),
        ),
        migrations.AddIndex(
            model_name='informediario',
            index=models.Index(fields=['linea', 'fecha'], name='informes_di_linea_i_c7d8f3_idx'),
        ),
        migrations.AddIndex(
            model_name='informediario',
            index=models.Index(fields=['estado'], name='informes_di_estado_49c3e2_idx'),
        ),
    ]
