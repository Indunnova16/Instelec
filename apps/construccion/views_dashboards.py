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

B1 (#139) EXTIENDE este archivo con ``DashboardObraCivilView`` real y mueve la
lógica de cableado. B2–B5 importan ``_DashboardCurvaSBase`` desde aquí para sus
propios dashboards de fase. NO duplicar la base en cada sub-feature.
"""
from __future__ import annotations

import json

from . import calculators_avance_real as car
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

        Devuelve un STRING JSON pre-serializado (guard es-CO: nunca floats
        crudos en JS inline). B1 lo consume como dataset principal de la Curva S
        de OC; B2/B3 para Montaje/Tendido.
        """
        ejecutado = car.serie_curva_s_real(proyecto, fase)
        planeado = car.serie_planeado(proyecto, fase)
        return json.dumps({
            'fase': fase,
            'ejecutado': ejecutado,   # {'labels':[...], 'ejecutado':[...]}
            'planeado': planeado,     # {'labels':[...], 'planeado':[...]}
        })

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
