"""
B4 — Indicadores Mantenimiento detallado + ANS Contractual.

Issue #99 — modelos dedicados al dashboard de mantenimiento del proyecto:

1. ``IndicadorMantenimientoFinanciero`` — margen operativo + desviación
   presupuestal con cálculo automático en ``save()``.
2. ``IndicadorMantenimientoTecnico`` — 4 indicadores (ejecución presupuestal,
   producción cuadrillas, rentabilidad costo fijo, meta facturación).
3. ``IndicadorANSContractual`` — 5 componentes ponderados + ``puntaje_total_ans``
   y ``estado_ans`` (CUMPLE / PARCIAL / NO_CUMPLE) calculados en ``save()``.

NO reutiliza el modelo ``Indicador`` genérico existente: ese es config de KPIs
genéricos. Estos son tablas concretas con un registro por mes/línea.
"""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import BaseModel

# Pesos oficiales por componente ANS (fuente: issue #99).
PESO_PROGRAMACION = Decimal("0.30")
PESO_EJECUCION = Decimal("0.30")
PESO_INFO_CONTRACTUAL = Decimal("0.15")
PESO_INFO_AMBIENTAL = Decimal("0.15")
PESO_DISPONIBILIDAD = Decimal("0.10")

# Umbrales clasificación estado ANS (fuente: issue #99, meta total >= 90 %).
UMBRAL_ANS_CUMPLE = Decimal("90")
UMBRAL_ANS_PARCIAL = Decimal("75")

# Metas oficiales (fuente: issue #99).
META_MARGEN_OPERATIVO = Decimal("20")          # >= 20 %
META_DESVIACION_PRESUPUESTAL = Decimal("25")   # <= 25 %
META_EJECUCION_PRESUPUESTAL = Decimal("2.95")  # = 2.95 %
META_PRODUCCION_CUADRILLAS = Decimal("2.95")   # >= 2.95 %
META_RENTABILIDAD_COSTO_FIJO = Decimal("12")   # >= 12 (ratio)
META_FACTURACION_GENERAL = Decimal("100")      # >= 100 %


def _safe_div(num, den):
    """Divide returning Decimal; 0/0 -> 0; negatives passed through."""
    if den is None or den == 0:
        return Decimal("0")
    return Decimal(num) / Decimal(den)


# ---------------------------------------------------------------------------
# 1) Financieros
# ---------------------------------------------------------------------------
class IndicadorMantenimientoFinanciero(BaseModel):
    """
    Indicadores financieros del mantenimiento del proyecto.

    Calcula ``margen_operativo`` y ``desviacion_presupuestal`` en ``save()``
    a partir de los insumos crudos. Si todos los insumos vienen en 0, conserva
    los valores explícitos (carga histórica donde solo se guarda el %).
    """

    linea = models.ForeignKey(
        "lineas.Linea",
        on_delete=models.PROTECT,
        related_name="indicadores_mant_financiero",
        null=True,
        blank=True,
        verbose_name="Linea",
        help_text="Linea asociada (opcional, agregado por proyecto si vacio).",
    )
    fecha = models.DateField("Fecha de corte")
    anio = models.PositiveSmallIntegerField("Anio")
    mes = models.PositiveSmallIntegerField(
        "Mes",
        validators=[MinValueValidator(1), MaxValueValidator(12)],
    )

    # Insumos crudos
    ingresos_ejecutados = models.DecimalField(
        "Ingresos ejecutados", max_digits=18, decimal_places=2, default=0
    )
    costos_directos = models.DecimalField(
        "Costos directos", max_digits=18, decimal_places=2, default=0
    )
    gastos = models.DecimalField(
        "Gastos", max_digits=18, decimal_places=2, default=0
    )
    costo_real = models.DecimalField(
        "Costo real", max_digits=18, decimal_places=2, default=0
    )
    costo_presupuestado = models.DecimalField(
        "Costo presupuestado", max_digits=18, decimal_places=2, default=0
    )

    # Calculados
    margen_operativo = models.DecimalField(
        "Margen operativo (%)",
        max_digits=8,
        decimal_places=2,
        default=0,
        help_text="(IE - (CD + G)) / IE x 100. Meta >= 20 %.",
    )
    desviacion_presupuestal = models.DecimalField(
        "Desviacion presupuestal (%)",
        max_digits=8,
        decimal_places=2,
        default=0,
        help_text="(CR - CP) / CP x 100. Meta <= 25 %.",
    )

    observaciones = models.TextField("Observaciones", blank=True)
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Actualizado por",
    )

    class Meta:
        db_table = "indicadores_mant_financiero"
        verbose_name = "Indicador Mantenimiento Financiero"
        verbose_name_plural = "Indicadores Mantenimiento Financiero"
        ordering = ["-anio", "-mes", "-fecha"]
        constraints = [
            models.UniqueConstraint(
                fields=["linea", "anio", "mes"],
                name="uniq_mant_fin_linea_periodo",
            ),
        ]

    def __str__(self):
        line = self.linea.codigo if self.linea_id else "global"
        return f"Mant.Fin {line} {self.mes:02d}/{self.anio} - margen={self.margen_operativo}%"

    # --- calculo automatico ------------------------------------------------
    def calcular_margen(self) -> Decimal:
        if self.ingresos_ejecutados and self.ingresos_ejecutados > 0:
            return (
                (self.ingresos_ejecutados - (self.costos_directos + self.gastos))
                / self.ingresos_ejecutados
            ) * Decimal("100")
        return Decimal("0")

    def calcular_desviacion(self) -> Decimal:
        if self.costo_presupuestado and self.costo_presupuestado > 0:
            return (
                (self.costo_real - self.costo_presupuestado) / self.costo_presupuestado
            ) * Decimal("100")
        return Decimal("0")

    @property
    def cumple_margen(self) -> bool:
        return self.margen_operativo >= META_MARGEN_OPERATIVO

    @property
    def cumple_desviacion(self) -> bool:
        return self.desviacion_presupuestal <= META_DESVIACION_PRESUPUESTAL

    def save(self, *args, **kwargs):
        has_raw_inputs = bool(
            self.ingresos_ejecutados
            or self.costos_directos
            or self.gastos
            or self.costo_real
            or self.costo_presupuestado
        )
        if has_raw_inputs:
            self.margen_operativo = self.calcular_margen().quantize(Decimal("0.01"))
            self.desviacion_presupuestal = self.calcular_desviacion().quantize(
                Decimal("0.01")
            )
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# 2) Tecnicos
# ---------------------------------------------------------------------------
class IndicadorMantenimientoTecnico(BaseModel):
    """
    Indicadores tecnicos del mantenimiento.

    Calcula en ``save()``:
    - ejecucion_presupuestal = facturacion_real / meta_facturacion * 100
    - produccion_cuadrillas  = produccion_real / meta_produccion * 100
    - rentabilidad_costo_fijo = valor_facturado / costo_cuadrilla
    - meta_facturacion_general = facturacion_real / meta_facturacion * 100
    """

    linea = models.ForeignKey(
        "lineas.Linea",
        on_delete=models.PROTECT,
        related_name="indicadores_mant_tecnico",
        null=True,
        blank=True,
        verbose_name="Linea",
    )
    fecha = models.DateField("Fecha de corte")
    anio = models.PositiveSmallIntegerField("Anio")
    mes = models.PositiveSmallIntegerField(
        "Mes",
        validators=[MinValueValidator(1), MaxValueValidator(12)],
    )

    facturacion_real = models.DecimalField(
        "Facturacion real", max_digits=18, decimal_places=2, default=0
    )
    meta_facturacion = models.DecimalField(
        "Meta facturacion", max_digits=18, decimal_places=2, default=0
    )
    produccion_real = models.DecimalField(
        "Produccion real", max_digits=18, decimal_places=4, default=0
    )
    meta_produccion = models.DecimalField(
        "Meta produccion", max_digits=18, decimal_places=4, default=0
    )
    valor_facturado = models.DecimalField(
        "Valor facturado", max_digits=18, decimal_places=2, default=0
    )
    costo_cuadrilla = models.DecimalField(
        "Costo cuadrilla", max_digits=18, decimal_places=2, default=0
    )

    ejecucion_presupuestal = models.DecimalField(
        "Ejecucion presupuestal (%)",
        max_digits=10,
        decimal_places=4,
        default=0,
        help_text="FR / MF x 100. Meta 2.95 %.",
    )
    produccion_cuadrillas = models.DecimalField(
        "Produccion cuadrillas (%)",
        max_digits=10,
        decimal_places=4,
        default=0,
        help_text="PR / MP x 100. Meta >= 2.95 %.",
    )
    rentabilidad_costo_fijo = models.DecimalField(
        "Rentabilidad costo fijo (ratio)",
        max_digits=10,
        decimal_places=4,
        default=0,
        help_text="VF / CC. Meta >= 12.",
    )
    meta_facturacion_general = models.DecimalField(
        "Meta facturacion general (%)",
        max_digits=10,
        decimal_places=4,
        default=0,
        help_text="FR / MF x 100. Meta >= 100 %.",
    )

    observaciones = models.TextField("Observaciones", blank=True)
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Actualizado por",
    )

    class Meta:
        db_table = "indicadores_mant_tecnico"
        verbose_name = "Indicador Mantenimiento Tecnico"
        verbose_name_plural = "Indicadores Mantenimiento Tecnico"
        ordering = ["-anio", "-mes", "-fecha"]
        constraints = [
            models.UniqueConstraint(
                fields=["linea", "anio", "mes"],
                name="uniq_mant_tec_linea_periodo",
            ),
        ]

    def __str__(self):
        line = self.linea.codigo if self.linea_id else "global"
        return (
            f"Mant.Tec {line} {self.mes:02d}/{self.anio} - "
            f"ejec={self.ejecucion_presupuestal}% rcf={self.rentabilidad_costo_fijo}"
        )

    def calcular_ejecucion_presupuestal(self) -> Decimal:
        return _safe_div(self.facturacion_real, self.meta_facturacion) * Decimal("100")

    def calcular_produccion_cuadrillas(self) -> Decimal:
        return _safe_div(self.produccion_real, self.meta_produccion) * Decimal("100")

    def calcular_rentabilidad_costo_fijo(self) -> Decimal:
        return _safe_div(self.valor_facturado, self.costo_cuadrilla)

    def calcular_meta_facturacion_general(self) -> Decimal:
        return _safe_div(self.facturacion_real, self.meta_facturacion) * Decimal("100")

    @property
    def cumple_ejecucion(self) -> bool:
        return abs(self.ejecucion_presupuestal - META_EJECUCION_PRESUPUESTAL) <= Decimal(
            "0.30"
        )

    @property
    def cumple_produccion(self) -> bool:
        return self.produccion_cuadrillas >= META_PRODUCCION_CUADRILLAS

    @property
    def cumple_rentabilidad(self) -> bool:
        return self.rentabilidad_costo_fijo >= META_RENTABILIDAD_COSTO_FIJO

    @property
    def cumple_meta_facturacion(self) -> bool:
        return self.meta_facturacion_general >= META_FACTURACION_GENERAL

    def save(self, *args, **kwargs):
        has_raw_inputs = bool(
            self.facturacion_real
            or self.meta_facturacion
            or self.produccion_real
            or self.meta_produccion
            or self.valor_facturado
            or self.costo_cuadrilla
        )
        if has_raw_inputs:
            self.ejecucion_presupuestal = self.calcular_ejecucion_presupuestal().quantize(
                Decimal("0.0001")
            )
            self.produccion_cuadrillas = self.calcular_produccion_cuadrillas().quantize(
                Decimal("0.0001")
            )
            self.rentabilidad_costo_fijo = (
                self.calcular_rentabilidad_costo_fijo().quantize(Decimal("0.0001"))
            )
            self.meta_facturacion_general = (
                self.calcular_meta_facturacion_general().quantize(Decimal("0.0001"))
            )
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# 3) ANS Contractual (puntaje ponderado)
# ---------------------------------------------------------------------------
class IndicadorANSContractual(BaseModel):
    """
    ANS Contractual con 5 componentes ponderados.

    Pesos (fuente issue #99):
    - Programacion: 30 %
    - Ejecucion: 30 %
    - Informacion contractual: 15 %
    - Informacion ambiental: 15 %
    - Disponibilidad de circuitos: 10 % (peso "variable" del contrato; se fija
      en 10 % para que los 5 componentes sumen 100 %).

    Clasificacion ``estado_ans`` se calcula en ``save()``:
    - puntaje >= 90 -> CUMPLE
    - 75 <= puntaje < 90 -> PARCIAL
    - puntaje < 75 -> NO_CUMPLE
    """

    class Estado(models.TextChoices):
        CUMPLE = "CUMPLE", "Cumple"
        PARCIAL = "PARCIAL", "Cumplimiento parcial"
        NO_CUMPLE = "NO_CUMPLE", "No cumple"

    linea = models.ForeignKey(
        "lineas.Linea",
        on_delete=models.PROTECT,
        related_name="indicadores_ans",
        null=True,
        blank=True,
        verbose_name="Linea",
    )
    fecha = models.DateField("Fecha de corte")
    anio = models.PositiveSmallIntegerField("Anio")
    mes = models.PositiveSmallIntegerField(
        "Mes",
        validators=[MinValueValidator(1), MaxValueValidator(12)],
    )

    cumplimiento_programacion = models.DecimalField(
        "Cumplimiento programacion (%)",
        max_digits=6,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Peso 30 %. Meta >= 95 %.",
    )
    cumplimiento_ejecucion = models.DecimalField(
        "Cumplimiento ejecucion (%)",
        max_digits=6,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Peso 30 %. Meta >= 95 %.",
    )
    cumplimiento_informacion_contractual = models.DecimalField(
        "Cumplimiento informacion contractual (%)",
        max_digits=6,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Peso 15 %. Meta >= 100 %.",
    )
    cumplimiento_informacion_ambiental = models.DecimalField(
        "Cumplimiento informacion ambiental (%)",
        max_digits=6,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Peso 15 %. Meta >= 100 %.",
    )
    cumplimiento_disponibilidad_circuitos = models.DecimalField(
        "Disponibilidad circuitos (%)",
        max_digits=6,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Peso 10 %. Meta >= 98 %.",
    )

    puntaje_total_ans = models.DecimalField(
        "Puntaje total ANS (%)",
        max_digits=6,
        decimal_places=2,
        default=0,
        help_text="Suma ponderada. Meta >= 90 %.",
    )
    estado_ans = models.CharField(
        "Estado ANS",
        max_length=16,
        choices=Estado.choices,
        default=Estado.NO_CUMPLE,
    )

    observaciones = models.TextField("Observaciones", blank=True)
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Actualizado por",
    )

    class Meta:
        db_table = "indicadores_ans_contractual"
        verbose_name = "Indicador ANS Contractual"
        verbose_name_plural = "Indicadores ANS Contractual"
        ordering = ["-anio", "-mes", "-fecha"]
        constraints = [
            models.UniqueConstraint(
                fields=["linea", "anio", "mes"],
                name="uniq_ans_linea_periodo",
            ),
        ]

    def __str__(self):
        line = self.linea.codigo if self.linea_id else "global"
        return (
            f"ANS {line} {self.mes:02d}/{self.anio} - "
            f"{self.puntaje_total_ans}% ({self.estado_ans})"
        )

    def calcular_puntaje_ponderado(self) -> Decimal:
        """Suma ponderada de los 5 componentes."""
        total = (
            Decimal(self.cumplimiento_programacion) * PESO_PROGRAMACION
            + Decimal(self.cumplimiento_ejecucion) * PESO_EJECUCION
            + Decimal(self.cumplimiento_informacion_contractual) * PESO_INFO_CONTRACTUAL
            + Decimal(self.cumplimiento_informacion_ambiental) * PESO_INFO_AMBIENTAL
            + Decimal(self.cumplimiento_disponibilidad_circuitos) * PESO_DISPONIBILIDAD
        )
        return total.quantize(Decimal("0.01"))

    def clasificar_estado(self, puntaje: Decimal) -> str:
        if puntaje >= UMBRAL_ANS_CUMPLE:
            return self.Estado.CUMPLE
        if puntaje >= UMBRAL_ANS_PARCIAL:
            return self.Estado.PARCIAL
        return self.Estado.NO_CUMPLE

    @property
    def componentes(self) -> list:
        """Vector para render del dashboard: nombre, valor, peso, meta, ok."""
        return [
            {
                "key": "programacion",
                "nombre": "Cumplimiento programacion",
                "valor": self.cumplimiento_programacion,
                "peso": PESO_PROGRAMACION * 100,
                "meta": Decimal("95"),
                "ok": self.cumplimiento_programacion >= 95,
            },
            {
                "key": "ejecucion",
                "nombre": "Cumplimiento ejecucion",
                "valor": self.cumplimiento_ejecucion,
                "peso": PESO_EJECUCION * 100,
                "meta": Decimal("95"),
                "ok": self.cumplimiento_ejecucion >= 95,
            },
            {
                "key": "info_contractual",
                "nombre": "Informacion contractual",
                "valor": self.cumplimiento_informacion_contractual,
                "peso": PESO_INFO_CONTRACTUAL * 100,
                "meta": Decimal("100"),
                "ok": self.cumplimiento_informacion_contractual >= 100,
            },
            {
                "key": "info_ambiental",
                "nombre": "Informacion ambiental",
                "valor": self.cumplimiento_informacion_ambiental,
                "peso": PESO_INFO_AMBIENTAL * 100,
                "meta": Decimal("100"),
                "ok": self.cumplimiento_informacion_ambiental >= 100,
            },
            {
                "key": "disponibilidad",
                "nombre": "Disponibilidad circuitos",
                "valor": self.cumplimiento_disponibilidad_circuitos,
                "peso": PESO_DISPONIBILIDAD * 100,
                "meta": Decimal("98"),
                "ok": self.cumplimiento_disponibilidad_circuitos >= 98,
            },
        ]

    def save(self, *args, **kwargs):
        self.puntaje_total_ans = self.calcular_puntaje_ponderado()
        self.estado_ans = self.clasificar_estado(self.puntaje_total_ans)
        super().save(*args, **kwargs)
