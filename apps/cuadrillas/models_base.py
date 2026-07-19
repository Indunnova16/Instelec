"""
Models for work crews (cuadrillas) management.
"""
from django.db import models

from apps.core.models import BaseModel

from .models_cargo import Cargo


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


class PersonalCuadrilla(BaseModel):
    """
    Catálogo de personal disponible para cuadrillas, con su cargo predeterminado.

    Issue #176 (Maestro 3, A3): `rol_cuadrilla` pasó de CharField+choices
    (TextChoices `RolCuadrilla`, ahora eliminado) a FK contra el catálogo
    editable `Cargo` (apps/cuadrillas/models_cargo.py). `to_field='codigo'`
    + `db_column='rol_cuadrilla'` preservan el nombre y tipo físico de la
    columna (varchar(20)) — es aditivo a nivel de constraint, no reescribe
    valores existentes. `instance.rol_cuadrilla_id` sigue siendo el string
    del código exactamente como antes; `instance.rol_cuadrilla` (sin `_id`)
    es ahora el objeto `Cargo` completo.
    """

    nombre = models.CharField('Nombre completo', max_length=200)
    documento = models.CharField('Documento', max_length=30, unique=True)
    rol_cuadrilla = models.ForeignKey(
        Cargo,
        to_field='codigo',
        db_column='rol_cuadrilla',
        on_delete=models.PROTECT,
        default='LINIERO_I',
        related_name='personal_cuadrilla',
        verbose_name='Cargo / Rol',
    )
    activo = models.BooleanField('Activo', default=True)
    celular = models.CharField(
        'Celular',
        max_length=20,
        blank=True,
        help_text='Issue #188 (A1): celular del colaborador, expuesto en el autocompletado '
        'de PersonalCuadrillaAPIView para el grid editable de programación semanal.',
    )
    salario_base = models.DecimalField(
        'Salario base',
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text='Salario mensual base del colaborador (permite calcular costo/día en reportes de cuadrilla semanal)',
    )
    fecha_ingreso = models.DateField(
        'Fecha de ingreso',
        null=True,
        blank=True,
    )
    fecha_salida = models.DateField(
        'Fecha de salida',
        null=True,
        blank=True,
        help_text='Al registrarla, el colaborador se marca automáticamente como inactivo',
    )

    class Meta:
        db_table = 'personal_cuadrilla'
        verbose_name = 'Personal de Cuadrilla'
        verbose_name_plural = 'Personal de Cuadrillas'
        ordering = ['nombre']

    def __str__(self):
        return f"{self.nombre} - {self.get_rol_cuadrilla_display()}"

    def get_rol_cuadrilla_display(self):
        """Shim manual (issue #176 A3): con `rol_cuadrilla` convertido a FK,
        Django ya NO auto-genera `get_<field>_display()` (solo lo hace para
        campos con `choices=`). Este método reemplaza ese auto-generado
        para que los ~10 call sites que lo invocan (templates, reports,
        exporters) sigan funcionando sin cambios."""
        return self.rol_cuadrilla.nombre if self.rol_cuadrilla_id else ''

    def save(self, *args, **kwargs):
        """
        Issue #176 (A2): registrar fecha_salida marca automaticamente
        activo=False. No se revierte automaticamente si se borra
        fecha_salida despues (decision de diseno: la reactivacion es un
        acto explicito del usuario via el CRUD de colaboradores, no un
        efecto secundario implicito de limpiar una fecha).
        """
        if self.fecha_salida:
            self.activo = False
        super().save(*args, **kwargs)


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
    tipo_actividad = models.ForeignKey(
        'actividades.TipoActividad',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cuadrillas_bloque',
        verbose_name='Tipo de actividad',
        help_text='Issue #188 (A1): tipo de actividad del bloque, cabeza de la cascada '
        'Tipo de actividad → Línea → Tramo del grid editable de programación semanal.',
    )
    tramo = models.ForeignKey(
        'lineas.Tramo',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cuadrillas_bloque',
        verbose_name='Tramo',
        help_text='Issue #188 (A1): tramo de la línea asignada (cascada Línea → Tramo). '
        'La tabla tramos puede estar vacía hasta que el cliente la cargue — el campo '
        'admite None sin romper el bloque.',
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

    Issue #176 (Maestro 3, A3): `rol_cuadrilla` pasó de CharField+choices
    (TextChoices `RolCuadrilla`, ahora eliminado — unificado con el mismo
    catálogo `Cargo` que usa `PersonalCuadrilla.rol_cuadrilla`, ver
    models_cargo.py) a FK contra `Cargo`. NO CONFUNDIR con `cargo`
    (`CargoJerarquico`: JT_CTA/MIEMBRO) — ese es un concepto distinto,
    la jerarquía del miembro DENTRO de la cuadrilla, no tocado por este
    maestro.
    """

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
    rol_cuadrilla = models.ForeignKey(
        Cargo,
        to_field='codigo',
        db_column='rol_cuadrilla',
        on_delete=models.PROTECT,
        default='LINIERO_I',
        related_name='cuadrilla_miembros',
        verbose_name='Rol en cuadrilla',
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
    es_conductor_interno = models.BooleanField(
        'Conductor interno',
        default=True,
        help_text='Si es conductor: True=empleado Instelec, False=externo/subcontratado'
    )
    placa_vehiculo = models.CharField(
        'Placa del vehículo',
        max_length=10,
        blank=True,
        help_text='Issue #188 (A1/A5): placa manual del vehículo cuando el rol del miembro '
        'es CONDUCTOR (el grid la exige en ese caso; para el resto queda vacía).',
    )

    class Meta:
        db_table = 'cuadrilla_miembros'
        verbose_name = 'Miembro de Cuadrilla'
        verbose_name_plural = 'Miembros de Cuadrilla'
        unique_together = ['cuadrilla', 'usuario', 'activo']
        ordering = ['cuadrilla', 'rol_cuadrilla', 'usuario__first_name']

    def __str__(self):
        return f"{self.usuario.get_full_name()} - {self.cuadrilla.codigo}"

    def get_rol_cuadrilla_display(self):
        """Shim manual (issue #176 A3) — ver PersonalCuadrilla.get_rol_cuadrilla_display."""
        return self.rol_cuadrilla.nombre if self.rol_cuadrilla_id else ''


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
        COMPENSATORIO = 'COMPENSATORIO', 'Compensatorio'
        DESCANSO = 'DESCANSO', 'Descanso'

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
        help_text='Total horas extra (auto-calculado)'
    )
    he_diurna = models.DecimalField(
        'HE Diurna',
        max_digits=4,
        decimal_places=1,
        default=0,
        blank=True,
        help_text='Horas extra diurnas'
    )
    he_nocturna = models.DecimalField(
        'HE Nocturna',
        max_digits=4,
        decimal_places=1,
        default=0,
        blank=True,
        help_text='Horas extra nocturnas'
    )
    he_dominical_diurna = models.DecimalField(
        'HE Dom. Diurna',
        max_digits=4,
        decimal_places=1,
        default=0,
        blank=True,
        help_text='Horas extra dominicales diurnas'
    )
    he_dominical_nocturna = models.DecimalField(
        'HE Dom. Nocturna',
        max_digits=4,
        decimal_places=1,
        default=0,
        blank=True,
        help_text='Horas extra dominicales nocturnas'
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

    JORNADA_POR_DIA = {
        0: 8.0,   # Lunes
        1: 7.5,   # Martes
        2: 7.5,   # Miércoles
        3: 7.5,   # Jueves
        4: 7.5,   # Viernes
        5: 6.0,   # Sábado
        6: 0.0,   # Domingo
    }

    def save(self, *args, **kwargs):
        detail_sum = (
            (self.he_diurna or 0) +
            (self.he_nocturna or 0) +
            (self.he_dominical_diurna or 0) +
            (self.he_dominical_nocturna or 0)
        )
        self.horas_extra = detail_sum
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.usuario.get_full_name()} - {self.fecha} - {self.get_tipo_novedad_display()}"

    @property
    def tiene_horas_extra(self):
        return any([
            self.he_diurna and self.he_diurna > 0,
            self.he_nocturna and self.he_nocturna > 0,
            self.he_dominical_diurna and self.he_dominical_diurna > 0,
            self.he_dominical_nocturna and self.he_dominical_nocturna > 0,
        ])

    @property
    def jornada_regular(self):
        return self.JORNADA_POR_DIA.get(self.fecha.weekday(), 0)

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


class NovedadPersonalSemana(BaseModel):
    """Registro INDEPENDIENTE de personal en sección NOVEDADES de una semana
    de programación (issue #178, A2).

    Las filas del Excel real bajo el encabezado 'NOVEDADES' (vacaciones,
    incapacidad, nuevo ingreso, reincorporación...) NO pertenecen a ninguna
    actividad/cuadrilla. Antes del fix, ambos importers (S18 y
    ProgramacionSemanalImporter) NO reseteaban el bloque/actividad activa al
    detectar 'NOVEDADES', así que esas personas quedaban mezcladas
    silenciosamente como miembro de la ÚLTIMA actividad real de la hoja.

    Deliberadamente NO tiene FK a Cuadrilla/Actividad/PersonalCuadrilla:
    estos registros son independientes por diseño (persona + semana + nota),
    y la misma cédula puede aparecer AQUÍ y también como miembro real de una
    actividad en la misma semana (p.ej. reincorporación a mitad de semana) —
    ambos registros deben coexistir sin deduplicación entre sí.
    """

    cedula = models.CharField('Cédula', max_length=20)
    nombre = models.CharField('Nombre', max_length=200, blank=True, default='')
    cargo = models.CharField('Cargo', max_length=100, blank=True, default='')
    semana = models.PositiveSmallIntegerField('Semana ISO')
    anio = models.PositiveSmallIntegerField('Año')
    nota = models.CharField(
        'Nota',
        max_length=200,
        blank=True,
        default='',
        help_text='Texto de la columna AVISOS en la fila de NOVEDADES (ej. "Vacaciones", "Incapacidad").'
    )
    hoja_origen = models.CharField('Hoja de origen', max_length=50, blank=True, default='')

    class Meta:
        verbose_name = 'Novedad de personal (semana)'
        verbose_name_plural = 'Novedades de personal (semana)'
        ordering = ['-anio', '-semana', 'nombre']
        indexes = [
            models.Index(fields=['anio', 'semana']),
            models.Index(fields=['cedula']),
        ]

    def __str__(self):
        return f'{self.nombre or self.cedula} — semana {self.semana}/{self.anio} ({self.nota or "sin nota"})'
