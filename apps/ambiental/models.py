"""
Models for environmental management and reporting.
"""
from django.db import models
from apps.core.models import BaseModel


class InformeAmbiental(BaseModel):
    """
    Monthly environmental report.
    """

    class Estado(models.TextChoices):
        BORRADOR = 'BORRADOR', 'Borrador'
        EN_REVISION = 'EN_REVISION', 'En Revisión'
        APROBADO = 'APROBADO', 'Aprobado'
        ENVIADO = 'ENVIADO', 'Enviado al Cliente'
        RECHAZADO = 'RECHAZADO', 'Rechazado'

    periodo_mes = models.PositiveIntegerField('Mes')
    periodo_anio = models.PositiveIntegerField('Año')
    linea = models.ForeignKey(
        'lineas.Linea',
        on_delete=models.CASCADE,
        related_name='informes_ambientales',
        verbose_name='Línea'
    )

    estado = models.CharField(
        'Estado',
        max_length=20,
        choices=Estado.choices,
        default=Estado.BORRADOR
    )

    # Report content summary
    total_actividades = models.PositiveIntegerField(
        'Total actividades',
        default=0
    )
    total_podas = models.PositiveIntegerField(
        'Total podas',
        default=0
    )
    hectareas_intervenidas = models.DecimalField(
        'Hectáreas intervenidas',
        max_digits=10,
        decimal_places=2,
        default=0
    )
    m3_vegetacion = models.DecimalField(
        'M³ vegetación removida',
        max_digits=10,
        decimal_places=2,
        default=0
    )

    # Approval workflow
    elaborado_por = models.ForeignKey(
        'usuarios.Usuario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='informes_elaborados',
        verbose_name='Elaborado por'
    )
    revisado_por = models.ForeignKey(
        'usuarios.Usuario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='informes_revisados',
        verbose_name='Revisado por'
    )
    aprobado_por = models.ForeignKey(
        'usuarios.Usuario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='informes_ambientales_aprobados',
        verbose_name='Aprobado por'
    )

    fecha_elaboracion = models.DateTimeField(
        'Fecha elaboración',
        null=True,
        blank=True
    )
    fecha_revision = models.DateTimeField(
        'Fecha revisión',
        null=True,
        blank=True
    )
    fecha_aprobacion = models.DateTimeField(
        'Fecha aprobación',
        null=True,
        blank=True
    )
    fecha_envio = models.DateTimeField(
        'Fecha envío',
        null=True,
        blank=True
    )

    # Generated files
    url_pdf = models.URLField(
        'URL PDF',
        blank=True
    )
    url_excel = models.URLField(
        'URL Excel',
        blank=True
    )

    observaciones = models.TextField(
        'Observaciones',
        blank=True
    )

    class Meta:
        db_table = 'informes_ambientales'
        verbose_name = 'Informe Ambiental'
        verbose_name_plural = 'Informes Ambientales'
        unique_together = ['periodo_mes', 'periodo_anio', 'linea']
        ordering = ['-periodo_anio', '-periodo_mes', 'linea']

    def __str__(self):
        return f"Informe Ambiental {self.linea.codigo} - {self.periodo_mes}/{self.periodo_anio}"


class PermisoServidumbre(BaseModel):
    """
    Easement permission from landowners.
    """

    torre = models.ForeignKey(
        'lineas.Torre',
        on_delete=models.CASCADE,
        related_name='permisos_servidumbre',
        verbose_name='Torre'
    )

    # Landowner info
    propietario_nombre = models.CharField(
        'Nombre del propietario',
        max_length=200
    )
    propietario_documento = models.CharField(
        'Documento de identidad',
        max_length=20,
        blank=True
    )
    propietario_telefono = models.CharField(
        'Teléfono',
        max_length=20,
        blank=True
    )

    # Property info
    predio_nombre = models.CharField(
        'Nombre del predio',
        max_length=200,
        blank=True
    )
    predio_matricula = models.CharField(
        'Matrícula inmobiliaria',
        max_length=50,
        blank=True
    )

    # Authorization
    fecha_autorizacion = models.DateField('Fecha de autorización')
    fecha_vencimiento = models.DateField(
        'Fecha de vencimiento',
        null=True,
        blank=True
    )
    actividades_autorizadas = models.TextField(
        'Actividades autorizadas',
        blank=True
    )

    # Signed document
    url_documento_firmado = models.URLField(
        'URL documento firmado',
        blank=True
    )
    url_firma_digital = models.URLField(
        'URL firma digital',
        blank=True
    )

    observaciones = models.TextField(
        'Observaciones',
        blank=True
    )

    class Meta:
        db_table = 'permisos_servidumbre'
        verbose_name = 'Permiso de Servidumbre'
        verbose_name_plural = 'Permisos de Servidumbre'
        ordering = ['-fecha_autorizacion']

    def __str__(self):
        return f"Permiso {self.propietario_nombre} - Torre {self.torre.numero_display}"

    @property
    def vigente(self):
        """Check if permission is still valid."""
        from django.utils import timezone
        if not self.fecha_vencimiento:
            return True
        return self.fecha_vencimiento >= timezone.now().date()
