# Generated for TransMaint - Extended SAP fields and consignation for Actividad

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('actividades', '0002_actividad_transelca_fields'),
    ]

    operations = [
        # Update TipoActividad categories with new Transelca categories
        migrations.AlterField(
            model_name='tipoactividad',
            name='categoria',
            field=models.CharField(
                choices=[
                    ('PODA', 'Poda de Vegetacion'),
                    ('HERRAJES', 'Cambio de Herrajes'),
                    ('AISLADORES', 'Cambio de Aisladores'),
                    ('INSPECCION', 'Inspeccion General'),
                    ('LIMPIEZA', 'Limpieza'),
                    ('SENALIZACION', 'Senalizacion'),
                    ('MEDICION', 'Medicion'),
                    ('LAVADO', 'Lavado Tradicional'),
                    ('SERVIDUMBRE', 'Servidumbre'),
                    ('PERMISO', 'Gestionar Permiso'),
                    ('CORREDOR', 'Corredor Electrico'),
                    ('INSPECCION_PED', 'Inspeccion Pedestre'),
                    ('TERMOGRAFIA', 'Termografia'),
                    ('DESCARGAS', 'Descargas Parciales'),
                    ('ELECTROMEC', 'Mtto Electromecanico'),
                    ('MEDICION_PT', 'Medida Puesta Tierra'),
                    ('OTRO', 'Otro')
                ],
                max_length=20,
                verbose_name='Categoria'
            ),
        ),
        # Add SAP order number
        migrations.AddField(
            model_name='actividad',
            name='orden_sap',
            field=models.CharField(
                blank=True,
                help_text='Numero de orden de trabajo en SAP',
                max_length=20,
                verbose_name='Numero Orden SAP'
            ),
        ),
        # Add SAP work position
        migrations.AddField(
            model_name='actividad',
            name='pt_sap',
            field=models.CharField(
                blank=True,
                help_text='Codigo del puesto de trabajo SAP',
                max_length=20,
                verbose_name='Puesto Trabajo SAP'
            ),
        ),
        # Add consignation requirement flag
        migrations.AddField(
            model_name='actividad',
            name='requiere_consignacion',
            field=models.BooleanField(
                default=False,
                help_text='Indica si la actividad requiere consignacion del circuito',
                verbose_name='Requiere consignacion'
            ),
        ),
        # Add consignation number
        migrations.AddField(
            model_name='actividad',
            name='numero_consignacion',
            field=models.CharField(
                blank=True,
                help_text='Numero de consignacion asignado por el operador',
                max_length=30,
                verbose_name='Numero de consignacion'
            ),
        ),
    ]
