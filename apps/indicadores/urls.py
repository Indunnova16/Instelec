"""
Indicadores URL patterns.
"""
from django.urls import path
from . import views

app_name = 'indicadores'

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('mantenimiento/', views.DashboardMantenimientoView.as_view(), name='dashboard_mantenimiento'),
    path('mantenimiento/export-xlsx/', views.ExportarDashboardMantenimientoExcelView.as_view(), name='dashboard_mantenimiento_xlsx'),
    path('detalle/<uuid:pk>/', views.IndicadorDetailView.as_view(), name='detalle'),
    path('actas/', views.ActaListView.as_view(), name='actas'),
    path('acta/<uuid:pk>/', views.ActaDetailView.as_view(), name='acta_detalle'),
]

# === /modulo indicadores_construccion_sub_run_a — split de archivo magnet ===
# F2 scaffolding agregó este aggregator. B4 plantará urlpatterns de
# /indicadores/mantenimiento-v2/* en urls_b4.py.
from . import urls_b4

urlpatterns += urls_b4.urlpatterns
