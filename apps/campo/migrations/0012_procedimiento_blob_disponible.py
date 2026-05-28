# Generated for issue #118 — track GCS blob availability.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('campo', '0011_procedimiento_mime_max_length'),
    ]

    operations = [
        migrations.AddField(
            model_name='procedimiento',
            name='blob_disponible',
            field=models.BooleanField(
                default=True,
                verbose_name='Archivo disponible en storage',
                help_text='False si el blob no existe en GCS (huérfano).',
            ),
        ),
    ]
