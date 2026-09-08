"""Persistencia compartida de conciliación bancaria y flujo de caja (S1)."""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel

from .models_base import CicloFacturacion
from .models_finv2_facturas import Banco, FacturaGasto


class MovimientoBancario(BaseModel):
    """Una fila importada desde el extracto bancario."""

    class Tipo(models.TextChoices):
        DEPOSITO = "DEPOSITO", "Depósito"
        TRANSFERENCIA = "TRANSFERENCIA", "Transferencia"

    banco = models.ForeignKey(Banco, on_delete=models.PROTECT, related_name="movimientos")
    fecha = models.DateField("Fecha del movimiento")
    referencia = models.CharField("Referencia", max_length=100)
    descripcion = models.TextField("Descripción", blank=True)
    monto = models.DecimalField("Monto", max_digits=18, decimal_places=2)
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    origen_importacion = models.CharField("Archivo de origen", max_length=255, blank=True)

    class Meta:
        db_table = "financiero_movimientos_bancarios"
        ordering = ["-fecha", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["banco", "fecha", "referencia", "monto", "tipo"],
                name="uq_finv2_movimiento_bancario_importado",
            )
        ]
        indexes = [
            models.Index(fields=["banco", "fecha"], name="idx_finv2_mov_banco_fecha"),
            models.Index(fields=["referencia"], name="idx_finv2_mov_referencia"),
        ]

    def __str__(self):
        return f"{self.banco} — {self.referencia} ({self.monto})"


class ConciliacionBancaria(BaseModel):
    """Vincula un movimiento con una sola factura de gasto o de ingreso."""

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        CONCILIADA = "CONCILIADA", "Conciliada"
        DIFERENCIA = "DIFERENCIA", "Con diferencia"

    movimiento = models.OneToOneField(
        MovimientoBancario, on_delete=models.CASCADE, related_name="conciliacion"
    )
    factura_gasto = models.ForeignKey(
        FacturaGasto,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="conciliaciones",
    )
    ciclo_ingreso = models.ForeignKey(
        CicloFacturacion,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="conciliaciones",
    )
    estado = models.CharField(max_length=15, choices=Estado.choices, default=Estado.PENDIENTE)
    monto_documento = models.DecimalField(
        "Monto del documento", max_digits=18, decimal_places=2, null=True, blank=True
    )
    diferencia = models.DecimalField("Diferencia", max_digits=18, decimal_places=2, default=0)
    es_override = models.BooleanField("Es override manual", default=False)
    motivo_override = models.TextField("Motivo del override", blank=True)
    usuario_override = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conciliaciones_override",
    )
    fecha_override = models.DateTimeField("Fecha del override", null=True, blank=True)

    class Meta:
        db_table = "financiero_conciliaciones_bancarias"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    (Q(factura_gasto__isnull=False) & Q(ciclo_ingreso__isnull=True))
                    | (Q(factura_gasto__isnull=True) & Q(ciclo_ingreso__isnull=False))
                    | (Q(factura_gasto__isnull=True) & Q(ciclo_ingreso__isnull=True))
                ),
                name="ck_finv2_conciliacion_un_documento",
            )
        ]

    def __str__(self):
        return f"Conciliación {self.movimiento.referencia}"


class CajaProyecto(BaseModel):
    """Caja hoy configurable para cada contrato/proyecto financiero."""

    contrato = models.OneToOneField(
        "contratos.Contrato", on_delete=models.CASCADE, related_name="caja_proyectada"
    )
    saldo_inicial = models.DecimalField("Caja hoy", max_digits=18, decimal_places=2, default=0)

    class Meta:
        db_table = "financiero_cajas_proyecto"
        ordering = ["contrato__codigo"]

    def __str__(self):
        return f"Caja {self.contrato}"


class EgresoFijoProyecto(BaseModel):
    """Egreso recurrente configurable que participa en la proyección de caja."""

    class Frecuencia(models.TextChoices):
        MENSUAL = "MENSUAL", "Mensual"

    contrato = models.ForeignKey(
        "contratos.Contrato", on_delete=models.CASCADE, related_name="egresos_fijos"
    )
    descripcion = models.CharField("Descripción", max_length=255)
    monto = models.DecimalField("Monto", max_digits=18, decimal_places=2)
    frecuencia = models.CharField(
        max_length=15, choices=Frecuencia.choices, default=Frecuencia.MENSUAL
    )
    activo = models.BooleanField("Activo", default=True)

    class Meta:
        db_table = "financiero_egresos_fijos_proyecto"
        ordering = ["contrato__codigo", "descripcion"]

    def __str__(self):
        return f"{self.contrato} — {self.descripcion}"
