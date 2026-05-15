from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('campo', '0009_registroavance'),
    ]

    operations = [
        migrations.AddField(
            model_name='registrocampo',
            name='severidad',
            field=models.CharField(
                blank=True,
                choices=[
                    ('BAJA', 'Baja'),
                    ('MEDIA', 'Media'),
                    ('ALTA', 'Alta'),
                    ('CRITICA', 'Crítica'),
                ],
                default='',
                help_text='Severidad del hallazgo si aplica (inspecciones)',
                max_length=10,
                verbose_name='Severidad del hallazgo',
            ),
        ),
    ]
