"""Rutas del workflow de carga financiera B2."""
from django.urls import path

from .views_finv2_carga import CargaFinancieraView, PlanoFinancieroCsvView


urlpatterns = [
    path('carga-financiera/', CargaFinancieraView.as_view(), name='carga_financiera'),
    path('carga-financiera/<uuid:carga_id>/plano.csv', PlanoFinancieroCsvView.as_view(), name='plano_financiero_csv'),
]
