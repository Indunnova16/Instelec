"""
Admin de Programación / Ejecución semanal de cuadrillas (B5, #155).

Registra los 2 modelos de `models_pc` en el Django admin. Se importa desde
`apps/cuadrillas/admin.py` vía el aggregator add-only (`try: from .admin_pc
import *`) que dejó el scaffolding S1, para no tocar el `admin.py` monolítico.

- `ProgramacionSemanalCuadrilla`: lista por cuadrilla / año / semana, con la
  ejecución 1:1 editable inline (torres ejecutadas + rendimiento de solo
  lectura).
- `EjecucionSemanalCuadrilla`: registro propio con el rendimiento derivado
  expuesto como columna calculada de solo lectura. Incluye `vehiculo`
  (#270 sub-item B) como `raw_id_fields` (catálogo puede crecer).
"""
from django.contrib import admin

from apps.core.admin import BaseModelAdmin

from .models_pc import (
    AsistenciaEjecucionSemanal,
    EjecucionSemanalCuadrilla,
    EjecucionSemanalPersonal,
    EjecucionSemanalTorre,
    ProgramacionSemanalCuadrilla,
)


class EjecucionSemanalInline(admin.StackedInline):
    """Ejecución 1:1 editable desde el detalle de la programación."""

    model = EjecucionSemanalCuadrilla
    extra = 0
    fields = ('torres_ejecutadas', 'vehiculo', 'rendimiento_pct_display', 'observaciones')
    readonly_fields = ('rendimiento_pct_display',)
    raw_id_fields = ('vehiculo',)

    @admin.display(description='Rendimiento')
    def rendimiento_pct_display(self, obj):
        if obj is None or obj.pk is None:
            return '—'
        return f"{obj.rendimiento_pct:.1f}%"


@admin.register(ProgramacionSemanalCuadrilla)
class ProgramacionSemanalCuadrillaAdmin(BaseModelAdmin):
    list_display = (
        'cuadrilla', 'anio', 'semana', 'proyecto',
        'torres_programadas', 'rendimiento_display',
    )
    list_filter = ('anio', 'semana', 'cuadrilla', 'proyecto')
    search_fields = (
        'cuadrilla__codigo', 'cuadrilla__nombre',
        'actividades_programadas', 'observaciones',
    )
    raw_id_fields = ('cuadrilla', 'proyecto')
    inlines = [EjecucionSemanalInline]

    fieldsets = (
        (None, {
            'fields': ('cuadrilla', 'proyecto', 'anio', 'semana')
        }),
        ('Programación', {
            'fields': ('torres_programadas', 'actividades_programadas')
        }),
        ('Observaciones', {
            'fields': ('observaciones',)
        }),
        ('Auditoría', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    @admin.display(description='Rendimiento')
    def rendimiento_display(self, obj):
        ejecucion = getattr(obj, 'ejecucion', None)
        if ejecucion is None:
            return '—'
        return f"{ejecucion.rendimiento_pct:.1f}%"


@admin.register(EjecucionSemanalCuadrilla)
class EjecucionSemanalCuadrillaAdmin(BaseModelAdmin):
    list_display = ('programacion', 'torres_ejecutadas', 'vehiculo', 'rendimiento_display')
    list_filter = ('programacion__anio', 'programacion__semana', 'programacion__cuadrilla')
    search_fields = (
        'programacion__cuadrilla__codigo',
        'programacion__cuadrilla__nombre',
        'observaciones',
        'vehiculo__placa',
    )
    raw_id_fields = ('programacion', 'vehiculo')

    fieldsets = (
        (None, {
            'fields': ('programacion', 'torres_ejecutadas', 'vehiculo', 'rendimiento_display')
        }),
        ('Observaciones', {
            'fields': ('observaciones',)
        }),
        ('Auditoría', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ('id', 'created_at', 'updated_at', 'rendimiento_display')

    @admin.display(description='Rendimiento')
    def rendimiento_display(self, obj):
        if obj is None or obj.pk is None:
            return '—'
        return f"{obj.rendimiento_pct:.1f}%"


@admin.register(EjecucionSemanalPersonal)
class EjecucionSemanalPersonalAdmin(BaseModelAdmin):
    """#270 (sub-item C): personal asignado a la ejecución semanal."""

    list_display = ('personal', 'ejecucion', 'costo_dia')
    list_filter = (
        'ejecucion__programacion__anio', 'ejecucion__programacion__semana',
        'ejecucion__programacion__cuadrilla',
    )
    search_fields = (
        'personal__nombre', 'personal__documento',
        'ejecucion__programacion__cuadrilla__codigo',
    )
    raw_id_fields = ('ejecucion', 'personal')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(EjecucionSemanalTorre)
class EjecucionSemanalTorreAdmin(BaseModelAdmin):
    """#270 (sub-item A): trazabilidad de torres nombradas (programado vs
    ejecutado). `torres_ejecutadas` (int, en `EjecucionSemanalCuadrillaAdmin`
    arriba) sigue siendo el conteo manual -- este registro es la lista
    NOMBRADA de torres y su estado, independiente de ese conteo."""

    list_display = ('torre', 'ejecucion', 'ejecutada', 'motivo_cambio')
    list_filter = (
        'ejecutada',
        'ejecucion__programacion__anio', 'ejecucion__programacion__semana',
        'ejecucion__programacion__cuadrilla',
    )
    search_fields = (
        'torre__numero',
        'ejecucion__programacion__cuadrilla__codigo',
        'motivo_cambio',
    )
    raw_id_fields = ('ejecucion', 'torre')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(AsistenciaEjecucionSemanal)
class AsistenciaEjecucionSemanalAdmin(BaseModelAdmin):
    """#270 (sub-item D): asistencia diaria por persona/día de la ejecución."""

    list_display = (
        'personal', 'fecha', 'tipo_novedad', 'horas_trabajadas', 'horas_extra',
    )
    list_filter = (
        'tipo_novedad',
        'ejecucion__programacion__anio', 'ejecucion__programacion__semana',
        'ejecucion__programacion__cuadrilla',
    )
    search_fields = (
        'personal__nombre', 'personal__documento',
        'ejecucion__programacion__cuadrilla__codigo',
    )
    raw_id_fields = ('ejecucion', 'personal')
    readonly_fields = ('id', 'created_at', 'updated_at')
