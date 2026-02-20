"""
Admin configuration for field records.
"""
from django.contrib import admin
from django.utils.html import format_html
from apps.core.admin import BaseModelAdmin
from .models import RegistroCampo, Evidencia, ReporteDano


class EvidenciaInline(admin.TabularInline):
    model = Evidencia
    extra = 0
    fields = ('tipo', 'preview', 'fecha_captura', 'es_valida_display', 'latitud', 'longitud')
    readonly_fields = ('preview', 'es_valida_display')

    def preview(self, obj):
        if obj.url_thumbnail:
            return format_html('<img src="{}" height="60" />', obj.url_thumbnail)
        elif obj.url_original:
            return format_html('<img src="{}" height="60" />', obj.url_original)
        return '-'
    preview.short_description = 'Preview'

    def es_valida_display(self, obj):
        if obj.es_valida:
            return format_html('<span style="color: green;">✓ Válida</span>')
        return format_html('<span style="color: red;">✗ Inválida</span>')
    es_valida_display.short_description = 'Validación IA'


@admin.register(RegistroCampo)
class RegistroCampoAdmin(BaseModelAdmin):
    list_display = (
        'actividad', 'usuario', 'fecha_inicio', 'fecha_fin',
        'duracion_minutos', 'total_evidencias', 'dentro_poligono', 'sincronizado'
    )
    list_filter = ('sincronizado', 'dentro_poligono', 'fecha_inicio')
    search_fields = (
        'actividad__torre__numero',
        'actividad__linea__codigo',
        'usuario__email',
        'usuario__first_name'
    )
    raw_id_fields = ('actividad', 'usuario')
    date_hierarchy = 'fecha_inicio'
    inlines = [EvidenciaInline]

    fieldsets = (
        ('Actividad', {
            'fields': ('actividad', 'usuario')
        }),
        ('Tiempos', {
            'fields': ('fecha_inicio', 'fecha_fin')
        }),
        ('Ubicación Inicio', {
            'fields': ('latitud_inicio', 'longitud_inicio', 'dentro_poligono')
        }),
        ('Ubicación Fin', {
            'fields': ('latitud_fin', 'longitud_fin'),
            'classes': ('collapse',)
        }),
        ('Datos del formulario', {
            'fields': ('datos_formulario',)
        }),
        ('Observaciones', {
            'fields': ('observaciones', 'observaciones_audio_url', 'firma_responsable_url')
        }),
        ('Sincronización', {
            'fields': ('sincronizado', 'fecha_sincronizacion')
        }),
    )

    def duracion_minutos(self, obj):
        dur = obj.duracion_minutos
        return f"{dur} min" if dur else '-'
    duracion_minutos.short_description = 'Duración'


@admin.register(Evidencia)
class EvidenciaAdmin(BaseModelAdmin):
    list_display = ('registro_campo', 'tipo', 'fecha_captura', 'es_valida', 'preview')
    list_filter = ('tipo', 'fecha_captura')
    search_fields = ('registro_campo__actividad__torre__numero',)
    raw_id_fields = ('registro_campo',)

    def preview(self, obj):
        if obj.url_thumbnail:
            return format_html('<img src="{}" height="40" />', obj.url_thumbnail)
        return '-'
    preview.short_description = 'Preview'

    def es_valida(self, obj):
        return obj.es_valida
    es_valida.boolean = True
    es_valida.short_description = 'Válida'


@admin.register(ReporteDano)
class ReporteDanoAdmin(BaseModelAdmin):
    list_display = ('usuario', 'descripcion_corta', 'latitud', 'longitud', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('descripcion', 'usuario__email', 'usuario__first_name', 'usuario__last_name')
    raw_id_fields = ('usuario',)
    readonly_fields = ('latitud', 'longitud')

    def descripcion_corta(self, obj):
        if len(obj.descripcion) > 80:
            return obj.descripcion[:80] + '...'
        return obj.descripcion
    descripcion_corta.short_description = 'Descripción'
