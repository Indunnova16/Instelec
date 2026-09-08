from django.urls import path

from .views_finv2_flujo_caja import (
    ExportarFlujoCajaCsvView,
    FlujoCajaAlertasView,
    FlujoCajaCalendarioView,
    FlujoCajaDashboardView,
    FlujoCajaEscenariosView,
)

urlpatterns = [
    path("flujo-caja/", FlujoCajaDashboardView.as_view(), name="flujo_caja_dashboard"),
    path("flujo-caja/calendario/", FlujoCajaCalendarioView.as_view(), name="flujo_caja_calendario"),
    path("flujo-caja/escenarios/", FlujoCajaEscenariosView.as_view(), name="flujo_caja_escenarios"),
    path("flujo-caja/alertas/", FlujoCajaAlertasView.as_view(), name="flujo_caja_alertas"),
    path("flujo-caja/exportar/", ExportarFlujoCajaCsvView.as_view(), name="flujo_caja_exportar"),
]
