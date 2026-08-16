"""
Core URL patterns.
"""
from django.urls import path
from . import views
from apps.cuadrillas import views as cuadrillas_views

app_name = 'core'

urlpatterns = [
    path('', views.HomeView.as_view(), name='home'),
    path('health/', views.health_check, name='health'),
    path('api/health/', views.health_check, name='api_health'),
    path('api/health/simple/', views.health_check_simple, name='api_health_simple'),
    path('set-unidad-negocio/', views.set_unidad_negocio_view, name='set_unidad_negocio'),
    path('presentacion/', views.PresentacionView.as_view(), name='presentacion'),
    # Roles y Permisos -- CRUD sobre Role + matriz de permisos (issue #186, A5)
    path('parametrizacion/roles/', views.RoleListView.as_view(), name='roles_lista'),
    path('parametrizacion/roles/crear/', views.RoleCreateView.as_view(), name='roles_crear'),
    path('parametrizacion/roles/<uuid:pk>/editar/', views.RoleEditView.as_view(), name='roles_editar'),
    path('parametrizacion/roles/<uuid:pk>/inactivar/', views.RoleInactivarView.as_view(), name='roles_inactivar'),
    path('parametrizacion/roles/matriz/', views.RoleModuloPermisoMatrizView.as_view(), name='roles_matriz'),
    path(
        'parametrizacion/roles/matriz/<str:role_codigo>/<str:columna>/celda/',
        views.RoleModuloPermisoCeldaView.as_view(),
        name='roles_matriz_celda',
    ),
    # El modelo se aloja en cuadrillas por sus FKs operativas, pero el maestro
    # se expone al usuario bajo Parametrización (issue #226, A2).
    path('parametrizacion/vehiculos/', cuadrillas_views.VehiculoEntryView.as_view(), name='vehiculos_lista'),
    path('parametrizacion/vehiculos/crear/', cuadrillas_views.VehiculoCreateView.as_view(), name='vehiculos_crear'),
    path('parametrizacion/vehiculos/<uuid:pk>/', cuadrillas_views.VehiculoDetailView.as_view(), name='vehiculos_detalle'),
    path('parametrizacion/vehiculos/<uuid:pk>/editar/', cuadrillas_views.VehiculoEditView.as_view(), name='vehiculos_editar'),
    path('parametrizacion/vehiculos/<uuid:pk>/estado/', cuadrillas_views.VehiculoEstadoView.as_view(), name='vehiculos_estado'),
    path('parametrizacion/vehiculos/<uuid:pk>/eliminar/', cuadrillas_views.VehiculoDeleteView.as_view(), name='vehiculos_eliminar'),
]
