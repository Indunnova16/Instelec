from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('construccion', '0001_initial'),
    ]

    operations = [
        # ============ SocialPredial — gaps del #51 ============
        migrations.AddField(
            model_name='socialpredial',
            name='persona_contacto',
            field=models.CharField(blank=True, help_text='Si difiere del propietario',
                                   max_length=300, verbose_name='Persona de contacto'),
        ),
        migrations.AlterField(
            model_name='socialpredial',
            name='telefono',
            field=models.CharField(blank=True, max_length=50,
                                   verbose_name='Teléfono de contacto'),
        ),
        migrations.AddField(
            model_name='socialpredial',
            name='departamento',
            field=models.CharField(blank=True, max_length=100, verbose_name='Departamento'),
        ),
        migrations.AddField(
            model_name='socialpredial',
            name='fecha_socializacion',
            field=models.DateField(
                blank=True, null=True,
                verbose_name='Fecha de socialización del proyecto a comunidades'),
        ),

        # ============ AmbientalTorre — gaps del #52 ============
        migrations.AddField(
            model_name='ambientaltorre',
            name='ahuyentamiento_aplica',
            field=models.BooleanField(default=True, verbose_name='Aplica ahuyentamiento'),
        ),
        migrations.AddField(
            model_name='ambientaltorre',
            name='epifitas_aplica',
            field=models.BooleanField(default=True, verbose_name='Aplica gestión de epífitas'),
        ),
        migrations.AddField(
            model_name='ambientaltorre',
            name='conteo_epifitas',
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name='Conteo de epífitas a reubicar'),
        ),
        migrations.AddField(
            model_name='ambientaltorre',
            name='conteo_epifitas_fecha',
            field=models.DateField(
                blank=True, null=True, verbose_name='Conteo de epífitas - Fecha'),
        ),
        migrations.AddField(
            model_name='ambientaltorre',
            name='traslado_epifitas_fecha',
            field=models.DateField(
                blank=True, null=True,
                verbose_name='Traslado de epífitas a vivero - Fecha'),
        ),
        migrations.AddField(
            model_name='ambientaltorre',
            name='traslado_epifitas_ok',
            field=models.BooleanField(default=False,
                                      verbose_name='Traslado de epífitas - OK'),
        ),
        migrations.AddField(
            model_name='ambientaltorre',
            name='reubicacion_epifitas_fecha',
            field=models.DateField(
                blank=True, null=True,
                verbose_name='Reubicación de epífitas (con corporación) - Fecha'),
        ),
        migrations.AddField(
            model_name='ambientaltorre',
            name='reubicacion_epifitas_ok',
            field=models.BooleanField(default=False,
                                      verbose_name='Reubicación de epífitas - OK'),
        ),
        migrations.AddField(
            model_name='ambientaltorre',
            name='aprov_forestal_torre_aplica',
            field=models.BooleanField(
                default=True, verbose_name='Aplica aprovechamiento forestal (torre)'),
        ),
        migrations.AddField(
            model_name='ambientaltorre',
            name='aprov_forestal_vano_aplica',
            field=models.BooleanField(
                default=True, verbose_name='Aplica aprovechamiento forestal (vano)'),
        ),
        migrations.AddField(
            model_name='ambientaltorre',
            name='rescate_arqueologico_aplica',
            field=models.BooleanField(default=True,
                                      verbose_name='Aplica rescate arqueológico'),
        ),
        migrations.AddField(
            model_name='ambientaltorre',
            name='monitoreo_arqueologico_aplica',
            field=models.BooleanField(
                default=False,
                help_text='Sí/No — definir si requiere monitoreo continuo',
                verbose_name='Monitoreo arqueológico durante excavaciones'),
        ),
        migrations.AddField(
            model_name='ambientaltorre',
            name='adecuacion_accesos_porcentaje',
            field=models.PositiveSmallIntegerField(
                default=0, verbose_name='Adecuación de accesos - % avance'),
        ),
        migrations.AlterField(
            model_name='ambientaltorre',
            name='arqueologia_poligonos_fecha',
            field=models.DateField(
                blank=True, null=True,
                verbose_name='Polígonos prospección ICAN - Fecha'),
        ),
        migrations.AlterField(
            model_name='ambientaltorre',
            name='arqueologia_poligonos_ok',
            field=models.BooleanField(default=False,
                                      verbose_name='Polígonos ICAN - OK'),
        ),
    ]
