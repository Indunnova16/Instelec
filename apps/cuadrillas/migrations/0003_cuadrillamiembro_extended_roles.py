# Generated for TransMaint - Extended roles and cargo for CuadrillaMiembro

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cuadrillas', '0002_asistencia'),
    ]

    operations = [
        # Update RolCuadrilla choices (this is handled by the model, but we need
        # to ensure the field can accept the new values)
        migrations.AlterField(
            model_name='cuadrillamiembro',
            name='rol_cuadrilla',
            field=models.CharField(
                choices=[
                    ('SUPERVISOR', 'Supervisor'),
                    ('LINIERO_I', 'Liniero I'),
                    ('LINIERO_II', 'Liniero II'),
                    ('AYUDANTE', 'Ayudante'),
                    ('CONDUCTOR', 'Conductor')
                ],
                default='LINIERO_I',
                max_length=20,
                verbose_name='Rol en cuadrilla'
            ),
        ),
        # Add cargo field for hierarchical position
        migrations.AddField(
            model_name='cuadrillamiembro',
            name='cargo',
            field=models.CharField(
                choices=[
                    ('JT_CTA', 'Jefe de Trabajo / Capacitado'),
                    ('MIEMBRO', 'Miembro')
                ],
                default='MIEMBRO',
                help_text='Define si el miembro es Jefe de Trabajo/Capacitado o Miembro regular',
                max_length=20,
                verbose_name='Cargo jerárquico'
            ),
        ),
    ]
