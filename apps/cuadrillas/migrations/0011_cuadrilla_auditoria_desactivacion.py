"""
B3 — Auditoría de desactivación de cuadrillas.

Issue: Indunnova16/Instelec#104.

Agrega 3 campos al modelo Cuadrilla:
  - motivo_desactivacion (CharField 255, default vacío)
  - fecha_desactivacion (DateTimeField nullable)
  - desactivado_por (FK Usuario nullable, SET_NULL)

Los registros legacy quedan con motivo='' y fecha=NULL (compatible
con queryset Cuadrilla.objects.filter(activa=False)).
"""
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cuadrillas', '0010_add_personal_cuadrilla_and_attendance_options'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='cuadrilla',
            name='motivo_desactivacion',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Razón por la que la cuadrilla fue desactivada',
                max_length=255,
                verbose_name='Motivo desactivación',
            ),
        ),
        migrations.AddField(
            model_name='cuadrilla',
            name='fecha_desactivacion',
            field=models.DateTimeField(
                blank=True,
                help_text='Timestamp del momento en que se desactivó la cuadrilla',
                null=True,
                verbose_name='Fecha desactivación',
            ),
        ),
        migrations.AddField(
            model_name='cuadrilla',
            name='desactivado_por',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name='cuadrillas_desactivadas',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Desactivado por',
            ),
        ),
    ]
