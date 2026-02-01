# Generated for TransMaint - CostoActividad model

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('actividades', '0004_informediario'),
        ('financiero', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='CostoActividad',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creacion')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Fecha de actualizacion')),
                ('costo_personal', models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name='Costo personal')),
                ('costo_vehiculos', models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name='Costo vehiculos')),
                ('costo_viaticos', models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name='Costo viaticos')),
                ('costo_materiales', models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name='Costo materiales')),
                ('otros_costos', models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name='Otros costos')),
                ('actividad', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='costo_actividad',
                    to='actividades.actividad',
                    verbose_name='Actividad'
                )),
            ],
            options={
                'verbose_name': 'Costo de Actividad',
                'verbose_name_plural': 'Costos de Actividades',
                'db_table': 'costos_actividad',
            },
        ),
    ]
