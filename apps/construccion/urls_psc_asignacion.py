"""Rutas de asignación manual para Programación Semanal de Construcción (#225, B6)."""
from django.urls import path

from .views_psc_asignacion import (
    ProgramacionSemanalConstruccionAgregarPersonalView,
    ProgramacionSemanalConstruccionAgregarVehiculoView,
    ProgramacionSemanalConstruccionQuitarPersonalView,
    ProgramacionSemanalConstruccionQuitarVehiculoView,
)


urlpatterns = [
    path('cuadrillas/semanal/<uuid:pk>/personal/agregar/', ProgramacionSemanalConstruccionAgregarPersonalView.as_view(), name='psc_personal_agregar'),
    path('cuadrillas/semanal/<uuid:pk>/personal/<uuid:personal_pk>/quitar/', ProgramacionSemanalConstruccionQuitarPersonalView.as_view(), name='psc_personal_quitar'),
    path('cuadrillas/semanal/<uuid:pk>/vehiculos/agregar/', ProgramacionSemanalConstruccionAgregarVehiculoView.as_view(), name='psc_vehiculo_agregar'),
    path('cuadrillas/semanal/<uuid:pk>/vehiculos/<uuid:vehiculo_pk>/quitar/', ProgramacionSemanalConstruccionQuitarVehiculoView.as_view(), name='psc_vehiculo_quitar'),
]
