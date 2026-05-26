"""
Models for KPIs and SLA tracking.
"""
from django.db import models
from apps.core.models import BaseModel
from apps.core.validators import resumen_indicadores_validator


class Indicador(BaseModel):
    """
    KPI/SLA indicator configuration.
    """

    class Categoria(models.TextChoices):
        GESTION = 'GESTION', 'Gestión de Mantenimiento'
        EJECUCION = 'EJECUCION', 'Ejecución de Mantenimiento'
        AMBIENTAL = 'AMBIENTAL', 'Gestión Ambiental'
        SEGURIDAD = 'SEGURIDAD', 'Seguridad Industrial'
        CALIDAD = 'CALIDAD', 'Calidad de Información'

    codigo = models.CharField('Código', max_length=20, unique=True)
    nombre = models.CharField('Nombre', max_length=100)
    descripcion = models.TextField('Descripción', blank=True)
    categoria = models.CharField(
        'Categoría',
        max_length=20,
        choices=Categoria.choices
    )
    formula = models.TextField(
        'Fórmula',
        help_text='Descripción de cómo se calcula el indicador'
    )
    unidad = models.CharField(
        'Unidad',
        max_length=20,
        default='%'
    )
    meta = models.DecimalField(
        'Meta',
        max_digits=6,
        decimal_places=2,
        help_text='Valor objetivo del indicador'
    )
    umbral_alerta = models.DecimalField(
        'Umbral de alerta',
        max_digits=6,
        decimal_places=2,
        help_text='Valor por debajo del cual se genera alerta'
    )
    peso_ponderacion = models.DecimalField(
        'Peso ponderación',
        max_digits=4,
        decimal_places=2,
        default=1.0,
        help_text='Peso para cálculo de indicador global'
    )
    activo = models.BooleanField('Activo', default=True)

    class Meta:
        db_table = 'indicadores'
        verbose_name = 'Indicador'
        verbose_name_plural = 'Indicadores'
        ordering = ['categoria', 'codigo']

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"


class MedicionIndicador(BaseModel):
    """
    Monthly indicator measurement.
    """

    indicador = models.ForeignKey(
        Indicador,
        on_delete=models.CASCADE,
        related_name='mediciones',
        verbose_name='Indicador'
    )
    linea = models.ForeignKey(
        'lineas.Linea',
        on_delete=models.CASCADE,
        related_name='mediciones_indicador',
        verbose_name='Línea',
        null=True,
        blank=True
    )
    anio = models.PositiveIntegerField('Año')
    mes = models.PositiveIntegerField('Mes')

    # Measurement values
    valor_numerador = models.DecimalField(
        'Numerador',
        max_digits=10,
        decimal_places=2,
        default=0
    )
    valor_denominador = models.DecimalField(
        'Denominador',
        max_digits=10,
        decimal_places=2,
        default=0
    )
    valor_calculado = models.DecimalField(
        'Valor calculado',
        max_digits=10,
        decimal_places=2,
        default=0
    )

    # Status
    cumple_meta = models.BooleanField('Cumple meta', default=False)
    en_alerta = models.BooleanField('En alerta', default=False)

    observaciones = models.TextField('Observaciones', blank=True)

    class Meta:
        db_table = 'mediciones_indicador'
        verbose_name = 'Medición de Indicador'
        verbose_name_plural = 'Mediciones de Indicador'
        unique_together = ['indicador', 'linea', 'anio', 'mes']
        ordering = ['-anio', '-mes', 'indicador']

    def __str__(self):
        return f"{self.indicador.codigo} - {self.mes}/{self.anio}: {self.valor_calculado}"

    def calcular(self):
        """Calculate indicator value and status."""
        if self.valor_denominador > 0:
            self.valor_calculado = (self.valor_numerador / self.valor_denominador) * 100

        self.cumple_meta = self.valor_calculado >= self.indicador.meta
        self.en_alerta = self.valor_calculado < self.indicador.umbral_alerta
        self.save()


class ActaSeguimiento(BaseModel):
    """
    Monthly follow-up meeting minutes.
    """

    class Estado(models.TextChoices):
        BORRADOR = 'BORRADOR', 'Borrador'
        PENDIENTE_FIRMA = 'PENDIENTE_FIRMA', 'Pendiente Firma'
        FIRMADA = 'FIRMADA', 'Firmada'

    linea = models.ForeignKey(
        'lineas.Linea',
        on_delete=models.CASCADE,
        related_name='actas_seguimiento',
        verbose_name='Línea'
    )
    anio = models.PositiveIntegerField('Año')
    mes = models.PositiveIntegerField('Mes')
    fecha_reunion = models.DateField('Fecha de reunión')

    estado = models.CharField(
        'Estado',
        max_length=20,
        choices=Estado.choices,
        default=Estado.BORRADOR
    )

    # Attendees
    asistentes_instelec = models.TextField(
        'Asistentes Instelec',
        blank=True
    )
    asistentes_cliente = models.TextField(
        'Asistentes Cliente',
        blank=True
    )

    # Content
    resumen_indicadores = models.JSONField(
        'Resumen de indicadores',
        default=dict,
        blank=True,
        validators=[resumen_indicadores_validator]
    )
    compromisos = models.TextField('Compromisos', blank=True)
    observaciones = models.TextField('Observaciones', blank=True)

    # Signatures
    url_acta_firmada = models.URLField('URL acta firmada', blank=True)

    class Meta:
        db_table = 'actas_seguimiento'
        verbose_name = 'Acta de Seguimiento'
        verbose_name_plural = 'Actas de Seguimiento'
        unique_together = ['linea', 'anio', 'mes']
        ordering = ['-anio', '-mes']

    def __str__(self):
        return f"Acta {self.linea.codigo} - {self.mes}/{self.anio}"


# === /modulo indicadores_construccion_sub_run_a — split de archivo magnet ===
# F2 scaffolding agregó este import. Los modelos nuevos van en el archivo
# dedicado de B4, NO en este archivo.
from .models_b4_mantenimiento_detallado import *  # noqa: F401, F403
