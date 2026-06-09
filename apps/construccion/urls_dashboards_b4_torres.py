"""B4 — URLs de la Vista por torre consolidada + drill-down (#139).

WIRING (lo aplica F4 al integrar, NO se edita ``urls.py`` desde B4):

    # apps/construccion/urls.py  — junto a los demás includes de dashboards
    from .urls_dashboards_b4_torres import urlpatterns as dashboards_b4_urls  # noqa: E402
    urlpatterns += dashboards_b4_urls

``proyecto_id`` es UUID (igual que el resto de las rutas de construccion). Las
rutas viven bajo el namespace ``construccion`` (``app_name = 'construccion'`` en
``urls.py``):

  - ``construccion:dashboard_vista_torres``      (página HTML)
  - ``construccion:dashboard_drilldown_torre``   (endpoint JSON reusable)
"""
from django.urls import path

from .views_dashboards_b4_torres import (
    DashboardVistaTorresView,
    DrilldownTorreFaseView,
)

urlpatterns = [
    path(
        '<uuid:proyecto_id>/dashboard-vista-torres/',
        DashboardVistaTorresView.as_view(),
        name='dashboard_vista_torres',
    ),
    path(
        '<uuid:proyecto_id>/dashboard-vista-torres/drilldown/',
        DrilldownTorreFaseView.as_view(),
        name='dashboard_drilldown_torre',
    ),
]
