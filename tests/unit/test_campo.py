"""Unit tests for campo app."""

import re

import pytest
from datetime import timedelta
from decimal import Decimal
from django.urls import reverse
from django.utils import timezone

from apps.campo.models import RegistroCampo, Evidencia


@pytest.mark.django_db
class TestRegistroCampoModel:
    """Tests for RegistroCampo model."""

    def test_create_registro_campo(self):
        """Test creating a field record."""
        from tests.factories import RegistroCampoFactory

        registro = RegistroCampoFactory()
        assert registro.actividad is not None
        assert registro.usuario is not None
        assert registro.fecha_inicio is not None
        assert not registro.sincronizado

    def test_registro_campo_str(self):
        """Test field record string representation."""
        from tests.factories import RegistroCampoFactory

        registro = RegistroCampoFactory()
        str_repr = str(registro)
        assert "Registro" in str_repr

    def test_duracion_minutos_none_sin_fin(self):
        """Test duration is None when not finished."""
        from tests.factories import RegistroCampoFactory

        registro = RegistroCampoFactory(fecha_fin=None)
        assert registro.duracion_minutos is None

    def test_duracion_minutos_calculada(self):
        """Test duration calculation."""
        from tests.factories import RegistroCampoFactory

        inicio = timezone.now()
        fin = inicio + timedelta(hours=2, minutes=30)

        registro = RegistroCampoFactory(
            fecha_inicio=inicio,
            fecha_fin=fin,
        )
        assert registro.duracion_minutos == 150

    def test_total_evidencias(self):
        """Test evidence count property."""
        from tests.factories import (
            RegistroCampoFactory,
            EvidenciaAntesFactory,
            EvidenciaDuranteFactory,
            EvidenciaDespuesFactory,
        )

        registro = RegistroCampoFactory()
        EvidenciaAntesFactory(registro_campo=registro)
        EvidenciaDuranteFactory(registro_campo=registro)
        EvidenciaDespuesFactory(registro_campo=registro)

        assert registro.total_evidencias == 3

    def test_evidencias_completas_all_required(self):
        """Test evidence completeness check with all types required."""
        from tests.factories import (
            RegistroCampoFactory,
            EvidenciaAntesFactory,
            EvidenciaDuranteFactory,
            EvidenciaDespuesFactory,
            TipoActividadFactory,
            ActividadEnCursoFactory,
        )

        tipo = TipoActividadFactory(
            requiere_fotos_antes=True,
            requiere_fotos_durante=True,
            requiere_fotos_despues=True,
        )
        actividad = ActividadEnCursoFactory(tipo_actividad=tipo)
        registro = RegistroCampoFactory(actividad=actividad)

        # Initially incomplete
        assert not registro.evidencias_completas

        # Add all evidence types
        EvidenciaAntesFactory(registro_campo=registro)
        assert not registro.evidencias_completas

        EvidenciaDuranteFactory(registro_campo=registro)
        assert not registro.evidencias_completas

        EvidenciaDespuesFactory(registro_campo=registro)
        assert registro.evidencias_completas

    def test_evidencias_completas_partial_required(self):
        """Test evidence completeness when only some types are required."""
        from tests.factories import (
            RegistroCampoFactory,
            EvidenciaAntesFactory,
            TipoActividadFactory,
            ActividadEnCursoFactory,
        )

        tipo = TipoActividadFactory(
            requiere_fotos_antes=True,
            requiere_fotos_durante=False,
            requiere_fotos_despues=False,
        )
        actividad = ActividadEnCursoFactory(tipo_actividad=tipo)
        registro = RegistroCampoFactory(actividad=actividad)

        EvidenciaAntesFactory(registro_campo=registro)
        assert registro.evidencias_completas

    def test_datos_formulario_json(self):
        """Test form data JSON field."""
        from tests.factories import RegistroCampoFactory

        datos = {
            "observaciones": "Todo en orden",
            "metros_podados": 15.5,
            "estado_torre": "Bueno",
        }
        registro = RegistroCampoFactory(datos_formulario=datos)

        assert registro.datos_formulario["observaciones"] == "Todo en orden"
        assert registro.datos_formulario["metros_podados"] == 15.5

    def test_coordenadas_inicio(self):
        """Test start coordinates."""
        from tests.factories import RegistroCampoFactory

        registro = RegistroCampoFactory(
            latitud_inicio=Decimal("10.12345678"),
            longitud_inicio=Decimal("-74.87654321"),
        )
        assert registro.latitud_inicio == Decimal("10.12345678")
        assert registro.longitud_inicio == Decimal("-74.87654321")


@pytest.mark.django_db
class TestEvidenciaModel:
    """Tests for Evidencia model."""

    def test_create_evidencia(self):
        """Test creating evidence."""
        from tests.factories import EvidenciaFactory

        evidencia = EvidenciaFactory()
        assert evidencia.registro_campo is not None
        assert evidencia.tipo in ["ANTES", "DURANTE", "DESPUES"]
        assert evidencia.url_original

    def test_evidencia_str(self):
        """Test evidence string representation."""
        from tests.factories import EvidenciaAntesFactory

        evidencia = EvidenciaAntesFactory()
        str_repr = str(evidencia)
        assert "Antes" in str_repr

    def test_es_valida_true(self):
        """Test valid evidence detection."""
        from tests.factories import EvidenciaFactory

        evidencia = EvidenciaFactory(validacion_ia={"valida": True, "nitidez": 0.95})
        assert evidencia.es_valida

    def test_es_valida_false(self):
        """Test invalid evidence detection."""
        from tests.factories import EvidenciaFactory

        evidencia = EvidenciaFactory(validacion_ia={"valida": False, "nitidez": 0.3})
        assert not evidencia.es_valida

    def test_es_valida_default(self):
        """Test default validation when not set."""
        from tests.factories import EvidenciaFactory

        evidencia = EvidenciaFactory(validacion_ia={})
        assert evidencia.es_valida  # Default to True

    def test_puntaje_nitidez(self):
        """Test sharpness score property."""
        from tests.factories import EvidenciaFactory

        evidencia = EvidenciaFactory(validacion_ia={"nitidez": 0.87})
        assert evidencia.puntaje_nitidez == 0.87

    def test_puntaje_iluminacion(self):
        """Test lighting score property."""
        from tests.factories import EvidenciaFactory

        evidencia = EvidenciaFactory(validacion_ia={"iluminacion": 0.92})
        assert evidencia.puntaje_iluminacion == 0.92

    def test_tipos_evidencia(self):
        """Test all evidence types."""
        from tests.factories import (
            EvidenciaAntesFactory,
            EvidenciaDuranteFactory,
            EvidenciaDespuesFactory,
        )

        antes = EvidenciaAntesFactory()
        durante = EvidenciaDuranteFactory()
        despues = EvidenciaDespuesFactory()

        assert antes.tipo == "ANTES"
        assert durante.tipo == "DURANTE"
        assert despues.tipo == "DESPUES"

    def test_metadata_exif(self):
        """Test EXIF metadata storage."""
        from tests.factories import EvidenciaFactory

        metadata = {
            "make": "Samsung",
            "model": "Galaxy S23",
            "datetime": "2025-01-15 10:30:00",
            "gps": True,
            "latitude": 10.12345,
            "longitude": -74.87654,
        }
        evidencia = EvidenciaFactory(metadata_exif=metadata)

        assert evidencia.metadata_exif["make"] == "Samsung"
        assert evidencia.metadata_exif["gps"] is True


@pytest.mark.django_db
class TestCampoFactories:
    """Tests for campo factories."""

    def test_registro_campo_factory(self):
        """Test RegistroCampoFactory."""
        from tests.factories import RegistroCampoFactory

        registro = RegistroCampoFactory()
        assert registro.actividad
        assert registro.usuario
        assert registro.fecha_inicio
        assert not registro.sincronizado

    def test_registro_campo_completado_factory(self):
        """Test RegistroCampoCompletadoFactory."""
        from tests.factories import RegistroCampoCompletadoFactory

        registro = RegistroCampoCompletadoFactory()
        assert registro.fecha_fin
        assert registro.latitud_fin
        assert registro.longitud_fin
        assert registro.sincronizado

    def test_evidencia_factory(self):
        """Test EvidenciaFactory."""
        from tests.factories import EvidenciaFactory

        evidencia = EvidenciaFactory()
        assert evidencia.registro_campo
        assert evidencia.url_original
        assert evidencia.fecha_captura


# ==============================================================================
# Issue #175 — A1: link "Ver en Google Maps" con separador decimal correcto
# ==============================================================================


@pytest.mark.django_db
class TestDetalleDanoLinkGoogleMaps:
    """A1 (#175): el href del link a Google Maps debe usar punto decimal.

    Root cause: LANGUAGE_CODE='es-co' + USE_I18N=True localiza los
    DecimalField con coma en templates. Fix: `|unlocalize` solo en el href.
    """

    HREF_SIN_COMA = re.compile(r'href="https://www\.google\.com/maps\?q=-?\d+\.\d+,-?\d+\.\d+"')

    def test_href_google_maps_usa_punto_no_coma(self, client, user_password):
        """El href generado debe tener coordenadas con punto decimal, sin coma."""
        from tests.factories import ReporteDanoFactory, LinieroFactory

        usuario = LinieroFactory()
        reporte = ReporteDanoFactory(
            usuario=usuario,
            latitud=Decimal("10.99194655"),
            longitud=Decimal("-74.81943206"),
        )
        client.login(username=usuario.email, password=user_password)

        url = reverse("campo:detalle_dano", kwargs={"pk": reporte.pk})
        response = client.get(url)

        assert response.status_code == 200
        html = response.content.decode()

        # No debe existir una coma entre los dígitos decimales dentro del href.
        assert self.HREF_SIN_COMA.search(html), (
            "El href de Google Maps no matchea el patrón esperado (punto decimal, sin coma)"
        )
        assert "10,99194655,-74,81943206" not in html
        assert "q=10.99194655,-74.81943206" in html

    def test_edge_case_reporte_sin_coordenadas_no_rompe(self, client, user_password):
        """Reporte sin latitud/longitud no debe mostrar el link ni romper el render."""
        from tests.factories import ReporteDanoFactory, LinieroFactory

        usuario = LinieroFactory()
        reporte = ReporteDanoFactory(usuario=usuario, latitud=None, longitud=None)
        client.login(username=usuario.email, password=user_password)

        url = reverse("campo:detalle_dano", kwargs={"pk": reporte.pk})
        response = client.get(url)

        assert response.status_code == 200
        html = response.content.decode()
        assert "Ubicación no disponible" in html
        assert "google.com/maps" not in html


# ==============================================================================
# Issue #175 — A2: fotos rotas → placeholder defensivo "Imagen no disponible"
# ==============================================================================


@pytest.mark.django_db
class TestDetalleDanoFotoDefensiva:
    """A2 (#175): el <img> de fotos de daño debe tener manejo `onerror`
    que muestre un placeholder "Imagen no disponible" en vez de un ícono roto.

    Root cause: el único registro FotoDano en prod (FOTO_PRUEBA.png) es un
    dato de prueba huérfano sin archivo real en GCS — no reparable. El fix
    de código es defensivo, para cualquier caso futuro de subida fallida.
    """

    def test_img_tiene_atributo_onerror(self, client, user_password):
        """El <img> debe incluir el atributo onerror con el placeholder."""
        from tests.factories import ReporteDanoFactory, FotoDanoFactory, LinieroFactory

        usuario = LinieroFactory()
        reporte = ReporteDanoFactory(usuario=usuario)
        FotoDanoFactory(reporte=reporte)
        client.login(username=usuario.email, password=user_password)

        url = reverse("campo:detalle_dano", kwargs={"pk": reporte.pk})
        response = client.get(url)

        assert response.status_code == 200
        html = response.content.decode()
        assert "data-foto-imagen" in html
        assert "onerror=" in html
        assert "Imagen no disponible" in html

    def test_multiples_fotos_cada_una_maneja_su_error_independiente(self, client, user_password):
        """Con varias fotos (algunas potencialmente rotas), cada <img> debe
        tener su propio onerror independiente — no debe compartir estado."""
        from tests.factories import ReporteDanoFactory, FotoDanoFactory, LinieroFactory

        usuario = LinieroFactory()
        reporte = ReporteDanoFactory(usuario=usuario)
        FotoDanoFactory(reporte=reporte, descripcion="Foto valida")
        FotoDanoFactory(reporte=reporte, descripcion="Foto potencialmente rota")
        client.login(username=usuario.email, password=user_password)

        url = reverse("campo:detalle_dano", kwargs={"pk": reporte.pk})
        response = client.get(url)

        assert response.status_code == 200
        html = response.content.decode()
        # Dos <img data-foto-imagen>, cada uno con su propio onerror (no
        # comparten estado). Se cuentan onerror solo dentro de los <img>
        # marcados con data-foto-imagen para no contaminar con otros <img
        # onerror=...> del layout base (ej. avatar de usuario).
        foto_imgs = re.findall(r"<img[^>]*data-foto-imagen[^>]*>", html)
        assert len(foto_imgs) == 2
        assert all("onerror=" in tag for tag in foto_imgs)
        assert "Foto valida" in html
        assert "Foto potencialmente rota" in html

    def test_sin_fotos_no_muestra_seccion_fotografias(self, client, user_password):
        """Reporte sin fotos: la sección de fotografías no debe renderizarse."""
        from tests.factories import ReporteDanoFactory, LinieroFactory

        usuario = LinieroFactory()
        reporte = ReporteDanoFactory(usuario=usuario)
        client.login(username=usuario.email, password=user_password)

        url = reverse("campo:detalle_dano", kwargs={"pk": reporte.pk})
        response = client.get(url)

        assert response.status_code == 200
        html = response.content.decode()
        assert "Fotografías" not in html
