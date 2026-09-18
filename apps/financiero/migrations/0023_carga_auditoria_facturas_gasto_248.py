# Generated for issue #248 (B1 -- /modulo ERP-Financiero-E)

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("financiero", "0022_facturas_ingreso_v2_249"),
    ]

    operations = [
        migrations.AddField(
            model_name="facturagasto",
            name="fecha_vencimiento",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="Fecha de vencimiento",
                help_text=(
                    "#248: el checklist del cliente pide alertar facturas próximas a "
                    "vencer pero el modelo no traía este campo. Supuesto documentado "
                    "(pendiente de confirmación de Indunnova): si no se indica, se "
                    "calcula fecha + 30 días al guardar (ver forms_finv2_gastos.py y "
                    "views_finv2_gastos.py::GastoImportarPreviewView)."
                ),
            ),
        ),
        migrations.CreateModel(
            name="CargaFacturaGasto",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="Fecha de actualización"),
                ),
                ("archivo_nombre", models.CharField(max_length=255)),
                ("usuario", models.CharField(blank=True, max_length=150)),
                ("filas_total", models.PositiveIntegerField(default=0)),
                ("filas_validas", models.PositiveIntegerField(default=0)),
                ("filas_error", models.PositiveIntegerField(default=0)),
                ("filas_creadas", models.PositiveIntegerField(default=0)),
                ("filas_actualizadas", models.PositiveIntegerField(default=0)),
                (
                    "resultado",
                    models.CharField(
                        choices=[
                            ("PREVIEW", "Vista previa"),
                            ("CONFIRMADA", "Confirmada"),
                            ("RECHAZADA", "Rechazada"),
                        ],
                        max_length=20,
                    ),
                ),
                ("detalle_errores", models.JSONField(blank=True, default=list)),
                ("detalle_filas", models.JSONField(blank=True, default=list)),
            ],
            options={
                "db_table": "financiero_cargas_facturas_gasto",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="AuditoriaFacturaGasto",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="Fecha de actualización"),
                ),
                ("campo", models.CharField(max_length=80)),
                ("valor_anterior", models.TextField(blank=True)),
                ("valor_nuevo", models.TextField(blank=True)),
                ("usuario", models.CharField(blank=True, max_length=150)),
                (
                    "factura",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="auditoria",
                        to="financiero.facturagasto",
                    ),
                ),
            ],
            options={
                "db_table": "financiero_auditoria_facturas_gasto",
                "ordering": ["-created_at"],
            },
        ),
    ]
