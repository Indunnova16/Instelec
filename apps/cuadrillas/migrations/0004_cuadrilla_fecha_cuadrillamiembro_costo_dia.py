"""
Add fecha to Cuadrilla and costo_dia to CuadrillaMiembro.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cuadrillas', '0003_cuadrillamiembro_extended_roles'),
    ]

    operations = [
        migrations.AddField(
            model_name='cuadrilla',
            name='fecha',
            field=models.DateField(
                blank=True,
                help_text='Fecha de operacion de la cuadrilla',
                null=True,
                verbose_name='Fecha',
            ),
        ),
        migrations.AddField(
            model_name='cuadrillamiembro',
            name='costo_dia',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Costo diario del miembro segun su rol/cargo',
                max_digits=12,
                verbose_name='Costo por dia',
            ),
        ),
    ]
