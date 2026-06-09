"""Dashboard de Tendido (Conductor + Fibra OPGW) — B3 (#139).

Tercer dashboard de fase del bloque dashboards. Replica el patrón del Dashboard
de Obra Civil (B1) sobre el backbone real ``calculators_avance_real`` para que la
Curva S "Ejecutado" deje de salir en 0% (hoy cuelga de ``DashboardAvanceSemanal``,
solo 2 filas en prod) y refleje el avance REAL por torre de Tendido.

Particularidad de Tendido frente a OC/Montaje: el avance se compone de DOS
secciones independientes con SUMPRODUCT propio —

  - **Conductor** (6 etapas ponderadas): Riega manila · Riega guaya ·
    Tendido conductor · Grapado · Accesorios · Balizas
    (``TendidoTorre.avance_conductor``).
  - **Fibra OPGW** (5 etapas ponderadas): Riega manila fibra · Riega guaya OPGW ·
    Tendido OPGW · Grapado fibra · Empalmes OPGW
    (``TendidoTorre.avance_fibra``).

Por eso el dashboard expone DOS gráficas de avance por etapa
(``#tendido-conductor-chart`` + ``#tendido-fibra-chart``) en vez de una sola, y la
Curva S real promedia ambas secciones por torre
(``serie_curva_s_real(proyecto,'TENDIDO')`` ya las pondera 50/50).

Vista por torre: ``vista_por_torre(proyecto,'TENDIDO')`` combina las pendientes de
ambos sets. Cada fila enlaza al detalle ``construccion:tendido_torre`` (drill-down).

GUARDS es-CO (memorias recurrentes del portafolio): todos los datasets viajan
PRE-SERIALIZADOS vía ``json.dumps`` + ``{{ ...|json_script }}`` en el template
(nunca floats crudos ni JSON crudo en JS inline / x-data). La vista NO emite
floats al JS; el template los lee con ``JSON.parse(...textContent)``.
"""
from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View

from apps.core.mixins import RoleRequiredMixin

from . import calculators_avance_real as car
from .models import ProyectoConstruccion
from .views import ALL_ADMIN_ROLES, OPERARIO_ROLES
from .views_dashboards import _DashboardCurvaSBase


class DashboardTendidoView(_DashboardCurvaSBase):
    """Dashboard Curva S de Tendido (#139) — Conductor + Fibra OPGW.

    Extiende ``_DashboardCurvaSBase`` (que ya inyecta ``curva_real_json`` con la
    serie real ejecutado/planeado de la fase) y añade:

      - ``avance_conductor`` / ``avance_fibra``: las dos listas de avance por
        etapa (``avance_por_etapa_tendido``) para las 2 gráficas.
      - ``vista_torres``: avance por torre con pendientes combinadas y drill-down.
      - JSONs pre-serializados (``etapas_tendido_json``) para el render Chart.js.

    Robusto ante proyecto sin torres / sin tendido: el backbone devuelve listas
    con pct=0 y la vista por torre vacía — HTTP 200 siempre, sin 500.
    """

    template_name = 'construccion/dashboard_tendido.html'
    FASE_DEFAULT = 'TENDIDO'
    FASE_BACKBONE = car.FASE_TENDIDO

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = ctx['proyecto']

        etapas = car.avance_por_etapa_tendido(proyecto)
        avance_conductor = etapas.get('conductor', [])
        avance_fibra = etapas.get('fibra', [])
        vista_torres = car.vista_por_torre(proyecto, car.FASE_TENDIDO)

        # % global de cada sección (promedio del avance real por torre) — para las
        # tarjetas resumen. Derivado del real, NO del semanal vacío.
        pct_conductor, pct_fibra = self._pct_secciones(proyecto)

        ctx.update({
            'fase_codigo': car.FASE_TENDIDO,
            'fase_label': 'Tendido',
            'avance_conductor': avance_conductor,
            'avance_fibra': avance_fibra,
            'vista_torres': vista_torres,
            'pct_conductor': pct_conductor,
            'pct_fibra': pct_fibra,
            # El parcial base (_dashboard_fase_base.html) hace
            # ``{{ curva_real_json|json_script:... }}`` y su JS lee
            # ``curva.ejecutado`` / ``curva.planeado``. ``json_script`` espera un
            # OBJETO (lo serializa él); si le pasáramos el string que produce
            # ``_DashboardCurvaSBase.build_curva_real`` quedaría doble-codificado
            # (JSON.parse devolvería un string, no el dict) y la Curva S no
            # pintaría. Por eso sobreescribimos con un dict con las claves que el
            # parcial espera. Guard es-CO igualmente cubierto: json_script escapa
            # y no hay floats crudos en el JS inline.
            'curva_real_json': {
                'ejecutado': car.serie_curva_s_real(proyecto, car.FASE_TENDIDO),
                'planeado': car.serie_planeado(proyecto, car.FASE_TENDIDO),
            },
            # Para que el parcial base NO pinte su gráfica genérica de etapas
            # (B3 usa dos charts propios) le pasamos avance_etapas vacío.
            'avance_etapas': [],
            # Datasets para el Chart.js de las 2 gráficas de etapa de B3. Se
            # pasa como dict (no string): el template usa ``json_script`` para
            # serializarlo de forma segura (guard es-CO; sin floats crudos en JS
            # inline). Pasar un string aquí lo doble-codificaría.
            'etapas_tendido': {
                'conductor': avance_conductor,
                'fibra': avance_fibra,
            },
        })
        return ctx

    @staticmethod
    def _pct_secciones(proyecto):
        """(% conductor, % fibra) global = promedio del avance real por torre.

        Reusa las properties del modelo (``avance_conductor``/``avance_fibra``,
        0..1). Divide por el total de torres del proyecto (no solo las que tienen
        registro de tendido) para ser coherente con la Curva S real. Si no hay
        torres, devuelve (0.0, 0.0). NUNCA 500.
        """
        n = proyecto.torres.count() or 0
        if n == 0:
            return 0.0, 0.0
        torres = list(
            proyecto.tendido_torres.select_related('proyecto', 'torre').all()
        )
        if not torres:
            return 0.0, 0.0
        suma_c = sum(float(t.avance_conductor) for t in torres)
        suma_f = sum(float(t.avance_fibra) for t in torres)
        return round((suma_c / n) * 100, 2), round((suma_f / n) * 100, 2)


class DashboardTendidoDataView(LoginRequiredMixin, RoleRequiredMixin, View):
    """GET JSON con los datos de las gráficas del Dashboard de Tendido (#139).

    Single source of truth para el refresh/AJAX y el contrato que valida el E2E:
      - ``curva_s``: serie real ejecutado + planeado de la fase TENDIDO.
      - ``avance_conductor`` / ``avance_fibra``: % torres completas por etapa.
      - ``vista_torres``: avance por torre + pendientes.

    Robusto: proyecto sin torres → listas vacías, HTTP 200 (nunca 500).
    """
    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES

    def get(self, request, proyecto_id, *args, **kwargs):
        proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)
        etapas = car.avance_por_etapa_tendido(proyecto)
        return JsonResponse({
            'curva_s': {
                'ejecutado': car.serie_curva_s_real(proyecto, car.FASE_TENDIDO),
                'planeado': car.serie_planeado(proyecto, car.FASE_TENDIDO),
            },
            'avance_conductor': etapas.get('conductor', []),
            'avance_fibra': etapas.get('fibra', []),
            'vista_torres': car.vista_por_torre(proyecto, car.FASE_TENDIDO),
        })
