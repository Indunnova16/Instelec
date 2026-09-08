from django.urls import path

from .views_finv2_conciliacion_reportes import (
    DiferenciasConciliacionView,
    EstadoConciliacionView,
    ExportarConciliacionCsvView,
    HistorialConciliacionView,
)

urlpatterns = [
    path("conciliacion/estado/", EstadoConciliacionView.as_view(), name="conciliacion_estado"),
    path(
        "conciliacion/historial/",
        HistorialConciliacionView.as_view(),
        name="conciliacion_historial",
    ),
    path(
        "conciliacion/diferencias/",
        DiferenciasConciliacionView.as_view(),
        name="conciliacion_diferencias",
    ),
    path(
        "conciliacion/exportar/",
        ExportarConciliacionCsvView.as_view(),
        name="conciliacion_exportar",
    ),
]
