"""
B4 — URLs del dashboard de mantenimiento detallado + CRUD.

Montado en apps/indicadores/urls.py como ``urlpatterns += urls_b4.urlpatterns``.
"""
from django.urls import path

from . import views_b4

urlpatterns = [
    # Dashboard v2
    path(
        "mantenimiento-v2/",
        views_b4.DashboardMantenimientoV2View.as_view(),
        name="dashboard_mantenimiento_v2",
    ),
    # CRUD Financiero
    path(
        "mantenimiento-v2/financiero/",
        views_b4.IndicadorMantFinancieroListView.as_view(),
        name="mant_fin_list",
    ),
    path(
        "mantenimiento-v2/financiero/nuevo/",
        views_b4.IndicadorMantFinancieroCreateView.as_view(),
        name="mant_fin_create",
    ),
    path(
        "mantenimiento-v2/financiero/<uuid:pk>/editar/",
        views_b4.IndicadorMantFinancieroUpdateView.as_view(),
        name="mant_fin_update",
    ),
    # CRUD Tecnico
    path(
        "mantenimiento-v2/tecnico/",
        views_b4.IndicadorMantTecnicoListView.as_view(),
        name="mant_tec_list",
    ),
    path(
        "mantenimiento-v2/tecnico/nuevo/",
        views_b4.IndicadorMantTecnicoCreateView.as_view(),
        name="mant_tec_create",
    ),
    path(
        "mantenimiento-v2/tecnico/<uuid:pk>/editar/",
        views_b4.IndicadorMantTecnicoUpdateView.as_view(),
        name="mant_tec_update",
    ),
    # CRUD ANS
    path(
        "mantenimiento-v2/ans/",
        views_b4.IndicadorANSListView.as_view(),
        name="ans_list",
    ),
    path(
        "mantenimiento-v2/ans/nuevo/",
        views_b4.IndicadorANSCreateView.as_view(),
        name="ans_create",
    ),
    path(
        "mantenimiento-v2/ans/<uuid:pk>/editar/",
        views_b4.IndicadorANSUpdateView.as_view(),
        name="ans_update",
    ),
]
