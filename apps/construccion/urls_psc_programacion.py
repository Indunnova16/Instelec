"""Rutas de formulario y detalle de Programación Semanal de Construcción (#225)."""
from django.urls import path

from .views_psc_programacion import (
    ProgramacionSemanalConstruccionCreateView,
    ProgramacionSemanalConstruccionDetailView,
    ProgramacionSemanalConstruccionUpdateView,
)


urlpatterns = [
    path(
        'cuadrillas/semanal/crear/',
        ProgramacionSemanalConstruccionCreateView.as_view(),
        name='psc_programacion_crear',
    ),
    path(
        'cuadrillas/semanal/<uuid:pk>/',
        ProgramacionSemanalConstruccionDetailView.as_view(),
        name='psc_programacion_detalle',
    ),
    path(
        'cuadrillas/semanal/<uuid:pk>/editar/',
        ProgramacionSemanalConstruccionUpdateView.as_view(),
        name='psc_programacion_editar',
    ),
]
