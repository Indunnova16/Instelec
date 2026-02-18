from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cuadrillas', '0006_asistencia_horas_extra_asistencia_viatico_aplica'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cuadrillamiembro',
            name='rol_cuadrilla',
            field=models.CharField(
                choices=[
                    ('SUPERVISOR', 'Supervisor'),
                    ('LINIERO_I', 'Liniero I'),
                    ('LINIERO_II', 'Liniero II'),
                    ('AYUDANTE', 'Ayudante'),
                    ('CONDUCTOR', 'Conductor'),
                    ('ADMINISTRADOR_OBRA', 'Administrador de Obra'),
                    ('PROFESIONAL_SST', 'Profesional SST'),
                    ('ING_RESIDENTE', 'Ingeniero Residente'),
                    ('SERVICIO_GENERAL', 'Servicio General'),
                    ('ALMACENISTA', 'Almacenista'),
                    ('SUPERVISOR_FOREST', 'Supervisor Forestal'),
                    ('ASISTENTE_FOREST', 'Asistente Forestal'),
                ],
                default='LINIERO_I',
                max_length=20,
                verbose_name='Rol en cuadrilla',
            ),
        ),
    ]
