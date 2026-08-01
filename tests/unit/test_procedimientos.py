"""Tests for Procedimientos upload + viewer (issue #72)."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.campo.models import Procedimiento

PDF_BYTES = b"%PDF-1.4\n%test\n"
XLSX_BYTES = b"PK\x03\x04test xlsx payload"
XLS_BYTES = b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1test xls payload"
JPG_BYTES = b"\xff\xd8\xff\xe0jpeg payload"


@pytest.fixture
def upload_url():
    return reverse("campo:procedimiento_crear")


@pytest.fixture
def admin_client(client, admin_user, user_password):
    client.login(username=admin_user.email, password=user_password)
    return client


@pytest.mark.django_db
class TestProcedimientoUploadMime:
    """Issue #72: solo se aceptan pdf/xls/xlsx con MIME válido."""

    def test_upload_pdf_aceptado(self, admin_client, upload_url):
        archivo = SimpleUploadedFile(
            "manual.pdf", PDF_BYTES, content_type="application/pdf"
        )
        resp = admin_client.post(
            upload_url,
            {"titulo": "Manual PDF", "descripcion": "", "archivo": archivo},
        )
        assert resp.status_code == 302
        assert Procedimiento.objects.filter(titulo="Manual PDF").exists()

    def test_upload_xlsx_aceptado(self, admin_client, upload_url):
        archivo = SimpleUploadedFile(
            "plan.xlsx",
            XLSX_BYTES,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp = admin_client.post(
            upload_url,
            {"titulo": "Plan XLSX", "descripcion": "", "archivo": archivo},
        )
        assert resp.status_code == 302
        assert Procedimiento.objects.filter(titulo="Plan XLSX").exists()

    def test_upload_xls_aceptado(self, admin_client, upload_url):
        archivo = SimpleUploadedFile(
            "plan.xls", XLS_BYTES, content_type="application/vnd.ms-excel"
        )
        resp = admin_client.post(
            upload_url,
            {"titulo": "Plan XLS", "descripcion": "", "archivo": archivo},
        )
        assert resp.status_code == 302
        assert Procedimiento.objects.filter(titulo="Plan XLS").exists()

    def test_upload_jpg_rechazado(self, admin_client, upload_url):
        archivo = SimpleUploadedFile(
            "foto.jpg", JPG_BYTES, content_type="image/jpeg"
        )
        resp = admin_client.post(
            upload_url,
            {"titulo": "Foto JPG", "descripcion": "", "archivo": archivo},
        )
        assert resp.status_code == 200
        assert b"Solo se aceptan archivos PDF, XLS, XLSX o DOCX" in resp.content
        assert not Procedimiento.objects.filter(titulo="Foto JPG").exists()

    def test_upload_docx_aceptado(self, admin_client, upload_url):
        """Issue #179: .docx con MIME oficial debe aceptarse (antes se rechazaba)."""
        archivo = SimpleUploadedFile(
            "doc.docx",
            b"PKtest docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        resp = admin_client.post(
            upload_url,
            {"titulo": "DOCX", "descripcion": "", "archivo": archivo},
        )
        assert resp.status_code == 302
        assert Procedimiento.objects.filter(titulo="DOCX").exists()

    def test_upload_pdf_con_mime_spoofeado_rechazado(self, admin_client, upload_url):
        """Extensión .pdf pero MIME image/jpeg → rechaza por MIME whitelist."""
        archivo = SimpleUploadedFile(
            "fake.pdf", JPG_BYTES, content_type="image/jpeg"
        )
        resp = admin_client.post(
            upload_url,
            {"titulo": "Fake PDF", "descripcion": "", "archivo": archivo},
        )
        assert resp.status_code == 200
        assert not Procedimiento.objects.filter(titulo="Fake PDF").exists()

    def test_upload_docx_con_mime_spoofeado_rechazado(self, admin_client, upload_url):
        """Issue #179: extensión .docx pero MIME image/jpeg → sigue rechazando
        (agregar .docx a la whitelist de extensión no debe debilitar el chequeo
        de MIME real; mismo patrón que test_upload_pdf_con_mime_spoofeado_rechazado)."""
        archivo = SimpleUploadedFile(
            "fake.docx", JPG_BYTES, content_type="image/jpeg"
        )
        resp = admin_client.post(
            upload_url,
            {"titulo": "Fake DOCX", "descripcion": "", "archivo": archivo},
        )
        assert resp.status_code == 200
        assert not Procedimiento.objects.filter(titulo="Fake DOCX").exists()


@pytest.mark.django_db
class TestProcedimientoCategoria:
    """Issue #24 (ampliación 2026-07-31): "Procedimientos" padre con 2
    categorías hijas (Guía de Mantenimiento / Ficha Técnica), mismo módulo
    técnico — solo se agrega la clasificación al subir y al listar."""

    def test_default_categoria_es_guia_mantenimiento(self, admin_user):
        """Registros creados sin categoría explícita (legacy / API antigua)
        caen en Guía de Mantenimiento por default del modelo."""
        archivo = SimpleUploadedFile("legacy.pdf", PDF_BYTES, content_type="application/pdf")
        p = Procedimiento.objects.create(
            titulo="Legacy sin categoría",
            archivo=archivo,
            nombre_original="legacy.pdf",
            tipo_archivo="application/pdf",
            tamanio=len(PDF_BYTES),
            subido_por=admin_user,
        )
        assert p.categoria == Procedimiento.CATEGORIA_GUIA_MANTENIMIENTO
        assert p.get_categoria_display() == "Guía de Mantenimiento"

    def test_upload_con_categoria_ficha_tecnica(self, admin_client, upload_url):
        archivo = SimpleUploadedFile("gafas.pdf", PDF_BYTES, content_type="application/pdf")
        resp = admin_client.post(
            upload_url,
            {
                "titulo": "Gafas oscuras — especificaciones",
                "descripcion": "",
                "categoria": Procedimiento.CATEGORIA_FICHA_TECNICA,
                "archivo": archivo,
            },
        )
        assert resp.status_code == 302
        proc = Procedimiento.objects.get(titulo="Gafas oscuras — especificaciones")
        assert proc.categoria == Procedimiento.CATEGORIA_FICHA_TECNICA

    def test_upload_con_categoria_guia_mantenimiento(self, admin_client, upload_url):
        archivo = SimpleUploadedFile("cadena.pdf", PDF_BYTES, content_type="application/pdf")
        resp = admin_client.post(
            upload_url,
            {
                "titulo": "Cambio de cadena",
                "descripcion": "",
                "categoria": Procedimiento.CATEGORIA_GUIA_MANTENIMIENTO,
                "archivo": archivo,
            },
        )
        assert resp.status_code == 302
        proc = Procedimiento.objects.get(titulo="Cambio de cadena")
        assert proc.categoria == Procedimiento.CATEGORIA_GUIA_MANTENIMIENTO

    def test_upload_sin_categoria_cae_a_default(self, admin_client, upload_url):
        """Si el POST no manda categoria (integraciones viejas), no se
        rechaza el upload — cae al default del modelo."""
        archivo = SimpleUploadedFile("sin_cat.pdf", PDF_BYTES, content_type="application/pdf")
        resp = admin_client.post(
            upload_url,
            {"titulo": "Sin categoría en el POST", "descripcion": "", "archivo": archivo},
        )
        assert resp.status_code == 302
        proc = Procedimiento.objects.get(titulo="Sin categoría en el POST")
        assert proc.categoria == Procedimiento.CATEGORIA_GUIA_MANTENIMIENTO

    def test_upload_con_categoria_invalida_cae_a_default(self, admin_client, upload_url):
        archivo = SimpleUploadedFile("cat_rara.pdf", PDF_BYTES, content_type="application/pdf")
        resp = admin_client.post(
            upload_url,
            {
                "titulo": "Categoría inválida",
                "descripcion": "",
                "categoria": "no-existe",
                "archivo": archivo,
            },
        )
        assert resp.status_code == 302
        proc = Procedimiento.objects.get(titulo="Categoría inválida")
        assert proc.categoria == Procedimiento.CATEGORIA_GUIA_MANTENIMIENTO

    def test_crear_form_expone_categoria_choices(self, admin_client, upload_url):
        resp = admin_client.get(upload_url)
        assert resp.status_code == 200
        assert resp.context["categoria_choices"] == Procedimiento.CATEGORIA_CHOICES
        assert b"Gu\xc3\xada de Mantenimiento" in resp.content
        assert b"Ficha T\xc3\xa9cnica" in resp.content

    def test_listado_filtra_por_categoria_guia(self, admin_client, admin_user):
        Procedimiento.objects.create(
            titulo="Guía A",
            categoria=Procedimiento.CATEGORIA_GUIA_MANTENIMIENTO,
            archivo=SimpleUploadedFile("a.pdf", PDF_BYTES, content_type="application/pdf"),
            nombre_original="a.pdf",
            tipo_archivo="application/pdf",
            tamanio=len(PDF_BYTES),
            subido_por=admin_user,
        )
        Procedimiento.objects.create(
            titulo="Ficha B",
            categoria=Procedimiento.CATEGORIA_FICHA_TECNICA,
            archivo=SimpleUploadedFile("b.pdf", PDF_BYTES, content_type="application/pdf"),
            nombre_original="b.pdf",
            tipo_archivo="application/pdf",
            tamanio=len(PDF_BYTES),
            subido_por=admin_user,
        )

        resp = admin_client.get(
            reverse("campo:procedimientos"),
            {"categoria": Procedimiento.CATEGORIA_GUIA_MANTENIMIENTO},
        )
        assert resp.status_code == 200
        titulos = [p.titulo for p in resp.context["procedimientos"]]
        assert "Guía A" in titulos
        assert "Ficha B" not in titulos

    def test_listado_filtra_por_categoria_ficha(self, admin_client, admin_user):
        Procedimiento.objects.create(
            titulo="Guía C",
            categoria=Procedimiento.CATEGORIA_GUIA_MANTENIMIENTO,
            archivo=SimpleUploadedFile("c.pdf", PDF_BYTES, content_type="application/pdf"),
            nombre_original="c.pdf",
            tipo_archivo="application/pdf",
            tamanio=len(PDF_BYTES),
            subido_por=admin_user,
        )
        Procedimiento.objects.create(
            titulo="Ficha D",
            categoria=Procedimiento.CATEGORIA_FICHA_TECNICA,
            archivo=SimpleUploadedFile("d.pdf", PDF_BYTES, content_type="application/pdf"),
            nombre_original="d.pdf",
            tipo_archivo="application/pdf",
            tamanio=len(PDF_BYTES),
            subido_por=admin_user,
        )

        resp = admin_client.get(
            reverse("campo:procedimientos"),
            {"categoria": Procedimiento.CATEGORIA_FICHA_TECNICA},
        )
        assert resp.status_code == 200
        titulos = [p.titulo for p in resp.context["procedimientos"]]
        assert "Ficha D" in titulos
        assert "Guía C" not in titulos

    def test_listado_sin_filtro_muestra_todas_las_categorias(self, admin_client, admin_user):
        Procedimiento.objects.create(
            titulo="Guía E",
            categoria=Procedimiento.CATEGORIA_GUIA_MANTENIMIENTO,
            archivo=SimpleUploadedFile("e.pdf", PDF_BYTES, content_type="application/pdf"),
            nombre_original="e.pdf",
            tipo_archivo="application/pdf",
            tamanio=len(PDF_BYTES),
            subido_por=admin_user,
        )
        Procedimiento.objects.create(
            titulo="Ficha F",
            categoria=Procedimiento.CATEGORIA_FICHA_TECNICA,
            archivo=SimpleUploadedFile("f.pdf", PDF_BYTES, content_type="application/pdf"),
            nombre_original="f.pdf",
            tipo_archivo="application/pdf",
            tamanio=len(PDF_BYTES),
            subido_por=admin_user,
        )

        resp = admin_client.get(reverse("campo:procedimientos"))
        assert resp.status_code == 200
        titulos = [p.titulo for p in resp.context["procedimientos"]]
        assert "Guía E" in titulos
        assert "Ficha F" in titulos
        assert resp.context["conteo_guias"] >= 1
        assert resp.context["conteo_fichas"] >= 1
        assert resp.context["conteo_total"] >= 2

    def test_listado_ignora_categoria_invalida_en_querystring(self, admin_client, admin_user):
        """Un valor de categoría no reconocido en el querystring no debe
        tumbar el listado — se ignora el filtro y se muestra todo."""
        Procedimiento.objects.create(
            titulo="Guía G",
            categoria=Procedimiento.CATEGORIA_GUIA_MANTENIMIENTO,
            archivo=SimpleUploadedFile("g.pdf", PDF_BYTES, content_type="application/pdf"),
            nombre_original="g.pdf",
            tipo_archivo="application/pdf",
            tamanio=len(PDF_BYTES),
            subido_por=admin_user,
        )
        resp = admin_client.get(reverse("campo:procedimientos"), {"categoria": "no-existe"})
        assert resp.status_code == 200
        titulos = [p.titulo for p in resp.context["procedimientos"]]
        assert "Guía G" in titulos


@pytest.mark.django_db
class TestProcedimientoModelProperties:
    """Issue #72: model expone es_pdf y es_excel."""

    def _crear(self, nombre, admin_user):
        archivo = SimpleUploadedFile(nombre, b"x", content_type="application/octet-stream")
        return Procedimiento.objects.create(
            titulo=f"P {nombre}",
            archivo=archivo,
            nombre_original=nombre,
            tipo_archivo="",
            tamanio=1,
            subido_por=admin_user,
        )

    def test_es_pdf_true(self, admin_user):
        p = self._crear("manual.pdf", admin_user)
        assert p.es_pdf is True
        assert p.es_excel is False

    def test_es_excel_xlsx(self, admin_user):
        p = self._crear("plan.xlsx", admin_user)
        assert p.es_excel is True
        assert p.es_pdf is False

    def test_es_excel_xls(self, admin_user):
        p = self._crear("plan.xls", admin_user)
        assert p.es_excel is True

    def test_otros_formatos_no_son_excel_ni_pdf(self, admin_user):
        p = self._crear("foto.jpg", admin_user)
        assert p.es_pdf is False
        assert p.es_excel is False

    def test_es_word_docx(self, admin_user):
        """Issue #179: model expone es_word para extensión .docx."""
        p = self._crear("procedimiento.docx", admin_user)
        assert p.es_word is True
        assert p.es_pdf is False
        assert p.es_excel is False

    def test_otros_formatos_no_son_word(self, admin_user):
        p = self._crear("foto.jpg", admin_user)
        assert p.es_word is False


@pytest.mark.django_db
class TestProcedimientoViewerContext:
    """Issue #72: viewer template recibe es_pdf, es_excel, url_archivo."""

    def test_viewer_pdf_context(self, admin_client, admin_user):
        archivo = SimpleUploadedFile("doc.pdf", PDF_BYTES, content_type="application/pdf")
        p = Procedimiento.objects.create(
            titulo="Doc PDF",
            archivo=archivo,
            nombre_original="doc.pdf",
            tipo_archivo="application/pdf",
            tamanio=len(PDF_BYTES),
            subido_por=admin_user,
        )
        resp = admin_client.get(
            reverse("campo:procedimiento_viewer", kwargs={"pk": p.pk})
        )
        assert resp.status_code == 200
        assert resp.context["es_pdf"] is True
        assert resp.context["es_excel"] is False
        assert resp.context["url_archivo"]

    def test_viewer_xlsx_context_carga_sheetjs(self, admin_client, admin_user):
        archivo = SimpleUploadedFile(
            "plan.xlsx",
            XLSX_BYTES,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        p = Procedimiento.objects.create(
            titulo="Plan XLSX",
            archivo=archivo,
            nombre_original="plan.xlsx",
            tipo_archivo="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            tamanio=len(XLSX_BYTES),
            subido_por=admin_user,
        )
        resp = admin_client.get(
            reverse("campo:procedimiento_viewer", kwargs={"pk": p.pk})
        )
        assert resp.status_code == 200
        assert resp.context["es_pdf"] is False
        assert resp.context["es_excel"] is True
        # El template debe inyectar SheetJS para Excel.
        assert b"sheetjs" in resp.content.lower() or b"xlsx.full.min.js" in resp.content

    def test_viewer_docx_context_carga_mammoth(self, admin_client, admin_user):
        """Issue #179: viewer debe exponer es_word=True y renderizar preview
        real del .docx (mammoth.js), no solo el fallback de descarga."""
        archivo = SimpleUploadedFile(
            "manual.docx",
            b"PKtest docx payload",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        p = Procedimiento.objects.create(
            titulo="Manual DOCX",
            archivo=archivo,
            nombre_original="manual.docx",
            tipo_archivo="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            tamanio=len(b"PKtest docx payload"),
            subido_por=admin_user,
        )
        resp = admin_client.get(
            reverse("campo:procedimiento_viewer", kwargs={"pk": p.pk})
        )
        assert resp.status_code == 200
        assert resp.context["es_pdf"] is False
        assert resp.context["es_excel"] is False
        assert resp.context["es_word"] is True
        # El template debe inyectar mammoth.js y el contenedor esperado por el
        # journey E2E (#docx-html-container), no el fallback genérico.
        assert b"mammoth" in resp.content.lower()
        assert b"docx-html-container" in resp.content
        assert b"Vista previa no disponible" not in resp.content
