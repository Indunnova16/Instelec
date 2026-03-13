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
    path('<uuid:pk>/miembros/subir/', views.CuadrillaMiembroUploadView.as_view(), name='miembros_upload'),
    path('<uuid:pk>/asistencia/', views.AsistenciaUpdateView.as_view(), name='asistencia_update'),
    path('<uuid:pk>/exportar-asistencia/', views.ExportarAsistenciaView.as_view(), name='exportar_asistencia'),
    path('personal/subir/', views.PersonalCuadrillaUploadView.as_view(), name='personal_upload'),
    path('api/personal/', views.PersonalCuadrillaListAPIView.as_view(), name='personal_list_api'),
    path('api/personal/detalle/', views.PersonalCuadrillaAPIView.as_view(), name='personal_detalle_api'),
    path('api/costo-rol/', views.CostoRolAPIView.as_view(), name='costo_rol_api'),
    path('masiva/upload/', views.CuadrillaMasivaUploadView.as_view(), name='masiva_upload'),
    path('mapa/', views.MapaCuadrillasView.as_view(), name='mapa'),
    path('mapa/partial/', views.MapaCuadrillasPartialView.as_view(), name='mapa_partial'),
    path('ubicaciones/json/', views.MapaCuadrillasPartialView.as_view(), name='ubicaciones_json'),
]
