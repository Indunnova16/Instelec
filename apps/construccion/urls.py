"""
URL patterns for the construccion (construction) app.
"""
from django.urls import path
from . import views

app_name = 'construccion'

urlpatterns = [
    # Projects
    path('', views.ProyectoListView.as_view(), name='lista'),
    path('<uuid:pk>/', views.ProyectoDashboardView.as_view(), name='dashboard'),

    # Project tabs
    path('<uuid:proyecto_id>/contrato/', views.ContratoView.as_view(), name='contrato'),
    path('<uuid:proyecto_id>/ingenieria/', views.IngenieriaView.as_view(), name='ingenieria'),
    path('<uuid:proyecto_id>/preliminares/', views.PreliminaresView.as_view(), name='preliminares'),

    # Torres
    path('<uuid:proyecto_id>/torres/', views.TorresListView.as_view(), name='torres_lista'),
    path('<uuid:proyecto_id>/torres/crear/', views.TorreCreateView.as_view(), name='torre_crear'),
    path('<uuid:proyecto_id>/torres/<uuid:pk>/editar/', views.TorreEditView.as_view(), name='torre_editar'),
    path('<uuid:proyecto_id>/torres/<uuid:pk>/eliminar/', views.TorreDeleteView.as_view(), name='torre_eliminar'),

    # Seguimiento Diario
    path('<uuid:proyecto_id>/seguimiento/', views.SeguimientoDiarioView.as_view(), name='seguimiento_diario'),

    # Social Predial
    path('<uuid:proyecto_id>/social/', views.SocialPredialView.as_view(), name='social_predial'),

    # Ambiental
    path('<uuid:proyecto_id>/ambiental/', views.AmbientalView.as_view(), name='ambiental'),

    # Control de Lluvia
    path('<uuid:proyecto_id>/lluvia/', views.ControlLluviaView.as_view(), name='control_lluvia'),

    # Replanteo
    path('<uuid:proyecto_id>/replanteo/', views.ReplanteoView.as_view(), name='replanteo'),

    # SST
    path('<uuid:proyecto_id>/sst/', views.SSTView.as_view(), name='sst'),

    # Entrega
    path('<uuid:proyecto_id>/entrega/', views.EntregaView.as_view(), name='entrega'),

    # Pendientes
    path('<uuid:proyecto_id>/pendientes/', views.PendientesView.as_view(), name='pendientes'),

    # Programación
    path('<uuid:proyecto_id>/programacion/', views.ProgramacionView.as_view(), name='programacion'),

    # RS Data
    path('<uuid:proyecto_id>/rs-data/', views.RSDataView.as_view(), name='rs_data'),

    # Hochimin
    path('<uuid:proyecto_id>/hochimin/', views.HochimimView.as_view(), name='hochimin'),

    # Lectura
    path('<uuid:proyecto_id>/lectura/', views.LecturaView.as_view(), name='lectura'),

    # Entrega Flechas
    path('<uuid:proyecto_id>/entrega-flechas/', views.EntregaFlechasView.as_view(), name='entrega_flechas'),

    # Electromecánica
    path('<uuid:proyecto_id>/electromecanica/', views.ElectromecanicaView.as_view(), name='electromecanica'),
]
