"""
Cuadrillas URL patterns.
"""
from django.urls import path
from . import views

app_name = 'cuadrillas'

urlpatterns = [
    path('', views.CuadrillaListView.as_view(), name='lista'),
    path('crear/', views.CuadrillaCreateView.as_view(), name='crear'),
    path('<uuid:pk>/', views.CuadrillaDetailView.as_view(), name='detalle'),
    path('<uuid:pk>/editar/', views.CuadrillaEditView.as_view(), name='editar'),
    path('<uuid:pk>/miembro/agregar/', views.CuadrillaMiembroAddView.as_view(), name='miembro_agregar'),
    path('<uuid:pk>/miembro/<uuid:miembro_pk>/eliminar/', views.CuadrillaMiembroRemoveView.as_view(), name='miembro_eliminar'),
    path('mapa/', views.MapaCuadrillasView.as_view(), name='mapa'),
    path('mapa/partial/', views.MapaCuadrillasPartialView.as_view(), name='mapa_partial'),
    path('ubicaciones/json/', views.MapaCuadrillasPartialView.as_view(), name='ubicaciones_json'),
]
