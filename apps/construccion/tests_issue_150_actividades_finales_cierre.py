"""Tests Instelec#150 — cierre definitivo (5ª ronda, 4 bounces previos
FIX_INCOMPLETO): B1 Gantt OC scroll+zoom, B2 barras de materiales
normalizadas, B3 línea "Planeado" de Montaje, B4 freeze-header de
Actividades Finales.

Archivo POR-ISSUE dedicado (no se apendea a ``tests.py`` compartido ni a
``tests_b1_dashboard_oc.py`` / ``tests_b1_actividades_finales.py``, que otro
issue de este mismo RUN toca en paralelo en otro worktree — ver
SPRINTS/PLAN_2026-07-09_actividades_finales_cierre.md).

Convención de tests: B1/B2/B4 son de RENDERING (assertions de presencia de
markup/script/config en el HTML servido, no pixel-perfect — la verificación
visual real la hace el journey ``journeys/Instelec_150.yaml`` vía Chrome
headless). B3 sí prueba el MECANISMO real end-to-end contra el backbone
(``serie_planeado``), porque el gap confirmado por F2 es de DATO (fechas NULL
en prod), no de CAMPO — el código ya funciona una vez el cronograma tenga
fecha_inicio/fecha_fin_planeada + peso_pct.
"""

import pytest
from django.urls import reverse

# ---------------------------------------------------------------------------
# Fixtures compartidas
# ---------------------------------------------------------------------------


@pytest.fixture
def proyecto_150(db):
    from apps.construccion.models import ProyectoConstruccion
    from apps.contratos.models import Contrato

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo="TEST-150-001",
        nombre="Contrato test Instelec#150",
        cliente="Test Cliente #150",
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre="Proyecto #150 test — cierre definitivo",
        estado="EJECUCION",
    )


def _torre(proyecto, numero):
    from apps.construccion.models import TorreConstruccion

    return TorreConstruccion.objects.create(proyecto=proyecto, numero=numero, tipo="D6")


# ===========================================================================
# B1 — Gantt OC: scroll horizontal/vertical + zoom con mouse
# ===========================================================================


@pytest.mark.django_db
class TestB1GanttScrollZoom:
    """El Gantt de Obra Civil gana un wrapper con scroll real (altura dinámica
    por número de torres) + zoom/pan vía ``chartjs-plugin-zoom`` (CDN)."""

    def test_wrapper_scroll_y_plugin_zoom_en_el_dom(self, authenticated_client, proyecto_150):
        url = reverse("construccion:dashboard_obra_civil", kwargs={"proyecto_id": proyecto_150.id})
        resp = authenticated_client.get(url)
        assert resp.status_code == 200, resp.content[:500]
        body = resp.content.decode()

        # Wrapper con overflow real (antes: altura fija 520px sin scroll).
        assert "max-h-[600px] overflow-auto" in body
        assert 'id="oc-gantt-chart"' in body
        # El atributo estático HTML height="520" del <canvas> se retiró — ahora
        # la altura la fija JS proporcional al número de torres.
        assert 'canvas id="oc-gantt-chart" height="520"' not in body
        assert 'canvas id="oc-gantt-chart"></canvas>' in body

        # Plugin de zoom registrado vía CDN (mismo patrón que
        # chartjs-plugin-datalabels en templates/campo/avance_registrar.html).
        assert "chartjs-plugin-zoom@2.0.1" in body
        assert "Chart.register(window.ChartZoom)" in body

    def test_render_oc_gantt_altura_dinamica_y_config_zoom_pan(
        self, authenticated_client, proyecto_150
    ):
        """El código de renderOcGantt() calcula la altura por fila y registra
        wheel-zoom (mode:'x', no 'xy' — no debe interceptar el scroll vertical
        de la página) + pan. Verificación de código fuente embebido; el render
        visual real (64+ torres) lo confirma el journey con screenshot."""
        url = reverse("construccion:dashboard_obra_civil", kwargs={"proyecto_id": proyecto_150.id})
        resp = authenticated_client.get(url)
        body = resp.content.decode()

        assert "filas.length * 22" in body
        assert "wrapper.style.height" in body
        assert "zoom: { wheel: { enabled: true }, pinch: { enabled: true }, mode: 'x' }" in body
        assert "pan: { enabled: true, mode: 'xy' }" in body

    def test_dashboard_oc_sigue_200_sin_torres_ni_gantt_data(
        self, authenticated_client, proyecto_150
    ):
        """Edge: proyecto sin torres → gantt_oc_json vacío ([]), el dashboard
        no debe romper (smoke de regresión, #b1 del plan)."""
        url = reverse("construccion:dashboard_obra_civil", kwargs={"proyecto_id": proyecto_150.id})
        resp = authenticated_client.get(url)
        assert resp.status_code == 200
        assert 'data-block="oc-gantt"' in resp.content.decode()
