# Generated manually (issue #210) -- puramente aditivo sobre choices, no
# toca datos existentes.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cuadrillas', '0025_area_usuario_personal'),
    ]

    operations = [
        migrations.AlterField(
            model_name='asistencia',
            name='tipo_novedad',
            field=models.CharField(
                choices=[
                    ('PRESENTE', 'Presente'),
                    ('VACACIONES', 'Vacaciones'),
                    ('INCAPACIDAD', 'Incapacidad'),
                    ('PERMISO', 'Permiso'),
                    ('AUSENTE', 'Ausente'),
                    ('LICENCIA', 'Licencia'),
                    ('CAPACITACION', 'Capacitación'),
                    ('COMPENSATORIO', 'Compensatorio'),
                    ('DESCANSO', 'Descanso'),
                    ('DIA_GANADO', 'Día ganado'),
                ],
                default='PRESENTE',
                max_length=20,
                verbose_name='Tipo de novedad',
            ),
        ),
    ]
