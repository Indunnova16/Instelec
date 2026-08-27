"""Issue #118 — hardening upload + audit command.

Cobertura:
- 118a_upload_rollback_si_storage_falla: si storage.exists() devuelve False
  tras create, la fila se borra y el form muestra error.
- 118b_upload_ok_no_borra: caso feliz, storage.exists() True → fila persiste.
- 118c_audit_marca_huerfanos: el management command actualiza blob_disponible.
- 118d_audit_dry_run_no_persiste: sin --apply, no toca BD.
"""
from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse

from apps.campo.models import Procedimiento


PDF_BYTES = b"%PDF-1.4\n%test 118 fixture\n%%EOF"


@pytest.fixture
def admin_client(client, admin_user, user_password):
    client.login(username=admin_user.email, password=user_password)
    return client


@pytest.mark.django_db
class TestProcedimientoUploadHardening118:
    """ProcedimientoCreateView debe rechazar uploads cuyo blob no aterrice."""

    def _post_upload(self, admin_client):
        archivo = SimpleUploadedFile(
            'sample.pdf', PDF_BYTES, content_type='application/pdf'
        )
        return admin_client.post(
            reverse('campo:procedimiento_crear'),
            data={
                'titulo': 'Test 118 hardening',
                'descripcion': 'Verifica rollback si storage falla',
                'archivo': archivo,
            },
        )

    def test_118a_upload_rollback_si_storage_falla(self, admin_client):
        # Simula el fallo REAL: django-storages reporta exito pero el blob nunca
        # aterriza (timeout/permisos GCS). Se parchea `_save` para que devuelva un
        # nombre valido SIN escribir el archivo -> el `exists()` de la vista da
        # False por si solo, sin mockearlo.
        #
        # NO mockear `FileSystemStorage.exists -> False` aca (id:instelec-media-root-
        # tests-bucle-infinito): ese mock rompe una invariante de Django. Si el
        # archivo destino ya existe en disco, `_save` cacha FileExistsError de
        # `os.open(O_CREAT|O_EXCL)` y pide otro nombre a `get_available_name()`,
        # que decide con `not exists(...)` -> con el mock siempre responde "libre"
        # y devuelve el MISMO nombre. `while True` infinito a ~35MB/s: 44GB de RSS
        # y la maquina tumbada. Parchear `_save` mantiene `exists()` real.
        def _save_sin_escribir(self, name, content, max_length=None):
            return self.get_available_name(name, max_length=max_length)

        with patch(
            'django.core.files.storage.FileSystemStorage._save',
            new=_save_sin_escribir,
        ):
            response = self._post_upload(admin_client)

        assert response.status_code == 200, 'Debe re-render con error, no redirect'
        assert b'No se pudo guardar el archivo' in response.content
        assert Procedimiento.objects.filter(
            titulo='Test 118 hardening'
        ).count() == 0, 'La fila huérfana debe haber sido eliminada'

    def test_118b_upload_ok_no_borra(self, admin_client):
        response = self._post_upload(admin_client)
        assert response.status_code == 302, 'Redirect tras éxito'
        assert Procedimiento.objects.filter(
            titulo='Test 118 hardening'
        ).exists()


@pytest.mark.django_db
class TestAuditCommand118:
    """Management command audit_procedimientos_storage."""

    def _crear_proc(self, admin_user, *, nombre='audit.pdf', blob_disp=True):
        archivo = SimpleUploadedFile(nombre, PDF_BYTES, content_type='application/pdf')
        return Procedimiento.objects.create(
            titulo=f'Audit fixture {nombre}',
            descripcion='audit test',
            archivo=archivo,
            nombre_original=nombre,
            tipo_archivo='application/pdf',
            tamanio=len(PDF_BYTES),
            subido_por=admin_user,
            blob_disponible=blob_disp,
        )

    def test_118c_audit_marca_huerfanos(self, admin_user):
        proc = self._crear_proc(admin_user, blob_disp=True)
        out = StringIO()
        # Forzar exists=False → debe marcar como huérfano
        with patch(
            'django.core.files.storage.FileSystemStorage.exists',
            return_value=False,
        ):
            call_command('audit_procedimientos_storage', '--apply', stdout=out)

        proc.refresh_from_db()
        assert proc.blob_disponible is False
        assert 'huérfano' in out.getvalue()

    def test_118d_audit_dry_run_no_persiste(self, admin_user):
        proc = self._crear_proc(admin_user, blob_disp=True)
        out = StringIO()
        with patch(
            'django.core.files.storage.FileSystemStorage.exists',
            return_value=False,
        ):
            call_command('audit_procedimientos_storage', stdout=out)

        proc.refresh_from_db()
        assert proc.blob_disponible is True, 'Sin --apply no debe tocar BD'
        assert 'Dry-run' in out.getvalue()

    def test_118e_audit_recupera_si_existe(self, admin_user):
        # Procedimiento marcado huérfano que aparece nuevamente en storage:
        # el audit lo "recupera" (blob_disponible=True).
        proc = self._crear_proc(admin_user, blob_disp=False)
        out = StringIO()
        with patch(
            'django.core.files.storage.FileSystemStorage.exists',
            return_value=True,
        ):
            call_command('audit_procedimientos_storage', '--apply', stdout=out)

        proc.refresh_from_db()
        assert proc.blob_disponible is True
        assert 'recuperado' in out.getvalue()
