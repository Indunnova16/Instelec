import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('cuadrillas', '0001_initial'),
        ('construccion', '0004_montaje_spt_tendido'),
    ]

    operations = [
        migrations.CreateModel(
            name='ObraProteccion',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('tipos_medida', models.CharField(blank=True, help_text='Lista CSV: CUNETAS,TRINCHOS,GAVIONES,REVEGETALIZACION,GEOTEXTIL', max_length=200, verbose_name='Tipos de medida de manejo')),
                ('metros_trinchos', models.FloatField(blank=True, null=True, verbose_name='Metros lineales trinchos')),
                ('metros_cunetas', models.FloatField(blank=True, null=True, verbose_name='Metros lineales cunetas')),
                ('nota', models.TextField(blank=True, verbose_name='Nota / descripción')),
                ('tubo_metalico_unidades', models.FloatField(blank=True, null=True, verbose_name='Tubo metálico 3x3" zinc 50µ (uds 3m)')),
                ('malla_eslabonada_m2', models.FloatField(blank=True, null=True, verbose_name='Malla eslabonada galvanizada (m²)')),
                ('alambre_galvanizado_kg', models.FloatField(blank=True, null=True, verbose_name='Alambre galvanizado (kg)')),
                ('geotextil_m2', models.FloatField(blank=True, null=True, verbose_name='Geotextil (m²)')),
                ('cemento_bultos', models.FloatField(blank=True, null=True, verbose_name='Cemento general (bultos 50 kg)')),
                ('arena_cunetes', models.FloatField(blank=True, help_text='Zona montañosa — no camiones', null=True, verbose_name='Arena (cuñetes)')),
                ('grava_cunetes', models.FloatField(blank=True, null=True, verbose_name='Grava (cuñetes)')),
                ('revegetalizacion_m2', models.FloatField(blank=True, null=True, verbose_name='Revegetalización (m²)')),
                ('fecha_ejecucion', models.DateField(blank=True, null=True, verbose_name='Fecha de ejecución')),
                ('completada_ok', models.BooleanField(default=False, verbose_name='Obra completada')),
                ('observaciones', models.TextField(blank=True, verbose_name='Observaciones')),
                ('cuadrilla', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='obras_proteccion', to='cuadrillas.cuadrilla')),
                ('torre', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='obra_proteccion', to='construccion.torreconstruccion')),
            ],
            options={
                'verbose_name': 'Obra de Protección',
                'verbose_name_plural': 'Obras de Protección',
                'db_table': 'construccion_obra_proteccion',
            },
        ),
        migrations.CreateModel(
            name='PruebaTecnica',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('nombre', models.CharField(help_text='Editable; ej: "Pruebas comunicación F.O entre subestaciones"', max_length=300, verbose_name='Nombre de la prueba')),
                ('orden', models.PositiveSmallIntegerField(default=0, verbose_name='Orden')),
                ('fecha_programada', models.DateField(blank=True, null=True, verbose_name='Fecha programada')),
                ('fecha_ejecucion', models.DateField(blank=True, null=True, verbose_name='Fecha real de ejecución')),
                ('laboratorio', models.CharField(blank=True, max_length=200, verbose_name='Laboratorio / Empresa certificadora')),
                ('resultado', models.CharField(choices=[('PENDIENTE', 'Pendiente'), ('CUMPLE', 'Cumple'), ('NO_CUMPLE', 'No cumple'), ('NO_APLICA', 'No aplica')], default='PENDIENTE', max_length=15, verbose_name='Resultado')),
                ('adjunto', models.FileField(blank=True, null=True, upload_to='construccion/pruebas/', verbose_name='Documento del resultado')),
                ('observaciones', models.TextField(blank=True, verbose_name='Observaciones')),
                ('proyecto', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pruebas_tecnicas', to='construccion.proyectoconstruccion')),
            ],
            options={
                'verbose_name': 'Prueba Técnica',
                'verbose_name_plural': 'Pruebas Técnicas',
                'db_table': 'construccion_prueba_tecnica',
                'ordering': ['proyecto', 'orden', 'nombre'],
            },
        ),
        migrations.CreateModel(
            name='KitCerramiento',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('codigo', models.CharField(help_text='Ej: KIT-001, KIT-002', max_length=30, verbose_name='Código del kit')),
                ('componentes', models.CharField(help_text='CSV libre: madera, lona, alambre', max_length=200, verbose_name='Tipo de componentes')),
                ('cantidad', models.PositiveIntegerField(default=1, verbose_name='Cantidad de componentes')),
                ('estado', models.CharField(choices=[('DISPONIBLE', 'Disponible'), ('EN_USO', 'En uso'), ('DAÑADO', 'Dañado'), ('PERDIDO', 'Perdido')], default='DISPONIBLE', max_length=15, verbose_name='Estado')),
                ('fecha_ingreso_torre', models.DateField(blank=True, null=True, verbose_name='Fecha de ingreso a esta torre')),
                ('fecha_salida_torre', models.DateField(blank=True, null=True, verbose_name='Fecha de salida de esta torre')),
                ('observaciones', models.TextField(blank=True, verbose_name='Observaciones')),
                ('proyecto', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='kits_cerramiento', to='construccion.proyectoconstruccion')),
                ('torre_actual', models.ForeignKey(blank=True, help_text='Torre donde está actualmente el kit', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='kits_en_torre', to='construccion.torreconstruccion')),
            ],
            options={
                'verbose_name': 'Kit de Cerramiento',
                'verbose_name_plural': 'Kits de Cerramiento',
                'db_table': 'construccion_kit_cerramiento',
                'ordering': ['proyecto', 'codigo'],
                'unique_together': {('proyecto', 'codigo')},
            },
        ),
    ]
