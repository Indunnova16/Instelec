# Issue #210: choice aditivo; no transforma ni sobrescribe asistencias legacy.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cuadrillas', '0028_vehiculo_catalogo_estado'),
    ]

    operations = [
        migrations.AlterField(
            model_name='asistencia',
            name='tipo_novedad',
            field=models.CharField(
                choices=[
                    ('PRESENTE', 'Presente'), ('VACACIONES', 'Vacaciones'),
                    ('INCAPACIDAD', 'Incapacidad'), ('PERMISO', 'Permiso'),
                    ('AUSENTE', 'Ausente'), ('LICENCIA', 'Licencia'),
                    ('CAPACITACION', 'Capacitación'), ('COMPENSATORIO', 'Compensatorio'),
                    ('DESCANSO', 'Descanso'), ('DIA_GANADO', 'Día ganado'),
                    ('FESTIVO', 'Festivo'),
                ],
                default='PRESENTE', max_length=20, verbose_name='Tipo de novedad',
            ),
        ),
    ]
