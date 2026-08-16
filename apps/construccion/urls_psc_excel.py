"""Rutas XLSX de Programación Semanal de Construcción (#225, B4)."""
from django.urls import path

from .views_psc_excel import (
    ProgramacionSemanalConstruccionExcelView,
    ProgramacionSemanalConstruccionExportView,
    ProgramacionSemanalConstruccionPlantillaView,
)


urlpatterns = [
    path('cuadrillas/semanal/importar/', ProgramacionSemanalConstruccionExcelView.as_view(), name='psc_importar_excel'),
    path('cuadrillas/semanal/plantilla.xlsx', ProgramacionSemanalConstruccionPlantillaView.as_view(), name='psc_plantilla_excel'),
    path('cuadrillas/semanal/exportar.xlsx', ProgramacionSemanalConstruccionExportView.as_view(), name='psc_exportar_excel'),
]
