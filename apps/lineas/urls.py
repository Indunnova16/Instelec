"""
Lineas URL patterns — aggregator.

Pre-block: a single list. After block `portafolio_sofi_may2026` (F2 scaffolding
S1) sub-features may declare their own urlpatterns in `urls_<sub_id>.py` (B2.1
uses `views_b21.urlpatterns` exposed through that module). They get appended
here so include('apps.lineas.urls') keeps resolving every route.
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
    path('<uuid:linea_pk>/torre/crear/', views.TorreCreateView.as_view(), name='torre_crear'),
    path('<uuid:linea_pk>/torres/crear-masivas/', views.TorreMasivaCreateView.as_view(), name='torre_masiva_crear'),
    path('torre/<uuid:pk>/editar/', views.TorreEditView.as_view(), name='torre_editar'),
    path('torre/<uuid:pk>/', views.TorreDeleteView.as_view(), name='torre_eliminar'),
    path('<uuid:linea_id>/vano/crear/', views.VanoCreateView.as_view(), name='vano_crear'),
    path('vano/<uuid:pk>/editar/', views.VanoEditView.as_view(), name='vano_editar'),
    path('vano/<uuid:pk>/', views.VanoDeleteView.as_view(), name='vano_eliminar'),
    path('mapa/', views.MapaLineasView.as_view(), name='mapa'),
    path('importar-kmz/', views.ImportarKMZView.as_view(), name='importar_kmz'),
    path('<uuid:pk>/avance/', views.AvanceLineaView.as_view(), name='avance'),
    path('<uuid:pk>/hoja-de-vida/', views.HojaDeVidaLineaView.as_view(), name='hoja_de_vida'),
    path('mi-avance/', views.AvanceCampoView.as_view(), name='mi_avance'),
    path('mi-avance/<uuid:pk>/', views.AvanceCampoLineaView.as_view(), name='avance_campo_linea'),
    path('mi-avance/<uuid:pk>/marcar/', views.MarcarActividadCompletadaView.as_view(), name='marcar_actividad_completada'),
    path('api/torres/<uuid:pk>/observaciones/', views.TorreUpdateObservacionesView.as_view(), name='torre_update_observaciones'),
]

# B2.1 — Sub-feature urls. Optional import so the repo stays importable before F3
# writes views_b21.py / urls_b21.py.
try:
    from . import views_b21  # noqa: F401
    urlpatterns += views_b21.urlpatterns
except ImportError:
    pass
