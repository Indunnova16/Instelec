from django.urls import path

from .views_finv2_conciliacion import ConciliacionImportarView, MovimientosPendientesView

urlpatterns = [
    path("conciliacion/", ConciliacionImportarView.as_view(), name="conciliacion_importar"),
    path(
        "conciliacion/importar/",
        ConciliacionImportarView.as_view(),
        name="conciliacion_importar_csv",
    ),
    path(
        "conciliacion/pendientes/",
        MovimientosPendientesView.as_view(),
        name="conciliacion_pendientes",
    ),
]
