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

from datetime import date, timedelta
from decimal import Decimal

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


# ===========================================================================
# B2 — Barras Agua/Grava en Desviación de materiales (Solado/Vaciado)
# ===========================================================================


@pytest.mark.django_db
class TestB2BarrasMaterialesNormalizadas:
    """Root cause (F2): NO es un bug de dato — es escala compartida en un eje
    lineal (Cemento en kg aplasta Agua/Arena/Grava en m³ a 1-2px). Fix:
    normalizar a % de Calculado, reusando ``desv_pct`` que YA calcula el
    backend. CERO cambios en ``calculators.py``."""

    def test_backend_conserva_desv_pct_no_none_para_agua_y_grava(self, proyecto_150):
        """Regresión de DATO (no de render): el backend sigue devolviendo las
        4 entradas por etapa con desv_pct completo — el bug era 100% de
        visualización, confirmado por F2 contra calculators.py."""
        from apps.construccion.calculators import desviacion_materiales_solado
        from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle

        torre = _torre(proyecto_150, "T1")
        ObraCivilTorreDetalle.objects.create(
            proyecto=proyecto_150,
            torre=torre,
            pata="A",
            sol_agua_calc=Decimal("10.00"),
            sol_agua_real=Decimal("12.98"),  # +29.8% (m³)
            sol_grava_calc=Decimal("5.00"),
            sol_grava_real=Decimal("15.85"),  # +217.0% (m³)
            sol_cemento_calc=Decimal("300.00"),
            sol_cemento_real=Decimal("310.00"),  # +3.3% (kg, aplasta el eje)
            sol_arena_calc=Decimal("8.00"),
            sol_arena_real=Decimal("8.10"),
        )

        materiales = desviacion_materiales_solado(proyecto_150)
        por_material = {m["material"]: m for m in materiales}

        assert por_material["agua"]["desv_pct"] is not None
        assert por_material["agua"]["semaforo"] == "rojo"
        assert por_material["grava"]["desv_pct"] is not None
        assert por_material["grava"]["semaforo"] == "rojo"
        # Cemento en unidades "grandes" (kg) sigue con dato completo también.
        assert por_material["cemento"]["calc"] == pytest.approx(300.0)

    def test_chart_js_normaliza_a_pct_de_calculado_no_unidades_crudas(
        self, authenticated_client, proyecto_150
    ):
        """El chart de Desviación de materiales ya NO grafica calc/real
        crudos (que aplastaban Agua/Grava contra Cemento) — grafica
        Calculado=100 fijo y Real=100+desv_pct, mismo dato, escala normalizada."""
        url = reverse("construccion:dashboard_obra_civil", kwargs={"proyecto_id": proyecto_150.id})
        resp = authenticated_client.get(url)
        assert resp.status_code == 200
        body = resp.content.decode()

        assert "materiales.map(m => 100)" in body
        assert "Math.max(0, 100 + m.desv_pct)" in body
        assert "text: '% de Calculado'" in body
        # La tabla debajo del chart (ya validada por Indunnova) no se tocó.
        assert 'data-material="agua"' in body
        assert 'data-material="grava"' in body


# ===========================================================================
# B3 — Línea "Planeado" en Curva S de Montaje (gap de DATO, no de CAMPO)
# ===========================================================================


@pytest.mark.django_db
class TestB3CurvaSPlaneadoMontaje:
    """F2 confirmó contra BD prod que ``ProgramacionFase(seccion=MONTAJE)``
    existe pero con fecha_inicio_planeada/fecha_fin_planeada=NULL y
    peso_pct=0 — ``serie_planeado()`` YA arma la serie sola en cuanto esos 3
    campos se pueblan vía /cronograma/. NO requiere migración ni campo nuevo."""

    def test_serie_planeado_arma_serie_cuando_hay_fechas_pobladas(self, proyecto_150):
        """Mecanismo real: con fecha_inicio/fecha_fin/peso poblados (como
        haría el cliente en /cronograma/), la serie deja de estar vacía."""
        from apps.construccion import calculators_avance_real as car
        from apps.construccion.models import ProgramacionFase

        hoy = date.today()
        ProgramacionFase.objects.create(
            proyecto=proyecto_150,
            seccion=ProgramacionFase.Seccion.MONTAJE,
            fecha_inicio_planeada=hoy - timedelta(days=180),
            fecha_fin_planeada=hoy + timedelta(days=30),
            peso_pct=100,
        )

        serie = car.serie_planeado(proyecto_150, car.FASE_MONTAJE)
        assert serie["planeado"], "la serie planeado no debe quedar vacía con fechas pobladas"
        assert serie["labels"]
        assert serie["planeado"][0] == 0.0
        assert serie["planeado"][-1] == 100.0

    def test_serie_planeado_vacia_sin_fechas_replica_gap_de_dato_prod(self, proyecto_150):
        """Réplica del estado real de prod (MONTAJE existe, fechas NULL, peso
        0) — confirma que sin dato la serie sale vacía SIN romper (gap de
        DATO, no de CAMPO: no hace falta migración ni código nuevo)."""
        from apps.construccion import calculators_avance_real as car
        from apps.construccion.models import ProgramacionFase

        ProgramacionFase.objects.create(
            proyecto=proyecto_150,
            seccion=ProgramacionFase.Seccion.MONTAJE,
        )  # fecha_inicio_planeada/fecha_fin_planeada NULL, peso_pct=0 (default)

        serie = car.serie_planeado(proyecto_150, car.FASE_MONTAJE)
        assert not serie["planeado"]

    def test_dashboard_montaje_real_hint_estado_vacio_cuando_falta_cronograma(
        self, authenticated_client, proyecto_150
    ):
        """B3 opcional (implementado): hint de estado vacío + link directo a
        /cronograma/ cuando la serie planeada está vacía."""
        url = reverse(
            "construccion:dashboard_montaje_real", kwargs={"proyecto_id": proyecto_150.id}
        )
        resp = authenticated_client.get(url)
        assert resp.status_code == 200
        body = resp.content.decode()
        assert 'data-hint="planeado-vacio"' in body
        assert "/cronograma/" in body

    def test_dashboard_montaje_real_sin_hint_cuando_cronograma_poblado(
        self, authenticated_client, proyecto_150
    ):
        """El hint desaparece en cuanto el cronograma tiene dato (no es un
        banner permanente)."""
        from apps.construccion.models import ProgramacionFase

        hoy = date.today()
        ProgramacionFase.objects.create(
            proyecto=proyecto_150,
            seccion=ProgramacionFase.Seccion.MONTAJE,
            fecha_inicio_planeada=hoy - timedelta(days=180),
            fecha_fin_planeada=hoy + timedelta(days=30),
            peso_pct=100,
        )

        url = reverse(
            "construccion:dashboard_montaje_real", kwargs={"proyecto_id": proyecto_150.id}
        )
        resp = authenticated_client.get(url)
        assert resp.status_code == 200
        assert 'data-hint="planeado-vacio"' not in resp.content.decode()
