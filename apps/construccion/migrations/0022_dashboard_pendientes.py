"""Agregar campo `pendientes` (TextField) a DashboardAvanceSemanal — refs #75 #77."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('construccion', '0021_merge_b2_b3_oc_mont'),
    ]

    operations = [
        migrations.AddField(
            model_name='dashboardavancesemanal',
            name='pendientes',
            field=models.TextField(
                blank=True,
                help_text='Texto libre — clima, falta materiales, espera permisos, etc.',
                verbose_name='Pendientes',
            ),
        ),
    ]
