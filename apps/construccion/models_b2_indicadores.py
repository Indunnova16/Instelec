"""Modelos B2 — Indicadores de Construcción (#98).

3 modelos dedicados (NO reusan el modelo Indicador genérico de apps/indicadores,
que es config de KPIs para mantenimiento):

1. IndicadorFinancieroConstruccion — margen + desviación auto-calculados en save().
2. IndicadorTecnicoConstruccion — 11 campos derivados auto-calculados en save().
3. IndicadorDesempenoLinea — FK linea+cuadrilla + meta vs actual + estado clasificado.

Los cálculos viven en apps.construccion.calculators (funciones puras testeables).
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel

from . import calculators


# ===========================================================================
# 1. INDICADOR FINANCIERO
# ===========================================================================

class IndicadorFinancieroConstruccion(BaseModel):
    """Indicadores financieros del proyecto (margen + desviación)."""

    proyecto = models.ForeignKey(
        'construccion.ProyectoConstruccion',
        on_delete=models.CASCADE,
        related_name='indicadores_financieros_b2',
        verbose_name='Proyecto',
    )
    fecha = models.DateField('Fecha', default=timezone.now)

    # Inputs (entrada manual o sync semanal)
    ingresos_ejecutados = models.DecimalField(
        'Ingresos ejecutados', max_digits=15, decimal_places=2,
        default=Decimal('0'),
    )
    costos_directos = models.DecimalField(
        'Costos directos', max_digits=15, decimal_places=2,
        default=Decimal('0'),
    )
    gastos = models.DecimalField(
        'Gastos', max_digits=15, decimal_places=2,
        default=Decimal('0'),
    )
    costo_real = models.DecimalField(
        'Costo real', max_digits=15, decimal_places=2,
        default=Decimal('0'),
    )
    costo_presupuestado = models.DecimalField(
        'Costo presupuestado', max_digits=15, decimal_places=2,
        default=Decimal('0'),
    )

    # Auto-calculados en save()
    margen_operativo = models.FloatField(
        'Margen operativo (%)', null=True, blank=True,
        help_text='(IE - (CD + G)) / IE × 100. Auto-calculado.',
    )
    desviacion_presupuestal = models.FloatField(
        'Desviación presupuestal (%)', null=True, blank=True,
        help_text='(CR - CP) / CP × 100. Auto-calculado.',
    )

    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='indicadores_financieros_b2_actualizados',
    )
    observaciones = models.TextField('Observaciones', blank=True)

    class Meta:
        db_table = 'construccion_indicador_financiero'
        verbose_name = 'Indicador Financiero de Construcción'
        verbose_name_plural = 'Indicadores Financieros de Construcción'
        ordering = ['-fecha']
        indexes = [
            models.Index(fields=['proyecto', '-fecha']),
        ]

    def __str__(self):
        return f'Fin {self.proyecto.nombre} @ {self.fecha:%Y-%m-%d}'

    def recalcular(self):
        """Recalcula margen y desviación sin guardar."""
        self.margen_operativo = calculators.calcular_margen_operativo(
            self.ingresos_ejecutados, self.costos_directos, self.gastos,
        )
        self.desviacion_presupuestal = calculators.calcular_desviacion_presupuestal(
            self.costo_real, self.costo_presupuestado,
        )

    def save(self, *args, **kwargs):
        self.recalcular()
        super().save(*args, **kwargs)

    @property
    def estado_margen(self) -> str:
        return calculators.clasificar_margen_operativo(self.margen_operativo)

    @property
    def estado_desviacion(self) -> str:
        return calculators.clasificar_desviacion_presupuestal(self.desviacion_presupuestal)


# ===========================================================================
# 2. INDICADOR TÉCNICO
# ===========================================================================

class IndicadorTecnicoConstruccion(BaseModel):
    """Indicadores técnicos del proyecto (avance, productividad, etc).

    11 campos: 6 inputs + 5 derivados (auto-calculados en save).
    """

    proyecto = models.ForeignKey(
        'construccion.ProyectoConstruccion',
        on_delete=models.CASCADE,
        related_name='indicadores_tecnicos_b2',
        verbose_name='Proyecto',
    )
    fecha = models.DateField('Fecha', default=timezone.now)

    # Inputs presupuesto
    presupuesto_ejecutado_pct = models.FloatField(
        '% Presupuesto ejecutado', default=0.0,
    )
    presupuesto_planeado_pct = models.FloatField(
        '% Presupuesto planeado', default=0.0,
    )

    # Inputs obra
    obra_ejecutada = models.DecimalField(
        'Obra ejecutada', max_digits=12, decimal_places=2,
        default=Decimal('0'),
    )
    obra_programada = models.DecimalField(
        'Obra programada', max_digits=12, decimal_places=2,
        default=Decimal('0'),
    )

    # Inputs cronograma
    actividades_completadas = models.IntegerField(
        'Actividades completadas', default=0,
    )
    actividades_planificadas = models.IntegerField(
        'Actividades planificadas', default=0,
    )

    # Inputs productividad / rendimiento
    cantidad_ejecutada = models.FloatField(
        'Cantidad ejecutada', default=0.0,
    )
    horas_hombre = models.FloatField(
        'Horas hombre', default=0.0,
    )

    # Auto-calculados en save() — 5 fórmulas
    ejecucion_presupuestal = models.FloatField(
        'Ejecución Presupuestal (%)', null=True, blank=True,
    )
    avance_obra = models.FloatField(
        'Avance de Obra (%)', null=True, blank=True,
    )
    cumplimiento_cronograma = models.FloatField(
        'Cumplimiento Cronograma (%)', null=True, blank=True,
    )
    productividad = models.FloatField(
        'Productividad (%)', null=True, blank=True,
    )
    rendimiento_cuadrillas = models.FloatField(
        'Rendimiento Cuadrillas (%)', null=True, blank=True,
    )

    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='indicadores_tecnicos_b2_actualizados',
    )
    observaciones = models.TextField('Observaciones', blank=True)

    class Meta:
        db_table = 'construccion_indicador_tecnico'
        verbose_name = 'Indicador Técnico de Construcción'
        verbose_name_plural = 'Indicadores Técnicos de Construcción'
        ordering = ['-fecha']
        indexes = [
            models.Index(fields=['proyecto', '-fecha']),
        ]

    def __str__(self):
        return f'Téc {self.proyecto.nombre} @ {self.fecha:%Y-%m-%d}'

    def recalcular(self):
        """Recalcula los 5 indicadores derivados sin guardar."""
        self.ejecucion_presupuestal = calculators.calcular_ejecucion_presupuestal(
            self.presupuesto_ejecutado_pct, self.presupuesto_planeado_pct,
        )
        self.avance_obra = calculators.calcular_avance_obra(
            self.obra_ejecutada, self.obra_programada,
        )
        self.cumplimiento_cronograma = calculators.calcular_cumplimiento_cronograma(
            self.actividades_completadas, self.actividades_planificadas,
        )
        self.productividad = calculators.calcular_productividad(
            self.cantidad_ejecutada, self.horas_hombre,
        )
        self.rendimiento_cuadrillas = calculators.calcular_rendimiento_cuadrillas(
            self.cantidad_ejecutada, self.horas_hombre,
        )

    def save(self, *args, **kwargs):
        self.recalcular()
        super().save(*args, **kwargs)

    @property
    def estado_avance_obra(self) -> str:
        return calculators.clasificar_cumplimiento(self.avance_obra, meta=80.0)

    @property
    def estado_cumplimiento(self) -> str:
        return calculators.clasificar_cumplimiento(self.cumplimiento_cronograma, meta=95.0)


# ===========================================================================
# 3. INDICADOR DESEMPEÑO LÍNEA
# ===========================================================================

class IndicadorDesempenoLinea(BaseModel):
    """Indicadores de desempeño por línea + cuadrilla + tipo trabajo.

    Estado se clasifica automáticamente en save() comparando actual vs meta.
    """

    class TipoTrabajo(models.TextChoices):
        OBRA_CIVIL = 'OBRA_CIVIL', 'Obra Civil'
        MONTAJE = 'MONTAJE', 'Montaje'
        TENDIDO = 'TENDIDO', 'Tendido'
        TENDIDO_CONDUCTOR = 'TENDIDO_CONDUCTOR', 'Tendido Conductor'

    class Unidad(models.TextChoices):
        UND_DIA = 'und/día', 'Unidades por día'
        TORRES_SEMANA = 'torres/semana', 'Torres por semana'
        KM_SEMANA = 'km/semana', 'Kilómetros por semana'
        KM_DIA = 'km/día', 'Kilómetros por día'

    class Estado(models.TextChoices):
        EN_META = 'EN_META', 'En meta'
        BAJO_META = 'BAJO_META', 'Bajo meta'
        SOBRE_META = 'SOBRE_META', 'Sobre meta'
        SIN_DATOS = 'SIN_DATOS', 'Sin datos'

    proyecto = models.ForeignKey(
        'construccion.ProyectoConstruccion',
        on_delete=models.CASCADE,
        related_name='indicadores_desempeno_b2',
        verbose_name='Proyecto',
    )
    linea = models.ForeignKey(
        'lineas.Linea',
        on_delete=models.PROTECT,
        related_name='indicadores_desempeno_construccion_b2',
        verbose_name='Línea',
    )
    cuadrilla = models.ForeignKey(
        'cuadrillas.Cuadrilla',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='indicadores_desempeno_construccion_b2',
        verbose_name='Cuadrilla',
    )
    fecha = models.DateField('Fecha', default=timezone.now)
    tipo_trabajo = models.CharField(
        'Tipo de trabajo',
        max_length=30,
        choices=TipoTrabajo.choices,
    )
    unidad = models.CharField(
        'Unidad',
        max_length=20,
        choices=Unidad.choices,
    )
    rendimiento = models.FloatField('Rendimiento', default=0.0)
    meta = models.FloatField('Meta', default=0.0)
    actual = models.FloatField('Actual', default=0.0)
    estado = models.CharField(
        'Estado',
        max_length=12,
        choices=Estado.choices,
        default=Estado.SIN_DATOS,
        help_text='Auto-clasificado en save() según actual vs meta.',
    )
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='indicadores_desempeno_b2_actualizados',
    )
    observaciones = models.TextField('Observaciones', blank=True)

    class Meta:
        db_table = 'construccion_indicador_desempeno_linea'
        verbose_name = 'Indicador Desempeño Línea'
        verbose_name_plural = 'Indicadores Desempeño Línea'
        ordering = ['-fecha', 'linea', 'tipo_trabajo']
        indexes = [
            models.Index(fields=['proyecto', '-fecha']),
            models.Index(fields=['linea', 'tipo_trabajo']),
        ]

    def __str__(self):
        return f'{self.linea} {self.get_tipo_trabajo_display()} @ {self.fecha:%Y-%m-%d}'

    def clasificar(self):
        """Clasifica estado según actual vs meta sin guardar."""
        self.estado = calculators.clasificar_estado_desempeno(self.actual, self.meta)

    def save(self, *args, **kwargs):
        self.clasificar()
        super().save(*args, **kwargs)

    @property
    def pct_cumplimiento(self):
        """Porcentaje actual / meta. None si meta es 0."""
        if not self.meta:
            return None
        return (self.actual / self.meta) * 100
