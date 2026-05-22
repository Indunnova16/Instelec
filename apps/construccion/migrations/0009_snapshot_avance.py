import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('construccion', '0008_pesos_proyecto'),
    ]

    operations = [
        migrations.CreateModel(
            name='SnapshotAvance',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('fecha', models.DateField(verbose_name='Fecha del snapshot')),
                ('pct_civil', models.FloatField(default=0, verbose_name='% Obra Civil (ponderado)')),
                ('pct_montaje', models.FloatField(default=0, verbose_name='% Montaje')),
                ('pct_tendido', models.FloatField(default=0, verbose_name='% Tendido')),
                ('pct_general', models.FloatField(default=0, verbose_name='% General (promedio)')),
                ('proyecto', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='snapshots_avance', to='construccion.proyectoconstruccion')),
            ],
            options={
                'verbose_name': 'Snapshot de Avance',
                'verbose_name_plural': 'Snapshots de Avance',
                'db_table': 'construccion_snapshot_avance',
                'ordering': ['proyecto', 'fecha'],
                'unique_together': {('proyecto', 'fecha')},
            },
        ),
    ]
