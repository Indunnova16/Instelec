"""
Admin configuration for construccion app.
"""
from django.contrib import admin
from .models import (
    ProyectoConstruccion,
    TorreConstruccion,
    PataObra,
    FaseTorre,
    SocialPredial,
    AmbientalTorre,
    ControlLluvia,
    ReporteReplanteo,
    PersonalSST,
    EntregaElectromecanica,
    CorreccionEntrega,
)


@admin.register(ProyectoConstruccion)
class ProyectoConstruccionAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'contrato', 'estado', 'porcentaje_avance_civil']
    list_filter = ['estado', 'created_at']
    search_fields = ['nombre', 'contrato__codigo']


@admin.register(TorreConstruccion)
class TorreConstruccionAdmin(admin.ModelAdmin):
    list_display = ['numero', 'proyecto', 'tipo', 'tipo_cimentacion', 'peso_kg']
    list_filter = ['proyecto', 'tipo_cimentacion']
    search_fields = ['numero', 'proyecto__nombre']


@admin.register(PataObra)
class PataObraAdmin(admin.ModelAdmin):
    list_display = ['torre', 'pata', 'liberacion_arqueologica_ok', 'excavacion_ok', 'vaciado_ok']
    list_filter = ['pata', 'liberacion_arqueologica_ok', 'excavacion_ok']
    search_fields = ['torre__numero']


@admin.register(FaseTorre)
class FaseTorreAdmin(admin.ModelAdmin):
    list_display = ['torre', 'proyecto', 'pct_montaje', 'pct_tendido']
    list_filter = ['proyecto']
    search_fields = ['torre__numero']


@admin.register(SocialPredial)
class SocialPredialAdmin(admin.ModelAdmin):
    list_display = ['torre', 'propietario', 'semaforo']
    list_filter = ['semaforo']
    search_fields = ['torre__numero', 'propietario']


@admin.register(AmbientalTorre)
class AmbientalTorreAdmin(admin.ModelAdmin):
    list_display = ['torre', 'semaforo']
    list_filter = ['semaforo']
    search_fields = ['torre__numero']


@admin.register(ControlLluvia)
class ControlLluviaAdmin(admin.ModelAdmin):
    list_display = ['torre', 'fecha', 'duracion_horas']
    list_filter = ['fecha']
    search_fields = ['torre__numero']


@admin.register(ReporteReplanteo)
class ReporteReplanteoAdmin(admin.ModelAdmin):
    list_display = ['proyecto', 'fecha_ejecutado', 'torres_ejecutadas']
    list_filter = ['proyecto', 'fecha_ejecutado']


@admin.register(PersonalSST)
class PersonalSSTAdmin(admin.ModelAdmin):
    list_display = ['nombre_completo', 'proyecto', 'cargo', 'estado_sylogi']
    list_filter = ['proyecto', 'cargo', 'estado_sylogi']
    search_fields = ['nombre_completo']


@admin.register(EntregaElectromecanica)
class EntregaElectromecanicaAdmin(admin.ModelAdmin):
    list_display = ['torre', 'estado', 'firma_hmv', 'firma_wsp']
    list_filter = ['estado', 'firma_hmv', 'firma_wsp']
    search_fields = ['torre__numero']


@admin.register(CorreccionEntrega)
class CorreccionEntregaAdmin(admin.ModelAdmin):
    list_display = ['torre', 'avance_correccion', 'firma_hmv']
    list_filter = ['firma_hmv']
    search_fields = ['torre__numero']
