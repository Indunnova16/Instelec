"""Dashboard de Montaje con avance REAL (#139 · B2).

Sub-feature B2 del bloque "Dashboards de fase". El dashboard de Montaje legacy
(``views.DashboardMontajeView`` → ``dashboard_curva_s.html``) cuelga de
``DashboardAvanceSemanal`` (solo 2 filas en prod) → sale en 0%. Esta vista usa
el backbone ``calculators_avance_real`` (S1) para cablear el avance REAL
ponderado por torre de Montaje (``MontajeEstructuraTorreDetalle.avance_ponderado``
con pesos 10/20/45/25) a:

  1. Curva S Montaje real (serie "Ejecutado" del avance real distribuido en el
     tiempo, NO del semanal) + "Planeado" del cronograma.
  2. Avance por etapa Montaje: Estructura en sitio 10% · Prearmada 20% ·
     Torre montada 45% · Revisada 25% (% de torres con la etapa completa).
  3. Vista por torre Montaje con drill-down a la pata de avance
     (``construccion:montaje_torre``).

Reusa el parcial base ``_dashboard_fase_base.html`` (S3) vía el template propio
``dashboard_montaje.html`` y AÑADE un canvas dedicado ``#montaje-etapas-chart``
(contrato del scope B2). Los datasets viajan PRE-SERIALIZADOS (guard es-CO:
nunca floats crudos ni JSON crudo en JS inline / x-data).

Coexiste con la URL legacy ``dashboard-montaje/`` (name ``dashboard_montaje``);
B2 registra ``dashboard-montaje-real/`` (name ``dashboard_montaje_real``) para
NO colisionar — ver ``urls_dashboards_b2_montaje.py``.
"""
from __future__ import annotations

import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from . import calculators_avance_real as car
from .models import ProyectoConstruccion
from .views import _DashboardCurvaSBase as _DashboardCurvaSBaseLegacy
from .views_dashboards import _DashboardCurvaSBase


class DashboardMontajeRealView(_DashboardCurvaSBase):
    """Dashboard de Montaje con avance real (Curva S + etapas + por torre).

    Hereda la base de avance real de ``views_dashboards`` (que ya inyecta
    ``curva_real_json`` para la fase indicada). B2 fija la fase MONTAJE y añade
    el avance por etapa y la vista por torre del backbone, más el dataset
    dedicado del chart de etapas de Montaje.
    """

    template_name = 'construccion/dashboard_montaje.html'
    FASE_DEFAULT = 'MONTAJE'
    FASE_BACKBONE = car.FASE_MONTAJE  # 'MONTAJE'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = ctx.get('proyecto')
        fase = car.FASE_MONTAJE

        # --- Avance por etapa Montaje (10/20/45/25) ---
        # Edge case: proyecto sin montaje → backbone devuelve [] (sin crash).
        avance_etapas = car.avance_por_etapa(proyecto, fase) if proyecto is not None else []

        # --- Vista por torre Montaje (drill-down a montaje_torre) ---
        # Edge case: proyecto sin torres/sin montaje → [] (la tabla muestra el
        # estado vacío del parcial base sin reventar).
        vista_torres = car.vista_por_torre(proyecto, fase) if proyecto is not None else []

        # "Sin datos" = no hay NINGUNA torre con avance de Montaje. OJO:
        # avance_por_etapa SIEMPRE devuelve las 4 etapas (al 0% si no hay datos),
        # así que NO sirve como señal de vacío; la señal real es vista_torres
        # vacía (no hay MontajeEstructuraTorreDetalle). Así el banner de estado
        # vacío aparece correctamente para un proyecto sin montaje.
        montaje_sin_datos = not vista_torres

        ctx.update({
            # Contexto que consume el parcial base _dashboard_fase_base.html.
            'fase_codigo': fase,
            'fase_label': 'Montaje',
            'avance_etapas': avance_etapas,
            'vista_torres': vista_torres,
            # Dataset dedicado del canvas #montaje-etapas-chart (guard es-CO:
            # json_script en el template, NUNCA floats crudos en JS inline).
            'montaje_etapas_json': json.dumps(avance_etapas),
            # Bandera de estado vacío para la UI (loading/success/empty).
            'montaje_sin_datos': montaje_sin_datos,
        })
        return ctx


class DashboardMontajeDatosGraficasView(_DashboardCurvaSBaseLegacy):
    """Endpoint JSON de las gráficas del Dashboard de Montaje real (#139 · B2).

    Sirve los datasets de la Curva S real + avance por etapa Montaje para
    refrescos async del front sin re-renderizar el template completo. Hereda la
    base legacy SOLO por los mixins de auth/rol (LoginRequired + RoleRequired);
    NO usa su ``get_context_data`` (responde JSON directo).

    Edge case: proyecto sin montaje → series/etapas vacías con HTTP 200 (NO 500).
    """

    template_name = 'construccion/dashboard_montaje.html'  # no se renderiza
    FASE_DEFAULT = 'MONTAJE'

    def get(self, request, *args, **kwargs):
        proyecto = get_object_or_404(ProyectoConstruccion, id=self.kwargs['proyecto_id'])
        fase = car.FASE_MONTAJE
        payload = {
            'fase': fase,
            'curva_real': {
                'ejecutado': car.serie_curva_s_real(proyecto, fase),
                'planeado': car.serie_planeado(proyecto, fase),
            },
            'avance_etapas': car.avance_por_etapa(proyecto, fase),
        }
        return JsonResponse(payload)
