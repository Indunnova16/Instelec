# Generated manually for performance optimization

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('campo', '0001_initial'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='registrocampo',
            index=models.Index(fields=['actividad'], name='idx_registro_actividad'),
        ),
        migrations.AddIndex(
            model_name='registrocampo',
            index=models.Index(fields=['usuario'], name='idx_registro_usuario'),
        ),
        migrations.AddIndex(
            model_name='registrocampo',
            index=models.Index(fields=['fecha_inicio'], name='idx_registro_fecha'),
        ),
        migrations.AddIndex(
            model_name='registrocampo',
            index=models.Index(fields=['sincronizado'], name='idx_registro_sincronizado'),
        ),
        migrations.AddIndex(
            model_name='evidencia',
            index=models.Index(fields=['registro_campo'], name='idx_evidencia_registro'),
        ),
        migrations.AddIndex(
            model_name='evidencia',
            index=models.Index(fields=['tipo'], name='idx_evidencia_tipo'),
        ),
        migrations.AddIndex(
            model_name='evidencia',
            index=models.Index(fields=['fecha_captura'], name='idx_evidencia_fecha'),
        ),
    ]
