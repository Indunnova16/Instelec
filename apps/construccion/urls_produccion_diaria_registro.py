"""Rutas B1 del registro de producción diaria (#252)."""

from django.urls import path

from apps.cuadrillas.views_produccion_diaria_registro import (
    ProduccionDiariaCreateView,
    ProduccionDiariaDetailView,
)

urlpatterns = [
    path(
        "produccion-diaria/registrar/",
        ProduccionDiariaCreateView.as_view(),
        name="produccion_diaria_registrar",
    ),
    path(
        "produccion-diaria/<uuid:pk>/",
        ProduccionDiariaDetailView.as_view(),
        name="produccion_diaria_detalle",
    ),
]
