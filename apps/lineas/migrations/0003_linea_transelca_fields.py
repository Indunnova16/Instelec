# Generated for TransMaint - Extended Transelca integration fields for Linea

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lineas', '0002_tramo'),
    ]

    operations = [
        migrations.AddField(
            model_name='linea',
            name='codigo_transelca',
            field=models.CharField(
                blank=True,
                help_text='Código en formato Transelca (ej: 801/802, 5156/5157)',
                max_length=30,
                verbose_name='Código Transelca'
            ),
        ),
        migrations.AddField(
            model_name='linea',
            name='circuito',
            field=models.CharField(
                blank=True,
                help_text='Número de circuito (ej: 801, 802)',
                max_length=20,
                verbose_name='Circuito'
            ),
        ),
        migrations.AddField(
            model_name='linea',
            name='contratista',
            field=models.CharField(
                blank=True,
                choices=[
                    ('CTE_NORTE', 'CTE Norte'),
                    ('OUTSOURCING', 'Outsourcing'),
                    ('CONVENIO', 'Convenio')
                ],
                help_text='Contratista responsable del mantenimiento',
                max_length=20,
                verbose_name='Contratista asignado'
            ),
        ),
        migrations.AddField(
            model_name='linea',
            name='centro_emplazamiento',
            field=models.CharField(
                blank=True,
                help_text='Código SAP del centro de emplazamiento (ej: TR01)',
                max_length=20,
                verbose_name='Centro de emplazamiento'
            ),
        ),
        migrations.AddField(
            model_name='linea',
            name='puesto_trabajo',
            field=models.CharField(
                blank=True,
                help_text='Código SAP del puesto de trabajo',
                max_length=20,
                verbose_name='Puesto de trabajo'
            ),
        ),
    ]
