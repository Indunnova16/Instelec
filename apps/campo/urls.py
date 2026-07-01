"""
Campo URL patterns — aggregator.

Pre-block: a single list. After block `portafolio_sofi_may2026` (F2 scaffolding
S1) sub-features may declare their own urlpatterns in `urls_<sub_id>.py`. B6
exposes ProcedimientoDownloadView/proxy via views_b6.urlpatterns. They get
appended here so include('apps.campo.urls') keeps resolving every route.
"""
from django.urls import path
from . import views

app_name = 'campo'

urlpatterns = [
    path('', views.RegistroListView.as_view(), name='lista'),
    path('registros/', views.RegistroListView.as_view(), name='registros'),
    path('crear/', views.RegistroCreateView.as_view(), name='crear'),
    path('<uuid:pk>/', views.RegistroDetailView.as_view(), name='detalle'),
    path('<uuid:pk>/evidencias/', views.EvidenciasView.as_view(), name='evidencias'),
    path('reportar-dano/', views.ReportarDanoCreateView.as_view(), name='reportar_dano'),
    path('reportes-dano/', views.ReportesDanoListView.as_view(), name='reportes_dano'),
    path('reportes-dano/mapa/', views.ReportesDanoMapaView.as_view(), name='reportes_dano_mapa'),
    path('reportes-dano/mapa/data/', views.ReportesDanoMapaPartialView.as_view(), name='reportes_dano_mapa_data'),
    path('reportes-dano/<uuid:pk>/', views.ReporteDanoDetailView.as_view(), name='detalle_dano'),
    path('procedimientos/', views.ProcedimientoListView.as_view(), name='procedimientos'),
    path('procedimientos/crear/', views.ProcedimientoCreateView.as_view(), name='procedimiento_crear'),
    path('procedimientos/<uuid:pk>/', views.ProcedimientoViewerView.as_view(), name='procedimiento_viewer'),
    path('procedimientos/<uuid:pk>/proxy/', views.ProcedimientoProxyView.as_view(), name='procedimiento_proxy'),
    # Avances de vanos - Agregado 1 abril 2026
    path('avances/', views.AvancesCuadrillaView.as_view(), name='avances_cuadrilla'),
    path('vanos/<uuid:vano_id>/marcar/', views.MarcarVanoView.as_view(), name='marcar_vano'),
    path('vanos/<uuid:pk>/estado/', views.VanoEstadoUpdateView.as_view(), name='vano_estado'),
    path('vanos/<uuid:vano_id>/pendientes/', views.PendienteVanoCreateView.as_view(), name='pendiente_crear'),
    path('pendientes/<uuid:pendiente_id>/toggle/', views.PendienteVanoToggleView.as_view(), name='pendiente_toggle'),
    # Registro de avances - Agregado 13 abril 2026
    path('avance/registrar/', views.RegistroAvanceCreateView.as_view(), name='avance_registrar'),
    path('mis-avances/', views.MisAvancesListView.as_view(), name='mis_avances'),
]

# B6 — ProcedimientoDownloadView proxy GCS (fix CORS preview). Optional import.
try:
    from . import views_b6  # noqa: F401
    urlpatterns += views_b6.urlpatterns
except ImportError:
    pass
