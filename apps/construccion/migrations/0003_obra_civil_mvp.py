from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('construccion', '0002_predial_ambiental_gaps'),
    ]

    operations = [
        # Bloque 1: Cerramiento
        migrations.AddField(
            model_name='pataobra',
            name='cerramiento_finalizado_ok',
            field=models.BooleanField(
                default=False,
                help_text='Habilita inicio de excavación (regla Gabriel Valencia)',
                verbose_name='Cerramiento finalizado'),
        ),
        migrations.AddField(
            model_name='pataobra',
            name='cerramiento_fecha',
            field=models.DateField(blank=True, null=True,
                                   verbose_name='Fecha cerramiento'),
        ),
        # Bloque 2: Excavación
        migrations.AddField(
            model_name='pataobra',
            name='tipo_excavacion',
            field=models.CharField(
                blank=True,
                choices=[('MANUAL', 'Manual'), ('MAQUINA', 'Con máquina')],
                max_length=20,
                verbose_name='Tipo de excavación'),
        ),
        migrations.AddField(
            model_name='pataobra',
            name='aplica_pilotes',
            field=models.BooleanField(
                default=False,
                verbose_name='Aplica instalación de pilotes'),
        ),
        # Bloque 4: Acero (#54 control materiales)
        migrations.AddField(
            model_name='pataobra',
            name='acero_solicitado_kg',
            field=models.FloatField(
                blank=True, null=True,
                verbose_name='Acero solicitado según planilla (kg)'),
        ),
        migrations.AddField(
            model_name='pataobra',
            name='acero_instalado_kg',
            field=models.FloatField(
                blank=True, null=True,
                verbose_name='Acero instalado (kg)'),
        ),
        # Bloque 5: Vaciado — diseño vs real (#54)
        migrations.AddField(
            model_name='pataobra',
            name='concreto_solicitado_m3',
            field=models.FloatField(
                blank=True, null=True,
                verbose_name='Concreto solicitado (m3)'),
        ),
        migrations.AddField(
            model_name='pataobra',
            name='concreto_instalado_m3',
            field=models.FloatField(
                blank=True, null=True,
                verbose_name='Concreto instalado (m3)'),
        ),
        migrations.AddField(
            model_name='pataobra',
            name='resistencia_especificada_mpa',
            field=models.PositiveSmallIntegerField(
                blank=True, help_text='Ej: 21, 28', null=True,
                verbose_name='Resistencia especificada (MPa)'),
        ),
        # Bloque 5: Cilindros (#55 alarmas)
        migrations.AddField(
            model_name='pataobra',
            name='cilindro_7d_mpa',
            field=models.FloatField(blank=True, null=True,
                                    verbose_name='Cilindro 7 días (MPa)'),
        ),
        migrations.AddField(
            model_name='pataobra',
            name='cilindro_14d_mpa',
            field=models.FloatField(blank=True, null=True,
                                    verbose_name='Cilindro 14 días (MPa)'),
        ),
        migrations.AddField(
            model_name='pataobra',
            name='cilindro_21d_mpa',
            field=models.FloatField(blank=True, null=True,
                                    verbose_name='Cilindro 21 días (MPa)'),
        ),
        migrations.AddField(
            model_name='pataobra',
            name='cilindro_51d_mpa',
            field=models.FloatField(blank=True, null=True,
                                    verbose_name='Cilindro 51 días (MPa)'),
        ),
        # AlterField vaciado_fecha — update help_text
        migrations.AlterField(
            model_name='pataobra',
            name='vaciado_fecha',
            field=models.DateField(
                blank=True,
                help_text='Trigger para alarmas de cilindros 7/14/21/51 días (#55)',
                null=True,
                verbose_name='Fecha vaciado'),
        ),
    ]
