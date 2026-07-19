"""
Core URL patterns.
"""
from django.urls import path
from . import views

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
]
