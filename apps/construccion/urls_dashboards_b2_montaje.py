"""URLs del Dashboard de Montaje real (#139 · B2).

Partición física por sub-feature (S2): B2 escribe SOLO aquí. F4 (integración)
registra este módulo en ``urls.py`` con la línea de include documentada en el
output JSON de B2:

    from .urls_dashboards_b2_montaje import urlpatterns as dashboards_b2_urls
    urlpatterns += dashboards_b2_urls

Namespace: ``construccion:`` (app_name en urls.py).

Coexistencia con el legacy: ``urls.py`` ya define ``dashboard-montaje/`` (name
``dashboard_montaje`` → ``views.DashboardMontajeView``, basado en el semanal en
0%). B2 NO lo toca; registra rutas NUEVAS con path/name distintos para evitar
colisión:
  - ``dashboard-montaje-real/``               name ``dashboard_montaje_real``
  - ``dashboard-montaje-real/datos-graficas/`` name ``dashboard_montaje_real_datos``
"""
from django.urls import path

from .views_dashboards_b2_montaje import (
    DashboardMontajeDatosGraficasView,
    DashboardMontajeRealView,
)

urlpatterns = [
    path(
        '<uuid:proyecto_id>/dashboard-montaje-real/',
        DashboardMontajeRealView.as_view(),
        name='dashboard_montaje_real',
    ),
    path(
        '<uuid:proyecto_id>/dashboard-montaje-real/datos-graficas/',
        DashboardMontajeDatosGraficasView.as_view(),
        name='dashboard_montaje_real_datos',
    ),
]
