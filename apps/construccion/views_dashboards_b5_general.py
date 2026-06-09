"""B5 (#139) — Dashboard GENERAL del proyecto (7 fases).

Vista consolidada de las 7 fases de un ``ProyectoConstruccion``:
  - Gráfica global agregando las 7 fases (Ingeniería, Actividades Preliminares,
    Obra Civil, Montaje, Tendido, SPT y Pintura, Detalles Finales) + el global
    ponderado.
  - Curva S consolidada REAL del proyecto (no la de ``DashboardAvanceSemanal``,
    que en prod solo tiene 2 filas): se construye agregando las series reales
    por torre de las fases con anclaje temporal (OOCC / Montaje / Tendido) que
    expone el backbone ``calculators_avance_real``.
  - Drill-down: cada fase enlaza a SU dashboard de fase. Los names de URL los
    crean B1–B4 y F4 los cablea en ``urls.py``. Si un name no resuelve aún en
    el entorno aislado, el template degrada el enlace a "#" sin romper la página
    (ver ``DRILLDOWN_URL_NAMES`` + ``_safe_reverse``).

Reusa el backbone PURO ``calculators_avance_real.avance_general`` (ya en la
base). NO duplica lógica de cálculo: todo el % por fase y el global ponderado
(pesos de ``ProgramacionFase.peso_pct``, fallback equiponderado) viven allí.

GUARDS es-CO (memorias recurrentes del portafolio):
  - Los datasets viajan PRE-SERIALIZADOS vía ``json.dumps`` + ``json_script`` en
    el template. NUNCA floats crudos ni JSON crudo dentro de ``x-data`` / JS
    inline (coma decimal es-CO rompe el ``<script>`` entero).
"""
from __future__ import annotations

import json
from collections import defaultdict

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.urls import NoReverseMatch, reverse
from django.views.generic import TemplateView

from apps.core.mixins import RoleRequiredMixin

from . import calculators_avance_real as car
from .models import ProyectoConstruccion
from .views import ALL_ADMIN_ROLES, OPERARIO_ROLES


#: Drill-down: sección de fase del backbone -> name de URL del dashboard de esa
#: fase (creados por B1–B4, cableados por F4 en urls.py). Las fases sin
#: dashboard propio (Ingeniería, Preliminares, SPT, Detalles Finales) no tienen
#: entrada → el template no muestra botón de drill-down para ellas.
DRILLDOWN_URL_NAMES = {
    'OBRA_CIVIL': 'construccion:dashboard_obra_civil',
    'MONTAJE': 'construccion:dashboard_montaje_real',
    'TENDIDO': 'construccion:dashboard_tendido',
}

#: Vista consolidada de torres (B4) — enlace global, no por fase.
VISTA_TORRES_URL_NAME = 'construccion:dashboard_vista_torres'

#: Fases del backbone con serie temporal real por torre (las que alimentan la
#: Curva S consolidada real). Las otras 4 fases no tienen un origen de avance
#: real distribuible en el tiempo (no rompen, simplemente no aportan curva).
FASES_CON_CURVA_REAL = (car.FASE_OOCC, car.FASE_MONTAJE, car.FASE_TENDIDO)


def _safe_reverse(name, **kwargs):
    """``reverse`` que devuelve None si el name aún no está registrado.

    En el entorno aislado de la sub-feature B5 los names de B1–B4 pueden no
    resolver todavía (F4 garantiza el wiring al integrar). El template degrada
    el enlace a deshabilitado en ese caso, sin romper la página.
    """
    if not name:
        return None
    try:
        return reverse(name, kwargs=kwargs)
    except NoReverseMatch:
        return None


def curva_s_consolidada_real(proyecto) -> dict:
    """Curva S consolidada REAL del proyecto agregando las fases con datos.

    A diferencia de ``calculators.curva_s_consolidada`` (que cuelga de
    ``DashboardAvanceSemanal``, solo 2 filas en prod), esta función agrega las
    series reales por torre de ``serie_curva_s_real`` para OOCC + Montaje +
    Tendido. Cada fase aporta su avance acumulado al global como promedio simple
    de las fases con datos en cada fecha (denominador = número de fases que ya
    tienen algún avance), de modo que el % consolidado nunca excede 100.

    Devuelve ``{'labels': [iso], 'ejecutado': [float]}``. Edge: proyecto sin
    avance real en ninguna fase → arreglos vacíos (NO error).
    """
    # incremento_por_fecha[fecha] = suma de los incrementos de cada fase en esa
    # fecha, dividido por el número total de fases con datos.
    series = []
    for fase in FASES_CON_CURVA_REAL:
        s = car.serie_curva_s_real(proyecto, fase)
        if s.get('labels'):
            series.append(s)

    if not series:
        return {'labels': [], 'ejecutado': []}

    n_fases = len(series)

    # Convertir cada curva acumulada de fase a incrementos por fecha.
    incrementos = defaultdict(float)
    fechas = set()
    for s in series:
        labels = s['labels']
        valores = s['ejecutado']
        prev = 0.0
        for i, fecha in enumerate(labels):
            actual = valores[i]
            incrementos[fecha] += (actual - prev) / n_fases
            prev = actual
            fechas.add(fecha)

    labels = sorted(fechas)
    ejecutado = []
    acum = 0.0
    for f in labels:
        acum += incrementos[f]
        ejecutado.append(round(acum, 2))
    return {'labels': labels, 'ejecutado': ejecutado}


class DashboardGeneralView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Dashboard GENERAL del proyecto — 7 fases + global ponderado + curva S real.

    URL: ``/<proyecto_id>/dashboard-general/`` (ver
    ``urls_dashboards_b5_general.py``).
    """

    template_name = 'construccion/dashboard_general.html'
    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = get_object_or_404(
            ProyectoConstruccion, id=self.kwargs['proyecto_id']
        )

        # 1) Las 7 fases + global ponderado (backbone puro, con fallback
        #    equiponderado si todos los pesos están en 0 — estado de prod).
        general = car.avance_general(proyecto)
        fases = general['fases']
        global_pct = general['global_pct']

        # Enriquecer cada fase con su URL de drill-down (si existe y resuelve).
        fases_ui = []
        for f in fases:
            drill = _safe_reverse(
                DRILLDOWN_URL_NAMES.get(f['seccion']),
                proyecto_id=proyecto.id,
            )
            fases_ui.append({
                'seccion': f['seccion'],
                'label': f['label'],
                'pct': f['pct'],
                'peso': f['peso'],
                'drill_url': drill,            # None si no hay dashboard / no resuelve
                'completa': f['pct'] >= 100.0,
            })

        # 2) Curva S consolidada real del proyecto.
        curva_real = curva_s_consolidada_real(proyecto)

        # Pesos efectivos: equiponderado si todos en 0 (mismo criterio del
        # backbone) — para que la UI explique de dónde sale el global.
        total_peso = sum(f['peso'] for f in fases)
        pesos_equiponderados = total_peso == 0

        # 3) Dataset pre-serializado para el chart global (#general-fases-chart)
        #    y para la curva S — guard es-CO: viaja como JSON, no floats inline.
        chart_payload = json.dumps({
            'fases': [
                {'label': f['label'], 'pct': f['pct'], 'seccion': f['seccion']}
                for f in fases_ui
            ],
            'global_pct': global_pct,
            'curva_s': curva_real,   # {'labels':[...], 'ejecutado':[...]}
        })

        ctx.update({
            'proyecto': proyecto,
            'fases': fases_ui,
            'global_pct': global_pct,
            'pesos_equiponderados': pesos_equiponderados,
            'tiene_avance': global_pct > 0,
            'tiene_curva_s': bool(curva_real['labels']),
            'vista_torres_url': _safe_reverse(
                VISTA_TORRES_URL_NAME, proyecto_id=proyecto.id
            ),
            'general_chart_json': chart_payload,
            'active_tab': 'dashboard_general',
        })
        return ctx
