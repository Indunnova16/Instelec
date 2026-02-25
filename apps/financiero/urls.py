"""
Financiero URL patterns.
"""
from django.urls import path
from . import views

app_name = 'financiero'

urlpatterns = [
    path('', views.DashboardFinancieroView.as_view(), name='dashboard'),
    path('exportar-excel/', views.ExportarDashboardExcelView.as_view(), name='exportar_excel'),
    path('presupuestos/', views.PresupuestoListView.as_view(), name='presupuestos'),
    path('presupuestos/crear/', views.PresupuestoCreateView.as_view(), name='presupuesto_crear'),
    path('presupuesto/<uuid:pk>/', views.PresupuestoDetailView.as_view(), name='presupuesto_detalle'),
    path('presupuesto/<uuid:pk>/editar/', views.PresupuestoUpdateView.as_view(), name='presupuesto_editar'),
    path('cuadro-costos/', views.CuadroCostosView.as_view(), name='cuadro_costos'),
    path('facturacion/', views.FacturacionView.as_view(), name='facturacion'),
    path('costos-cuadrilla/', views.CostosCuadrillaView.as_view(), name='costos_cuadrilla'),
    path('costos-vs-produccion/', views.CostosVsProduccionDashboardView.as_view(), name='costos_vs_produccion'),
    path('api/costos-vs-produccion/', views.CostosVsProduccionAPIView.as_view(), name='api_costos_vs_produccion'),
    path('checklist-facturacion/', views.ChecklistFacturacionView.as_view(), name='checklist_facturacion'),
    path('checklist-facturacion/<uuid:pk>/toggle/', views.ToggleFacturadoView.as_view(), name='toggle_facturado'),
    path('checklist-facturacion/<uuid:pk>/detalle/', views.ChecklistDetallePartialView.as_view(), name='checklist_detalle_partial'),
    path('checklist-facturacion/<uuid:pk>/editar/', views.ChecklistEditarView.as_view(), name='checklist_editar'),
    path('checklist-facturacion/<uuid:pk>/archivos/subir/', views.ChecklistSubirArchivoView.as_view(), name='checklist_subir_archivo'),
    path('checklist-facturacion/archivo/<uuid:pk>/eliminar/', views.ChecklistEliminarArchivoView.as_view(), name='checklist_eliminar_archivo'),
    path('checklist-facturacion/periodo/archivos/subir/', views.PeriodoSubirArchivoView.as_view(), name='periodo_subir_archivo'),
    path('checklist-facturacion/periodo/archivo/<uuid:pk>/eliminar/', views.PeriodoEliminarArchivoView.as_view(), name='periodo_eliminar_archivo'),
]
