"""B4 (#123) — URLs del Módulo Financiero de Construcción (Fase 2/5).

Las 6 rutas viven bajo ``/construccion/<uuid:proyecto_id>/financiero/<subruta>/``
y se agregan a ``apps.construccion.urls`` vía
``urlpatterns += urls_fin.urlpatterns`` (ya cableado por F2).

Namespace: ``construccion`` (app_name en urls.py). Reverse:
``construccion:fin_dashboard`` etc.
"""
from django.urls import path

from . import views_fin

urlpatterns = [
    path(
        '<uuid:proyecto_id>/financiero/dashboard/',
        views_fin.DashboardFinancieroConstruccionView.as_view(),
        name='fin_dashboard',
    ),
    path(
        '<uuid:proyecto_id>/financiero/presupuesto-planeado/',
        views_fin.PresupuestoPlaneadoConstruccionView.as_view(),
        name='fin_presupuesto_planeado',
    ),
    # #120: alias de la carga de BD contable en Construcción (espejo de la URL
    # dedicada de Mantenimiento financiero:cargar_bd_contable). La carga ya vive
    # dentro de PresupuestoPlaneadoConstruccionView (POST action=cargar_bd); la
    # ruta no estaba registrada → 404 al teclear/compartir la URL como en Mant.
    path(
        '<uuid:proyecto_id>/financiero/cargar-bd-contable/',
        views_fin.PresupuestoPlaneadoConstruccionView.as_view(),
        name='fin_cargar_bd_contable',
    ),
    path(
        '<uuid:proyecto_id>/financiero/presupuesto-real/',
        views_fin.PresupuestoRealConstruccionView.as_view(),
        name='fin_presupuesto_real',
    ),
    path(
        '<uuid:proyecto_id>/financiero/nomina/',
        views_fin.NominaConstruccionView.as_view(),
        name='fin_nomina',
    ),
    path(
        '<uuid:proyecto_id>/financiero/costos/',
        views_fin.CostosDetalladoConstruccionView.as_view(),
        name='fin_costos',
    ),
    path(
        '<uuid:proyecto_id>/financiero/facturacion/',
        views_fin.FacturacionConstruccionView.as_view(),
        name='fin_facturacion',
    ),
]
