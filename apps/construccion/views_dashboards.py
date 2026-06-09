"""Vistas de los Dashboards de fase (#139) — partición física de ``views.py``.

``views.py`` ya es magnet (2446 líneas, 4 sub-features lo tocarían). Este módulo
es el hogar de las vistas de los dashboards de avance real, para que B1–B5
escriban a archivos separados (``views_dashboards_b*.py``) sin colisión.

F2 (scaffolding) deja aquí:
  - ``_DashboardCurvaSBase``: re-exporta/extiende la base existente de
    ``views.py`` con un punto de extensión (``serie_real_source``) que B1
    cablea al backbone ``calculators_avance_real`` para que la Curva S
    "Ejecutado" deje de salir en 0% (hoy cuelga de ``DashboardAvanceSemanal``,
    solo 2 filas en prod).

B1 (#139) EXTIENDE este archivo con ``DashboardObraCivilRealView`` real y mueve
la lógica de cableado. B2–B5 importan ``_DashboardCurvaSBase`` desde aquí para
sus propios dashboards de fase. NO duplicar la base en cada sub-feature.

────────────────────────────────────────────────────────────────────────────
B1 — cableado del avance REAL de Obra Civil (#139)
────────────────────────────────────────────────────────────────────────────
``DashboardObraCivilRealView`` SUSTITUYE funcionalmente a
``views.DashboardObraCivilView`` (legacy #141) **sin tocar** ``views.py`` ni
``urls.py``: ``urls_dashboards`` re-registra el nombre de URL
``dashboard_obra_civil`` apuntando a esta vista. Como ``urlpatterns +=
dashboards_urls`` se agrega DESPUÉS en ``urls.py``, en Django el último
``name`` registrado gana en ``reverse()`` → todos los menús/links del sistema
resuelven a esta vista real, sin editar el archivo magnet.

La vista hereda de la legacy ``DashboardObraCivilView`` para conservar TODO el
comportamiento de #141 (las 3 gráficas G1/G2/G3, materiales de vaciado,
selector "Consolidada", flag ``data-charts-ready``) y le superpone:

  1. La Curva S real: serie "Ejecutado" = ``serie_curva_s_real(proyecto,'OOCC')``
     (257 ``oc_detalle`` de prod), "Planeado" = ``serie_planeado``. Reemplaza la
     curva inicial que colgaba del semanal vacío (``datos_chart``).
  2. Las tarjetas %ejecutado / %planeado / varianza derivadas del REAL.
  3. La gráfica de avance por etapa con las **6** etapas OC + pesos
     (Cerramiento incluido), no las 5 del legacy.
  4. La vista por torre OC (cuáles 100% / pendientes) con drill-down a
     ``obra_civil_torre``.
"""
from __future__ import annotations

import json

from django.urls import reverse

from . import calculators_avance_real as car

# La vista legacy #141 con las 3 gráficas (G1/G2/G3). B1 la extiende para
# conservar ese comportamiento y superponerle el avance REAL (import read-only).
from .views import DashboardObraCivilView as _DashboardObraCivilViewLegacy

# Reusa la base ya probada de views.py (LoginRequired + RoleRequired + el
# armado de tarjetas/semanas). B1 la sobreescribe/extiende según el scope.
from .views import _DashboardCurvaSBase as _DashboardCurvaSBaseLegacy


class _DashboardCurvaSBase(_DashboardCurvaSBaseLegacy):
    """Base compartida por los dashboards de fase con datos de avance REAL.

    Extiende la base legacy (que arma tarjetas/semanas desde
    ``DashboardAvanceSemanal``) con un punto de extensión para inyectar las
    series reales del backbone ``calculators_avance_real``. F2 deja el cableado
    listo pero conservador: por defecto añade ``curva_real`` al contexto sin
    alterar el comportamiento existente; B1 decide promover ``curva_real`` a la
    serie principal de la Curva S de Obra Civil.

    Subclases (B1–B5) definen ``FASE_DEFAULT`` y ``template_name``.
    """

    #: Fase del backbone (OOCC / MONTAJE / TENDIDO). Por defecto deriva de
    #: ``FASE_DEFAULT`` de la base legacy. B2/B3 la sobreescriben si difiere.
    FASE_BACKBONE = None

    def fase_backbone(self):
        """Resuelve la fase a pasar al backbone de cálculo real."""
        return (self.FASE_BACKBONE or self.FASE_DEFAULT or car.FASE_OOCC).upper()

    def build_curva_real(self, proyecto, fase):
        """Series reales ejecutado + planeado, listas para el template.

        Devuelve un **DICT** (NO un string json.dumps). El parcial base
        ``_dashboard_fase_base.html`` lo emite con ``{{ curva_real_json|json_script }}``
        y su JS hace ``JSON.parse(...).ejecutado`` / ``.planeado``. ``json_script``
        ya serializa+escapa el valor de forma segura (guard es-CO: nunca floats
        crudos en JS inline), así que el contexto debe traer el dict, no el string.
        Si pasáramos un string pre-serializado quedaría doble-codificado:
        ``JSON.parse`` devolvería un string y ``.ejecutado`` sería ``undefined`` →
        la Curva S no pintaría (bug de integración B2/B4 que reusan este parcial).

        B1 (Obra Civil) usa su propio ``datos_chart`` para el canvas legacy y NO
        depende de este dict; B2/B3 (Montaje/Tendido) sí lo consumen vía el parcial.
        """
        ejecutado = car.serie_curva_s_real(proyecto, fase)
        planeado = car.serie_planeado(proyecto, fase)
        return {
            'fase': fase,
            'ejecutado': ejecutado,   # {'labels':[...], 'ejecutado':[...]}
            'planeado': planeado,     # {'labels':[...], 'planeado':[...]}
        }

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = ctx.get('proyecto')
        if proyecto is not None:
            fase = self.fase_backbone()
            # Aditivo: no rompe el contrato legacy (datos_chart sigue intacto).
            # B1 promueve estas series a la Curva S principal de OC.
            ctx['curva_real_json'] = self.build_curva_real(proyecto, fase)
            ctx['fase_backbone'] = fase
        return ctx


# ==========================================================================
# B1 — Dashboard de Obra Civil con avance REAL (#139)
# ==========================================================================

def _curva_s_chart_payload(proyecto, fase=car.FASE_OOCC) -> dict:
    """Arma el dict ``{labels, planeado, ejecutado}`` de la Curva S REAL.

    Une los ejes de las series "Ejecutado" (avance real por torre distribuido en
    el tiempo) y "Planeado" (cronograma ``ProgramacionFase``) sobre un eje X
    común de fechas ordenadas, interpolando con "último valor conocido" (carry
    forward) para que Chart.js trace dos líneas alineadas.

    Edge (proyecto sin avance): ambas series vacías → ``{labels:[], planeado:[],
    ejecutado:[]}`` (la gráfica queda vacía, NO lanza).
    """
    ejecutado = car.serie_curva_s_real(proyecto, fase)
    planeado = car.serie_planeado(proyecto, fase)

    # Eje X común = unión ordenada de fechas de ambas series.
    labels = sorted(set(ejecutado.get('labels', [])) | set(planeado.get('labels', [])))
    if not labels:
        return {'labels': [], 'planeado': [], 'ejecutado': []}

    def _carry(series_labels, series_vals):
        """Mapea cada label del eje común al último valor ≤ él (carry forward)."""
        pares = list(zip(series_labels, series_vals, strict=False))
        out = []
        ult = 0.0
        idx = 0
        for lab in labels:
            while idx < len(pares) and pares[idx][0] <= lab:
                ult = pares[idx][1]
                idx += 1
            out.append(round(ult, 2))
        return out

    return {
        'labels': labels,
        'ejecutado': _carry(ejecutado.get('labels', []), ejecutado.get('ejecutado', [])),
        'planeado': _carry(planeado.get('labels', []), planeado.get('planeado', [])),
    }


def _tarjetas_real(proyecto, fase=car.FASE_OOCC) -> dict:
    """Deriva las tarjetas %ejecutado / %planeado / varianza del avance REAL.

    - ``pct_construido``: último punto acumulado de la serie "Ejecutado" real.
    - ``pct_programado``: último punto de la serie "Planeado" del cronograma.
    - ``varianza_pct``: ejecutado − planeado (negativo = atraso).

    Edge (sin datos): todo a 0.0, nunca None ni división por cero.
    """
    payload = _curva_s_chart_payload(proyecto, fase)
    pct_ejec = payload['ejecutado'][-1] if payload['ejecutado'] else 0.0
    pct_plan = payload['planeado'][-1] if payload['planeado'] else 0.0
    return {
        'pct_construido': round(pct_ejec, 1),
        'pct_programado': round(pct_plan, 1),
        'varianza_pct': round(pct_ejec - pct_plan, 1),
    }


class DashboardObraCivilRealView(_DashboardObraCivilViewLegacy):
    """Dashboard de Obra Civil con la Curva S y tarjetas del avance REAL (#139).

    Hereda de la vista legacy #141 → conserva sus 3 gráficas (G1 Curva S
    consolidada, G2 avance por etapa, G3 desviación de materiales), el selector
    "Consolidada" y el flag ``data-charts-ready``. Sobre eso superpone el avance
    REAL de los 257 ``oc_detalle`` de prod:

      - ``datos_chart``: pasa a ser la Curva S REAL (Ejecutado/Planeado del
        backbone), de modo que la línea verde "Ejecutado" deja de salir en 0%.
      - tarjetas ``pct_construido_total`` / ``pct_programado_total`` /
        ``varianza_pct_real`` derivadas del REAL.
      - ``avance_etapas_oc6``: las **6** etapas OC con pesos (incluye
        Cerramiento), vía ``avance_por_etapa(proyecto,'OOCC')`` del backbone.
      - ``vista_torres_oc``: lista por torre (% / completa / pendientes) con la
        URL de drill-down a ``obra_civil_torre`` por torre.
    """

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = ctx['proyecto']
        fase = car.FASE_OOCC

        # 1. Curva S REAL — reemplaza datos_chart (que colgaba del semanal vacío).
        chart_real = _curva_s_chart_payload(proyecto, fase)
        ctx['datos_chart'] = json.dumps(chart_real)
        # Para los assert/probe del journey: serie ejecutado real cruda + flag.
        ctx['curva_real_json'] = json.dumps({
            'fase': fase,
            'ejecutado': car.serie_curva_s_real(proyecto, fase),
            'planeado': car.serie_planeado(proyecto, fase),
        })

        # 2. Tarjetas derivadas del REAL (no del DashboardAvanceSemanal vacío).
        tarjetas = _tarjetas_real(proyecto, fase)
        ctx['pct_construido_total'] = tarjetas['pct_construido']
        ctx['pct_programado_total'] = tarjetas['pct_programado']
        ctx['varianza_pct_real'] = tarjetas['varianza_pct']

        # 3. Avance por etapa OC — 6 etapas (con Cerramiento) del backbone.
        avance_etapas6 = car.avance_por_etapa(proyecto, fase)
        ctx['avance_etapas_oc6'] = avance_etapas6
        # Promueve la gráfica G2 a las 6 etapas reales (el JS lee graficas_json).
        # Mantiene la clave 'avance_etapas' legacy (5 etapas) para no romper los
        # asserts del test #141, pero la gráfica usa las 6 reales vía oc6.
        try:
            graficas = json.loads(ctx.get('graficas_json', '{}'))
        except (TypeError, ValueError):
            graficas = {}
        graficas['avance_etapas_oc6'] = avance_etapas6
        ctx['graficas_json'] = json.dumps(graficas)

        # 4. Vista por torre OC + drill-down a obra_civil_torre.
        vista = car.vista_por_torre(proyecto, fase)
        for fila in vista:
            torre_id = fila.get('torre_id')
            try:
                fila['url_detalle'] = reverse(
                    'construccion:obra_civil_torre',
                    kwargs={'proyecto_id': proyecto.id, 'torre_id': torre_id},
                ) if torre_id else ''
            except Exception:
                fila['url_detalle'] = ''
        ctx['vista_torres_oc'] = vista
        ctx['torres_oc_completas'] = sum(1 for f in vista if f.get('completa'))
        ctx['torres_oc_total'] = len(vista)

        return ctx
