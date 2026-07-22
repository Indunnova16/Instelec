"""#183 — 3 correcciones de UI/texto en Construcción, confirmadas contra prod
2026-07-22 (F2, reproceso #2 sobre #171/#147):

1. Montaje (matriz resumen, `montaje_matriz.html`): el cliente señaló la
   columna "Detalle" / botón "Abrir detalle" como redundante — el número de
   torre ya es el único punto de entrada al detalle (mismo patrón que
   Tendido/SPT/Obra Civil). Se elimina la columna completa (th + td + ajuste
   de colspan del estado vacío).
2. Tendido (matriz, `tendido_matriz.html`): el header "HMV" (con
   title="Facturadas HMV") exponía el nombre del contratista subcontratado al
   cliente final. Se renombra a "Fact." con un title genérico.
3. Unificación terminológica "OPGW"/"Fibra óptica" -> "Cable de guarda" (la
   MISMA convención ya shippeada en #147 sobre `tendido_matriz.html`) en 5
   archivos: `models.py` (verbose_name de 5 campos de `TendidoTorre`),
   `tendido_lista.html`, `entrega_torre.html`, `dashboard_tendido.html`,
   `entrega.html`. Explícitamente EXCLUIDO: `planillas/ft-931.html` (planilla
   técnica regulatoria) y `COLUMNAS_FIBRA`/`ETAPAS_TENDIDO_FIBRA_PESOS`
   (constantes internas, fuera de scope a propósito desde #147 — ver
   `tests_issue_147.py`).
"""
import pytest
from django.urls import reverse

from apps.contratos.models import Contrato
from apps.construccion.models import (
    ProyectoConstruccion,
    TorreConstruccion,
    MontajeEstructuraTorre,
    TendidoTorre,
)


@pytest.fixture
def proyecto_i183(db):
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-I183-001',
        nombre='Proyecto test #183 montaje/tendido',
        cliente='Test',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto LT 230kV — Test #183',
        estado='EJECUCION',
    )


@pytest.fixture
def torre_legacy_i183(proyecto_i183):
    """Torre 'legacy' (existía antes del fix, sin dato nuevo) — evita el
    riesgo de validar el fix SOLO contra un fixture recién creado (regla
    'dato legacy obligatorio')."""
    return TorreConstruccion.objects.create(
        proyecto=proyecto_i183, numero='E1', aplica=True)


@pytest.fixture
def montaje_row_i183(proyecto_i183, torre_legacy_i183):
    return MontajeEstructuraTorre.objects.create(
        proyecto=proyecto_i183, torre=torre_legacy_i183,
        avance_estructura_sitio=1,
    )


@pytest.fixture
def tendido_row_i183(proyecto_i183, torre_legacy_i183):
    return TendidoTorre.objects.create(
        proyecto=proyecto_i183, torre=torre_legacy_i183,
        facturadas_hmv=True,
    )


def _montaje_url(proyecto):
    return reverse('construccion:montaje_lista', kwargs={'proyecto_id': proyecto.id})


def _tendido_url(proyecto):
    return reverse('construccion:tendido_lista', kwargs={'proyecto_id': proyecto.id})


@pytest.mark.django_db
class TestI183MontajeSinColumnaDetalle:
    """Sub-item 1: montaje_matriz.html ya no expone la columna 'Detalle' /
    el botón 'Abrir detalle' — el número de torre es el único punto de
    entrada al detalle."""

    def test_matriz_montaje_no_tiene_columna_detalle(
        self, authenticated_client, montaje_row_i183,
    ):
        proyecto = montaje_row_i183.proyecto
        resp = authenticated_client.get(_montaje_url(proyecto))
        assert resp.status_code == 200
        html = resp.content.decode()
        assert 'Abrir detalle' not in html
        assert '>Detalle<' not in html

    def test_matriz_montaje_numero_torre_sigue_siendo_link_al_detalle(
        self, authenticated_client, montaje_row_i183,
    ):
        """El número de torre (único punto de entrada al detalle) se preserva."""
        proyecto = montaje_row_i183.proyecto
        torre = montaje_row_i183.torre
        resp = authenticated_client.get(_montaje_url(proyecto))
        html = resp.content.decode()
        detalle_url = reverse(
            'construccion:montaje_detalle',
            kwargs={'proyecto_id': proyecto.id, 'torre_id': torre.id},
        )
        assert detalle_url in html


@pytest.mark.django_db
class TestI183TendidoFacturadaNoHMV:
    """Sub-item 2: tendido_matriz.html ya no expone 'HMV' (nombre del
    contratista) — el header dice 'Fact.' con un title genérico."""

    def test_matriz_tendido_no_dice_hmv(
        self, authenticated_client, tendido_row_i183,
    ):
        proyecto = tendido_row_i183.proyecto
        resp = authenticated_client.get(_tendido_url(proyecto))
        assert resp.status_code == 200
        html = resp.content.decode()
        assert 'HMV' not in html
        assert 'Facturadas HMV' not in html

    def test_matriz_tendido_dice_facturada(
        self, authenticated_client, tendido_row_i183,
    ):
        proyecto = tendido_row_i183.proyecto
        resp = authenticated_client.get(_tendido_url(proyecto))
        html = resp.content.decode()
        assert 'Fact.' in html
        assert 'Actividad facturada al dueño del proyecto' in html


@pytest.mark.django_db
class TestI183CableDeGuardaUnificado:
    """Sub-item 3: 'OPGW'/'Fibra óptica' -> 'Cable de guarda' en los 5
    archivos que F2 identificó (SIN tocar ft-931.html ni COLUMNAS_FIBRA)."""

    def test_verbose_name_tendidotorre_ya_no_dice_opgw(self):
        campos = [
            'riega_manila_fibra', 'riega_guaya_opgw', 'tendido_opgw',
            'grapado_amarre_fibra', 'empalmes_opgw',
        ]
        for campo in campos:
            field = TendidoTorre._meta.get_field(campo)
            assert 'OPGW' not in field.verbose_name, (
                f"{campo}.verbose_name sigue diciendo OPGW: {field.verbose_name!r}"
            )
            assert 'cable de guarda' in field.verbose_name.lower(), (
                f"{campo}.verbose_name no usa la convención 'cable de guarda': "
                f"{field.verbose_name!r}"
            )
            # El nombre del campo/columna DB NUNCA debe tocarse (#183 F2).
        assert TendidoTorre._meta.get_field('riega_guaya_opgw').name == 'riega_guaya_opgw'
        assert TendidoTorre._meta.get_field('tendido_opgw').name == 'tendido_opgw'
        assert TendidoTorre._meta.get_field('empalmes_opgw').name == 'empalmes_opgw'

    def test_dashboard_tendido_dice_cable_de_guarda_no_fibra_opgw(
        self, authenticated_client, tendido_row_i183,
    ):
        proyecto = tendido_row_i183.proyecto
        url = reverse('construccion:dashboard_tendido', kwargs={'proyecto_id': proyecto.id})
        resp = authenticated_client.get(url)
        assert resp.status_code == 200
        html = resp.content.decode()
        assert 'Fibra OPGW' not in html
        assert '% Cable de guarda (real)' in html
        assert 'Avance por etapa — Cable de guarda' in html

    def test_entrega_dice_cajas_cable_de_guarda(
        self, authenticated_client, tendido_row_i183,
    ):
        proyecto = tendido_row_i183.proyecto
        url = reverse('construccion:entrega', kwargs={'proyecto_id': proyecto.id})
        resp = authenticated_client.get(url)
        assert resp.status_code == 200
        html = resp.content.decode()
        assert 'Cajas OPGW' not in html
        assert 'Cajas Cable de guarda' in html

    def test_tendido_lista_legacy_dice_cable_de_guarda(
        self, authenticated_client, tendido_row_i183,
    ):
        proyecto = tendido_row_i183.proyecto
        url = reverse('construccion:tendido_lista_legacy', kwargs={'proyecto_id': proyecto.id})
        resp = authenticated_client.get(url)
        assert resp.status_code == 200
        html = resp.content.decode()
        assert 'OPGW (I' not in html
        assert 'Cable de guarda (I' in html

    def test_ft931_planilla_regulatoria_no_se_toca(self):
        """ft-931.html es una planilla técnica regulatoria — decisión de F1/F2
        de NO tocarla. Este test documenta la exclusión explícita (no hace
        una request HTTP: la planilla requiere un contexto de tiro/fase que
        no es el foco de #183)."""
        import pathlib
        path = pathlib.Path(__file__).resolve().parent.parent.parent / (
            'templates/construccion/planillas/ft-931.html'
        )
        content = path.read_text(encoding='utf-8')
        assert 'OPGW' in content, (
            'ft-931.html debía seguir diciendo OPGW (excluido a propósito de #183)'
        )
