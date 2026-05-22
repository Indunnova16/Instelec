import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('construccion', '0005_proteccion_pruebas_kits'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProgramacionFase',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('seccion', models.CharField(
                    choices=[
                        ('INGENIERIA', 'Ingeniería'),
                        ('SOCIOPREDIAL', 'Actividades Preliminares — Sociopredial'),
                        ('SOCIOAMBIENTAL', 'Actividades Preliminares — Socioambiental'),
                        ('OBRA_CIVIL', 'Obra Civil'),
                        ('MONTAJE', 'Montaje'),
                        ('SPT', 'SPT y Pintura'),
                        ('TENDIDO', 'Tendido'),
                        ('PROTECCIONES', 'Trinchos y Cunetas'),
                        ('PRUEBAS', 'Pruebas y Actividades Finales'),
                    ],
                    max_length=20,
                    verbose_name='Sección')),
                ('fecha_inicio_planeada', models.DateField(blank=True, null=True, verbose_name='Fecha inicio planeada')),
                ('fecha_fin_planeada', models.DateField(blank=True, null=True, verbose_name='Fecha fin planeada')),
                ('torres_planeadas', models.PositiveIntegerField(blank=True, null=True, verbose_name='Torres / cantidad planeada')),
                ('peso_pct', models.PositiveSmallIntegerField(default=0, help_text='Suma de pesos por proyecto debe ≈ 100; editable para curva S', verbose_name='Peso % de la sección')),
                ('observaciones', models.TextField(blank=True, verbose_name='Observaciones')),
                ('proyecto', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='programacion_fases', to='construccion.proyectoconstruccion')),
            ],
            options={
                'verbose_name': 'Programación de Fase',
                'verbose_name_plural': 'Programaciones de Fases',
                'db_table': 'construccion_programacion_fase',
                'ordering': ['proyecto', 'seccion'],
                'unique_together': {('proyecto', 'seccion')},
            },
        ),
    ]
