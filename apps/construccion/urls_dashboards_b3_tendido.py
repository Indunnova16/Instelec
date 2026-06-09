"""URLs del Dashboard de Tendido (Conductor + Fibra OPGW) — B3 (#139).

WIRING (lo agrega F4 en ``apps/construccion/urls.py``, NO este archivo):

    from .urls_dashboards_b3_tendido import urlpatterns as dashboards_b3_urls
    urlpatterns += dashboards_b3_urls

Namespace ``construccion:`` (heredado del ``app_name`` de ``urls.py``). Los
nombres ``dashboard_tendido`` / ``dashboard_tendido_datos`` siguen la convención
de los dashboards existentes (``dashboard_obra_civil`` / ``dashboard_graficas_data``).
"""
from django.urls import path

from .views_dashboards_b3_tendido import (
    DashboardTendidoDataView,
    DashboardTendidoView,
)

urlpatterns = [
    path(
        '<uuid:proyecto_id>/dashboard-tendido/',
        DashboardTendidoView.as_view(),
        name='dashboard_tendido',
    ),
    path(
        '<uuid:proyecto_id>/dashboard-tendido/datos-graficas/',
        DashboardTendidoDataView.as_view(),
        name='dashboard_tendido_datos',
    ),
]
