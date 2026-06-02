"""B3 (#123) — Admin de los 5 modelos financieros de Construcción.

Registra en el admin de Django los modelos definidos en ``models_fin.py``.

WIRING: para que Django descubra estos registros, ``apps/construccion/admin.py``
debe importar este módulo (``from .admin_fin import *  # noqa``). Esa línea vive
en ``admin.py``, que NO es FILES_OWNED de B3 — la agrega F2/F4 (ver nota emitida
por B3 al orquestador). Sin esa línea los modelos existen y migran igual, pero no
aparecen en /admin/.
"""
from django.contrib import admin

from .models_fin import (
    PresupuestoDetalladoConstruccion,
    CostosConstruccion,
    CostosActividadConstruccion,
    FacturacionConstruccion,
    IndicadorANSConstruccion,
)


@admin.register(PresupuestoDetalladoConstruccion)
class PresupuestoDetalladoConstruccionAdmin(admin.ModelAdmin):
    list_display = ['proyecto', 'anio', 'tipo', 'created_at']
    list_filter = ['tipo', 'anio']
    search_fields = ['proyecto__nombre']
    raw_id_fields = ['proyecto']


@admin.register(CostosConstruccion)
class CostosConstruccionAdmin(admin.ModelAdmin):
    list_display = ['concepto', 'proyecto', 'tipo_recurso', 'cantidad',
                    'costo_unitario', 'costo_total', 'fecha']
    list_filter = ['tipo_recurso', 'fecha']
    search_fields = ['concepto', 'proyecto__nombre']
    raw_id_fields = ['proyecto', 'actividad']
    readonly_fields = ['costo_total']
    date_hierarchy = 'fecha'


@admin.register(CostosActividadConstruccion)
class CostosActividadConstruccionAdmin(admin.ModelAdmin):
    list_display = ['actividad', 'costo_materiales', 'costo_mano_obra',
                    'costo_equipos', 'costo_subcontratos', 'costo_otros']
    raw_id_fields = ['actividad']


@admin.register(FacturacionConstruccion)
class FacturacionConstruccionAdmin(admin.ModelAdmin):
    list_display = ['numero_factura', 'proyecto', 'fecha_emision',
                    'monto_facturado', 'monto_pagado', 'estado']
    list_filter = ['estado', 'fecha_emision']
    search_fields = ['numero_factura', 'proyecto__nombre']
    raw_id_fields = ['proyecto']
    date_hierarchy = 'fecha_emision'


@admin.register(IndicadorANSConstruccion)
class IndicadorANSConstruccionAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'proyecto', 'periodo_anio', 'periodo_mes',
                    'meta_porcentaje', 'valor_actual', 'estado']
    list_filter = ['estado', 'periodo_anio', 'periodo_mes']
    search_fields = ['nombre', 'proyecto__nombre']
    raw_id_fields = ['proyecto']
    readonly_fields = ['estado']
