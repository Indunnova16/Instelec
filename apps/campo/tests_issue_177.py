"""Issue #177 — Tests del endpoint/modal de historial de estado de Vanos.

Reescrito completo (sub-item A11) sobre el archivo original (3 tests de
``VanoEstadoUpdateView``, ya eliminada) — reconstruido de forma incremental
a medida que A4..A9 se implementaron en este mismo sprint, no en un único
paso al final; A11 cierra con esta pasada de coherencia + confirmación
100% verde.

Cobertura (app `campo` — los tests de modelos/migración de `lineas` viven en
``apps/lineas/tests/test_issue_177.py``, ver nota de scope más abajo):

- ``TestVanoHistorialCreateView`` (A4, ENTREGABLE #1 — root cause fix del
  bounce): reemplaza al viejo ``VanoEstadoUpdateView``. Happy path, escenario
  EXACTO de los logs (2 POST consecutivos sin pérdida de datos), estado
  inválido, 'no_ejecutado' rechazado, sin permiso, admin_general OK, tope de
  5 fotos, vano legacy post-backfill.
- ``TestAvanceRegistrarModalRenderIssue177`` (A6/A7): smoke de renderizado
  end-to-end vía ``Client.get`` real (no solo ``get_context_data`` como
  B1.2) — confirma el contrato de selectores completo en el HTML servido y
  que no quedó ninguna referencia colgante a la URL 'vano_estado' eliminada.
- ``TestVanoHistorialListPartialView`` (A5): listado ordenado -fecha, fotos
  0..N por registro, 403 sin acceso, empty state.
- ``TestEstadoLabelParcialIssue177``: regresión del rename 'En Espera' ->
  'Parcial' de un issue previo — sigue válido, no se toca acá.
- ``TestAvanceRegistrarDatalabelsIssue177`` + ``TestAvanceRegistrarContexto
  SeccionadoEspecial`` (A8): Stats Row + donut a 6 categorías, contexto de
  vista correcto, datalabels plugin (Ajuste 3 / A10) intacto.
- ``TestSeedDataVanosIssue177`` (A9): verificación explícita de que
  ``seed_data.py`` no rompe con las 7 choices nuevas.

Nota de scope: los tests de ``Vano.Estado`` (7 choices/seleccionables()),
``VanoHistorialEstado``/``VanoHistorialFoto`` (creación/orden) y el backfill
(migración 0016) viven en ``apps/lineas/tests/test_issue_177.py`` — son
modelos de la app `lineas`, y ese archivo no colisiona con otros issues del
mismo RUN (Instelec#179 toca `apps/campo`, Instelec#182 toca otros archivos
de `apps/lineas`). El journey E2E (``SPRINTS/RUN_2026-07-03_0800/journeys/
Instelec_177.yaml``) ya fue entregado por F2 y no se modifica acá — corre
vía F5 (``run_e2e_or_die.py``) contra la revisión promovida.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.campo.models import AvanceVano
from apps.lineas.models import Vano, VanoHistorialEstado

User = get_user_model()


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
class TestVanoHistorialCreateView:
    """A4 — root cause fix del bounce (ENTREGABLE #1 del DoD).

    Reemplaza VanoEstadoUpdateView. Cada POST crea una fila NUEVA de
    historial (append-only) — nunca sobreescribe una anterior.
    """

    def test_happy_path_estado_nota_2_fotos(self, admin_client, admin_user, vano):
        url = reverse('campo:vano_historial_crear', kwargs={'pk': vano.pk})
        foto1 = SimpleUploadedFile('f1.png', PNG_BYTES, content_type='image/png')
        foto2 = SimpleUploadedFile('f2.png', PNG_BYTES, content_type='image/png')

        resp = admin_client.post(url, {
            'estado': Vano.Estado.EJECUTADO,
            'nota': 'Trabajo terminado.',
            'fotos': [foto1, foto2],
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data['ok'] is True
        assert data['fotos_guardadas'] == 2

        vano.refresh_from_db()
        assert vano.estado == Vano.Estado.EJECUTADO
        assert vano.marcado_por_id == admin_user.id

        historial = vano.historial.get()
        assert historial.nota == 'Trabajo terminado.'
        assert historial.fotos.count() == 2

    def test_escenario_exacto_logs_2_posts_consecutivos_ninguno_se_pierde(self, admin_client, vano):
        """Reproduce el escenario EXACTO confirmado por logs Cloud Run
        (gcloud logging read, ventana 2026-07-01T13:38-13:39Z): 2 POST sobre
        el mismo vano en <10s, cada uno con su propia nota. El bug original
        perdía la nota del primer intento al reabrir el dropdown — acá
        ambos deben quedar en el historial, ninguno sobreescribe al otro."""
        url = reverse('campo:vano_historial_crear', kwargs={'pk': vano.pk})
        foto = SimpleUploadedFile('primero.png', PNG_BYTES, content_type='image/png')

        resp1 = admin_client.post(url, {
            'estado': Vano.Estado.SIN_PERMISO,
            'nota': 'Primer intento — con foto.',
            'fotos': [foto],
        })
        assert resp1.status_code == 200

        resp2 = admin_client.post(url, {
            'estado': Vano.Estado.EJECUTADO,
            'nota': '',
        })
        assert resp2.status_code == 200

        vano.refresh_from_db()
        historial = list(vano.historial.order_by('fecha'))
        assert len(historial) == 2
        assert historial[0].estado == Vano.Estado.SIN_PERMISO
        assert historial[0].nota == 'Primer intento — con foto.'
        assert historial[0].fotos.count() == 1  # el primero SIGUE con su foto
        assert historial[1].estado == Vano.Estado.EJECUTADO
        assert historial[1].nota == ''
        # El estado "actual" denormalizado refleja el ÚLTIMO cambio.
        assert vano.estado == Vano.Estado.EJECUTADO

    def test_estado_invalido_400(self, admin_client, vano):
        url = reverse('campo:vano_historial_crear', kwargs={'pk': vano.pk})
        resp = admin_client.post(url, {'estado': 'no-existe', 'nota': ''})
        assert resp.status_code == 400
        assert vano.historial.count() == 0

    def test_no_ejecutado_ya_no_es_seleccionable_400(self, admin_client, vano):
        """'no_ejecutado' sigue siendo un choice válido del modelo (dato
        legacy) pero ya NO es seleccionable desde el modal nuevo."""
        url = reverse('campo:vano_historial_crear', kwargs={'pk': vano.pk})
        resp = admin_client.post(url, {'estado': Vano.Estado.NO_EJECUTADO, 'nota': ''})
        assert resp.status_code == 400
        assert vano.historial.count() == 0

    def test_sin_permiso_403(self, client, liniero_user, user_password, vano):
        """Usuario de campo sin membresía en una cuadrilla de la línea del vano."""
        client.login(username=liniero_user.email, password=user_password)
        url = reverse('campo:vano_historial_crear', kwargs={'pk': vano.pk})
        resp = client.post(url, {'estado': Vano.Estado.EJECUTADO, 'nota': ''})
        assert resp.status_code == 403
        assert vano.historial.count() == 0

    def test_admin_general_si_tiene_acceso(self, client, user_password, vano):
        """Regresión del bug latente: admin_general (RBAC v2 #44) SÍ puede
        acceder — el VanoEstadoUpdateView original NO lo permitía."""
        admin_general = User.objects.create_user(
            email='admingeneral@test.com',
            password=user_password,
            first_name='Admin',
            last_name='General',
            rol='admin_general',
        )
        client.login(username=admin_general.email, password=user_password)
        url = reverse('campo:vano_historial_crear', kwargs={'pk': vano.pk})
        resp = client.post(url, {'estado': Vano.Estado.EJECUTADO, 'nota': ''})
        assert resp.status_code == 200

    def test_tope_5_fotos_de_6_enviadas(self, admin_client, vano):
        url = reverse('campo:vano_historial_crear', kwargs={'pk': vano.pk})
        fotos = [
            SimpleUploadedFile(f'f{i}.png', PNG_BYTES, content_type='image/png')
            for i in range(6)
        ]
        resp = admin_client.post(url, {
            'estado': Vano.Estado.EJECUTADO,
            'nota': '',
            'fotos': fotos,
        })
        assert resp.status_code == 200
        assert resp.json()['fotos_guardadas'] == 5
        assert vano.historial.get().fotos.count() == 5

    def test_vano_legacy_post_backfill_acepta_nuevo_cambio(self, admin_client, linea):
        """Vano legacy con 1 fila de historial "backfill" (simulada) — un
        cambio nuevo vía el endpoint no rompe ni sobreescribe el backfill."""
        vano_legacy = Vano.objects.create(
            linea=linea, numero='999', estado=Vano.Estado.NO_EJECUTADO
        )
        backfill_row = VanoHistorialEstado.objects.create(
            vano=vano_legacy, estado=Vano.Estado.NO_EJECUTADO, nota=''
        )

        url = reverse('campo:vano_historial_crear', kwargs={'pk': vano_legacy.pk})
        resp = admin_client.post(url, {
            'estado': Vano.Estado.PENDIENTE,
            'nota': 'Reclasificado por campo.',
        })

        assert resp.status_code == 200
        vano_legacy.refresh_from_db()
        assert vano_legacy.estado == Vano.Estado.PENDIENTE
        assert vano_legacy.historial.count() == 2
        backfill_row.refresh_from_db()
        assert backfill_row.estado == 'no_ejecutado'  # el backfill sigue intacto


@pytest.mark.django_db
class TestAvanceRegistrarModalRenderIssue177:
    """A6/A7 — smoke de renderizado end-to-end: el modal + su contrato de
    selectores aparecen en el HTML real servido por RegistroAvanceCreateView
    (no solo en tests aislados de get_context_data, como B1.2)."""

    def test_grid_renderiza_modal_con_contrato_de_selectores(self, admin_client, linea):
        Vano.objects.create(linea=linea, numero='1')
        Vano.objects.create(linea=linea, numero='2', estado=Vano.Estado.SECCIONADO)

        url = reverse('campo:avance_registrar')
        resp = admin_client.get(url, {'linea_id': str(linea.id)})

        assert resp.status_code == 200
        content = resp.content.decode()

        # Contrato de selectores obligatorio (journey E2E Instelec_177.yaml).
        assert content.count('data-testid="vano-estado-modal-root"') == 2  # 1 por vano
        assert 'data-testid="vano-estado-modal-save"' in content
        assert '<select name="estado"' in content
        assert '<textarea name="nota"' in content
        assert 'name="fotos"' in content and 'multiple' in content
        # La función JS se define UNA sola vez (forloop.first), no 2 veces.
        assert content.count('function vanoEstadoModal(') == 1
        # El dropdown/endpoint viejo ya no existe en el HTML servido —
        # ('Cambiar estado' SÍ aparece, pero como encabezado del modal
        # nuevo: "Cambiar estado — Vano N", no como el botón viejo).
        assert 'vano_estado' not in content
        assert 'Cambiar estado — Vano' in content
        assert 'showMenu' not in content

    def test_grid_no_referencia_url_vano_estado_eliminada(self, admin_client, linea):
        """Regresión directa del riesgo documentado: si vano_cuadro.html
        quedara con `{% url 'campo:vano_estado' %}` colgante, esto reventaría
        con NoReverseMatch al renderizar — este test lo hubiera atrapado."""
        Vano.objects.create(linea=linea, numero='1')
        url = reverse('campo:avance_registrar')
        resp = admin_client.get(url, {'linea_id': str(linea.id)})
        assert resp.status_code == 200  # no 500 por NoReverseMatch


@pytest.mark.django_db
class TestVanoHistorialListPartialView:
    """A5 — listado del historial completo de un Vano."""

    def test_get_devuelve_historial_ordenado_desc_por_fecha(self, admin_client, admin_user, vano):
        h1 = VanoHistorialEstado.objects.create(
            vano=vano, usuario=admin_user, estado=Vano.Estado.PENDIENTE, nota='Primero.'
        )
        h2 = VanoHistorialEstado.objects.create(
            vano=vano, usuario=admin_user, estado=Vano.Estado.EJECUTADO, nota='Segundo.'
        )

        url = reverse('campo:vano_historial_lista', kwargs={'pk': vano.pk})
        resp = admin_client.get(url)

        assert resp.status_code == 200
        content = resp.content.decode()
        assert 'data-testid="vano-historial-list"' in content
        # El más reciente (h2) aparece antes que el más viejo (h1) en el HTML.
        assert content.index('Segundo.') < content.index('Primero.')
        assert str(h1.id) or str(h2.id)  # sanity — ids existen

    def test_incluye_fotos_de_cada_registro_no_solo_la_primera(self, admin_client, admin_user, vano):
        h1 = VanoHistorialEstado.objects.create(
            vano=vano, usuario=admin_user, estado=Vano.Estado.SIN_PERMISO, nota=''
        )
        from apps.lineas.models import VanoHistorialFoto

        VanoHistorialFoto.objects.create(historial=h1, imagen='campo/vanos/historial/x1.jpg')
        h2 = VanoHistorialEstado.objects.create(
            vano=vano, usuario=admin_user, estado=Vano.Estado.EJECUTADO, nota=''
        )
        VanoHistorialFoto.objects.create(historial=h2, imagen='campo/vanos/historial/y1.jpg')
        VanoHistorialFoto.objects.create(historial=h2, imagen='campo/vanos/historial/y2.jpg')

        url = reverse('campo:vano_historial_lista', kwargs={'pk': vano.pk})
        resp = admin_client.get(url)

        content = resp.content.decode()
        assert 'x1.jpg' in content
        assert 'y1.jpg' in content
        assert 'y2.jpg' in content  # 0..N fotos, no solo la primera de cada registro

    def test_403_para_usuario_sin_acceso_a_la_linea(self, client, liniero_user, user_password, vano):
        client.login(username=liniero_user.email, password=user_password)
        url = reverse('campo:vano_historial_lista', kwargs={'pk': vano.pk})
        resp = client.get(url)
        assert resp.status_code == 403

    def test_vano_sin_historial_muestra_empty_state(self, admin_client, vano):
        url = reverse('campo:vano_historial_lista', kwargs={'pk': vano.pk})
        resp = admin_client.get(url)
        assert resp.status_code == 200
        assert 'Aún no hay cambios de estado' in resp.content.decode()


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
    """A8 — Stats Row + donut a 6 categorías. Incluye el sanity check
    original del datalabels plugin (A10 — Ajuste 3, no se toca su mecánica)."""

    def test_template_incluye_plugin_y_registro(self):
        with open('templates/campo/avance_registrar.html', encoding='utf-8') as f:
            contenido = f.read()

        assert 'chartjs-plugin-datalabels' in contenido
        assert 'Chart.register(ChartDataLabels)' in contenido
        assert 'datalabels:' in contenido
        assert "'Parcial'" in contenido
        assert "'En Espera'" not in contenido

    def test_template_donut_tiene_6_categorias_sin_no_ejecutado(self):
        """A8: 'Seccionado'/'Especial' presentes en las labels del donut;
        'No Ejecutado' retirado del RESUMEN (dato legacy no se cuenta,
        PLAN.md Decisión HITL #1 — la card individual del vano legacy
        sigue mostrando su propio label, eso no vive en este archivo)."""
        with open('templates/campo/avance_registrar.html', encoding='utf-8') as f:
            contenido = f.read()

        assert "'Seccionado'" in contenido
        assert "'Especial'" in contenido
        assert "labels: ['Pendiente', 'Ejecutado', 'Sin Permiso', 'Parcial', 'Seccionado', 'Especial']" in contenido
        assert "'No Ejecutado'" not in contenido
        assert 'vanos_seccionados' in contenido
        assert 'vanos_especiales' in contenido
        assert 'vanos_no_ejecutado' not in contenido


@pytest.mark.django_db
class TestSeedDataVanosIssue177:
    """A9 — verificación (sin cambio de código esperado): seed_data.py
    itera Vano.Estado.choices dinámicamente, se adapta solo a las 7
    choices nuevas. Se ejercita _create_vanos() directo (no el comando
    completo, que crea usuarios/cuadrillas/etc. fuera de scope de este
    test) contra un fixture propio con torres reales."""

    def test_create_vanos_no_rompe_con_7_choices(self, linea):
        from apps.core.management.commands.seed_data import Command
        from apps.lineas.models import Torre, Vano
        from tests.factories import TorreFactory

        for _ in range(5):
            TorreFactory(linea=linea)

        cmd = Command()
        cmd.stdout = __import__('io').StringIO()
        cmd.lineas = {linea.codigo: linea}
        cmd._create_vanos()  # no debe lanzar excepción

        creados = Vano.objects.filter(linea=linea)
        assert creados.count() == 4  # 5 torres -> 4 vanos consecutivos
        estados_usados = set(creados.values_list('estado', flat=True))
        # Todos los estados usados deben ser choices válidas de las 7.
        assert estados_usados.issubset({v for v, _ in Vano.Estado.choices})


@pytest.mark.django_db
class TestAvanceRegistrarContextoSeccionadoEspecial:
    """A8: contexto de RegistroAvanceCreateView expone vanos_seccionados /
    vanos_especiales correctos para una línea con vanos en esos 2 estados."""

    def test_context_vanos_seccionados_y_especiales(self, admin_client, linea):
        Vano.objects.create(linea=linea, numero='1', estado=Vano.Estado.SECCIONADO)
        Vano.objects.create(linea=linea, numero='2', estado=Vano.Estado.SECCIONADO)
        Vano.objects.create(linea=linea, numero='3', estado=Vano.Estado.ESPECIAL)
        Vano.objects.create(linea=linea, numero='4', estado=Vano.Estado.PENDIENTE)

        url = reverse('campo:avance_registrar')
        resp = admin_client.get(url, {'linea_id': str(linea.id)})

        assert resp.status_code == 200
        assert resp.context['vanos_seccionados'] == 2
        assert resp.context['vanos_especiales'] == 1
        assert resp.context['total_vanos'] == 4

    def test_vano_legacy_no_ejecutado_no_se_cuenta_en_ninguna_categoria(self, admin_client, linea):
        """Decisión HITL #1: el vano legacy no aparece en el resumen de 6
        categorías (no se migra su dato), pero SÍ cuenta en total_vanos."""
        Vano.objects.create(linea=linea, numero='15', estado=Vano.Estado.NO_EJECUTADO)
        Vano.objects.create(linea=linea, numero='16', estado=Vano.Estado.PENDIENTE)

        url = reverse('campo:avance_registrar')
        resp = admin_client.get(url, {'linea_id': str(linea.id)})

        assert resp.status_code == 200
        assert resp.context['total_vanos'] == 2  # cuenta TODOS los vanos
        assert resp.context['vanos_pendientes'] == 1
        suma_6_categorias = (
            resp.context['vanos_pendientes']
            + resp.context['vanos_ejecutados']
            + resp.context['vanos_sin_permiso']
            + resp.context['vanos_en_espera']
            + resp.context['vanos_seccionados']
            + resp.context['vanos_especiales']
        )
        assert suma_6_categorias == 1  # el legacy 'no_ejecutado' queda fuera


# ==============================================================================
# Bounce=2 (SIN_VALIDAR) — F2/F3 2026-07-04
# ==============================================================================
#
# El cierre 2026-07-03T17:29:01Z declaro los 6 estados "correctos" validando
# SOLO los nombres pedidos, sin tener todavia el Excel de control de color
# del cliente (att_04) como oraculo — el cliente lo compartio recien 35 min
# despues, en el propio comentario de bounce (2026-07-03T18:02:41Z), citando
# 2 imagenes (att_06=dropdown actual, att_04=Excel RESUMEN de referencia).
# Los NOMBRES de los 6 estados ya eran correctos (no se tocan aca); el gap
# real era de COLOR: Sin Permiso/Parcial/Seccionado/Especial no coincidian
# con la convencion operativa del cliente. Se agrega tambien: (a) swatch de
# color en el <select> nativo del modal (b) contador de "novedades" por
# tarjeta — pedido NUEVO, no reproceso (att_05).

import re

from django.db import connection
from django.test.utils import CaptureQueriesContext


def _clases_tarjeta_vano(content: str, vano_id) -> str:
    """Extrae el valor del atributo ``class`` del div raiz de una tarjeta de
    Vano (``id="vano-<uuid>"``), sin depender de una ventana de caracteres
    fija — el bloque de atributos (x-data/@click) tiene longitud variable."""
    patron = re.compile(
        rf'id="vano-{re.escape(str(vano_id))}".*?class="([^"]*)"', re.DOTALL
    )
    match = patron.search(content)
    assert match, f'no se encontro la tarjeta de vano {vano_id} en el HTML'
    return match.group(1)


def _conteo_novedades_tarjeta(content: str, vano_id) -> int:
    """Extrae el numero mostrado en el span
    ``data-testid="vano-novedades-count"`` de un vano especifico."""
    patron = re.compile(
        rf'data-testid="vano-novedades-count" data-vano="{re.escape(str(vano_id))}"'
        r'[^>]*>(\d+)</span>',
        re.DOTALL,
    )
    match = patron.search(content)
    assert match, f'no se encontro el contador de novedades para vano {vano_id}'
    return int(match.group(1))


@pytest.mark.django_db
class TestColoresEstadoConvencionClienteIssue177Bounce2:
    """Recoloreado de Sin Permiso(rojo)/Parcial(verde-claro/lime)/
    Seccionado(naranja-dorado/amber)/Especial(azul) segun la convencion del
    Excel de control del cliente (att_04). Ejecutado(verde)/Pendiente(gris)
    sin cambio — ya coincidian. Cubre los 3 lugares donde el color esta
    hardcoded (F2: no hay COLOR_MAP central): donut, stats row, tarjetas."""

    def test_donut_backgroundcolor_usa_hex_convencion_cliente(self, admin_client, linea):
        Vano.objects.create(linea=linea, numero='1', estado=Vano.Estado.SIN_PERMISO)
        url = reverse('campo:avance_registrar')
        resp = admin_client.get(url, {'linea_id': str(linea.id)})
        content = resp.content.decode()

        assert '#ef4444' in content  # red — sin_permiso (convencion cliente)
        assert '#84cc16' in content  # lime — en_espera (Parcial, verde-claro)
        assert '#f59e0b' in content  # amber — seccionado (naranja/dorado)
        assert '#3b82f6' in content  # blue — especial
        # Los hex del bounce=1 (arbitrarios, sin oraculo de color) ya NO
        # deben aparecer.
        assert '#f97316' not in content  # orange viejo (sin_permiso)
        assert '#eab308' not in content  # yellow viejo (en_espera)
        assert '#a855f7' not in content  # purple viejo (seccionado)
        assert '#ec4899' not in content  # pink viejo (especial)
        # Sin cambio — ya coincidian con la convencion del cliente.
        assert '#d1d5db' in content  # gray — pendiente
        assert '#10b981' in content  # green — ejecutado

    def test_stats_row_usa_clases_tailwind_convencion_cliente(self, admin_client, linea):
        Vano.objects.create(linea=linea, numero='1', estado=Vano.Estado.SIN_PERMISO)
        url = reverse('campo:avance_registrar')
        resp = admin_client.get(url, {'linea_id': str(linea.id)})
        content = resp.content.decode()

        assert 'bg-red-50' in content and 'text-red-600' in content  # Sin Permiso
        assert 'bg-lime-50' in content and 'text-lime-600' in content  # Parcial
        assert 'bg-amber-50' in content and 'text-amber-600' in content  # Seccionado
        assert 'bg-blue-50' in content and 'text-blue-600' in content  # Especial

    def test_tarjeta_sin_permiso_usa_border_red_300(self, admin_client, linea):
        """Selector EXACTO que asserta el journey E2E (Instelec_177.yaml):
        ``#vano-<id>.border-red-300``."""
        vano = Vano.objects.create(linea=linea, numero='15', estado=Vano.Estado.SIN_PERMISO)
        url = reverse('campo:avance_registrar')
        resp = admin_client.get(url, {'linea_id': str(linea.id)})
        content = resp.content.decode()

        assert f'id="vano-{vano.id}"' in content
        clases = _clases_tarjeta_vano(content, vano.id)
        assert 'border-red-300' in clases
        assert 'bg-red-50' in clases

    def test_tarjeta_no_ejecutado_legacy_usa_tono_distinguible_de_sin_permiso(
        self, admin_client, linea
    ):
        """Riesgo documentado por F2 (riesgos_adicionales_detectados): el
        estado legacy 'no_ejecutado' (retirado de seleccionables, 1 vano en
        prod) YA usaba rojo — si Sin Permiso tambien usara el mismo tono
        quedarian visualmente identicos. Se usa 'rose' (no 'red') para
         'no_ejecutado' y se deja 'red' exclusivo para Sin Permiso."""
        vano = Vano.objects.create(linea=linea, numero='999', estado=Vano.Estado.NO_EJECUTADO)
        url = reverse('campo:avance_registrar')
        resp = admin_client.get(url, {'linea_id': str(linea.id)})
        content = resp.content.decode()

        clases = _clases_tarjeta_vano(content, vano.id)
        assert 'border-rose-300' in clases
        assert 'border-red-300' not in clases

    def test_modal_select_tiene_swatch_color_indicador(self, admin_client, linea):
        """A6 ampliado (bounce=2): el <select> nativo no traia ningun
        indicador de color (agrava la percepcion de discrepancia en una
        convencion 100% color-driven para el cliente) — se agrega un swatch
        sincronizado via Alpine x-model + estadoColor(), SIN reemplazar el
        widget nativo (F2 descarto el listbox custom por scope mayor)."""
        Vano.objects.create(linea=linea, numero='1')
        url = reverse('campo:avance_registrar')
        resp = admin_client.get(url, {'linea_id': str(linea.id)})
        content = resp.content.decode()

        assert 'data-testid="vano-estado-select-swatch"' in content
        assert 'estadoColor(estadoSeleccionado)' in content
        assert 'x-model="estadoSeleccionado"' in content
        assert '<select name="estado"' in content  # contrato previo intacto


@pytest.mark.django_db
class TestContadorNovedadesPorTarjetaIssue177:
    """Pedido NUEVO (no reproceso) del comentario de bounce (att_05, junto a
    la tarjeta "Vano 15 / No Ejecutado" sin contador): "poner un conteo de
    novedades para saber cuantas tiene cada vano". Anotado via
    ``Count('historial')`` a nivel de queryset (``apps/campo/views.py``,
    ``_build_context``) — NO ``vano.historial.count()`` en el template
    (dispararia 1 query extra POR VANO)."""

    def test_vano_sin_historial_muestra_contador_cero(self, admin_client, linea):
        vano = Vano.objects.create(linea=linea, numero='1')
        url = reverse('campo:avance_registrar')
        resp = admin_client.get(url, {'linea_id': str(linea.id)})
        content = resp.content.decode()

        assert _conteo_novedades_tarjeta(content, vano.id) == 0

    def test_vano_con_n_registros_historial_cuenta_exacto(self, admin_client, linea):
        vano = Vano.objects.create(linea=linea, numero='2', estado=Vano.Estado.SIN_PERMISO)
        for _ in range(3):
            VanoHistorialEstado.objects.create(vano=vano, estado=Vano.Estado.SIN_PERMISO, nota='')

        url = reverse('campo:avance_registrar')
        resp = admin_client.get(url, {'linea_id': str(linea.id)})
        content = resp.content.decode()

        assert _conteo_novedades_tarjeta(content, vano.id) == 3

    def test_context_vanos_expone_num_novedades_anotado(self, admin_client, linea):
        """La anotacion vive en el queryset (``context['vanos']``), no en un
        loop Python adicional sobre ``vano.historial.all()``."""
        vano = Vano.objects.create(linea=linea, numero='3')
        VanoHistorialEstado.objects.create(vano=vano, estado=Vano.Estado.PENDIENTE, nota='')
        VanoHistorialEstado.objects.create(vano=vano, estado=Vano.Estado.EJECUTADO, nota='')

        url = reverse('campo:avance_registrar')
        resp = admin_client.get(url, {'linea_id': str(linea.id)})

        assert resp.status_code == 200
        vanos_ctx = list(resp.context['vanos'])
        assert len(vanos_ctx) == 1
        assert vanos_ctx[0].num_novedades == 2

    def test_conteo_novedades_no_dispara_n_mas_1(self, admin_user, linea, rf):
        """Prueba comparativa (no un numero magico hardcodeado): si
        ``vano.historial.count()`` se llamara en el template, la cantidad de
        queries crecería proporcional al numero de vanos. Con la anotacion
        ``Count('historial')`` en el queryset (``_build_context``), la
        cantidad de queries debe ser IGUAL con 1 vano que con 6 vanos (todos
        con historial), porque el conteo viaja en la misma fila del SELECT
        principal — no hay round-trip adicional por vano.

        Se invoca ``get_context_data()`` directamente (no ``Client.get`` +
        render de pagina completa) para aislar la queryset de esta vista de
        un N+1 PRE-EXISTENTE y NO relacionado en la seccion "Pendientes de la
        Línea" del template (``{% for vano in linea.vanos.all %}{% for
        pendiente in vano.pendientes.all %}`` — esa seccion re-consulta
        ``linea.vanos.all`` SIN prefetch y esta fuera de scope de este
        issue/bounce; no se toca aca)."""
        from apps.campo.views import RegistroAvanceCreateView

        def _construir_contexto(n_vanos):
            request = rf.get('/campo/avance/registrar/', {'linea_id': str(linea.id)})
            request.user = admin_user
            view = RegistroAvanceCreateView()
            view.request = request
            view.args = ()
            view.kwargs = {}
            with CaptureQueriesContext(connection) as ctx:
                context = view.get_context_data()
                conteos = [v.num_novedades for v in context['vanos']]
            assert context['total_vanos'] == n_vanos
            assert conteos == [2] * n_vanos
            return len(ctx.captured_queries)

        vano_unico = Vano.objects.create(linea=linea, numero='1', estado=Vano.Estado.SIN_PERMISO)
        VanoHistorialEstado.objects.create(vano=vano_unico, estado=Vano.Estado.SIN_PERMISO, nota='')
        VanoHistorialEstado.objects.create(vano=vano_unico, estado=Vano.Estado.EJECUTADO, nota='')
        queries_1_vano = _construir_contexto(1)

        for i in range(2, 7):
            v = Vano.objects.create(linea=linea, numero=str(i), estado=Vano.Estado.SIN_PERMISO)
            VanoHistorialEstado.objects.create(vano=v, estado=Vano.Estado.SIN_PERMISO, nota='')
            VanoHistorialEstado.objects.create(vano=v, estado=Vano.Estado.EJECUTADO, nota='')
        queries_6_vanos = _construir_contexto(6)

        assert queries_6_vanos == queries_1_vano, (
            f'N+1 detectado: {queries_1_vano} queries con 1 vano vs '
            f'{queries_6_vanos} con 6 vanos (deberian ser iguales — el '
            "conteo de historial va anotado en el SELECT principal, no en "
            'un loop por vano)'
        )
