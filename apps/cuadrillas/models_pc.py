"""
Programación / Ejecución semanal de cuadrillas (#155).

Scaffolding S1 del bloque `programacion_cuadrillas`. Estos modelos son la base
compartida que las sub-features B1–B5 asumen pre-existente:

- `ProgramacionSemanalCuadrilla`: lo que se planea ejecutar por cuadrilla en una
  semana ISO (torres + actividades programadas), opcionalmente atada a un
  proyecto de construcción.
- `EjecucionSemanalCuadrilla`: lo realmente ejecutado (1:1 con la programación),
  con la propiedad `rendimiento_pct` (ejecutado/programado × 100, guarda div/0).

Patrón seguido de `models_base.py`: heredan de `apps.core.models.BaseModel`
(PK UUID + created_at/updated_at), `db_table` explícito, verbose_name ES.
"""
from django.db import models

from apps.core.models import BaseModel

from .models_base import PersonalCuadrilla, Vehiculo


class ProgramacionSemanalCuadrilla(BaseModel):
    """
    Programación semanal de una cuadrilla: torres y actividades planeadas para
    una semana ISO (año + número de semana).
    """

    # Macro-bloques del proyecto (#155, item 12). El cumplimiento de cuadrilla
    # debe servir para los 3 bloques. OJO: NO confundir con `BLOQUES_ORDEN`
    # (apps/construccion/models.py), que son las sub-fases internas de Obra Civil
    # (#53). Estos son los 3 macro-bloques de la obra completa.
    BLOQUE_OBRA_CIVIL = 'obra_civil'
    BLOQUE_MONTAJE = 'montaje'
    BLOQUE_TENDIDO = 'tendido'
    BLOQUE_CHOICES = [
        (BLOQUE_OBRA_CIVIL, 'Obra civil'),
        (BLOQUE_MONTAJE, 'Montaje'),
        (BLOQUE_TENDIDO, 'Tendido'),
    ]

    cuadrilla = models.ForeignKey(
        'cuadrillas.Cuadrilla',
        on_delete=models.CASCADE,
        related_name='programaciones_semanales',
        verbose_name='Cuadrilla',
    )
    proyecto = models.ForeignKey(
        'construccion.ProyectoConstruccion',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='programaciones_cuadrilla',
        verbose_name='Proyecto de construcción',
    )
    anio = models.PositiveIntegerField(
        'Año',
        help_text='Año ISO de la programación (ej: 2026)',
    )
    semana = models.PositiveSmallIntegerField(
        'Semana ISO',
        help_text='Número de semana ISO (1-53)',
    )
    bloque = models.CharField(
        'Bloque',
        max_length=20,
        choices=BLOQUE_CHOICES,
        null=True,
        blank=True,
        help_text='Macro-bloque del proyecto (obra civil / montaje / tendido). '
                  'Opcional: las programaciones sin bloque quedan "sin asignar".',
    )
    torres_programadas = models.PositiveIntegerField(
        'Torres programadas',
        default=0,
        help_text='Cantidad de torres planeadas para la semana',
    )
    # #269: selección real de torres del proyecto (M2M, ADITIVA/trazabilidad).
    # NO reemplaza `torres_programadas` (que sigue siendo el conteo manual
    # editable e independiente usado por `rendimiento_pct` y por los goldens
    # del corpus) -- es puramente informativa: qué torres concretas del
    # proyecto quedaron incluidas en esta programación semanal.
    torres = models.ManyToManyField(
        'construccion.TorreConstruccion',
        blank=True,
        related_name='programaciones_cuadrilla',
        verbose_name='Torres',
        help_text='Torres reales del proyecto incluidas en esta programación '
                  '(selección informativa/trazabilidad; no reemplaza "Torres '
                  'programadas", que sigue siendo el conteo manual editable).',
    )
    horas_planeadas = models.DecimalField(
        'Horas planeadas',
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Horas de trabajo planeadas para la semana',
    )
    actividades_programadas = models.TextField(
        'Actividades programadas',
        blank=True,
        help_text='Descripción de las actividades planeadas para la semana',
    )
    observaciones = models.TextField(
        'Observaciones',
        blank=True,
    )

    class Meta:
        db_table = 'programacion_semanal_cuadrilla'
        verbose_name = 'Programación Semanal de Cuadrilla'
        verbose_name_plural = 'Programaciones Semanales de Cuadrilla'
        ordering = ['-anio', '-semana', 'cuadrilla']
        unique_together = ['cuadrilla', 'anio', 'semana']
        indexes = [
            models.Index(fields=['anio', 'semana']),
            models.Index(fields=['cuadrilla', 'anio', 'semana']),
        ]

    def __str__(self):
        return f"{self.cuadrilla} - {self.anio}-S{self.semana:02d}"


class EjecucionSemanalCuadrilla(BaseModel):
    """
    Ejecución real de una programación semanal. 1:1 con
    `ProgramacionSemanalCuadrilla`; `rendimiento_pct` se deriva.
    """

    programacion = models.OneToOneField(
        ProgramacionSemanalCuadrilla,
        on_delete=models.CASCADE,
        related_name='ejecucion',
        verbose_name='Programación',
    )
    torres_ejecutadas = models.PositiveIntegerField(
        'Torres ejecutadas',
        default=0,
        help_text='Cantidad de torres realmente ejecutadas en la semana',
    )
    # #270 (sub-item B): vehículo asignado a la ejecución. Editable/reasignable
    # -- se guarda por el mismo upsert AJAX de `EjecucionSemanalUpdateView`
    # (torres_ejecutadas/observaciones). SET_NULL: si el vehículo se elimina
    # del catálogo, la ejecución queda "sin vehículo" en vez de perder el
    # registro (mismo patrón que `Cuadrilla.vehiculo`, models_base.py).
    vehiculo = models.ForeignKey(
        Vehiculo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ejecuciones_semanales_cuadrilla',
        verbose_name='Vehículo asignado',
        help_text='Vehículo asignado a la ejecución de esta semana '
                  '(editable/reasignable).',
    )
    observaciones = models.TextField(
        'Observaciones',
        blank=True,
    )

    class Meta:
        db_table = 'ejecucion_semanal_cuadrilla'
        verbose_name = 'Ejecución Semanal de Cuadrilla'
        verbose_name_plural = 'Ejecuciones Semanales de Cuadrilla'
        ordering = ['-created_at']

    def __str__(self):
        return f"Ejecución {self.programacion} ({self.rendimiento_pct:.0f}%)"

    @property
    def rendimiento_pct(self):
        """
        Rendimiento = torres_ejecutadas / torres_programadas × 100.
        Guarda div/0: si no hay torres programadas, retorna 0.0.
        """
        programadas = self.programacion.torres_programadas or 0
        if programadas <= 0:
            return 0.0
        return (self.torres_ejecutadas / programadas) * 100


class EjecucionSemanalPersonal(BaseModel):
    """
    Personal asignado a la ejecución semanal (#270, sub-item C).

    Through-model explícito `EjecucionSemanalCuadrilla` <-> `PersonalCuadrilla`
    (M2M con datos propios: mismo patrón que `CuadrillaMiembro` en
    `models_base.py`, FK+FK en vez de un `ManyToManyField(through=...)`
    -- más simple de manejar desde las vistas AJAX de alta/edición/baja).

    `costo_dia` es un SNAPSHOT tomado al agregar (desde
    `PersonalCuadrilla.rol_cuadrilla.salario_base`, mismo origen y misma
    convención de nombre que `views.py::CostoRolAPIView` / `CuadrillaMiembro.
    costo_dia` -- issue #176 A2 ya documentó que el campo se llama "por día"
    pero en la práctica guarda el valor MENSUAL del Cargo; se mantiene esa
    misma convención acá para no divergir del resto del portafolio, corregir
    la unidad es fuera de alcance de #270) y queda editable después por si el
    costo real de la semana difiere del default del cargo (ej. bono puntual,
    ajuste manual). No se recalcula solo si el `Cargo` referenciado cambia de
    `salario_base` más tarde -- es intencional, es un valor histórico de ESA
    semana ejecutada.

    `unique_together` evita agregar dos veces a la misma persona en la misma
    ejecución (edge case "agregar duplicado" del sub-item).
    """

    ejecucion = models.ForeignKey(
        EjecucionSemanalCuadrilla,
        on_delete=models.CASCADE,
        related_name='personal_asignado',
        verbose_name='Ejecución',
    )
    personal = models.ForeignKey(
        PersonalCuadrilla,
        on_delete=models.CASCADE,
        related_name='ejecuciones_semanales_personal',
        verbose_name='Personal',
    )
    costo_dia = models.DecimalField(
        'Costo por día',
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text='Costo diario de esta persona para la semana ejecutada '
                  '(snapshot editable, tomado del cargo al agregar).',
    )

    class Meta:
        db_table = 'ejecucion_semanal_personal'
        verbose_name = 'Personal de Ejecución Semanal'
        verbose_name_plural = 'Personal de Ejecución Semanal'
        ordering = ['personal__nombre']
        unique_together = ['ejecucion', 'personal']

    def __str__(self):
        return f"{self.personal} — {self.ejecucion}"
