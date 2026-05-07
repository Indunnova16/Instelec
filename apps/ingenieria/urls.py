from django.urls import path
from . import views

app_name = 'ingenieria'

urlpatterns = [
    path('', views.IngenieriaSeleccionarView.as_view(), name='seleccionar'),
    path('<uuid:contrato_id>/civil/', views.IngenieriaCivilView.as_view(), name='civil'),
    path('<uuid:contrato_id>/montaje/', views.IngenieriaMontajeView.as_view(), name='montaje'),
    path('<uuid:contrato_id>/tendido/', views.IngenieriaTendidoView.as_view(), name='tendido'),
    path('<uuid:contrato_id>/estado/', views.ActualizarEstadoView.as_view(), name='estado'),
    path('<uuid:contrato_id>/observacion/', views.GuardarObservacionView.as_view(), name='observacion'),
]
