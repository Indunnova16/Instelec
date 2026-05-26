"""URLs B3 — Dashboard Indicadores en General (#97).

Slug ``indicadores-financieros`` conservada para no romper bookmarks ni el
journey corpus existente. La vista que responde a ese path es ahora el
``DashboardIndicadoresGeneralesView`` (KPI cards + 6 gráficas Chart.js +
exportar PDF/Excel).
"""
from django.urls import path

from . import views_b3_dashboard_indicadores as views_b3


urlpatterns = [
    # Path conservado, view nueva (B3 reemplaza placeholder de F2).
    path(
        '<uuid:proyecto_id>/indicadores-financieros/',
        views_b3.DashboardIndicadoresGeneralesView.as_view(),
        name='indicadores_financieros',
    ),
]
