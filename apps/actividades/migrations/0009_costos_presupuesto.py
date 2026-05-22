from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('actividades', '0008_historialintervencion'),
    ]

    operations = [
        migrations.AddField(
            model_name='actividad',
            name='tipo_costo',
            field=models.CharField(
                choices=[('FIJO', 'Costo fijo'), ('VARIABLE', 'Costo variable')],
                default='FIJO',
                help_text='FIJO: costo unitario × cuadrillas asignadas. VARIABLE: costo se registra manual.',
                max_length=10,
                verbose_name='Tipo de costo',
            ),
        ),
        migrations.AddField(
            model_name='actividad',
            name='costo_unitario',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0'),
                help_text='Precio por cuadrilla-día (aplica si tipo_costo=FIJO)',
                max_digits=14,
                verbose_name='Costo unitario',
            ),
        ),
        migrations.AddField(
            model_name='actividad',
            name='presupuesto_planeado',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0'),
                help_text='Dinero asignado al aviso para ejecutarlo',
                max_digits=14,
                verbose_name='Presupuesto planeado',
            ),
        ),
        migrations.AddField(
            model_name='actividad',
            name='costo_acumulado',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0'),
                help_text='Dinero ya gastado. Calculado automáticamente si tipo_costo=FIJO.',
                max_digits=14,
                verbose_name='Costo acumulado',
            ),
        ),
    ]
