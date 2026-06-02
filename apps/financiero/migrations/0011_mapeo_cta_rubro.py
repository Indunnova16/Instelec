# B1 (#120) — escrita a mano (entorno sin Django para makemigrations).
# Número 0011 pre-asignado por F1 del skill /modulo.

import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('financiero', '0010_add_personal_administrativo'),
    ]

    operations = [
        migrations.CreateModel(
            name='MapeoCtaRubro',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creación')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Fecha de actualización')),
                ('cta_equivalente', models.CharField(help_text='Valor de la columna O ("Cta equivalente") de la BD contable.', max_length=255, verbose_name='Cuenta equivalente')),
                ('rubro_presupuestal', models.CharField(help_text='Rubro de la estructura de presupuesto al que se agrupa.', max_length=255, verbose_name='Rubro presupuestal')),
                ('activo', models.BooleanField(default=True, verbose_name='Activo')),
            ],
            options={
                'verbose_name': 'Mapeo cuenta → rubro',
                'verbose_name_plural': 'Mapeos cuenta → rubro',
                'db_table': 'financiero_mapeo_cta_rubro',
                'ordering': ['rubro_presupuestal', 'cta_equivalente'],
            },
        ),
    ]
