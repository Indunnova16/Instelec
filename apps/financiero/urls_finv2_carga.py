"""Rutas del workflow de carga financiera B2."""
from django.urls import path

from .views_finv2_carga import CargaFinancieraView, DescargarVersionHomologacionXlsxView, PlanoFinancieroCsvView


urlpatterns = [
    path('carga-financiera/', CargaFinancieraView.as_view(), name='carga_financiera'),
    path('carga-financiera/<uuid:carga_id>/plano.csv', PlanoFinancieroCsvView.as_view(), name='plano_financiero_csv'),
    path('carga-financiera/homologacion/version/<uuid:version_id>/xlsx/', DescargarVersionHomologacionXlsxView.as_view(), name='descargar_version_homologacion_xlsx'),
]
