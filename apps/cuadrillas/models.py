"""
Models for work crews (cuadrillas) management.
"""
from django.db import models

from apps.core.models import BaseModel


class Vehiculo(BaseModel):
    """
    Vehicle model for crew transportation.
    """

    class TipoVehiculo(models.TextChoices):
        CAMIONETA = 'CAMIONETA', 'Camioneta'
        CAMION = 'CAMION', 'Camión'
        GRUA = 'GRUA', 'Grúa'
        OTRO = 'OTRO', 'Otro'

    placa = models.CharField(
        'Placa',
        max_length=10,
        unique=True
    )
    tipo = models.CharField(
        'Tipo',
        max_length=20,
        choices=TipoVehiculo.choices,
        default=TipoVehiculo.CAMIONETA
    )
    marca = models.CharField(
        'Marca',
        max_length=50,
        blank=True
    )
    modelo = models.CharField(
        'Modelo',
        max_length=50,
        blank=True
    )
    ano = models.PositiveIntegerField(
        'Año',
        null=True,
        blank=True
    )
    capacidad_personas = models.PositiveIntegerField(
        'Capacidad (personas)',
        default=5
    )
    costo_dia = models.DecimalField(
        'Costo por día',
        max_digits=12,
        decimal_places=2,
        default=0
    )
    activo = models.BooleanField(
        'Activo',
        default=True
    )
    observaciones = models.TextField(
        'Observaciones',
        blank=True
    )

    class Meta:
        db_table = 'vehiculos'
        verbose_name = 'Vehículo'
        verbose_name_plural = 'Vehículos'
        ordering = ['placa']

    def __str__(self):
        return f"{self.placa} - {self.marca} {self.modelo}"


class Cuadrilla(BaseModel):
    """
    Work crew model.
    """

    codigo = models.CharField(
        'Código',
        max_length=20,
        unique=True,
        help_text='Código único de la cuadrilla (ej: CUA-001)'
    )
    nombre = models.CharField(
        'Nombre',
        max_length=100
    )
    supervisor = models.ForeignKey(
        'usuarios.Usuario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cuadrillas_supervisadas',
        verbose_name='Supervisor',
        limit_choices_to={'rol': 'supervisor'}
    )
    vehiculo = models.ForeignKey(
        Vehiculo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cuadrillas',
        verbose_name='Vehículo asignado'
    )
    linea_asignada = models.ForeignKey(
        'lineas.Linea',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cuadrillas',
        verbose_name='Línea asignada'
    )
    activa = models.BooleanField(
        'Activa',
        default=True
    )
    observaciones = models.TextField(
        'Observaciones',
        blank=True
    )
    fecha = models.DateField(
        'Fecha',
        null=True,
        blank=True,
        help_text='Fecha de operacion de la cuadrilla'
    )

    class Meta:
        db_table = 'cuadrillas'
        verbose_name = 'Cuadrilla'
        verbose_name_plural = 'Cuadrillas'
        ordering = ['codigo']

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"

    @property
    def miembros_activos(self):
        return self.miembros.filter(activo=True)

    @property
    def total_miembros(self):
        return self.miembros_activos.count()


class CuadrillaMiembro(BaseModel):
    """
    Crew member assignment.
    """

    class RolCuadrilla(models.TextChoices):
        SUPERVISOR = 'SUPERVISOR', 'Supervisor'
        LINIERO_I = 'LINIERO_I', 'Liniero I'
        LINIERO_II = 'LINIERO_II', 'Liniero II'
        AYUDANTE = 'AYUDANTE', 'Ayudante'
        CONDUCTOR = 'CONDUCTOR', 'Conductor'
        ADMINISTRADOR_OBRA = 'ADMINISTRADOR_OBRA', 'Administrador de Obra'
        PROFESIONAL_SST = 'PROFESIONAL_SST', 'Profesional SST'
        INGENIERO_RESIDENTE = 'ING_RESIDENTE', 'Ingeniero Residente'
        SERVICIO_GENERAL = 'SERVICIO_GENERAL', 'Servicio General'
        ALMACENISTA = 'ALMACENISTA', 'Almacenista'
        SUPERVISOR_FORESTAL = 'SUPERVISOR_FOREST', 'Supervisor Forestal'
        ASISTENTE_FORESTAL = 'ASISTENTE_FOREST', 'Asistente Forestal'

    class CargoJerarquico(models.TextChoices):
        JT_CTA = 'JT_CTA', 'Jefe de Trabajo / Capacitado'
        MIEMBRO = 'MIEMBRO', 'Miembro'

    cuadrilla = models.ForeignKey(
        Cuadrilla,
        on_delete=models.CASCADE,
        related_name='miembros',
        verbose_name='Cuadrilla'
    )
    usuario = models.ForeignKey(
        'usuarios.Usuario',
        on_delete=models.CASCADE,
        related_name='asignaciones_cuadrilla',
        verbose_name='Usuario'
    )
    rol_cuadrilla = models.CharField(
        'Rol en cuadrilla',
        max_length=20,
        choices=RolCuadrilla.choices,
        default=RolCuadrilla.LINIERO_I
    )
    cargo = models.CharField(
        'Cargo jerárquico',
        max_length=20,
        choices=CargoJerarquico.choices,
        default=CargoJerarquico.MIEMBRO,
        help_text='Define si el miembro es Jefe de Trabajo/Capacitado o Miembro regular'
    )
    fecha_inicio = models.DateField(
        'Fecha de inicio'
    )
    fecha_fin = models.DateField(
        'Fecha de fin',
        null=True,
        blank=True
    )
    activo = models.BooleanField(
        'Activo',
        default=True
    )
    costo_dia = models.DecimalField(
        'Costo por dia',
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text='Costo diario del miembro segun su rol/cargo'
    )

    class Meta:
        db_table = 'cuadrilla_miembros'
        verbose_name = 'Miembro de Cuadrilla'
        verbose_name_plural = 'Miembros de Cuadrilla'
        unique_together = ['cuadrilla', 'usuario', 'activo']
        ordering = ['cuadrilla', 'rol_cuadrilla', 'usuario__first_name']

    def __str__(self):
        return f"{self.usuario.get_full_name()} - {self.cuadrilla.codigo}"


class TrackingUbicacion(BaseModel):
    """
    Real-time location tracking for crews.
    """

    cuadrilla = models.ForeignKey(
        Cuadrilla,
        on_delete=models.CASCADE,
        related_name='ubicaciones',
        verbose_name='Cuadrilla'
    )
    usuario = models.ForeignKey(
        'usuarios.Usuario',
        on_delete=models.CASCADE,
        related_name='ubicaciones_tracking',
        verbose_name='Usuario'
    )
    latitud = models.DecimalField(
        'Latitud',
        max_digits=10,
        decimal_places=8
    )
    longitud = models.DecimalField(
        'Longitud',
        max_digits=11,
        decimal_places=8
    )
    precision_metros = models.DecimalField(
        'Precisión (metros)',
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True
    )
    velocidad = models.DecimalField(
        'Velocidad (km/h)',
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True
    )
    bateria = models.PositiveIntegerField(
        'Nivel batería (%)',
        null=True,
        blank=True
    )

    class Meta:
        db_table = 'tracking_ubicacion'
        verbose_name = 'Tracking de Ubicación'
        verbose_name_plural = 'Tracking de Ubicaciones'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['cuadrilla', '-created_at']),
            models.Index(fields=['usuario', '-created_at']),
        ]

    def __str__(self):
        return f"{self.cuadrilla.codigo} - {self.created_at}"


class Asistencia(BaseModel):
    """
    Modelo para registro de asistencia diaria del personal de cuadrillas.
    """

    class TipoNovedad(models.TextChoices):
        PRESENTE = 'PRESENTE', 'Presente'
        VACACIONES = 'VACACIONES', 'Vacaciones'
        INCAPACIDAD = 'INCAPACIDAD', 'Incapacidad'
        PERMISO = 'PERMISO', 'Permiso'
        AUSENTE = 'AUSENTE', 'Ausente'
        LICENCIA = 'LICENCIA', 'Licencia'
        CAPACITACION = 'CAPACITACION', 'Capacitación'

    usuario = models.ForeignKey(
        'usuarios.Usuario',
        on_delete=models.CASCADE,
        related_name='asistencias',
        verbose_name='Usuario'
    )
    cuadrilla = models.ForeignKey(
        Cuadrilla,
        on_delete=models.CASCADE,
        related_name='asistencias',
        verbose_name='Cuadrilla'
    )
    fecha = models.DateField(
        'Fecha',
        help_text='Fecha del registro de asistencia'
    )
    tipo_novedad = models.CharField(
        'Tipo de novedad',
        max_length=20,
        choices=TipoNovedad.choices,
        default=TipoNovedad.PRESENTE
    )
    hora_entrada = models.TimeField(
        'Hora de entrada',
        null=True,
        blank=True
    )
    hora_salida = models.TimeField(
        'Hora de salida',
        null=True,
        blank=True
    )
    observacion = models.TextField(
        'Observación',
        blank=True,
        help_text='Observaciones adicionales sobre la asistencia'
    )
    viaticos = models.DecimalField(
        'Viáticos',
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text='Costo de viáticos del día'
    )
    horas_extra = models.DecimalField(
        'Horas extra',
        max_digits=4,
        decimal_places=1,
        default=0,
        blank=True,
        help_text='Horas extra trabajadas en el día'
    )
    viatico_aplica = models.BooleanField(
        'Viático aplica',
        default=False,
        help_text='Indica si el día aplica viático (Sí/No)'
    )
    registrado_por = models.ForeignKey(
        'usuarios.Usuario',
        on_delete=models.SET_NULL,
        null=True,
        related_name='asistencias_registradas',
        verbose_name='Registrado por'
    )

    class Meta:
        db_table = 'asistencias'
        verbose_name = 'Asistencia'
        verbose_name_plural = 'Asistencias'
        unique_together = ['usuario', 'cuadrilla', 'fecha']
        ordering = ['-fecha', 'cuadrilla', 'usuario']
        indexes = [
            models.Index(fields=['fecha']),
            models.Index(fields=['cuadrilla', 'fecha']),
            models.Index(fields=['tipo_novedad']),
        ]

    def __str__(self):
        return f"{self.usuario.get_full_name()} - {self.fecha} - {self.get_tipo_novedad_display()}"

    @property
    def esta_presente(self):
        """Indica si el usuario estuvo presente."""
        return self.tipo_novedad == self.TipoNovedad.PRESENTE

    @property
    def horas_trabajadas(self):
        """Calcula las horas trabajadas si hay entrada y salida."""
        if self.hora_entrada and self.hora_salida:
            from datetime import datetime, timedelta
            entrada = datetime.combine(self.fecha, self.hora_entrada)
            salida = datetime.combine(self.fecha, self.hora_salida)
            if salida < entrada:
                salida += timedelta(days=1)
            delta = salida - entrada
            return round(delta.total_seconds() / 3600, 2)
        return None
