"""#150 (items 3/4/5) / #122 (item 6) — toggle "aplica / no aplica" por torre en
las matrices de Montaje y Tendido.

Antes: las matrices de Montaje y Tendido llamaban `ordenar_torres_construccion()`
SIN `incluir_no_aplica` → las torres marcadas `aplica=False` (#160) DESAPARECÍAN
de esos bloques y no había forma de re-activarlas desde ahí (item 3: "E19 no
aparece"). Además el % de avance se promediaba sobre TODAS las filas, así que una
torre no-construida marcada "aplica" la bajaba (item 4: 98.4%).

Fix (reusa el flag GLOBAL `TorreConstruccion.aplica` #160 y el endpoint existente
`construccion:obra_civil_aplica_update`, sin migración):
- Las dos vistas pasan `incluir_no_aplica=True` → listan TODAS las torres.
- El avance promedia SOLO las torres con `aplica=True` (display=todas, conteo=solo
  activas) → una torre "No aplica" no baja el %.
- El template muestra el toggle por fila (POST al endpoint global, campo `aplica`)
  y atenúa las filas no-aplica.

Tests:
- Una torre `aplica=False` SÍ aparece en la matriz de Montaje (antes no).
- El toggle (input que apunta al endpoint obra_civil_aplica_update) está en la fila.
- El avance promedia solo torres aplica=True (la no-aplica al 0% no diluye el %).
"""
import pytest
from django.urls import reverse

from apps.contratos.models import Contrato
from apps.construccion.models import (
    ProyectoConstruccion,
    TorreConstruccion,
    MontajeEstructuraTorre,
)
from apps.construccion.views import MontajeMatrizView


@pytest.fixture
def proyecto_i150m(db):
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-I150M-001',
        nombre='Proyecto test #150 montaje toggle',
        cliente='Test',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto LT 230kV — Test #150 montaje',
        estado='EJECUCION',
    )


@pytest.fixture
def torres_i150m(proyecto_i150m):
    """Torre E18 (aplica) y E19 (NO aplica). E18 con estructura en sitio al 100%."""
    e18 = TorreConstruccion.objects.create(
        proyecto=proyecto_i150m, numero='E18', aplica=True)
    e19 = TorreConstruccion.objects.create(
        proyecto=proyecto_i150m, numero='E19', aplica=False)
    # E18 con avance: estructura en sitio = 1 → avance_ponderado = peso 10/100 = 0.10
    MontajeEstructuraTorre.objects.create(
        proyecto=proyecto_i150m, torre=e18, avance_estructura_sitio=1)
    # E19 (no aplica) queda en 0; NO debe diluir el promedio.
    MontajeEstructuraTorre.objects.create(proyecto=proyecto_i150m, torre=e19)
    return proyecto_i150m, e18, e19


def _montaje_url(proyecto):
    return reverse('construccion:montaje_lista',
                   kwargs={'proyecto_id': proyecto.id})


@pytest.mark.django_db
class TestI150MontajeNoAplica:

    def test_torre_no_aplica_aparece_en_matriz_montaje(
        self, authenticated_client, torres_i150m,
    ):
        """Item 3: la torre 'No aplica' (E19) SÍ se lista en Montaje (antes no)."""
        proyecto, e18, e19 = torres_i150m
        resp = authenticated_client.get(_montaje_url(proyecto))
        assert resp.status_code == 200
        html = resp.content.decode()
        assert e19.numero_display in html, (
            "La torre 'No aplica' debe aparecer en la matriz de Montaje.")
        assert e18.numero_display in html

    def test_toggle_aplica_presente_en_la_fila(
        self, authenticated_client, torres_i150m,
    ):
        """El toggle por fila apunta al endpoint global obra_civil_aplica_update."""
        proyecto, e18, e19 = torres_i150m
        resp = authenticated_client.get(_montaje_url(proyecto))
        html = resp.content.decode()
        url_toggle = reverse(
            'construccion:obra_civil_aplica_update',
            kwargs={'proyecto_id': proyecto.id, 'torre_id': e19.id},
        )
        assert url_toggle in html, (
            "La fila debe incluir el toggle apuntando al endpoint de aplica.")
        # el input/checkbox del toggle por torre.
        assert f'data-toggle-aplica="aplica" data-torre="{e19.id}"' in html

    def test_fila_no_aplica_se_atenua(
        self, authenticated_client, torres_i150m,
    ):
        """La fila no-aplica se muestra atenuada (opacity-50)."""
        proyecto, e18, e19 = torres_i150m
        resp = authenticated_client.get(_montaje_url(proyecto))
        html = resp.content.decode()
        # marca de atenuación presente en el HTML (la fila no-aplica).
        assert 'opacity-50' in html

    def test_avance_promedia_solo_torres_que_aplican(
        self, admin_user, torres_i150m, rf,
    ):
        """Item 4/5: el avance general NO se diluye con la torre no-aplica.

        E18 (aplica) está al 10% (estructura en sitio=1, peso 10). E19 (no aplica)
        está al 0%. El avance general debe ser 10.0 (solo E18), NO 5.0 (promedio
        de las 2 filas).
        """
        proyecto, e18, e19 = torres_i150m
        request = rf.get(_montaje_url(proyecto))
        request.user = admin_user
        view = MontajeMatrizView()
        view.request = request
        view.kwargs = {'proyecto_id': proyecto.id}
        ctx = view.get_context_data()
        # display = ambas torres; conteo = solo la activa.
        assert len(ctx['filas']) == 2
        assert ctx['avance_general'] == 10.0, (
            f"El avance debe contar solo torres aplica=True (10.0), "
            f"no diluirse con la no-aplica; recibí {ctx['avance_general']}")

    def test_avance_cero_si_ninguna_aplica(self, admin_user, proyecto_i150m, rf):
        """Si NO hay torres activas, los promedios son 0 (sin ZeroDivision)."""
        t = TorreConstruccion.objects.create(
            proyecto=proyecto_i150m, numero='E20', aplica=False)
        MontajeEstructuraTorre.objects.create(proyecto=proyecto_i150m, torre=t)
        request = rf.get('/')
        request.user = admin_user
        view = MontajeMatrizView()
        view.request = request
        view.kwargs = {'proyecto_id': proyecto_i150m.id}
        ctx = view.get_context_data()
        assert ctx['avance_general'] == 0
        assert all(v == 0 for v in ctx['totales'].values())
