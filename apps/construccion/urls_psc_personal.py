"""Rutas de disponibilidad de personal para Programación Semanal (#225)."""
from django.urls import path

from .views_psc_personal import PersonalDisponiblePSCView


urlpatterns = [
    path(
        'cuadrillas/semanal/personal/disponible/',
        PersonalDisponiblePSCView.as_view(),
        name='psc_personal_disponible',
    ),
]
