from django.contrib import admin

from .models import Contrato


@admin.register(Contrato)
class ContratoAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'unidad_negocio', 'cliente', 'estado', 'fecha_inicio', 'fecha_fin')
    list_filter = ('unidad_negocio', 'estado')
    search_fields = ('codigo', 'nombre', 'cliente')
    ordering = ('unidad_negocio', 'codigo')
