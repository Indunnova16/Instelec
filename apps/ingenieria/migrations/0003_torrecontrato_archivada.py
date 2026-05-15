from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ingenieria', '0002_ingenieriaestado_observacion'),
    ]

    operations = [
        migrations.AddField(
            model_name='torrecontrato',
            name='archivada',
            field=models.BooleanField(db_index=True, default=False, verbose_name='Archivada'),
        ),
    ]
