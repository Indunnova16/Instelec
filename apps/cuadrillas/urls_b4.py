"""
URLs B4 — Carga masiva Cuadrillas formato Aviso SAP.

Importado vía ``try/except`` desde ``apps/cuadrillas/urls.py`` y también
re-exportado desde ``apps/cuadrillas/views_b4.py`` para que el aggregator
``urls.py`` siga funcionando con ``from . import views_b4; urlpatterns +=
views_b4.urlpatterns``.

Las rutas usan prefijo ``b4/`` para no colisionar con la vista pre-block
``CuadrillaMasivaUploadView`` (``masiva/upload/``) que sigue activa hasta
que el cliente valide B4.
"""
from django.urls import path

from .views_b4 import CuadrillaUploadView, DescargarPlantillaCuadrillasB4View

urlpatterns = [
    path('b4/upload-cuadrillas/', CuadrillaUploadView.as_view(), name='b4_upload_cuadrillas'),
    path('b4/descargar-plantilla/', DescargarPlantillaCuadrillasB4View.as_view(),
         name='b4_descargar_plantilla'),
]
