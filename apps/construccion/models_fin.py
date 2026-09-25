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

from django.conf import settings
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


# ===========================================================================
# 5. HISTORIAL DE CARGAS DE PRESUPUESTO (Instelec#267 Fase 1.3, A3)
# ===========================================================================
_MESES_ES_HISTORIAL_CARGA = {
    1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril', 5: 'Mayo', 6: 'Junio',
    7: 'Julio', 8: 'Agosto', 9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre',
    12: 'Diciembre',
}


class HistorialCargaPresupuestoConstruccion(BaseModel):
    """Auditoría de CADA POST de carga de presupuesto (éxito o error).

    El issue #267 (Fase 1.3, "Historial de Cargas") pide mostrar la última
    carga con Fecha/Usuario/Filas/Valor total/Estado/Período; este modelo la
    persiste para poder listar un historial (no solo la última) y sobrevivir
    al POST siguiente. Espejo del patrón auditable ``CargaFinanciera`` de
    ``apps.financiero.models_finv2_carga`` (mismo issue #267, dependencia
    confirmada #261 — ver ``scope_override_hitl`` de F2), adaptado a
    construcción: acá NO se persiste línea por línea (eso vive en
    ``PresupuestoDetalladoConstruccion.datos['finv2_bd']['filas_detalle']``,
    A2) — este modelo audita únicamente el EVENTO de carga.

    ``anio``/``mes`` son nullable a propósito: los formatos legacy
    ('contable', 'presupuesto' de columnas por mes) cubren el año completo,
    no un mes puntual — solo el formato plano (A2) trae mes por fila y
    permite resolver un período único cuando el archivo es de un solo mes
    (``PresupuestoPlaneadoConstruccionView.post`` calcula ``mes`` con
    ``_mes_unico_desde_datos``; ``anio`` es siempre el del formulario).
    """

    class Estado(models.TextChoices):
        PROCESADA = 'PROCESADA', 'Procesada'
        ERROR = 'ERROR', 'Error'

    proyecto = models.ForeignKey(
        'construccion.ProyectoConstruccion',
        on_delete=models.CASCADE,
        related_name='historial_cargas_presupuesto',
        verbose_name='Proyecto',
    )
    anio = models.PositiveIntegerField('Año', null=True, blank=True)
    mes = models.PositiveSmallIntegerField('Mes', null=True, blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='historial_cargas_presupuesto_construccion',
        verbose_name='Usuario',
    )
    fecha = models.DateTimeField('Fecha', default=timezone.now)
    filas_procesadas = models.PositiveIntegerField('Filas procesadas', default=0)
    valor_total = models.DecimalField(
        'Valor total', max_digits=18, decimal_places=2, default=Decimal('0'),
    )
    estado = models.CharField(
        'Estado', max_length=10, choices=Estado.choices, default=Estado.ERROR,
    )
    archivo_nombre = models.CharField('Archivo de origen', max_length=255, blank=True)
    detalle_errores = models.JSONField('Detalle de errores', default=dict, blank=True)
    # Instelec#268 — el mismo historial audita las cargas de gastos REALES.
    # Default PLANEADO: todas las filas previas a #268 son del planeado.
    tipo = models.CharField(
        'Tipo', max_length=10, choices=PresupuestoDetalladoConstruccion.Tipo.choices,
        default=PresupuestoDetalladoConstruccion.Tipo.PLANEADO,
    )

    class Meta:
        db_table = 'construccion_historial_carga_presupuesto'
        verbose_name = 'Historial de Carga de Presupuesto'
        verbose_name_plural = 'Historial de Cargas de Presupuesto'
        ordering = ['-fecha', '-created_at']
        indexes = [
            models.Index(fields=['proyecto', '-fecha'], name='idx_hist_carga_ppto_proyecto'),
        ]

    def __str__(self):
        periodo = f'{self.mes:02d}/{self.anio}' if self.mes and self.anio else str(self.anio or 's/año')
        return f'Carga {periodo} — {self.get_estado_display()} ({self.filas_procesadas} filas)'

    @property
    def periodo_display(self):
        """Texto legible del período — formato del ejemplo del issue (#267
        Fase 1.3): ``'Septiembre 2026 (09/2026)'``. Sin mes puntual (formatos
        legacy que cubren el año completo) muestra solo el año."""
        if self.mes and self.anio:
            nombre_mes = _MESES_ES_HISTORIAL_CARGA.get(self.mes, self.mes)
            return f'{nombre_mes} {self.anio} ({self.mes:02d}/{self.anio})'
        if self.anio:
            return str(self.anio)
        return '—'


# ===========================================================================
# Gastos reales (Instelec#268) — una fila por línea del Excel de 18 columnas
# ===========================================================================
class GastoRealConstruccion(BaseModel):
    """Línea de gasto real (ejecutado) del proyecto, cargada desde el Excel de
    18 columnas del cliente (Auxiliar … Fijo).

    Se persiste línea por línea (no JSON) porque #268 filtra por proveedor,
    centro de costo, clasificación y período, y liga cada gasto al maestro de
    proveedores (#262). Una carga reemplaza TODAS las líneas del proyecto en
    los períodos que trae el archivo (UPSERT por período).
    """

    proyecto = models.ForeignKey(
        'construccion.ProyectoConstruccion',
        on_delete=models.CASCADE,
        related_name='gastos_reales',
        verbose_name='Proyecto',
    )
    carga = models.ForeignKey(
        HistorialCargaPresupuestoConstruccion,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='gastos_reales',
        verbose_name='Carga',
    )
    proveedor = models.ForeignKey(
        'financiero.Proveedor',
        on_delete=models.PROTECT, null=True, blank=True,
        related_name='gastos_reales_construccion',
        verbose_name='Proveedor (#262)',
    )
    periodo = models.CharField('Periodo (AAAAMM)', max_length=6)
    anio = models.PositiveIntegerField('Año')
    mes = models.PositiveSmallIntegerField('Mes')

    auxiliar = models.CharField('Auxiliar', max_length=50, blank=True)
    desc_auxiliar = models.CharField('Desc. auxiliar', max_length=255, blank=True)
    neto = models.DecimalField('Neto', max_digits=18, decimal_places=2)
    fecha = models.DateField('Fecha', null=True, blank=True)
    docto = models.CharField('Docto.', max_length=60, blank=True)
    tercero_nit = models.CharField('Tercero movto (NIT)', max_length=30, blank=True)
    tercero_razon_social = models.CharField('Razón social tercero', max_length=255, blank=True)
    desc_co_movto = models.CharField('Desc. C.O. movto', max_length=255, blank=True)
    usuario_creacion = models.CharField('Usuario creación', max_length=150, blank=True)
    co_movto = models.CharField('C.O. movto', max_length=30, blank=True)
    notas = models.TextField('Notas', blank=True)
    centro_costo = models.CharField('C.Costo', max_length=50, blank=True)
    desc_centro_costo = models.CharField('Desc. C.Costo', max_length=255, blank=True)
    cuenta_equiv = models.CharField('Cuenta Equiv', max_length=150, blank=True)
    cdec_equiv = models.CharField('CdeC equiv', max_length=150, blank=True)
    cargo = models.CharField('Cargo', max_length=150, blank=True)
    fijo = models.CharField('Fijo', max_length=30, blank=True)

    # Derivados en la carga: rubro presupuestal (MapeoCtaRubro, el mismo del
    # planeado) y clasificación Fijo/Variable (columna "Fijo").
    rubro = models.CharField('Rubro', max_length=150, blank=True)
    clasificacion = models.CharField('Clasificación', max_length=10, blank=True)

    class Meta:
        db_table = 'construccion_gasto_real'
        verbose_name = 'Gasto real de construcción'
        verbose_name_plural = 'Gastos reales de construcción'
        ordering = ['periodo', 'cuenta_equiv', 'fecha']
        indexes = [
            models.Index(fields=['proyecto', 'periodo'], name='idx_gasto_real_proy_periodo'),
            models.Index(fields=['proyecto', 'proveedor'], name='idx_gasto_real_proy_prov'),
        ]

    def __str__(self):
        return f'{self.periodo} {self.cuenta_equiv} {self.neto}'
