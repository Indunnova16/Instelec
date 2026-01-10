"""
Models for financial management and billing.
"""
from django.db import models
from apps.core.models import BaseModel


class CostoRecurso(BaseModel):
    """
    Resource cost configuration.
    """

    class TipoRecurso(models.TextChoices):
        DIA_HOMBRE = 'DIA_HOMBRE', 'Día Hombre'
        VEHICULO = 'VEHICULO', 'Vehículo'
        VIATICO = 'VIATICO', 'Viático'
        HERRAMIENTA = 'HERRAMIENTA', 'Herramienta'
        MATERIAL = 'MATERIAL', 'Material'
        OTRO = 'OTRO', 'Otro'

    tipo = models.CharField(
        'Tipo de recurso',
        max_length=20,
        choices=TipoRecurso.choices
    )
    descripcion = models.CharField(
        'Descripción',
        max_length=200
    )
    costo_unitario = models.DecimalField(
        'Costo unitario',
        max_digits=12,
        decimal_places=2
    )
    unidad = models.CharField(
        'Unidad',
        max_length=20,
        default='DIA',
        help_text='DIA, HORA, UNIDAD, etc.'
    )
    vigencia_desde = models.DateField('Vigencia desde')
    vigencia_hasta = models.DateField(
        'Vigencia hasta',
        null=True,
        blank=True
    )
    activo = models.BooleanField('Activo', default=True)

    class Meta:
        db_table = 'costos_recursos'
        verbose_name = 'Costo de Recurso'
        verbose_name_plural = 'Costos de Recursos'
        ordering = ['tipo', 'descripcion']

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.descripcion}"


class Presupuesto(BaseModel):
    """
    Monthly budget.
    """

    class Estado(models.TextChoices):
        PROYECTADO = 'PROYECTADO', 'Proyectado'
        APROBADO = 'APROBADO', 'Aprobado'
        EN_EJECUCION = 'EN_EJECUCION', 'En Ejecución'
        CERRADO = 'CERRADO', 'Cerrado'

    anio = models.PositiveIntegerField('Año')
    mes = models.PositiveIntegerField('Mes')
    linea = models.ForeignKey(
        'lineas.Linea',
        on_delete=models.CASCADE,
        related_name='presupuestos',
        verbose_name='Línea'
    )

    estado = models.CharField(
        'Estado',
        max_length=20,
        choices=Estado.choices,
        default=Estado.PROYECTADO
    )

    # Planned costs
    dias_hombre_planeados = models.PositiveIntegerField(
        'Días hombre planeados',
        default=0
    )
    costo_dias_hombre = models.DecimalField(
        'Costo días hombre',
        max_digits=14,
        decimal_places=2,
        default=0
    )
    dias_vehiculo_planeados = models.PositiveIntegerField(
        'Días vehículo planeados',
        default=0
    )
    costo_vehiculos = models.DecimalField(
        'Costo vehículos',
        max_digits=14,
        decimal_places=2,
        default=0
    )
    viaticos_planeados = models.DecimalField(
        'Viáticos planeados',
        max_digits=14,
        decimal_places=2,
        default=0
    )
    otros_costos = models.DecimalField(
        'Otros costos',
        max_digits=14,
        decimal_places=2,
        default=0
    )

    # Totals
    total_presupuestado = models.DecimalField(
        'Total presupuestado',
        max_digits=14,
        decimal_places=2,
        default=0
    )
    total_ejecutado = models.DecimalField(
        'Total ejecutado',
        max_digits=14,
        decimal_places=2,
        default=0
    )

    # Billing
    facturacion_esperada = models.DecimalField(
        'Facturación esperada',
        max_digits=14,
        decimal_places=2,
        default=0
    )

    observaciones = models.TextField('Observaciones', blank=True)

    class Meta:
        db_table = 'presupuestos'
        verbose_name = 'Presupuesto'
        verbose_name_plural = 'Presupuestos'
        unique_together = ['anio', 'mes', 'linea']
        ordering = ['-anio', '-mes', 'linea']

    def __str__(self):
        return f"Presupuesto {self.linea.codigo} - {self.mes}/{self.anio}"

    @property
    def desviacion(self):
        """Calculate budget deviation."""
        if self.total_presupuestado == 0:
            return 0
        return ((self.total_ejecutado - self.total_presupuestado) / self.total_presupuestado) * 100

    @property
    def utilidad_proyectada(self):
        """Projected profit."""
        return self.facturacion_esperada - self.total_presupuestado

    def calcular_totales(self):
        """Calculate totals from components."""
        self.total_presupuestado = (
            self.costo_dias_hombre +
            self.costo_vehiculos +
            self.viaticos_planeados +
            self.otros_costos
        )
        self.save(update_fields=['total_presupuestado', 'updated_at'])


class EjecucionCosto(BaseModel):
    """
    Actual cost execution tracking.
    """

    presupuesto = models.ForeignKey(
        Presupuesto,
        on_delete=models.CASCADE,
        related_name='ejecuciones',
        verbose_name='Presupuesto'
    )
    actividad = models.ForeignKey(
        'actividades.Actividad',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='costos',
        verbose_name='Actividad'
    )

    concepto = models.CharField('Concepto', max_length=200)
    tipo_recurso = models.CharField(
        'Tipo de recurso',
        max_length=20,
        choices=CostoRecurso.TipoRecurso.choices
    )
    cantidad = models.DecimalField(
        'Cantidad',
        max_digits=10,
        decimal_places=2
    )
    costo_unitario = models.DecimalField(
        'Costo unitario',
        max_digits=12,
        decimal_places=2
    )
    costo_total = models.DecimalField(
        'Costo total',
        max_digits=14,
        decimal_places=2
    )
    fecha = models.DateField('Fecha')

    class Meta:
        db_table = 'ejecucion_costos'
        verbose_name = 'Ejecución de Costo'
        verbose_name_plural = 'Ejecución de Costos'
        ordering = ['-fecha']
        indexes = [
            models.Index(fields=['presupuesto'], name='idx_ejecucion_presupuesto'),
            models.Index(fields=['actividad'], name='idx_ejecucion_actividad'),
            models.Index(fields=['fecha'], name='idx_ejecucion_fecha'),
            models.Index(fields=['tipo_recurso'], name='idx_ejecucion_tipo'),
        ]

    def __str__(self):
        return f"{self.concepto} - {self.fecha}"

    def save(self, *args, **kwargs):
        self.costo_total = self.cantidad * self.costo_unitario
        super().save(*args, **kwargs)


class CicloFacturacion(BaseModel):
    """
    Billing cycle tracking.
    """

    class Estado(models.TextChoices):
        INFORME_GENERADO = 'INFORME_GENERADO', 'Informe Generado'
        EN_VALIDACION = 'EN_VALIDACION', 'En Validación Cliente'
        ORDEN_ENTREGA = 'ORDEN_ENTREGA', 'Orden de Entrega'
        FACTURA_EMITIDA = 'FACTURA_EMITIDA', 'Factura Emitida'
        PAGO_RECIBIDO = 'PAGO_RECIBIDO', 'Pago Recibido'

    presupuesto = models.ForeignKey(
        Presupuesto,
        on_delete=models.CASCADE,
        related_name='ciclos_facturacion',
        verbose_name='Presupuesto'
    )

    estado = models.CharField(
        'Estado',
        max_length=20,
        choices=Estado.choices,
        default=Estado.INFORME_GENERADO
    )

    # Dates
    fecha_informe = models.DateField('Fecha informe', null=True, blank=True)
    fecha_validacion = models.DateField('Fecha validación', null=True, blank=True)
    fecha_orden = models.DateField('Fecha orden entrega', null=True, blank=True)
    fecha_factura = models.DateField('Fecha factura', null=True, blank=True)
    fecha_pago = models.DateField('Fecha pago', null=True, blank=True)

    # Amounts
    monto_facturado = models.DecimalField(
        'Monto facturado',
        max_digits=14,
        decimal_places=2,
        default=0
    )
    monto_pagado = models.DecimalField(
        'Monto pagado',
        max_digits=14,
        decimal_places=2,
        default=0
    )

    numero_factura = models.CharField(
        'Número de factura',
        max_length=50,
        blank=True
    )
    numero_orden = models.CharField(
        'Número orden de entrega',
        max_length=50,
        blank=True
    )

    observaciones = models.TextField('Observaciones', blank=True)

    class Meta:
        db_table = 'ciclos_facturacion'
        verbose_name = 'Ciclo de Facturación'
        verbose_name_plural = 'Ciclos de Facturación'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['presupuesto'], name='idx_ciclo_presupuesto'),
            models.Index(fields=['estado'], name='idx_ciclo_estado'),
        ]

    def __str__(self):
        return f"Facturación {self.presupuesto} - {self.estado}"

    @property
    def dias_ciclo(self):
        """Days from report to payment."""
        if self.fecha_pago and self.fecha_informe:
            return (self.fecha_pago - self.fecha_informe).days
        return None
