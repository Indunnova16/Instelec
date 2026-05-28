"""B6 — ProcedimientoDownloadView: proxy GCS para preview sin CORS.

Issues #72 y #95. Reemplaza el acceso directo a `procedimiento.archivo.url`
(URL firmada GCS sin CORS) por un endpoint Django que:

- Valida permisos via LoginRequiredMixin + RoleRequiredMixin (mismos roles que
  ProcedimientoViewerView).
- Abre el archivo en modo binario via storage backend (django-storages GCS o
  FileSystemStorage local), de forma transparente.
- Devuelve `FileResponse` streaming con `Content-Type` inferido (MIME del modelo
  o fallback por extensión via `mimetypes`) y `Content-Disposition: inline`
  para que el navegador haga preview embebido.

Es distinto del legacy `ProcedimientoProxyView` (`/procedimientos/<pk>/proxy/`)
porque ese leía todo el archivo en memoria y solo lo usaba el viewer Excel.
B6 expone `/procedimientos/<pk>/download/` (alias semantico, sirve cualquier
tipo) y centraliza el flujo PDF + Excel + fallback descarga.
"""

from __future__ import annotations

import mimetypes
import os

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import FileResponse, Http404
from django.urls import path
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.clickjacking import xframe_options_sameorigin

from apps.core.mixins import RoleRequiredMixin

from .models import Procedimiento


@method_decorator(xframe_options_sameorigin, name='dispatch')
class ProcedimientoDownloadView(LoginRequiredMixin, RoleRequiredMixin, View):
    """Proxy view que sirve un Procedimiento via storage backend.

    - 200 con FileResponse si el usuario tiene permiso y el archivo existe.
    - 403 (PermissionDenied) si el rol no está autorizado (manejado por mixin).
    - 302 a login si no autenticado.
    - 404 si el procedimiento no existe o el archivo no está disponible.
    """

    allowed_roles = [
        'admin',
        'director',
        'coordinador',
        'ing_residente',
        'supervisor',
        'liniero',
    ]

    def _content_type_for(self, procedimiento: Procedimiento) -> str:
        """Determina Content-Type robusto.

        Orden de preferencia:
        1. `tipo_archivo` persistido en el modelo (MIME detectado en upload).
        2. `mimetypes.guess_type` sobre el nombre original (extensión).
        3. `application/octet-stream` fallback.
        """
        mime = (procedimiento.tipo_archivo or '').strip()
        if mime and '/' in mime:
            return mime
        guessed, _ = mimetypes.guess_type(procedimiento.nombre_original or '')
        return guessed or 'application/octet-stream'

    def get(self, request, pk):
        try:
            procedimiento = Procedimiento.objects.get(pk=pk)
        except Procedimiento.DoesNotExist as exc:
            raise Http404('Procedimiento no encontrado') from exc

        if not procedimiento.archivo:
            raise Http404('Archivo no disponible')

        try:
            fh = procedimiento.archivo.open('rb')
        except (FileNotFoundError, OSError) as exc:
            # archivo registrado en BD pero no presente en storage
            raise Http404('Archivo no accesible en storage') from exc

        content_type = self._content_type_for(procedimiento)

        # nombre legible para el navegador; sanitizar saltos de línea
        filename = (procedimiento.nombre_original or os.path.basename(
            procedimiento.archivo.name or 'archivo'
        )).replace('"', '').replace('\n', '').replace('\r', '')

        response = FileResponse(fh, content_type=content_type)
        # inline para que iframe/<embed>/SheetJS lo previsualicen sin forzar
        # descarga; el botón "Descargar" del template añade el atributo
        # `download` en el cliente cuando hace falta.
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        # cache hint (1h) — el archivo en sí no cambia tras upload; ayuda al
        # preview Excel que hace fetch dos veces (selector de hojas + render).
        response['Cache-Control'] = 'private, max-age=3600'
        return response


urlpatterns = [
    path(
        'procedimientos/<uuid:pk>/download/',
        ProcedimientoDownloadView.as_view(),
        name='procedimiento_download',
    ),
]
