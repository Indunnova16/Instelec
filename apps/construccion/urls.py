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
]
