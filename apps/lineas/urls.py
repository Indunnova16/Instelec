"""
Lineas URL patterns.
"""
from django.urls import path
from . import views

app_name = 'lineas'

urlpatterns = [
    path('', views.LineaListView.as_view(), name='lista'),
    path('crear/', views.LineaCreateView.as_view(), name='crear'),
    path('<uuid:pk>/', views.LineaDetailView.as_view(), name='detalle'),
    path('<uuid:pk>/editar/', views.LineaEditView.as_view(), name='editar'),
    path('<uuid:pk>/subir-kmz/', views.LineaUploadKMZView.as_view(), name='subir_kmz'),
    path('<uuid:pk>/eliminar-kmz/', views.LineaDeleteKMZView.as_view(), name='eliminar_kmz'),
    path('<uuid:pk>/torres/', views.TorresLineaView.as_view(), name='torres'),
    path('torre/<uuid:pk>/', views.TorreDetailView.as_view(), name='torre_detalle'),
    path('mapa/', views.MapaLineasView.as_view(), name='mapa'),
    path('importar-kmz/', views.ImportarKMZView.as_view(), name='importar_kmz'),
    path('<uuid:pk>/avance/', views.AvanceLineaView.as_view(), name='avance'),
]
