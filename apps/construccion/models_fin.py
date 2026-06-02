"""B3 (#123) — Módulo Financiero de Construcción: 5 modelos nuevos.

Duplica e integra el módulo financiero mejorado del sistema de mantenimiento/líneas
hacia construcción (issue #123, Fase 1). Los 5 modelos:

1. ``PresupuestoDetalladoConstruccion`` — presupuesto con datos JSON por año/tipo.
2. ``CostosConstruccion``             — costos ejecutados con ``costo_total`` auto en save().
3. ``CostosActividadConstruccion``    — desglose de costos por actividad (OneToOne).
4. ``FacturacionConstruccion``        — facturación del proyecto.
5. ``IndicadorANSConstruccion``       — ANS con ``estado`` clasificado en save().

NO recrea ``IndicadorFinancieroConstruccion`` / ``IndicadorTecnicoConstruccion``
(ya viven en ``models_b2_indicadores.py``).

Nota sobre el FK ``actividad`` (CostosConstruccion / CostosActividadConstruccion):
    El issue #123 lo describe como ``ActividadConstruccion``, pero ese modelo NO
    existe en construcción. El propio issue advierte: "No tiene relación con
    Actividades (diferente modelo)". El único modelo de construcción que
    representa un work-item por estructura es ``ActividadFinalTorre`` (checklist
    de actividades finales/cierre por torre, db_table
    ``construccion_actividad_final_torre``). Se usa ese como target real:
      - ``CostosConstruccion.actividad`` → FK **nullable** (un costo puede no estar
        atado a una actividad específica).
      - ``CostosActividadConstruccion.actividad`` → OneToOne (un desglose por
        actividad). Si más adelante se introduce un modelo de actividad de
        construcción dedicado, migrar el target.
"""
from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel


# ===========================================================================
# 1. PRESUPUESTO DETALLADO
# ===========================================================================
class PresupuestoDetalladoConstruccion(BaseModel):
    """Presupuesto detallado con estructura de costos en JSON por año/tipo.

    ``datos`` almacena la estructura de costos con valores mensuales (mismo
    patrón que ``PresupuestoDetallado`` de mantenimiento). ``unique_together``
    garantiza un único presupuesto por (proyecto, año, tipo).
    """

    class Tipo(models.TextChoices):
        PLANEADO = 'PLANEADO', 'Planeado'
        REAL = 'REAL', 'Real'

    proyecto = models.ForeignKey(
        'construccion.ProyectoConstruccion',
        on_delete=models.CASCADE,
        related_name='presupuestos_detallados',
        verbose_name='Proyecto',
    )
    anio = models.PositiveIntegerField('Año')
    tipo = models.CharField(
        'Tipo', max_length=10, choices=Tipo.choices, default=Tipo.PLANEADO,
    )
    datos = models.JSONField(
        'Datos', default=dict, blank=True,
        help_text='Estructura de costos con valores mensuales.',
    )

    class Meta:
        db_table = 'construccion_presupuesto_detallado'
        verbose_name = 'Presupuesto Detallado de Construcción'
        verbose_name_plural = 'Presupuestos Detallados de Construcción'
        ordering = ['-anio', 'tipo']
        unique_together = (('proyecto', 'anio', 'tipo'),)

    def __str__(self):
        return f"Presupuesto {self.get_tipo_display()} {self.anio} — {self.proyecto_id}"


# ===========================================================================
# 2. COSTOS
# ===========================================================================
class CostosConstruccion(BaseModel):
    """Costo ejecutado individual. ``costo_total`` se calcula en save()."""

    class TipoRecurso(models.TextChoices):
        MATERIAL = 'MATERIAL', 'Material'
        MANO_OBRA = 'MANO_OBRA', 'Mano de obra'
        EQUIPOS = 'EQUIPOS', 'Equipos'
        SUBCONTRATA = 'SUBCONTRATA', 'Subcontrata'
        OTROS = 'OTROS', 'Otros'

    proyecto = models.ForeignKey(
        'construccion.ProyectoConstruccion',
        on_delete=models.CASCADE,
        related_name='costos',
        verbose_name='Proyecto',
    )
    # Ver nota de módulo: no existe ActividadConstruccion; ActividadFinalTorre es
    # el modelo de actividad real más cercano. FK nullable.
    actividad = models.ForeignKey(
        'construccion.ActividadFinalTorre',
        on_delete=models.SET_NULL,
        related_name='costos',
        null=True, blank=True,
        verbose_name='Actividad',
    )
    concepto = models.CharField('Concepto', max_length=300)
    tipo_recurso = models.CharField(
        'Tipo de recurso', max_length=20,
        choices=TipoRecurso.choices, default=TipoRecurso.MATERIAL,
    )
    cantidad = models.DecimalField(
        'Cantidad', max_digits=15, decimal_places=2, default=Decimal('0'),
    )
    costo_unitario = models.DecimalField(
        'Costo unitario', max_digits=15, decimal_places=2, default=Decimal('0'),
    )
    costo_total = models.DecimalField(
        'Costo total', max_digits=18, decimal_places=2, default=Decimal('0'),
        help_text='cantidad × costo_unitario. Auto-calculado en save().',
    )
    fecha = models.DateField('Fecha', default=timezone.now)

    class Meta:
        db_table = 'construccion_costos'
        verbose_name = 'Costo de Construcción'
        verbose_name_plural = 'Costos de Construcción'
        ordering = ['-fecha', '-created_at']

    def __str__(self):
        return f"{self.concepto} — {self.costo_total} ({self.get_tipo_recurso_display()})"

    def calcular_costo_total(self) -> Decimal:
        """cantidad × costo_unitario, redondeado a 2 decimales."""
        cantidad = self.cantidad if self.cantidad is not None else Decimal('0')
        unitario = self.costo_unitario if self.costo_unitario is not None else Decimal('0')
        return (Decimal(cantidad) * Decimal(unitario)).quantize(Decimal('0.01'))

    def save(self, *args, **kwargs):
        self.costo_total = self.calcular_costo_total()
        super().save(*args, **kwargs)


class CostosActividadConstruccion(BaseModel):
    """Desglose de costos por actividad (un registro por actividad)."""

    # Ver nota de módulo: target real ActividadFinalTorre.
    actividad = models.OneToOneField(
        'construccion.ActividadFinalTorre',
        on_delete=models.CASCADE,
        related_name='costos_actividad',
        verbose_name='Actividad',
    )
    costo_materiales = models.DecimalField(
        'Costo materiales', max_digits=18, decimal_places=2, default=Decimal('0'),
    )
    costo_mano_obra = models.DecimalField(
        'Costo mano de obra', max_digits=18, decimal_places=2, default=Decimal('0'),
    )
    costo_equipos = models.DecimalField(
        'Costo equipos', max_digits=18, decimal_places=2, default=Decimal('0'),
    )
    costo_subcontratos = models.DecimalField(
        'Costo subcontratos', max_digits=18, decimal_places=2, default=Decimal('0'),
    )
    costo_otros = models.DecimalField(
        'Costo otros', max_digits=18, decimal_places=2, default=Decimal('0'),
    )

    class Meta:
        db_table = 'construccion_costos_actividad'
        verbose_name = 'Costo por Actividad de Construcción'
        verbose_name_plural = 'Costos por Actividad de Construcción'
        ordering = ['-created_at']

    def __str__(self):
        return f"Costos actividad {self.actividad_id} — total {self.costo_total}"

    @property
    def costo_total(self) -> Decimal:
        """Suma de los 5 componentes de costo."""
        return (
            (self.costo_materiales or Decimal('0'))
            + (self.costo_mano_obra or Decimal('0'))
            + (self.costo_equipos or Decimal('0'))
            + (self.costo_subcontratos or Decimal('0'))
            + (self.costo_otros or Decimal('0'))
        )


# ===========================================================================
# 3. FACTURACIÓN
# ===========================================================================
class FacturacionConstruccion(BaseModel):
    """Facturación del proyecto de construcción."""

    class Estado(models.TextChoices):
        EMITIDA = 'EMITIDA', 'Emitida'
        EN_VALIDACION = 'EN_VALIDACION', 'En validación'
        PAGADA = 'PAGADA', 'Pagada'

    proyecto = models.ForeignKey(
        'construccion.ProyectoConstruccion',
        on_delete=models.CASCADE,
        related_name='facturacion',
        verbose_name='Proyecto',
    )
    numero_factura = models.CharField('Número de factura', max_length=100)
    fecha_emision = models.DateField('Fecha de emisión', default=timezone.now)
    monto_facturado = models.DecimalField(
        'Monto facturado', max_digits=18, decimal_places=2, default=Decimal('0'),
    )
    monto_pagado = models.DecimalField(
        'Monto pagado', max_digits=18, decimal_places=2, default=Decimal('0'),
    )
    estado = models.CharField(
        'Estado', max_length=20, choices=Estado.choices, default=Estado.EMITIDA,
    )
    observaciones = models.TextField('Observaciones', blank=True)

    class Meta:
        db_table = 'construccion_facturacion'
        verbose_name = 'Facturación de Construcción'
        verbose_name_plural = 'Facturación de Construcción'
        ordering = ['-fecha_emision', '-created_at']

    def __str__(self):
        return f"Factura {self.numero_factura} — {self.monto_facturado} ({self.get_estado_display()})"

    @property
    def saldo_pendiente(self) -> Decimal:
        """Monto facturado menos lo pagado."""
        return (self.monto_facturado or Decimal('0')) - (self.monto_pagado or Decimal('0'))


# ===========================================================================
# 4. INDICADOR ANS
# ===========================================================================
# Umbrales de clasificación de estado (espejo de IndicadorANSContractual del
# módulo de mantenimiento: cumple / parcial / no-cumple según valor vs meta).
# Aquí la meta es por-indicador, no un puntaje ponderado global.
UMBRAL_ANS_PARCIAL_PCT = Decimal('90')  # ≥ 90 % de la meta → parcial; ≥ meta → cumplido


class IndicadorANSConstruccion(BaseModel):
    """Indicador ANS (Acuerdo de Nivel de Servicio) de construcción.

    ``estado`` se clasifica en ``save()`` comparando ``valor_actual`` contra
    ``meta_porcentaje`` (espejo de la lógica de ``IndicadorANSContractual``):

    - ``valor_actual >= meta_porcentaje``                       → cumplido
    - ``meta * 90 % <= valor_actual < meta``                    → parcial
    - ``valor_actual < meta * 90 %``                            → incumplido
    """

    class Estado(models.TextChoices):
        CUMPLIDO = 'cumplido', 'Cumplido'
        PARCIAL = 'parcial', 'Parcial'
        INCUMPLIDO = 'incumplido', 'Incumplido'

    proyecto = models.ForeignKey(
        'construccion.ProyectoConstruccion',
        on_delete=models.CASCADE,
        related_name='indicadores_ans',
        verbose_name='Proyecto',
    )
    nombre = models.CharField(
        'Nombre', max_length=200,
        help_text='Ej: "% Cumplimiento Programación".',
    )
    descripcion = models.TextField('Descripción', blank=True)
    meta_porcentaje = models.DecimalField(
        'Meta (%)', max_digits=6, decimal_places=2, default=Decimal('0'),
    )
    peso = models.DecimalField(
        'Peso', max_digits=5, decimal_places=2, null=True, blank=True,
    )
    periodo_anio = models.PositiveIntegerField('Año del período')
    periodo_mes = models.PositiveSmallIntegerField('Mes del período')
    valor_actual = models.DecimalField(
        'Valor actual (%)', max_digits=6, decimal_places=2, default=Decimal('0'),
    )
    estado = models.CharField(
        'Estado', max_length=12, choices=Estado.choices, default=Estado.INCUMPLIDO,
    )

    class Meta:
        db_table = 'construccion_indicador_ans'
        verbose_name = 'Indicador ANS de Construcción'
        verbose_name_plural = 'Indicadores ANS de Construcción'
        ordering = ['-periodo_anio', '-periodo_mes', 'nombre']

    def __str__(self):
        return (
            f"{self.nombre} {self.periodo_mes:02d}/{self.periodo_anio} — "
            f"{self.valor_actual}% ({self.get_estado_display()})"
        )

    def clasificar_estado(self) -> str:
        """Clasifica estado según valor_actual vs meta_porcentaje.

        Espejo de ``IndicadorANSContractual.clasificar_estado`` adaptado a un
        único valor contra su meta (3 estados: cumplido / parcial / incumplido).
        """
        meta = self.meta_porcentaje if self.meta_porcentaje is not None else Decimal('0')
        valor = self.valor_actual if self.valor_actual is not None else Decimal('0')
        meta = Decimal(meta)
        valor = Decimal(valor)
        if meta <= 0:
            # Sin meta definida: cualquier valor ≥ 0 se considera cumplido.
            return self.Estado.CUMPLIDO
        if valor >= meta:
            return self.Estado.CUMPLIDO
        umbral_parcial = (meta * UMBRAL_ANS_PARCIAL_PCT) / Decimal('100')
        if valor >= umbral_parcial:
            return self.Estado.PARCIAL
        return self.Estado.INCUMPLIDO

    def save(self, *args, **kwargs):
        self.estado = self.clasificar_estado()
        super().save(*args, **kwargs)
