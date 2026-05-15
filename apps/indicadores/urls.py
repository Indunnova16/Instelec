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
