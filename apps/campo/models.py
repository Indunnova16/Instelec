"""
Models for field data capture.
"""
from django.db import models
from apps.core.models import BaseModel
from apps.core.validators import (
    datos_formulario_validator,
    metadata_exif_validator,
    validacion_ia_validator,
)


class RegistroCampo(BaseModel):
    """
    Field record for activity execution.
    Captures all data from mobile app.
    """

    class TipoPendiente(models.TextChoices):
        ACCESO = 'ACCESO', 'Problema de acceso'
        PERMISOS = 'PERMISOS', 'Falta de permisos'
        CLIMA = 'CLIMA', 'Condiciones climáticas'
        MATERIAL = 'MATERIAL', 'Falta de material'
        EQUIPO = 'EQUIPO', 'Falta de equipo'
        SEGURIDAD = 'SEGURIDAD', 'Condición de seguridad'
        PROPIETARIO = 'PROPIETARIO', 'Problema con propietario'
        OTRO = 'OTRO', 'Otro'

    actividad = models.ForeignKey(
        'actividades.Actividad',
        on_delete=models.CASCADE,
        related_name='registros_campo',
        verbose_name='Actividad'
    )
    usuario = models.ForeignKey(
        'usuarios.Usuario',
        on_delete=models.PROTECT,
        related_name='registros_campo',
        verbose_name='Registrado por'
    )

    # Timestamps
    fecha_inicio = models.DateTimeField('Fecha/hora inicio')
    fecha_fin = models.DateTimeField(
        'Fecha/hora fin',
        null=True,
        blank=True
    )

    # Location at start
    latitud_inicio = models.DecimalField(
        'Latitud inicio',
        max_digits=10,
        decimal_places=8,
        null=True,
        blank=True
    )
    longitud_inicio = models.DecimalField(
        'Longitud inicio',
        max_digits=11,
        decimal_places=8,
        null=True,
        blank=True
    )

    # Location at end
    latitud_fin = models.DecimalField(
        'Latitud fin',
        max_digits=10,
        decimal_places=8,
        null=True,
        blank=True
    )
    longitud_fin = models.DecimalField(
        'Longitud fin',
        max_digits=11,
        decimal_places=8,
        null=True,
        blank=True
    )

    # Validation
    dentro_poligono = models.BooleanField(
        'Dentro del polígono',
        null=True,
        blank=True,
        help_text='Indica si el registro se hizo dentro del área de servidumbre'
    )

    # Dynamic form data
    datos_formulario = models.JSONField(
        'Datos del formulario',
        default=dict,
        blank=True,
        validators=[datos_formulario_validator],
        help_text='Datos capturados según el tipo de actividad'
    )

    # Progress tracking
    porcentaje_avance_reportado = models.DecimalField(
        'Porcentaje de avance reportado',
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text='Porcentaje de avance reportado en este registro (0-100)'
    )

    # Pendientes/condiciones especiales
    tiene_pendiente = models.BooleanField(
        'Tiene pendiente',
        default=False,
        help_text='Indica si hay algún pendiente o condición especial'
    )
    tipo_pendiente = models.CharField(
        'Tipo de pendiente',
        max_length=20,
        choices=TipoPendiente.choices,
        blank=True,
        help_text='Clasificación del tipo de pendiente'
    )
    descripcion_pendiente = models.TextField(
        'Descripción del pendiente',
        blank=True,
        help_text='Descripción detallada del pendiente o condición especial'
    )

    # Observations
    observaciones = models.TextField(
        'Observaciones',
        blank=True
    )
    observaciones_audio_url = models.URLField(
        'URL audio observaciones',
        blank=True,
        help_text='Grabación de voz transcrita'
    )

    # Signature
    firma_responsable_url = models.URLField(
        'URL firma responsable',
        blank=True
    )

    # Sync status
    sincronizado = models.BooleanField(
        'Sincronizado',
        default=False,
        help_text='Indica si los datos fueron sincronizados desde el móvil'
    )
    fecha_sincronizacion = models.DateTimeField(
        'Fecha sincronización',
        null=True,
        blank=True
    )

    class Meta:
        db_table = 'registros_campo'
        verbose_name = 'Registro de Campo'
        verbose_name_plural = 'Registros de Campo'
        ordering = ['-fecha_inicio']
        indexes = [
            models.Index(fields=['actividad'], name='idx_registro_actividad'),
            models.Index(fields=['usuario'], name='idx_registro_usuario'),
            models.Index(fields=['fecha_inicio'], name='idx_registro_fecha'),
            models.Index(fields=['sincronizado'], name='idx_registro_sincronizado'),
            models.Index(fields=['tiene_pendiente'], name='idx_registro_pendiente'),
        ]

    def __str__(self):
        return f"Registro {self.actividad} - {self.fecha_inicio.date()}"

    def save(self, *args, **kwargs):
        """Override save to update parent Actividad's porcentaje_avance."""
        super().save(*args, **kwargs)
        # Actualizar porcentaje_avance de la Actividad padre
        if self.porcentaje_avance_reportado > 0:
            self._actualizar_avance_actividad()

    def _actualizar_avance_actividad(self):
        """Actualiza el porcentaje de avance de la actividad padre."""
        # El avance reportado en el registro reemplaza el avance de la actividad
        # si es mayor al actual
        if self.porcentaje_avance_reportado > self.actividad.porcentaje_avance:
            self.actividad.actualizar_avance(self.porcentaje_avance_reportado)

    @property
    def duracion_minutos(self):
        """Calculate duration in minutes."""
        if self.fecha_fin and self.fecha_inicio:
            delta = self.fecha_fin - self.fecha_inicio
            return int(delta.total_seconds() / 60)
        return None

    @property
    def total_evidencias(self):
        return self.evidencias.count()

    @property
    def evidencias_completas(self):
        """Check if all required photos are captured."""
        tipo = self.actividad.tipo_actividad
        tiene_antes = not tipo.requiere_fotos_antes or self.evidencias.filter(tipo='ANTES').exists()
        tiene_durante = not tipo.requiere_fotos_durante or self.evidencias.filter(tipo='DURANTE').exists()
        tiene_despues = not tipo.requiere_fotos_despues or self.evidencias.filter(tipo='DESPUES').exists()
        return tiene_antes and tiene_durante and tiene_despues


class Evidencia(BaseModel):
    """
    Photographic evidence for field records.
    """

    class TipoEvidencia(models.TextChoices):
        ANTES = 'ANTES', 'Antes'
        DURANTE = 'DURANTE', 'Durante'
        DESPUES = 'DESPUES', 'Después'

    registro_campo = models.ForeignKey(
        RegistroCampo,
        on_delete=models.CASCADE,
        related_name='evidencias',
        verbose_name='Registro de campo'
    )
    tipo = models.CharField(
        'Tipo',
        max_length=10,
        choices=TipoEvidencia.choices
    )

    # File URLs
    url_original = models.URLField(
        'URL imagen original'
    )
    url_thumbnail = models.URLField(
        'URL thumbnail',
        blank=True
    )
    url_estampada = models.URLField(
        'URL imagen estampada',
        blank=True,
        help_text='Imagen con fecha, hora y coordenadas estampadas'
    )

    # Location
    latitud = models.DecimalField(
        'Latitud',
        max_digits=10,
        decimal_places=8,
        null=True,
        blank=True
    )
    longitud = models.DecimalField(
        'Longitud',
        max_digits=11,
        decimal_places=8,
        null=True,
        blank=True
    )

    # Capture info
    fecha_captura = models.DateTimeField('Fecha de captura')

    # AI Validation results
    validacion_ia = models.JSONField(
        'Validación IA',
        default=dict,
        blank=True,
        validators=[validacion_ia_validator],
        help_text='Resultado de validación: nitidez, iluminación, válida'
    )

    # EXIF metadata
    metadata_exif = models.JSONField(
        'Metadata EXIF',
        default=dict,
        blank=True,
        validators=[metadata_exif_validator]
    )

    # Description
    descripcion = models.CharField(
        'Descripción',
        max_length=200,
        blank=True
    )

    class Meta:
        db_table = 'evidencias'
        verbose_name = 'Evidencia'
        verbose_name_plural = 'Evidencias'
        ordering = ['tipo', 'fecha_captura']
        indexes = [
            models.Index(fields=['registro_campo'], name='idx_evidencia_registro'),
            models.Index(fields=['tipo'], name='idx_evidencia_tipo'),
            models.Index(fields=['fecha_captura'], name='idx_evidencia_fecha'),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.registro_campo.actividad.torre.numero}"

    @property
    def es_valida(self):
        """Check if photo passed AI validation."""
        return self.validacion_ia.get('valida', True)

    @property
    def puntaje_nitidez(self):
        return self.validacion_ia.get('nitidez', 1.0)

    @property
    def puntaje_iluminacion(self):
        return self.validacion_ia.get('iluminacion', 1.0)


class ReporteDano(BaseModel):
    """
    Damage report with geolocation.
    Allows field workers to report damages found on site.
    """

    usuario = models.ForeignKey(
        'usuarios.Usuario',
        on_delete=models.PROTECT,
        related_name='reportes_dano',
        verbose_name='Reportado por'
    )
    descripcion = models.TextField(
        'Descripción del daño',
        help_text='Descripción detallada del daño encontrado'
    )
    latitud = models.DecimalField(
        'Latitud',
        max_digits=10,
        decimal_places=8,
        null=True,
        blank=True
    )
    longitud = models.DecimalField(
        'Longitud',
        max_digits=11,
        decimal_places=8,
        null=True,
        blank=True
    )

    class Meta:
        db_table = 'reportes_dano'
        verbose_name = 'Reporte de Daño'
        verbose_name_plural = 'Reportes de Daño'
        ordering = ['-created_at']

    def __str__(self):
        return f"Daño reportado por {self.usuario.get_full_name()} - {self.created_at.strftime('%d/%m/%Y %H:%M')}"
