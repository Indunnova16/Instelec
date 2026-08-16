"""Rutas de aprobación de personal para Programación Semanal (#225)."""
from django.urls import path

from .views_psc_aprobaciones import AprobacionPersonalProyectoView


urlpatterns = [
    path(
        'cuadrillas/semanal/aprobaciones/',
        AprobacionPersonalProyectoView.as_view(),
        name='psc_aprobaciones_personal',
    ),
]
