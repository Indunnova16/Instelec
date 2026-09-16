"""Persistencia compartida para facturas de gastos e ingresos (S1)."""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel

from .models_base import CicloFacturacion


class Banco(BaseModel):
    nombre = models.CharField("Nombre", max_length=150, unique=True)
    activo = models.BooleanField("Activo", default=True)

    class Meta:
        db_table = "financiero_bancos"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class MetodoPago(BaseModel):
    nombre = models.CharField("Nombre", max_length=100, unique=True)
    activo = models.BooleanField("Activo", default=True)

    class Meta:
        db_table = "financiero_metodos_pago"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Proveedor(BaseModel):
    nombre = models.CharField("Nombre o razón social", max_length=255)
    nit = models.CharField("NIT", max_length=30, blank=True, unique=True, null=True)
    email = models.EmailField("Correo electrónico", blank=True)
    telefono = models.CharField("Teléfono", max_length=50, blank=True)
    activo = models.BooleanField("Activo", default=True)
    direccion = models.CharField("Dirección", max_length=255, blank=True)
    tipo_servicio = models.CharField("Tipo de servicio", max_length=120, blank=True)
    plazo_pago_dias = models.PositiveIntegerField(
        "Plazo de pago (días)", default=30,
        validators=[MinValueValidator(1), MaxValueValidator(120)],
    )
    fecha_inicio_contrato = models.DateField("Inicio contractual", null=True, blank=True)
    fecha_fin_contrato = models.DateField("Fin contractual", null=True, blank=True)
    inactivo_desde = models.DateField("Inactivo desde", null=True, blank=True)
    motivo_inactivacion = models.CharField("Motivo de inactivación", max_length=255, blank=True)

    class Meta:
        db_table = "financiero_proveedores"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Cliente(BaseModel):
    nombre = models.CharField("Nombre o razón social", max_length=255)
    nit = models.CharField("NIT", max_length=30, blank=True, unique=True, null=True)
    email = models.EmailField("Correo electrónico", blank=True)
    telefono = models.CharField("Teléfono", max_length=50, blank=True)
    activo = models.BooleanField("Activo", default=True)
    direccion = models.CharField("Dirección", max_length=255, blank=True)
    industria = models.CharField("Industria", max_length=120, blank=True)
    plazo_pago_dias = models.PositiveIntegerField(
        "Plazo de pago (días)", default=30,
        validators=[MinValueValidator(1), MaxValueValidator(120)],
    )
    fecha_inicio_contrato = models.DateField("Inicio contractual", null=True, blank=True)
    fecha_fin_contrato = models.DateField("Fin contractual", null=True, blank=True)
    inactivo_desde = models.DateField("Inactivo desde", null=True, blank=True)
    motivo_inactivacion = models.CharField("Motivo de inactivación", max_length=255, blank=True)

    class Meta:
        db_table = "financiero_clientes"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class AuditoriaTercero(BaseModel):
    """Bitácora inmutable de cambios de los maestros financieros."""

    tercero_tipo = models.CharField(max_length=12, choices=[("CLIENTE", "Cliente"), ("PROVEEDOR", "Proveedor")])
    tercero_id = models.UUIDField()
    campo = models.CharField(max_length=80)
    valor_anterior = models.TextField(blank=True)
    valor_nuevo = models.TextField(blank=True)
    usuario = models.CharField(max_length=150, blank=True)

    class Meta:
        db_table = "financiero_auditoria_terceros"
        ordering = ["-created_at"]


class CargaTerceros(BaseModel):
    """Trazabilidad de una importación de maestros, incluso si fue rechazada."""

    tercero_tipo = models.CharField(max_length=12, choices=[("CLIENTE", "Cliente"), ("PROVEEDOR", "Proveedor")])
    archivo_nombre = models.CharField(max_length=255)
    usuario = models.CharField(max_length=150, blank=True)
    filas_total = models.PositiveIntegerField(default=0)
    filas_validas = models.PositiveIntegerField(default=0)
    filas_error = models.PositiveIntegerField(default=0)
    resultado = models.CharField(max_length=20, choices=[("PREVIEW", "Vista previa"), ("CONFIRMADA", "Confirmada"), ("RECHAZADA", "Rechazada")])
    detalle_errores = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "financiero_cargas_terceros"
        ordering = ["-created_at"]


class FacturaGasto(BaseModel):
    class Estado(models.TextChoices):
        PENDIENTE_APROBACION = "PENDIENTE_APROBACION", "Pendiente de aprobación"
        PENDIENTE_PAGO = "PENDIENTE_PAGO", "Pendiente de pago"
        RECHAZADA = "RECHAZADA", "Rechazada"
        PAGADA = "PAGADA", "Pagada"

    proveedor = models.ForeignKey(
        Proveedor, on_delete=models.PROTECT, related_name="facturas_gasto"
    )
    contrato = models.ForeignKey(
        "contratos.Contrato", on_delete=models.PROTECT, related_name="facturas_gasto"
    )
    presupuesto = models.ForeignKey(
        "financiero.Presupuesto",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="facturas_gasto",
    )
    homologacion = models.ForeignKey(
        "financiero.HomologacionProjectsContable",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="facturas_gasto",
    )
    banco = models.ForeignKey(
        Banco, on_delete=models.PROTECT, null=True, blank=True, related_name="facturas_gasto"
    )
    metodo_pago = models.ForeignKey(
        MetodoPago, on_delete=models.PROTECT, null=True, blank=True, related_name="facturas_gasto"
    )
    numero_documento = models.CharField("Número de documento", max_length=100)
    documento = models.FileField("Documento", upload_to="financiero/facturas_gasto/", blank=True)
    fecha = models.DateField("Fecha")
    concepto = models.CharField("Concepto", max_length=255)
    categoria = models.CharField("Categoría", max_length=255)
    centro_costo = models.CharField("Centro de costo", max_length=100, blank=True)
    subtotal = models.DecimalField("Subtotal", max_digits=18, decimal_places=2)
    iva = models.DecimalField("IVA", max_digits=18, decimal_places=2, default=0)
    total = models.DecimalField("Total", max_digits=18, decimal_places=2)
    estado = models.CharField(max_length=25, choices=Estado.choices, default=Estado.PENDIENTE_PAGO)
    comentario_decision = models.TextField("Comentario de aprobación", blank=True)
    referencia_pago = models.CharField("Referencia de pago", max_length=100, blank=True)

    class Meta:
        db_table = "financiero_facturas_gasto"
        ordering = ["-fecha", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["proveedor", "numero_documento"], name="uq_finv2_gasto_proveedor_doc"
            )
        ]

    def __str__(self):
        return f"{self.proveedor} — {self.numero_documento}"


class PagoFacturaGasto(BaseModel):
    factura = models.ForeignKey(FacturaGasto, on_delete=models.CASCADE, related_name="pagos")
    banco = models.ForeignKey(Banco, on_delete=models.PROTECT)
    metodo_pago = models.ForeignKey(MetodoPago, on_delete=models.PROTECT)
    fecha = models.DateField("Fecha")
    monto = models.DecimalField("Monto", max_digits=18, decimal_places=2)
    referencia = models.CharField("Referencia", max_length=100)

    class Meta:
        db_table = "financiero_pagos_factura_gasto"
        ordering = ["-fecha", "-created_at"]


# CicloFacturacion sigue siendo el agregado raíz del ingreso; los campos se
# instalan aquí para no volver a abrir el monolito legacy models_base.py.
CicloFacturacion.add_to_class(
    "cliente",
    models.ForeignKey(
        Cliente, on_delete=models.PROTECT, null=True, blank=True, related_name="ciclos_facturacion"
    ),
)
CicloFacturacion.add_to_class(
    "proyecto",
    models.ForeignKey(
        "contratos.Contrato",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="facturas_ingreso",
        verbose_name="Proyecto",
    ),
)
CicloFacturacion.add_to_class(
    "banco_pago",
    models.ForeignKey(
        Banco,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ciclos_facturacion_pagados",
    ),
)
CicloFacturacion.add_to_class(
    "numero_secuencial",
    models.PositiveIntegerField("Número secuencial", null=True, blank=True, unique=True),
)
CicloFacturacion.add_to_class(
    "subtotal", models.DecimalField("Subtotal", max_digits=18, decimal_places=2, default=0)
)
CicloFacturacion.add_to_class(
    "iva", models.DecimalField("IVA", max_digits=18, decimal_places=2, default=0)
)
CicloFacturacion.add_to_class(
    "total", models.DecimalField("Total", max_digits=18, decimal_places=2, default=0)
)
CicloFacturacion.add_to_class(
    "plazo_pago_dias", models.PositiveIntegerField("Plazo de pago (días)", null=True, blank=True)
)
CicloFacturacion.add_to_class(
    "referencia_cobro", models.CharField("Referencia de cobro", max_length=100, blank=True)
)
# Auditoría de emisión (#249 gap 6): BaseModel solo trae created_at/updated_at
# (sin autor) -- se agrega el campo mínimo para saber "quién" emitió la
# factura, análogo a `AuditoriaTercero.usuario` de #261/#262.
CicloFacturacion.add_to_class(
    "creado_por",
    models.CharField("Emitida por", max_length=150, blank=True),
)


def _dias_desde(fecha):
    if not fecha:
        return None
    return (timezone.localdate() - fecha).days


def _dias_morosidad(self):
    """Días de mora sobre la fecha de vencimiento, sólo si aún no está pagada.

    Vencimiento = fecha_factura + plazo_pago_dias (#249 gap 4, usa el plazo
    de la factura -- que a su vez hereda de `Cliente.plazo_pago_dias`, #261 --
    no un campo nuevo). Devuelve 0 si todavía no vence o si no hay datos
    suficientes para calcularlo.
    """
    if self.estado == CicloFacturacion.Estado.PAGO_RECIBIDO:
        return 0
    if not self.fecha_factura or not self.plazo_pago_dias:
        return 0
    vencimiento = self.fecha_factura + timezone.timedelta(days=self.plazo_pago_dias)
    dias = _dias_desde(vencimiento)
    return max(0, dias) if dias is not None else 0


CicloFacturacion.dias_morosidad = property(_dias_morosidad)


class AuditoriaFacturaIngreso(BaseModel):
    """Bitácora inmutable de cambios sobre una factura de ingreso ya emitida.

    Mismo patrón que `AuditoriaTercero` (#261/#262): campo/anterior/nuevo +
    quién + cuándo (created_at heredado de BaseModel).
    """

    ciclo = models.ForeignKey(
        CicloFacturacion, on_delete=models.CASCADE, related_name="auditoria_factura"
    )
    campo = models.CharField(max_length=80)
    valor_anterior = models.TextField(blank=True)
    valor_nuevo = models.TextField(blank=True)
    usuario = models.CharField(max_length=150, blank=True)

    class Meta:
        db_table = "financiero_auditoria_facturas_ingreso"
        ordering = ["-created_at"]


class CargaFacturasIngreso(BaseModel):
    """Trazabilidad de una importación masiva de facturas de ingreso (#249 gap 3)."""

    archivo_nombre = models.CharField(max_length=255)
    usuario = models.CharField(max_length=150, blank=True)
    filas_total = models.PositiveIntegerField(default=0)
    filas_validas = models.PositiveIntegerField(default=0)
    filas_error = models.PositiveIntegerField(default=0)
    filas_creadas = models.PositiveIntegerField(default=0)
    filas_actualizadas = models.PositiveIntegerField(default=0)
    resultado = models.CharField(
        max_length=20,
        choices=[("PREVIEW", "Vista previa"), ("CONFIRMADA", "Confirmada"), ("RECHAZADA", "Rechazada")],
    )
    detalle_errores = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "financiero_cargas_facturas_ingreso"
        ordering = ["-created_at"]


class LineaFacturaIngreso(BaseModel):
    ciclo = models.ForeignKey(
        CicloFacturacion, on_delete=models.CASCADE, related_name="lineas_factura"
    )
    descripcion = models.CharField("Descripción", max_length=255)
    cantidad = models.DecimalField("Cantidad", max_digits=12, decimal_places=2, default=1)
    valor_unitario = models.DecimalField("Valor unitario", max_digits=18, decimal_places=2)
    total = models.DecimalField("Total", max_digits=18, decimal_places=2)

    class Meta:
        db_table = "financiero_lineas_factura_ingreso"
        ordering = ["created_at"]


class PagoFacturaIngreso(BaseModel):
    ciclo = models.ForeignKey(
        CicloFacturacion, on_delete=models.CASCADE, related_name="pagos_factura"
    )
    banco = models.ForeignKey(Banco, on_delete=models.PROTECT)
    metodo_pago = models.ForeignKey(MetodoPago, on_delete=models.PROTECT)
    fecha = models.DateField("Fecha")
    monto = models.DecimalField("Monto", max_digits=18, decimal_places=2)
    referencia = models.CharField("Referencia", max_length=100)
    # #249 gap 6: quién registró el pago (created_at ya lo trae BaseModel;
    # faltaba el autor -- mismo criterio que CicloFacturacion.creado_por).
    registrado_por = models.CharField("Registrado por", max_length=150, blank=True)

    class Meta:
        db_table = "financiero_pagos_factura_ingreso"
        ordering = ["-fecha", "-created_at"]
