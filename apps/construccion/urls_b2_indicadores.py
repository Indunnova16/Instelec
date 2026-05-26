"""URLs B2 — Indicadores Construcción (#98).

Pattern: /construccion/<uuid:proyecto_id>/indicadores/<tipo>/...
Estos urlpatterns se agregan a `apps.construccion.urls.urlpatterns` por el
scaffolding S2 de F2.
"""
from django.urls import path

from . import views_b2_indicadores as views

urlpatterns = [
    # --- Financiero ---
    path(
        '<uuid:proyecto_id>/indicadores/financieros/',
        views.IndicadorFinancieroListView.as_view(),
        name='b2_indicador_financiero_lista',
    ),
    path(
        '<uuid:proyecto_id>/indicadores/financieros/crear/',
        views.IndicadorFinancieroCreateView.as_view(),
        name='b2_indicador_financiero_crear',
    ),
    path(
        '<uuid:proyecto_id>/indicadores/financieros/<uuid:pk>/editar/',
        views.IndicadorFinancieroUpdateView.as_view(),
        name='b2_indicador_financiero_editar',
    ),
    path(
        '<uuid:proyecto_id>/indicadores/financieros/<uuid:pk>/eliminar/',
        views.IndicadorFinancieroDeleteView.as_view(),
        name='b2_indicador_financiero_eliminar',
    ),

    # --- Técnico ---
    path(
        '<uuid:proyecto_id>/indicadores/tecnicos/',
        views.IndicadorTecnicoListView.as_view(),
        name='b2_indicador_tecnico_lista',
    ),
    path(
        '<uuid:proyecto_id>/indicadores/tecnicos/crear/',
        views.IndicadorTecnicoCreateView.as_view(),
        name='b2_indicador_tecnico_crear',
    ),
    path(
        '<uuid:proyecto_id>/indicadores/tecnicos/<uuid:pk>/editar/',
        views.IndicadorTecnicoUpdateView.as_view(),
        name='b2_indicador_tecnico_editar',
    ),
    path(
        '<uuid:proyecto_id>/indicadores/tecnicos/<uuid:pk>/eliminar/',
        views.IndicadorTecnicoDeleteView.as_view(),
        name='b2_indicador_tecnico_eliminar',
    ),

    # --- Desempeño Línea ---
    path(
        '<uuid:proyecto_id>/indicadores/desempeno/',
        views.IndicadorDesempenoListView.as_view(),
        name='b2_indicador_desempeno_lista',
    ),
    path(
        '<uuid:proyecto_id>/indicadores/desempeno/crear/',
        views.IndicadorDesempenoCreateView.as_view(),
        name='b2_indicador_desempeno_crear',
    ),
    path(
        '<uuid:proyecto_id>/indicadores/desempeno/<uuid:pk>/editar/',
        views.IndicadorDesempenoUpdateView.as_view(),
        name='b2_indicador_desempeno_editar',
    ),
    path(
        '<uuid:proyecto_id>/indicadores/desempeno/<uuid:pk>/eliminar/',
        views.IndicadorDesempenoDeleteView.as_view(),
        name='b2_indicador_desempeno_eliminar',
    ),

    # --- Recalcular on-demand ---
    path(
        '<uuid:proyecto_id>/indicadores/recalcular/',
        views.RecalcularIndicadoresView.as_view(),
        name='b2_indicadores_recalcular',
    ),
]
