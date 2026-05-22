from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('construccion', '0007_financiero_pdeo'),
    ]

    operations = [
        migrations.AddField(
            model_name='proyectoconstruccion',
            name='peso_cerramiento_pct',
            field=models.PositiveSmallIntegerField(default=5, verbose_name='Peso Cerramiento %'),
        ),
        migrations.AddField(
            model_name='proyectoconstruccion',
            name='peso_excavacion_pct',
            field=models.PositiveSmallIntegerField(default=30, verbose_name='Peso Excavación %'),
        ),
        migrations.AddField(
            model_name='proyectoconstruccion',
            name='peso_solado_pct',
            field=models.PositiveSmallIntegerField(default=5, verbose_name='Peso Solado %'),
        ),
        migrations.AddField(
            model_name='proyectoconstruccion',
            name='peso_acero_pct',
            field=models.PositiveSmallIntegerField(default=15, verbose_name='Peso Acero %'),
        ),
        migrations.AddField(
            model_name='proyectoconstruccion',
            name='peso_vaciado_pct',
            field=models.PositiveSmallIntegerField(default=30, verbose_name='Peso Vaciado %'),
        ),
        migrations.AddField(
            model_name='proyectoconstruccion',
            name='peso_compactacion_pct',
            field=models.PositiveSmallIntegerField(default=15, verbose_name='Peso Compactación %'),
        ),
    ]
