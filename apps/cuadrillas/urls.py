"""
Cuadrillas URL patterns — aggregator.

Pre-block: a single list. After block `portafolio_sofi_may2026` (F2 scaffolding
S1) sub-features may declare their own urlpatterns in `urls_<sub_id>.py`. B3
adds Reactivate/filter routes; B4 adds CuadrillaUpload/DescargarPlantilla
routes. They get appended here so include('apps.cuadrillas.urls') keeps
resolving every route.
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
    path('masiva/plantilla/', views.DescargarPlantillaCuadrillasView.as_view(), name='descargar_plantilla'),
    path('mapa/', views.MapaCuadrillasView.as_view(), name='mapa'),
    path('mapa/partial/', views.MapaCuadrillasPartialView.as_view(), name='mapa_partial'),
    path('ubicaciones/json/', views.MapaCuadrillasPartialView.as_view(), name='ubicaciones_json'),
    # Colaboradores — CRUD sobre PersonalCuadrilla (issue #176, A3)
    path('colaboradores/', views.ColaboradorListView.as_view(), name='colaboradores_lista'),
    path('colaboradores/crear/', views.ColaboradorCreateView.as_view(), name='colaboradores_crear'),
    path('colaboradores/<uuid:pk>/editar/', views.ColaboradorEditView.as_view(), name='colaboradores_editar'),
    path('colaboradores/<uuid:pk>/inactivar/', views.ColaboradorInactivarView.as_view(), name='colaboradores_inactivar'),
    # Cargos — CRUD sobre Cargo, Maestro 3 (issue #176, bounce 2)
    path('cargos/', views.CargoListView.as_view(), name='cargos_lista'),
    path('cargos/crear/', views.CargoCreateView.as_view(), name='cargos_crear'),
    path('cargos/<uuid:pk>/editar/', views.CargoEditView.as_view(), name='cargos_editar'),
    path('cargos/<uuid:pk>/inactivar/', views.CargoInactivarView.as_view(), name='cargos_inactivar'),
    path('cargos/subir/', views.CargoUploadView.as_view(), name='cargos_upload'),
    path('cargos/exportar/', views.CargoExportView.as_view(), name='cargos_export'),
]

# B3 — Cuadrilla auditoria/reactivar routes. Optional import.
try:
    from . import views_b3  # noqa: F401
    urlpatterns += views_b3.urlpatterns
except ImportError:
    pass

# B4 — Carga masiva via Excel. Optional import.
try:
    from . import views_b4  # noqa: F401
    urlpatterns += views_b4.urlpatterns
except ImportError:
    pass

# #178 Sprint C — Programación semanal (grid + duplicar + export PDF). Optional import.
try:
    from . import views_semanal  # noqa: F401
    urlpatterns += views_semanal.urlpatterns
except ImportError:
    pass
