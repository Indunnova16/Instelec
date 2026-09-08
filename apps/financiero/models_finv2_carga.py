"""Persistencia compartida para la carga financiera y su homologación."""
from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class HomologacionProjectsContable(BaseModel):
    """Equivalencia editable entre un concepto de Projects y Contabilidad."""

    tipo = models.CharField('Tipo', max_length=50)
    grupo = models.CharField('Grupo', max_length=255, blank=True)
    concepto = models.CharField('Concepto', max_length=255)
    rubro = models.CharField('Rubro', max_length=255, blank=True)
    codigo_contable = models.CharField('Código contable', max_length=50)
    centro_costo = models.CharField('Centro de costo', max_length=100, blank=True)
    activo = models.BooleanField('Activo', default=True)

    class Meta:
        db_table = 'financiero_homologacion_projects_contable'
        verbose_name = 'Homologación Projects → Contabilidad'
        verbose_name_plural = 'Homologaciones Projects → Contabilidad'
        ordering = ['tipo', 'grupo', 'concepto', 'rubro']
        constraints = [
            models.UniqueConstraint(
                fields=['tipo', 'grupo', 'concepto', 'rubro'],
                name='uq_finv2_homologacion_origen',
            ),
        ]

    def __str__(self):
        return f'{self.concepto} → {self.codigo_contable}'


class CargaFinanciera(BaseModel):
    """Cabecera auditable de un archivo procesado para un período financiero."""

    class Estado(models.TextChoices):
        VALIDADA = 'VALIDADA', 'Validada'
        PROCESADA = 'PROCESADA', 'Procesada'
        ERROR = 'ERROR', 'Error'

    proyecto = models.ForeignKey(
        'contratos.Contrato',
        on_delete=models.PROTECT,
        related_name='cargas_financieras',
        verbose_name='Proyecto',
    )
    anio = models.PositiveIntegerField('Año')
    mes = models.PositiveSmallIntegerField('Mes')
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cargas_financieras',
        verbose_name='Usuario',
    )
    estado = models.CharField(
        'Estado', max_length=15, choices=Estado.choices, default=Estado.VALIDADA,
    )
    nombre_archivo = models.CharField('Archivo de origen', max_length=255, blank=True)
    resumen = models.JSONField('Resumen de carga', default=dict, blank=True)

    class Meta:
        db_table = 'financiero_carga_financiera'
        verbose_name = 'Carga financiera'
        verbose_name_plural = 'Cargas financieras'
        ordering = ['-anio', '-mes', '-created_at']
        indexes = [
            models.Index(fields=['proyecto', 'anio', 'mes'], name='idx_finv2_carga_periodo'),
        ]

    def __str__(self):
        return f'{self.proyecto} — {self.mes:02d}/{self.anio}'


class LineaCargaFinanciera(BaseModel):
    """Fila inmutable de origen y su homologación para trazabilidad del plano."""

    class Tipo(models.TextChoices):
        REAL = 'REAL', 'Real'
        PRESUPUESTO = 'PRESUPUESTO', 'Presupuesto'

    carga = models.ForeignKey(
        CargaFinanciera,
        on_delete=models.CASCADE,
        related_name='lineas',
        verbose_name='Carga financiera',
    )
    homologacion = models.ForeignKey(
        HomologacionProjectsContable,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='lineas_cargadas',
        verbose_name='Homologación contable',
    )
    tipo = models.CharField('Tipo', max_length=15, choices=Tipo.choices)
    grupo = models.CharField('Grupo', max_length=255, blank=True)
    concepto = models.CharField('Concepto', max_length=255)
    rubro = models.CharField('Rubro', max_length=255, blank=True)
    valor = models.DecimalField('Valor', max_digits=18, decimal_places=2)
    referencia = models.CharField('Referencia', max_length=255, blank=True)
    fila_origen = models.PositiveIntegerField('Fila de origen', null=True, blank=True)
    datos_origen = models.JSONField('Datos de origen', default=dict, blank=True)

    class Meta:
        db_table = 'financiero_linea_carga_financiera'
        verbose_name = 'Línea de carga financiera'
        verbose_name_plural = 'Líneas de carga financiera'
        ordering = ['carga', 'tipo', 'fila_origen', 'created_at']
        indexes = [
            models.Index(fields=['carga', 'tipo'], name='idx_finv2_linea_carga_tipo'),
            models.Index(fields=['homologacion'], name='idx_finv2_linea_homolog'),
        ]

    def __str__(self):
        return f'{self.concepto}: {self.valor}'
