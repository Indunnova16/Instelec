"""Rutas del análisis comparativo de Producción Diaria (#252)."""

from django.urls import path

from apps.cuadrillas.views_produccion_diaria_analisis import ProduccionDiariaAnalisisView

urlpatterns = [
    path(
        "produccion-diaria/<uuid:pk>/analisis/",
        ProduccionDiariaAnalisisView.as_view(),
        name="produccion_diaria_analisis",
    ),
]
