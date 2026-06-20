"""
Financiero URL patterns.
"""
from django.urls import path
from django.views.generic import RedirectView
from . import views

app_name = 'financiero'

urlpatterns = [
    path('', views.DashboardFinancieroView.as_view(), name='dashboard'),
    path('exportar-excel/', views.ExportarDashboardExcelView.as_view(), name='exportar_excel'),
    path('cuadro-costos/', views.CuadroCostosView.as_view(), name='cuadro_costos'),
    path('facturacion/', views.FacturacionView.as_view(), name='facturacion'),
    path('costos-cuadrilla/', views.CostosCuadrillaView.as_view(), name='costos_cuadrilla'),
path('checklist-facturacion/', views.ChecklistFacturacionView.as_view(), name='checklist_facturacion'),
    path('checklist-facturacion/<uuid:pk>/toggle/', views.ToggleFacturadoView.as_view(), name='toggle_facturado'),
    path('checklist-facturacion/<uuid:pk>/detalle/', views.ChecklistDetallePartialView.as_view(), name='checklist_detalle_partial'),
    path('checklist-facturacion/<uuid:pk>/editar/', views.ChecklistEditarView.as_view(), name='checklist_editar'),
    path('checklist-facturacion/<uuid:pk>/archivos/subir/', views.ChecklistSubirArchivoView.as_view(), name='checklist_subir_archivo'),
    path('checklist-facturacion/archivo/<uuid:pk>/eliminar/', views.ChecklistEliminarArchivoView.as_view(), name='checklist_eliminar_archivo'),
    path('checklist-facturacion/periodo/archivos/subir/', views.PeriodoSubirArchivoView.as_view(), name='periodo_subir_archivo'),
    path('checklist-facturacion/periodo/archivo/<uuid:pk>/eliminar/', views.PeriodoEliminarArchivoView.as_view(), name='periodo_eliminar_archivo'),
    # #120: la pantalla vieja (filtros Unidad de Negocio/Contrato) ahora redirige
    # a la v2 de carga BD contable; query_string=True preserva params si los hay.
    path(
        'presupuesto-planeado/',
        RedirectView.as_view(
            pattern_name='financiero:cargar_bd_contable',
            permanent=False,
            query_string=True,
        ),
        name='presupuesto_planeado',
    ),
    path('presupuesto-real/', views.PresupuestoRealView.as_view(), name='presupuesto_real'),
    path('plantilla-excel/', views.DescargarPlantillaExcelView.as_view(), name='plantilla_excel'),
    path('cargar-costos-cuadrilla/', views.CargarCostosCuadrillaView.as_view(), name='cargar_costos_cuadrilla'),
    path('nomina/', views.NominaView.as_view(), name='nomina'),
]

# Financiero v2 (mapeo contable) — B1 (#120) llena urls_finv2.urlpatterns
from . import urls_finv2  # noqa
urlpatterns += urls_finv2.urlpatterns
