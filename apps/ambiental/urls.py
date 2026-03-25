"""
Ambiental URL patterns.
"""
from django.urls import path
from . import views

app_name = 'ambiental'

urlpatterns = [
    path('', views.InformeListView.as_view(), name='lista'),
    path('informe/<uuid:pk>/', views.InformeDetailView.as_view(), name='detalle'),
    path('informe/<uuid:pk>/generar/', views.GenerarInformeView.as_view(), name='generar'),
    path('permisos/', views.PermisoListView.as_view(), name='permisos'),
    path('consolidado/', views.ConsolidadoView.as_view(), name='consolidado'),
    path('consolidado/crear-informe/', views.CrearInformeDesdeConsolidadoView.as_view(), name='crear_informe_consolidado'),
    path('consolidado/exportar/', views.ExportarConsolidadoView.as_view(), name='exportar_consolidado'),
]
