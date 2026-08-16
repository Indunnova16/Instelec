"""Rutas del ciclo de vida de Programación Semanal de Construcción (#225, B5)."""
from django.urls import path

from .views_psc_lifecycle import (
    ProgramacionSemanalConstruccionDeleteView,
    ProgramacionSemanalConstruccionDuplicateView,
    ProgramacionSemanalConstruccionListView,
)


urlpatterns = [
    path('cuadrillas/semanal/', ProgramacionSemanalConstruccionListView.as_view(), name='psc_programacion_lista'),
    path('cuadrillas/semanal/<uuid:pk>/duplicar/', ProgramacionSemanalConstruccionDuplicateView.as_view(), name='psc_programacion_duplicar'),
    path('cuadrillas/semanal/<uuid:pk>/eliminar/', ProgramacionSemanalConstruccionDeleteView.as_view(), name='psc_programacion_eliminar'),
]
