"""
Models for activity scheduling and management.
"""
from django.db import models
from apps.core.models import BaseModel
from apps.core.validators import (
    campos_formulario_validator,
    datos_importados_validator,
)


class TipoActividad(BaseModel):
    """
    Activity type configuration with dynamic form fields.
    """

    class Categoria(models.TextChoices):
        # Categorías existentes
        PODA = 'PODA', 'Poda de Vegetación'
        HERRAJES = 'HERRAJES', 'Cambio de Herrajes'
        AISLADORES = 'AISLADORES', 'Cambio de Aisladores'
        INSPECCION = 'INSPECCION', 'Inspección General'
        LIMPIEZA = 'LIMPIEZA', 'Limpieza'
        SEÑALIZACION = 'SEÑALIZACION', 'Señalización'
        MEDICION = 'MEDICION', 'Medición'
        # Categorías Transelca
        LAVADO = 'LAVADO', 'Lavado Tradicional'
        SERVIDUMBRE = 'SERVIDUMBRE', 'Servidumbre'
        PERMISO = 'PERMISO', 'Gestionar Permiso'
        CORREDOR = 'CORREDOR', 'Corredor Eléctrico'
        INSPECCION_PED = 'INSPECCION_PED', 'Inspección Pedestre'
        TERMOGRAFIA = 'TERMOGRAFIA', 'Termografía'
        DESCARGAS = 'DESCARGAS', 'Descargas Parciales'
        ELECTROMEC = 'ELECTROMEC', 'Mtto Electromecánico'
        MEDICION_PT = 'MEDICION_PT', 'Medida Puesta Tierra'
        OTRO = 'OTRO', 'Otro'

    codigo = models.CharField(
        'Código',
        max_length=20,
        unique=True
    )
    nombre = models.CharField(
        'Nombre',
        max_length=100
    )
    categoria = models.CharField(
        'Categoría',
        max_length=20,
        choices=Categoria.choices
    )
    descripcion = models.TextField(
        'Descripción',
        blank=True
    )
    requiere_fotos_antes = models.BooleanField(
        'Requiere fotos ANTES',
        default=True
    )
    requiere_fotos_durante = models.BooleanField(
        'Requiere fotos DURANTE',
        default=True
    )
    requiere_fotos_despues = models.BooleanField(
        'Requiere fotos DESPUÉS',
        default=True
    )
    min_fotos = models.PositiveIntegerField(
        'Mínimo de fotos',
        default=3
    )
    campos_formulario = models.JSONField(
        'Campos del formulario',
        default=dict,
        blank=True,
        validators=[campos_formulario_validator],
        help_text='Configuración de campos dinámicos en formato JSON'
    )
    tiempo_estimado_horas = models.DecimalField(
        'Tiempo estimado (horas)',
        max_digits=4,
        decimal_places=2,
        default=2
    )
    rendimiento_estandar_vanos = models.PositiveIntegerField(
        'Vanos por día esperados',
        default=3,
        help_text='Rendimiento estándar en vanos por día para este tipo de actividad'
    )
    activo = models.BooleanField(
        'Activo',
        default=True
    )

    class Meta:
        db_table = 'tipos_actividad'
        verbose_name = 'Tipo de Actividad'
        verbose_name_plural = 'Tipos de Actividad'
        ordering = ['categoria', 'nombre']

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"


class ProgramacionMensual(BaseModel):
    """
    Monthly programming imported from client's Excel.
    """

    anio = models.PositiveIntegerField('Año')
    mes = models.PositiveIntegerField('Mes')
    linea = models.ForeignKey(
        'lineas.Linea',
        on_delete=models.CASCADE,
        related_name='programaciones',
        verbose_name='Línea'
    )
    archivo_origen = models.FileField(
        'Archivo Excel origen',
        upload_to='programacion/excel/',
        blank=True,
        null=True
    )
    datos_importados = models.JSONField(
        'Datos importados',
        default=dict,
        blank=True,
        validators=[datos_importados_validator]
    )
    total_actividades = models.PositiveIntegerField(
        'Total actividades',
        default=0
    )
    aprobado = models.BooleanField(
        'Aprobado',
        default=False
    )
    aprobado_por = models.ForeignKey(
        'usuarios.Usuario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='programaciones_aprobadas',
        verbose_name='Aprobado por'
    )
    fecha_aprobacion = models.DateTimeField(
        'Fecha de aprobación',
        null=True,
        blank=True
    )

    class Meta:
        db_table = 'programacion_mensual'
        verbose_name = 'Programación Mensual'
        verbose_name_plural = 'Programaciones Mensuales'
        unique_together = ['anio', 'mes', 'linea']
        ordering = ['-anio', '-mes', 'linea']

    def __str__(self):
        return f"Programación {self.linea.codigo} - {self.mes}/{self.anio}"


class Actividad(BaseModel):
    """
    Scheduled maintenance activity.
    """

    class Estado(models.TextChoices):
        PENDIENTE = 'PENDIENTE', 'Pendiente'
        PROGRAMADA = 'PROGRAMADA', 'Programada'
        EN_CURSO = 'EN_CURSO', 'En Curso'
        COMPLETADA = 'COMPLETADA', 'Completada'
        CANCELADA = 'CANCELADA', 'Cancelada'
        REPROGRAMADA = 'REPROGRAMADA', 'Reprogramada'

    class Prioridad(models.TextChoices):
        BAJA = 'BAJA', 'Baja'
        NORMAL = 'NORMAL', 'Normal'
        ALTA = 'ALTA', 'Alta'
        URGENTE = 'URGENTE', 'Urgente'

    # Relationships
    linea = models.ForeignKey(
        'lineas.Linea',
        on_delete=models.CASCADE,
        related_name='actividades',
        verbose_name='Línea'
    )
    torre = models.ForeignKey(
        'lineas.Torre',
        on_delete=models.CASCADE,
        related_name='actividades',
        verbose_name='Torre'
    )
    tipo_actividad = models.ForeignKey(
        TipoActividad,
        on_delete=models.PROTECT,
        related_name='actividades',
        verbose_name='Tipo de actividad'
    )
    cuadrilla = models.ForeignKey(
        'cuadrillas.Cuadrilla',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='actividades',
        verbose_name='Cuadrilla asignada'
    )
    programacion = models.ForeignKey(
        ProgramacionMensual,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='actividades',
        verbose_name='Programación mensual'
    )
    tramo = models.ForeignKey(
        'lineas.Tramo',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='actividades',
        verbose_name='Tramo'
    )

    # SAP Integration
    aviso_sap = models.CharField(
        'Número Aviso SAP',
        max_length=20,
        blank=True,
        help_text='Número de aviso en el sistema SAP de Transelca'
    )
    orden_sap = models.CharField(
        'Número Orden SAP',
        max_length=20,
        blank=True,
        help_text='Número de orden de trabajo en SAP'
    )
    pt_sap = models.CharField(
        'Puesto Trabajo SAP',
        max_length=20,
        blank=True,
        help_text='Código del puesto de trabajo SAP'
    )
    requiere_consignacion = models.BooleanField(
        'Requiere consignación',
        default=False,
        help_text='Indica si la actividad requiere consignación del circuito'
    )
    numero_consignacion = models.CharField(
        'Número de consignación',
        max_length=30,
        blank=True,
        help_text='Número de consignación asignado por el operador'
    )

    # Progress and billing
    porcentaje_avance = models.DecimalField(
        'Porcentaje de avance',
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text='Porcentaje de avance de la actividad (0-100)'
    )
    valor_facturacion = models.DecimalField(
        'Valor facturación',
        max_digits=14,
        decimal_places=2,
        default=0,
        help_text='Valor total de facturación de la actividad'
    )

    # Scheduling
    fecha_programada = models.DateField('Fecha programada')
    fecha_reprogramada = models.DateField(
        'Fecha reprogramada',
        null=True,
        blank=True
    )
    hora_inicio_estimada = models.TimeField(
        'Hora inicio estimada',
        null=True,
        blank=True
    )

    # Status
    estado = models.CharField(
        'Estado',
        max_length=20,
        choices=Estado.choices,
        default=Estado.PENDIENTE
    )
    prioridad = models.CharField(
        'Prioridad',
        max_length=10,
        choices=Prioridad.choices,
        default=Prioridad.NORMAL
    )

    # Notes
    observaciones_programacion = models.TextField(
        'Observaciones de programación',
        blank=True
    )
    motivo_reprogramacion = models.TextField(
        'Motivo de reprogramación',
        blank=True
    )
    motivo_cancelacion = models.TextField(
        'Motivo de cancelación',
        blank=True
    )

    class Meta:
        db_table = 'actividades'
        verbose_name = 'Actividad'
        verbose_name_plural = 'Actividades'
        ordering = ['-fecha_programada', 'prioridad', 'linea', 'torre']
        indexes = [
            models.Index(fields=['fecha_programada', 'estado']),
            models.Index(fields=['cuadrilla', 'fecha_programada']),
            models.Index(fields=['linea', 'fecha_programada']),
            models.Index(fields=['aviso_sap']),
            models.Index(fields=['tramo']),
        ]

    def __str__(self):
        return f"{self.tipo_actividad.nombre} - Torre {self.torre.numero} ({self.fecha_programada})"

    @property
    def fecha_efectiva(self):
        """Returns the effective date (reprogrammed or original)."""
        return self.fecha_reprogramada or self.fecha_programada

    @property
    def esta_atrasada(self):
        """Check if activity is overdue."""
        from django.utils import timezone
        if self.estado in [self.Estado.COMPLETADA, self.Estado.CANCELADA]:
            return False
        return self.fecha_efectiva < timezone.now().date()

    @property
    def produccion_proporcional(self):
        """Calcula la producción proporcional al avance: porcentaje_avance × valor_facturacion."""
        return (self.porcentaje_avance / 100) * self.valor_facturacion

    @property
    def rendimiento_esperado_diario(self):
        """Retorna el rendimiento esperado en vanos por día según el tipo de actividad."""
        return self.tipo_actividad.rendimiento_estandar_vanos

    def actualizar_avance(self, nuevo_porcentaje):
        """Actualiza el porcentaje de avance de la actividad."""
        from decimal import Decimal
        self.porcentaje_avance = Decimal(str(nuevo_porcentaje))
        if self.porcentaje_avance >= 100:
            self.estado = self.Estado.COMPLETADA
        self.save(update_fields=['porcentaje_avance', 'estado', 'updated_at'])

    def iniciar(self, usuario):
        """Mark activity as started."""
        self.estado = self.Estado.EN_CURSO
        self.save(update_fields=['estado', 'updated_at'])

    def completar(self):
        """Mark activity as completed."""
        self.estado = self.Estado.COMPLETADA
        self.save(update_fields=['estado', 'updated_at'])

    def cancelar(self, motivo: str):
        """Cancel activity with reason."""
        self.estado = self.Estado.CANCELADA
        self.motivo_cancelacion = motivo
        self.save(update_fields=['estado', 'motivo_cancelacion', 'updated_at'])

    def reprogramar(self, nueva_fecha, motivo: str):
        """Reschedule activity."""
        self.estado = self.Estado.REPROGRAMADA
        self.fecha_reprogramada = nueva_fecha
        self.motivo_reprogramacion = motivo
        self.save(update_fields=['estado', 'fecha_reprogramada', 'motivo_reprogramacion', 'updated_at'])


class InformeDiario(BaseModel):
    """
    Daily activity report for crews.
    Captures daily work summary, personnel, conditions, and performance.
    """

    class CondicionClimatica(models.TextChoices):
        SOLEADO = 'SOLEADO', 'Soleado'
        NUBLADO = 'NUBLADO', 'Nublado'
        LLUVIOSO = 'LLUVIOSO', 'Lluvioso'
        TORMENTA = 'TORMENTA', 'Tormenta Eléctrica'

    class EstadoInforme(models.TextChoices):
        BORRADOR = 'BORRADOR', 'Borrador'
        ENVIADO = 'ENVIADO', 'Enviado'
        APROBADO = 'APROBADO', 'Aprobado'
        RECHAZADO = 'RECHAZADO', 'Rechazado'

    # Core relationships
    fecha = models.DateField(
        'Fecha',
        help_text='Fecha del informe'
    )
    cuadrilla = models.ForeignKey(
        'cuadrillas.Cuadrilla',
        on_delete=models.CASCADE,
        related_name='informes_diarios',
        verbose_name='Cuadrilla'
    )
    linea = models.ForeignKey(
        'lineas.Linea',
        on_delete=models.CASCADE,
        related_name='informes_diarios',
        verbose_name='Línea'
    )
    tramo = models.ForeignKey(
        'lineas.Tramo',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='informes_diarios',
        verbose_name='Tramo'
    )

    # Work tracking
    torre_inicio = models.ForeignKey(
        'lineas.Torre',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='informes_inicio',
        verbose_name='Torre inicio del día'
    )
    torre_fin = models.ForeignKey(
        'lineas.Torre',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='informes_fin',
        verbose_name='Torre fin del día'
    )
    vanos_ejecutados = models.PositiveIntegerField(
        'Vanos ejecutados',
        default=0,
        help_text='Número de vanos completados en el día'
    )

    # Personnel (JSON array with member details)
    personal_presente = models.JSONField(
        'Personal presente',
        default=list,
        blank=True,
        help_text='Lista de personal presente con roles [{usuario_id, nombre, rol, cargo}]'
    )
    total_personas = models.PositiveIntegerField(
        'Total personas',
        default=0
    )

    # Conditions
    condicion_climatica = models.CharField(
        'Condición climática',
        max_length=20,
        choices=CondicionClimatica.choices,
        default=CondicionClimatica.SOLEADO
    )
    hora_inicio_jornada = models.TimeField(
        'Hora inicio jornada',
        null=True,
        blank=True
    )
    hora_fin_jornada = models.TimeField(
        'Hora fin jornada',
        null=True,
        blank=True
    )

    # Activities summary
    actividades_realizadas = models.ManyToManyField(
        Actividad,
        related_name='informes_diarios',
        blank=True,
        verbose_name='Actividades realizadas'
    )
    resumen_trabajo = models.TextField(
        'Resumen del trabajo',
        blank=True,
        help_text='Descripción detallada del trabajo realizado'
    )
    novedades = models.TextField(
        'Novedades',
        blank=True,
        help_text='Novedades o incidentes del día'
    )
    observaciones = models.TextField(
        'Observaciones',
        blank=True
    )

    # Status and approval
    estado = models.CharField(
        'Estado',
        max_length=20,
        choices=EstadoInforme.choices,
        default=EstadoInforme.BORRADOR
    )
    enviado_por = models.ForeignKey(
        'usuarios.Usuario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='informes_enviados',
        verbose_name='Enviado por'
    )
    fecha_envio = models.DateTimeField(
        'Fecha de envío',
        null=True,
        blank=True
    )
    aprobado_por = models.ForeignKey(
        'usuarios.Usuario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='informes_aprobados',
        verbose_name='Aprobado por'
    )
    fecha_aprobacion = models.DateTimeField(
        'Fecha de aprobación',
        null=True,
        blank=True
    )

    class Meta:
        db_table = 'informes_diarios'
        verbose_name = 'Informe Diario'
        verbose_name_plural = 'Informes Diarios'
        unique_together = ['fecha', 'cuadrilla']
        ordering = ['-fecha', 'cuadrilla']
        indexes = [
            models.Index(fields=['fecha']),
            models.Index(fields=['cuadrilla', 'fecha']),
            models.Index(fields=['linea', 'fecha']),
            models.Index(fields=['estado']),
        ]

    def __str__(self):
        return f"Informe {self.cuadrilla.codigo} - {self.fecha}"

    @property
    def rendimiento(self):
        """Calcula el rendimiento: vanos por persona."""
        if self.total_personas > 0:
            return round(self.vanos_ejecutados / self.total_personas, 2)
        return 0

    @property
    def horas_jornada(self):
        """Calcula las horas de jornada trabajadas."""
        if self.hora_inicio_jornada and self.hora_fin_jornada:
            from datetime import datetime, timedelta
            inicio = datetime.combine(self.fecha, self.hora_inicio_jornada)
            fin = datetime.combine(self.fecha, self.hora_fin_jornada)
            if fin < inicio:
                fin += timedelta(days=1)
            delta = fin - inicio
            return round(delta.total_seconds() / 3600, 2)
        return None

    def enviar(self, usuario):
        """Mark report as sent."""
        from django.utils import timezone
        self.estado = self.EstadoInforme.ENVIADO
        self.enviado_por = usuario
        self.fecha_envio = timezone.now()
        self.save(update_fields=['estado', 'enviado_por', 'fecha_envio', 'updated_at'])

    def aprobar(self, usuario):
        """Approve the report."""
        from django.utils import timezone
        self.estado = self.EstadoInforme.APROBADO
        self.aprobado_por = usuario
        self.fecha_aprobacion = timezone.now()
        self.save(update_fields=['estado', 'aprobado_por', 'fecha_aprobacion', 'updated_at'])

    def rechazar(self, usuario, motivo: str):
        """Reject the report."""
        self.estado = self.EstadoInforme.RECHAZADO
        self.observaciones = f"Rechazado: {motivo}"
        self.save(update_fields=['estado', 'observaciones', 'updated_at'])
