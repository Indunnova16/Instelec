"""Issue #177 — Tests para 3 ajustes del módulo de Avance de Vanos.

Cobertura:
1. VanoEstadoUpdateView.post persiste `observaciones` (ya existía, sigue
   funcionando) y ahora también `foto` cuando viene en request.FILES.
2. Vano.Estado.EN_ESPERA y AvanceVano.Estado.EN_ESPERA exponen el label
   'Parcial' (manteniendo el value interno 'en_espera' sin tocar datos
   legacy ya guardados con ese value).
3. Sanity check: el datalabels plugin de Chart.js está cableado en el
   template de avance_registrar (CDN + Chart.register + options.plugins).
"""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.campo.models import AvanceVano
from apps.lineas.models import Linea, Vano


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf"
    b"\xc0\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def admin_client(client, admin_user, user_password):
    client.login(username=admin_user.email, password=user_password)
    return client


@pytest.fixture
def vano(linea):
    """Vano legacy preexistente (sin foto/observaciones), igual al dato real."""
    return Vano.objects.create(linea=linea, numero="12")


@pytest.mark.django_db
class TestVanoEstadoUpdateViewIssue177:
    """Sub-ítem 1: nota + foto opcional al cambiar estado de un Vano."""

    def test_persiste_observaciones_sin_foto(self, admin_client, admin_user, vano):
        """Ya funcionaba antes del fix — debe seguir pasando (no regresión)."""
        url = reverse('campo:vano_estado', kwargs={'pk': vano.pk})
        resp = admin_client.post(url, {
            'estado': Vano.Estado.SIN_PERMISO,
            'observaciones': 'Acceso restringido por el predio.',
        })

        assert resp.status_code == 200
        vano.refresh_from_db()
        assert vano.estado == Vano.Estado.SIN_PERMISO
        assert vano.observaciones == 'Acceso restringido por el predio.'
        assert vano.marcado_por_id == admin_user.id

    def test_persiste_foto_cuando_viene_en_files(self, admin_client, vano):
        """Nuevo: si se envía un archivo `foto`, se guarda en Vano.foto."""
        foto = SimpleUploadedFile('vano12.png', PNG_BYTES, content_type='image/png')
        url = reverse('campo:vano_estado', kwargs={'pk': vano.pk})
        resp = admin_client.post(url, {
            'estado': Vano.Estado.NO_EJECUTADO,
            'observaciones': 'No se pudo ejecutar por clima.',
            'foto': foto,
        })

        assert resp.status_code == 200
        vano.refresh_from_db()
        assert vano.estado == Vano.Estado.NO_EJECUTADO
        assert vano.observaciones == 'No se pudo ejecutar por clima.'
        assert bool(vano.foto)
        assert vano.foto.name.startswith('campo/vanos/')

    def test_sin_foto_no_borra_foto_existente(self, admin_client, vano):
        """Si no llega `foto` en el POST, no se debe tocar el campo (no error)."""
        vano.foto = SimpleUploadedFile('previa.png', PNG_BYTES, content_type='image/png')
        vano.save()
        nombre_previo = vano.foto.name

        url = reverse('campo:vano_estado', kwargs={'pk': vano.pk})
        resp = admin_client.post(url, {'estado': Vano.Estado.EJECUTADO})

        assert resp.status_code == 200
        vano.refresh_from_db()
        assert vano.foto.name == nombre_previo

    def test_registro_legacy_sin_foto_ni_observaciones_sigue_funcionando(self, admin_client, vano):
        """Vano pre-existente (sin foto/observaciones, como en datos reales) —
        cambiar su estado sin enviar los campos opcionales no debe romper."""
        assert not vano.foto
        assert vano.observaciones == ''

        url = reverse('campo:vano_estado', kwargs={'pk': vano.pk})
        resp = admin_client.post(url, {'estado': Vano.Estado.EN_ESPERA})

        assert resp.status_code == 200
        vano.refresh_from_db()
        assert vano.estado == 'en_espera'


@pytest.mark.django_db
class TestEstadoLabelParcialIssue177:
    """Sub-ítem 2: rename de label 'En Espera' -> 'Parcial' (value intacto)."""

    def test_vano_estado_en_espera_label_es_parcial(self):
        assert Vano.Estado.EN_ESPERA.label == 'Parcial'
        assert Vano.Estado.EN_ESPERA.value == 'en_espera'

    def test_avancevano_estado_en_espera_label_es_parcial(self):
        assert AvanceVano.Estado.EN_ESPERA.label == 'Parcial'
        assert AvanceVano.Estado.EN_ESPERA.value == 'en_espera'

    def test_vano_legacy_con_value_en_espera_muestra_parcial(self, linea):
        """Dato legacy guardado con value='en_espera' (antes del rename) debe
        mostrar el nuevo label 'Parcial' vía get_estado_display, sin migrar datos."""
        vano = Vano.objects.create(linea=linea, numero="7", estado='en_espera')
        assert vano.get_estado_display() == 'Parcial'


class TestAvanceRegistrarDatalabelsIssue177:
    """Sub-ítem 3: datalabels del doughnut — sanity check del template."""

    def test_template_incluye_plugin_y_registro(self):
        with open('templates/campo/avance_registrar.html', encoding='utf-8') as f:
            contenido = f.read()

        assert 'chartjs-plugin-datalabels' in contenido
        assert 'Chart.register(ChartDataLabels)' in contenido
        assert 'datalabels:' in contenido
        assert "'Parcial'" in contenido
        assert "'En Espera'" not in contenido
