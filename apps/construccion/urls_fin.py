"""B4 (#123) — URLs del Módulo Financiero de Construcción (Fase 2/5).

Las 6 rutas viven bajo ``/construccion/<uuid:proyecto_id>/financiero/<subruta>/``
y se agregan a ``apps.construccion.urls`` vía
``urlpatterns += urls_fin.urlpatterns`` (ya cableado por F2).

Namespace: ``construccion`` (app_name en urls.py). Reverse:
``construccion:fin_dashboard`` etc.
"""
from django.urls import path

from apps.financiero.views import DescargarPlantillaPresupuestoPlanoView

from . import views_fin
from .reportes_gastos_real import (
    ReporteGastosRealCsvView,
    ReporteGastosRealExcelView,
    ReporteGastosRealPdfView,
)
from .reportes_presupuesto import (
    ReportePresupuestoCsvView,
    ReportePresupuestoExcelView,
    ReportePresupuestoPdfView,
    ReportePresupuestoPptView,
)

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
    # A6 (#267 Fase 1.6): plantilla XLSX descargable del formato plano
    # (Tipo|Proyecto|Rubro|Clasificacion|Valor|mes|año|ciudad) que consume
    # PresupuestoPlanoConstruccionExcelImporter (A2). Vive en
    # apps.financiero.views (junto a DescargarPlantillaExcelView) pero se
    # wirea desde Construcción -es donde vive el botón "Cargar bd" (A2/A3).
    path(
        '<uuid:proyecto_id>/financiero/plantilla-presupuesto-plano/',
        DescargarPlantillaPresupuestoPlanoView.as_view(),
        name='fin_plantilla_presupuesto_plano',
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
    # Instelec#267 A10 (Fase 5) — 4 Reportes descargables del Presupuesto
    # Planeado, gateados por formato server-side (permissions_fin.py, A7).
    # URL del CSV fijada por el journey de F2 (i267_a10_csv_contable):
    # .../presupuesto-planeado/csv/?anio=&mes= — las otras 3 siguen el mismo
    # patrón de sub-ruta bajo presupuesto-planeado/.
    path(
        '<uuid:proyecto_id>/financiero/presupuesto-planeado/pdf/',
        ReportePresupuestoPdfView.as_view(),
        name='fin_presupuesto_planeado_pdf',
    ),
    path(
        '<uuid:proyecto_id>/financiero/presupuesto-planeado/excel/',
        ReportePresupuestoExcelView.as_view(),
        name='fin_presupuesto_planeado_excel',
    ),
    path(
        '<uuid:proyecto_id>/financiero/presupuesto-planeado/csv/',
        ReportePresupuestoCsvView.as_view(),
        name='fin_presupuesto_planeado_csv',
    ),
    path(
        '<uuid:proyecto_id>/financiero/presupuesto-planeado/ppt/',
        ReportePresupuestoPptView.as_view(),
        name='fin_presupuesto_planeado_ppt',
    ),
    path(
        '<uuid:proyecto_id>/financiero/presupuesto-real/',
        views_fin.PresupuestoRealConstruccionView.as_view(),
        name='fin_presupuesto_real',
    ),
    # Instelec#268 — plantilla de carga + reportes del Presupuesto Real.
    path(
        '<uuid:proyecto_id>/financiero/presupuesto-real/plantilla/',
        views_fin.PlantillaGastosRealesView.as_view(),
        name='fin_presupuesto_real_plantilla',
    ),
    path(
        '<uuid:proyecto_id>/financiero/presupuesto-real/pdf/',
        ReporteGastosRealPdfView.as_view(),
        name='fin_presupuesto_real_pdf',
    ),
    path(
        '<uuid:proyecto_id>/financiero/presupuesto-real/excel/',
        ReporteGastosRealExcelView.as_view(),
        name='fin_presupuesto_real_excel',
    ),
    path(
        '<uuid:proyecto_id>/financiero/presupuesto-real/csv/',
        ReporteGastosRealCsvView.as_view(),
        name='fin_presupuesto_real_csv',
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
