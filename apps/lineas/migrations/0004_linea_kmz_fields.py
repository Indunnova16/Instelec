from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lineas', '0003_linea_transelca_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='linea',
            name='archivo_kmz',
            field=models.FileField(
                blank=True,
                help_text='Archivo KMZ o KML con datos geográficos de la línea',
                null=True,
                upload_to='lineas/kmz/',
                verbose_name='Archivo KMZ/KML',
            ),
        ),
        migrations.AddField(
            model_name='linea',
            name='kmz_geojson',
            field=models.JSONField(
                blank=True,
                help_text='Contenido del KMZ convertido a GeoJSON para visualización en mapa',
                null=True,
                verbose_name='GeoJSON del KMZ',
            ),
        ),
    ]
