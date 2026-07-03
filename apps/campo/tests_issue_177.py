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
