"""Rutas B3 para listado, historial y alertas de Producción Diaria (#252)."""

from django.urls import path

from apps.cuadrillas.views_produccion_diaria_alertas import (
    ProduccionDiariaHistorialView,
    ProduccionDiariaListView,
)

urlpatterns = [
    path(
        "produccion-diaria/",
        ProduccionDiariaListView.as_view(),
        name="produccion_diaria_lista",
    ),
    path(
        "produccion-diaria/historial/",
        ProduccionDiariaHistorialView.as_view(),
        name="produccion_diaria_historial",
    ),
]
