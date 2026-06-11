"""
Admin de Programación / Ejecución semanal de cuadrillas (B5, #155).

Registra los 2 modelos de `models_pc` en el Django admin. Se importa desde
`apps/cuadrillas/admin.py` vía el aggregator add-only (`try: from .admin_pc
import *`) que dejó el scaffolding S1, para no tocar el `admin.py` monolítico.

- `ProgramacionSemanalCuadrilla`: lista por cuadrilla / año / semana, con la
  ejecución 1:1 editable inline (torres ejecutadas + rendimiento de solo
  lectura).
- `EjecucionSemanalCuadrilla`: registro propio con el rendimiento derivado
  expuesto como columna calculada de solo lectura.
"""
from django.contrib import admin

from apps.core.admin import BaseModelAdmin

from .models_pc import EjecucionSemanalCuadrilla, ProgramacionSemanalCuadrilla


class EjecucionSemanalInline(admin.StackedInline):
    """Ejecución 1:1 editable desde el detalle de la programación."""

    model = EjecucionSemanalCuadrilla
    extra = 0
    fields = ('torres_ejecutadas', 'rendimiento_pct_display', 'observaciones')
    readonly_fields = ('rendimiento_pct_display',)

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
    list_display = ('programacion', 'torres_ejecutadas', 'rendimiento_display')
    list_filter = ('programacion__anio', 'programacion__semana', 'programacion__cuadrilla')
    search_fields = (
        'programacion__cuadrilla__codigo',
        'programacion__cuadrilla__nombre',
        'observaciones',
    )
    raw_id_fields = ('programacion',)

    fieldsets = (
        (None, {
            'fields': ('programacion', 'torres_ejecutadas', 'rendimiento_display')
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
