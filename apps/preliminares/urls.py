from django.urls import path
from . import views

app_name = 'preliminares'

urlpatterns = [
    path('', views.PreliminaresSeleccionarView.as_view(), name='seleccionar'),
    # Predial
    path('<uuid:contrato_id>/predial/',   views.PreliminaresPreDialView.as_view(),     name='predial'),
    path('<uuid:contrato_id>/campo/',     views.ActualizarCampoPredialView.as_view(),  name='campo'),
    # Ambiental
    path('<uuid:contrato_id>/ambiental/',       views.PreliminaresAmbientalView.as_view(),       name='ambiental'),
    path('<uuid:contrato_id>/campo-ambiental/', views.ActualizarCampoAmbientalView.as_view(),   name='campo_ambiental'),
]
