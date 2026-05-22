from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contratos', '0003_contrato_numero_torres'),
    ]

    operations = [
        migrations.AddField(
            model_name='contrato',
            name='fecha_acta_inicio',
            field=models.DateField(
                blank=True,
                help_text='Fecha de firma del Acta. Habilita registro de actividades y rige el cálculo de plazos.',
                null=True,
                verbose_name='Fecha del Acta de Inicio',
            ),
        ),
        migrations.AddField(
            model_name='contrato',
            name='voltaje',
            field=models.CharField(
                blank=True,
                choices=[('115', '115 kV'), ('230', '230 kV'), ('500', '500 kV')],
                max_length=5,
                verbose_name='Voltaje de la línea',
            ),
        ),
        migrations.AddField(
            model_name='contrato',
            name='numero_circuitos',
            field=models.PositiveSmallIntegerField(
                blank=True,
                choices=[(1, '1 circuito'), (2, '2 circuitos')],
                help_text='Afecta el tendido (Único / Doble)',
                null=True,
                verbose_name='Número de circuitos',
            ),
        ),
        migrations.AlterField(
            model_name='contrato',
            name='acta_inicio',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='contratos/actas/',
                verbose_name='Acta de inicio (documento firmado)',
            ),
        ),
    ]
