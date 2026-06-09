"""B5 (#139) — URLs del Dashboard GENERAL del proyecto (7 fases).

Archivo dedicado de la sub-feature B5 (no toca ``urls.py`` ni
``urls_dashboards.py`` — son de otros owners).

WIRING que F4 debe agregar a ``apps/construccion/urls.py`` (junto al resto de
los includes de dashboards, cerca de ``urls_dashboards``)::

    from .urls_dashboards_b5_general import urlpatterns as dashboards_b5_urls  # noqa: E402
    urlpatterns += dashboards_b5_urls

El name resultante es ``construccion:dashboard_general`` (el app_name de
``urls.py`` es ``construccion``).
"""
from django.urls import path

from .views_dashboards_b5_general import DashboardGeneralView

urlpatterns = [
    path(
        '<uuid:proyecto_id>/dashboard-general/',
        DashboardGeneralView.as_view(),
        name='dashboard_general',
    ),
]
