"""
Models for contract management by business unit.
"""
from django.db import models

from apps.core.models import BaseModel


class Contrato(BaseModel):
    """
    Contract linked to a business unit (Mantenimiento or Construccion).
    """

    class UnidadNegocio(models.TextChoices):
        MANTENIMIENTO = 'MANTENIMIENTO', 'Mantenimiento de Líneas'
        CONSTRUCCION = 'CONSTRUCCION', 'Construcción de Líneas'

    class Estado(models.TextChoices):
        ACTIVO = 'ACTIVO', 'Activo'
        FINALIZADO = 'FINALIZADO', 'Finalizado'
        SUSPENDIDO = 'SUSPENDIDO', 'Suspendido'

    unidad_negocio = models.CharField(
        'Unidad de negocio',
        max_length=20,
        choices=UnidadNegocio.choices,
    )
    codigo = models.CharField(
        'Código',
        max_length=50,
        unique=True,
    )
    nombre = models.CharField(
        'Nombre del contrato',
        max_length=300,
    )
    cliente = models.CharField(
        'Cliente',
        max_length=200,
        blank=True,
    )
    objeto = models.TextField(
        'Objeto del contrato',
        blank=True,
    )
    valor = models.DecimalField(
        'Valor del contrato',
        max_digits=16,
        decimal_places=2,
        default=0,
    )
    fecha_inicio = models.DateField(
        'Fecha de inicio',
        null=True,
        blank=True,
    )
    fecha_fin = models.DateField(
        'Fecha de finalización',
        null=True,
        blank=True,
    )
    estado = models.CharField(
        'Estado',
        max_length=20,
        choices=Estado.choices,
        default=Estado.ACTIVO,
    )
    observaciones = models.TextField(
        'Observaciones',
        blank=True,
    )

    class Meta:
        db_table = 'contratos'
        verbose_name = 'Contrato'
        verbose_name_plural = 'Contratos'
        ordering = ['unidad_negocio', 'codigo']

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"
