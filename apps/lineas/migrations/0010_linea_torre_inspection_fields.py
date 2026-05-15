from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lineas', '0009_pendientevano'),
    ]

    operations = [
        migrations.AddField(
            model_name='linea',
            name='last_inspection_date',
            field=models.DateField(blank=True, null=True, verbose_name='Última inspección'),
        ),
        migrations.AddField(
            model_name='linea',
            name='last_inspection_type',
            field=models.CharField(blank=True, max_length=50, verbose_name='Tipo última inspección'),
        ),
        migrations.AddField(
            model_name='linea',
            name='inspection_status',
            field=models.CharField(
                choices=[
                    ('OK', 'Al día'),
                    ('PROXIMA', 'Próxima a vencer'),
                    ('VENCIDA', 'Vencida'),
                    ('CRITICA', 'Crítica'),
                ],
                db_index=True,
                default='OK',
                max_length=10,
                verbose_name='Estado inspección',
            ),
        ),
        migrations.AddField(
            model_name='torre',
            name='last_inspection_date',
            field=models.DateField(blank=True, null=True, verbose_name='Última inspección'),
        ),
        migrations.AddField(
            model_name='torre',
            name='last_inspection_type',
            field=models.CharField(blank=True, max_length=50, verbose_name='Tipo última inspección'),
        ),
        migrations.AddField(
            model_name='torre',
            name='inspection_status',
            field=models.CharField(
                choices=[
                    ('OK', 'Al día'),
                    ('PROXIMA', 'Próxima a vencer'),
                    ('VENCIDA', 'Vencida'),
                    ('CRITICA', 'Crítica'),
                ],
                db_index=True,
                default='OK',
                max_length=10,
                verbose_name='Estado inspección',
            ),
        ),
    ]
