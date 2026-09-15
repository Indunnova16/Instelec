"""Modelos compartidos para Programación Semanal de Construcción (#225)."""
from django.db import models

from apps.core.models import BaseModel


class AsignacionPersonalProyectoConstruccion(BaseModel):
    """Ventana de aprobación de una persona para un proyecto de construcción."""

    proyecto = models.ForeignKey(
        'construccion.ProyectoConstruccion', on_delete=models.CASCADE,
        related_name='aprobaciones_personal_psc', verbose_name='Proyecto',
    )
    personal = models.ForeignKey(
        'cuadrillas.PersonalCuadrilla', on_delete=models.CASCADE,
        related_name='aprobaciones_proyecto_construccion', verbose_name='Personal',
    )
    fecha_inicio = models.DateField('Fecha de aprobación / inicio')
    fecha_fin = models.DateField('Fecha fin', null=True, blank=True)

    class Meta:
        db_table = 'construccion_asignacion_personal_proyecto'
        verbose_name = 'Aprobación de personal por proyecto'
        verbose_name_plural = 'Aprobaciones de personal por proyecto'
        ordering = ['proyecto', 'personal', 'fecha_inicio']

    def __str__(self):
        return f'{self.personal} — {self.proyecto}'


class ProgramacionSemanalConstruccion(BaseModel):
    """Cabecera de una actividad programada para una cuadrilla de construcción."""

    class TipoActividad(models.TextChoices):
        PRELIMINARES = 'PRELIMINARES', 'Preliminares'
        OBRA_CIVIL = 'OBRA_CIVIL', 'Obra Civil'
        MONTAJE = 'MONTAJE', 'Montaje'
        TENDIDO = 'TENDIDO', 'Tendido'
        COMPLEMENTARIAS = 'COMPLEMENTARIAS', 'Actividades Complementarias'

    proyecto = models.ForeignKey(
        'construccion.ProyectoConstruccion', on_delete=models.CASCADE,
        related_name='programaciones_semanales_psc', verbose_name='Proyecto',
    )
    cuadrilla = models.CharField(
        'Cuadrilla', max_length=150, blank=True,
        help_text='Nombre de la cuadrilla según la programación histórica.',
    )
    tipo_actividad = models.CharField(
        'Tipo de actividad', max_length=20, choices=TipoActividad.choices,
    )
    subactividad = models.CharField('Subactividad', max_length=150, blank=True)
    actividad_complementaria = models.TextField('Actividad complementaria', blank=True)
    fecha_inicio = models.DateField('Fecha inicio')
    fecha_fin = models.DateField('Fecha fin')
    hora_inicio = models.TimeField('Hora inicio', null=True, blank=True)
    hora_fin = models.TimeField('Hora fin', null=True, blank=True)
    supervisor = models.ForeignKey(
        'usuarios.Usuario', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='programaciones_semanales_psc_supervisadas', verbose_name='Supervisor',
    )
    observaciones = models.TextField('Observaciones', blank=True)

    class Meta:
        db_table = 'construccion_programacion_semanal'
        verbose_name = 'Programación semanal de construcción'
        verbose_name_plural = 'Programaciones semanales de construcción'
        ordering = ['fecha_inicio', 'hora_inicio']

    def __str__(self):
        return f'{self.proyecto} — {self.fecha_inicio:%Y-%m-%d}'


class ProgramacionSemanalConstruccionPersonal(BaseModel):
    """Integrante operativo o administrativo de una programación PSC."""

    class Categoria(models.TextChoices):
        OPERATIVO = 'OPERATIVO', 'Operativo'
        ADMINISTRATIVO = 'ADMINISTRATIVO', 'Administrativo'

    class RolPresupuesto(models.TextChoices):
        SUPERVISOR = 'SUPERVISOR', 'Supervisor presupuestario'
        COLABORADOR = 'COLABORADOR', 'Colaborador presupuestario'

    class FuenteTarifa(models.TextChoices):
        PERSONAL = 'PERSONAL', 'Salario individual'
        CARGO = 'CARGO', 'Salario del cargo'

    programacion = models.ForeignKey(
        ProgramacionSemanalConstruccion, on_delete=models.CASCADE,
        related_name='asignaciones_personal', verbose_name='Programación',
    )
    personal = models.ForeignKey(
        'cuadrillas.PersonalCuadrilla', on_delete=models.CASCADE,
        related_name='programaciones_semanales_psc', verbose_name='Personal',
    )
    categoria = models.CharField(
        'Categoría', max_length=20, choices=Categoria.choices, default=Categoria.OPERATIVO,
    )
    rol_presupuesto = models.CharField(
        'Rol en presupuesto', max_length=15, choices=RolPresupuesto.choices,
        default=RolPresupuesto.COLABORADOR,
        help_text='Rol de esta persona dentro del plan presupuestario; no reemplaza el supervisor legacy de la cabecera.',
    )
    salario_mensual_snapshot = models.DecimalField(
        'Salario mensual snapshot', max_digits=12, decimal_places=2, null=True, blank=True,
    )
    divisor_snapshot = models.PositiveSmallIntegerField(
        'Divisor snapshot', null=True, blank=True,
        help_text='Divisor usado para calcular la tarifa diaria (actualmente 30).',
    )
    tarifa_diaria_snapshot = models.DecimalField(
        'Tarifa diaria snapshot', max_digits=14, decimal_places=4, null=True, blank=True,
    )
    fuente_tarifa = models.CharField(
        'Fuente de tarifa', max_length=10, choices=FuenteTarifa.choices, blank=True,
    )
    cargo_snapshot_codigo = models.CharField(
        'Código de cargo snapshot', max_length=20, blank=True,
        help_text='Cargo que respaldó la tarifa cuando la fuente fue CARGO.',
    )
    snapshot_tomado_en = models.DateTimeField('Snapshot tomado en', null=True, blank=True)

    class Meta:
        db_table = 'construccion_programacion_semanal_personal'
        verbose_name = 'Personal programado de construcción'
        verbose_name_plural = 'Personal programado de construcción'
        constraints = [
            models.UniqueConstraint(
                fields=['programacion', 'personal'], name='psc_programacion_personal_unico',
            ),
            models.UniqueConstraint(
                fields=['programacion'], condition=models.Q(rol_presupuesto='SUPERVISOR'),
                name='psc_un_supervisor_presupuestario',
            ),
        ]


class ProgramacionSemanalConstruccionPlanPresupuesto(BaseModel):
    """Versión inmutable del presupuesto PSC tras el primer real de #252."""

    programacion = models.OneToOneField(
        ProgramacionSemanalConstruccion, on_delete=models.CASCADE,
        related_name='plan_presupuesto_congelado', verbose_name='Programación',
    )
    primer_real = models.ForeignKey(
        'cuadrillas.ProduccionDiaria', on_delete=models.PROTECT,
        related_name='planes_presupuesto_psc_congelados', verbose_name='Primer real',
    )
    congelado_en = models.DateTimeField('Congelado en')
    snapshot = models.JSONField(
        'Snapshot del plan', default=dict,
        help_text='Contrato serializado para conservar el comparativo aunque cambie el plan editable.',
    )

    class Meta:
        db_table = 'construccion_programacion_semanal_plan_presupuesto'
        verbose_name = 'Plan presupuestario congelado de construcción'
        verbose_name_plural = 'Planes presupuestarios congelados de construcción'


class ProgramacionSemanalConstruccionVehiculo(BaseModel):
    """Vehículo asignado a una programación PSC, con su conductor opcional."""

    programacion = models.ForeignKey(
        ProgramacionSemanalConstruccion, on_delete=models.CASCADE,
        related_name='asignaciones_vehiculo', verbose_name='Programación',
    )
    vehiculo = models.ForeignKey(
        'cuadrillas.Vehiculo', on_delete=models.CASCADE,
        related_name='programaciones_semanales_psc', verbose_name='Vehículo',
    )
    conductor = models.ForeignKey(
        'cuadrillas.PersonalCuadrilla', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='vehiculos_conducidos_psc', verbose_name='Conductor',
    )

    class Meta:
        db_table = 'construccion_programacion_semanal_vehiculo'
        verbose_name = 'Vehículo programado de construcción'
        verbose_name_plural = 'Vehículos programados de construcción'
        constraints = [
            models.UniqueConstraint(
                fields=['programacion', 'vehiculo'], name='psc_programacion_vehiculo_unico',
            ),
        ]
