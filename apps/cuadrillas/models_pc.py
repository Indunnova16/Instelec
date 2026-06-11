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


class ProgramacionSemanalCuadrilla(BaseModel):
    """
    Programación semanal de una cuadrilla: torres y actividades planeadas para
    una semana ISO (año + número de semana).
    """

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
    torres_programadas = models.PositiveIntegerField(
        'Torres programadas',
        default=0,
        help_text='Cantidad de torres planeadas para la semana',
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
