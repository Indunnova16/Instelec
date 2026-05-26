"""B6 — Tests para ProcedimientoDownloadView (issues #72, #95).

Cobertura:
- b6_pdf_preview_via_proxy: PDF servido como FileResponse inline con
  Content-Type application/pdf.
- b6_xlsx_preview_via_proxy: XLSX servido como FileResponse inline con
  Content-Type spreadsheetml.
- b6_proxy_403_sin_login: usuario no autenticado redirige a login (302).
- edge: 404 si el procedimiento no existe.
- edge: 404 si el archivo en storage no existe.
- legacy: Procedimiento con `tipo_archivo` vacío usa fallback de mimetypes.
"""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.campo.models import Procedimiento


PDF_BYTES = b"%PDF-1.4\n%test b6 content\n%%EOF"
XLSX_BYTES = (
    b"PK\x03\x04\x14\x00\x06\x00\x08\x00b6 fake xlsx body"
)


@pytest.fixture
def admin_client(client, admin_user, user_password):
    client.login(username=admin_user.email, password=user_password)
    return client


def _crear_procedimiento(admin_user, *, nombre, content, content_type):
    archivo = SimpleUploadedFile(nombre, content, content_type=content_type)
    return Procedimiento.objects.create(
        titulo=f"Doc {nombre}",
        descripcion="Test fixture B6",
        archivo=archivo,
        nombre_original=nombre,
        tipo_archivo=content_type,
        tamanio=len(content),
        subido_por=admin_user,
    )


@pytest.mark.django_db
class TestProcedimientoDownloadViewB6:
    """ProcedimientoDownloadView — fix CORS GCS preview."""

    def test_b6_pdf_preview_via_proxy(self, admin_client, admin_user):
        proc = _crear_procedimiento(
            admin_user,
            nombre="manual_b6.pdf",
            content=PDF_BYTES,
            content_type="application/pdf",
        )
        url = reverse('campo:procedimiento_download', kwargs={'pk': proc.pk})
        resp = admin_client.get(url)

        assert resp.status_code == 200
        assert resp['Content-Type'] == 'application/pdf'
        # inline, no force download — el navegador previsualiza
        assert 'inline' in resp['Content-Disposition']
        assert 'manual_b6.pdf' in resp['Content-Disposition']
        # FileResponse streaming — contenido correcto
        body = b''.join(resp.streaming_content)
        assert body == PDF_BYTES

    def test_b6_xlsx_preview_via_proxy(self, admin_client, admin_user):
        mime_xlsx = (
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        proc = _crear_procedimiento(
            admin_user,
            nombre="plan_b6.xlsx",
            content=XLSX_BYTES,
            content_type=mime_xlsx,
        )
        url = reverse('campo:procedimiento_download', kwargs={'pk': proc.pk})
        resp = admin_client.get(url)

        assert resp.status_code == 200
        assert resp['Content-Type'] == mime_xlsx
        assert 'inline' in resp['Content-Disposition']
        body = b''.join(resp.streaming_content)
        assert body == XLSX_BYTES

    def test_b6_proxy_403_sin_login(self, client, admin_user):
        """Usuario no autenticado: LoginRequiredMixin redirige a login (302).

        Nombre histórico "403" en el blueprint — la implementación real es
        302 hacia /usuarios/login/?next=... que es el comportamiento estándar
        de LoginRequiredMixin. Lo importante: NO sirve el archivo.
        """
        proc = _crear_procedimiento(
            admin_user,
            nombre="secret.pdf",
            content=PDF_BYTES,
            content_type="application/pdf",
        )
        url = reverse('campo:procedimiento_download', kwargs={'pk': proc.pk})
        resp = client.get(url)

        # 302 → login (LoginRequiredMixin estándar Django)
        assert resp.status_code in (302, 401, 403)
        if resp.status_code == 302:
            assert '/login' in resp.url.lower() or 'login' in resp.url.lower()
        # asegurar que NO sirvió el contenido del PDF
        body_attr = getattr(resp, 'content', b'') or b''
        assert PDF_BYTES not in body_attr

    def test_b6_404_si_procedimiento_no_existe(self, admin_client):
        import uuid
        url = reverse(
            'campo:procedimiento_download',
            kwargs={'pk': uuid.uuid4()},
        )
        resp = admin_client.get(url)
        assert resp.status_code == 404

    def test_b6_content_type_fallback_por_extension(
        self, admin_client, admin_user
    ):
        """Edge case (registro legacy): tipo_archivo vacío en BD.

        Para procedimientos creados antes del bump max_length=150 que
        truncó/no guardó MIME, la view debe inferir Content-Type por
        extensión del nombre original via mimetypes.
        """
        proc = _crear_procedimiento(
            admin_user,
            nombre="legacy.pdf",
            content=PDF_BYTES,
            content_type="application/pdf",
        )
        # simular legacy: borrar MIME persistido
        proc.tipo_archivo = ''
        proc.save(update_fields=['tipo_archivo'])

        url = reverse('campo:procedimiento_download', kwargs={'pk': proc.pk})
        resp = admin_client.get(url)
        assert resp.status_code == 200
        # mimetypes mapea .pdf → application/pdf
        assert resp['Content-Type'] == 'application/pdf'

    def test_b6_404_si_archivo_borrado_del_storage(
        self, admin_client, admin_user, tmp_path, settings
    ):
        """Edge case: registro en BD pero archivo borrado del storage.

        La view debe responder 404 limpio, no 500 traceback.
        """
        proc = _crear_procedimiento(
            admin_user,
            nombre="missing.pdf",
            content=PDF_BYTES,
            content_type="application/pdf",
        )
        # apuntar el FileField a un path inexistente
        proc.archivo.name = 'campo/procedimientos/no-existe-en-storage.pdf'
        proc.save(update_fields=['archivo'])

        url = reverse('campo:procedimiento_download', kwargs={'pk': proc.pk})
        resp = admin_client.get(url)
        assert resp.status_code == 404
