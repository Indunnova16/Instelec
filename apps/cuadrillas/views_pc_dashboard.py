"""
Dashboard de rendimiento por cuadrilla (#155).

Sub-feature B4 del bloque `programacion_cuadrillas`. Una sola vista
(`ProgramacionCuadrillaDashboardView`) que muestra el cumplimiento por cuadrilla
× semana: torres programadas vs ejecutadas y el rendimiento (%), con filtro
opcional por rango de semanas / año.

URL name del contrato (cableado por B1 en `urls_pc.py`):
    construccion:programacion_cuadrillas_dashboard

Guards (memorias del portafolio, instelec #139/#141):
  - Los datos para la gráfica viajan al template como objeto Python y se
    serializan ahí con `json_script` (NO `json.dumps` en la vista + interpolar,
    NO float crudo en JS inline). El template lee con `JSON.parse(textContent)`.
  - El rendimiento NO se denormaliza: lo calcula `calculators_pc` desde
    ejecutadas/programadas (la propiedad del modelo).
  - Acceso: LoginRequired + RoleRequired (roles construcción).
"""
from __future__ import annotations

from datetime import date

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from apps.core.mixins import RoleRequiredMixin

from . import calculators_pc
from .models_pc import ProgramacionSemanalCuadrilla


def _parse_int(value, default=None):
    """Convierte un querystring a int; devuelve `default` si vacío/inválido."""
    if value in (None, ''):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class ProgramacionCuadrillaDashboardView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Tabla rendimiento cuadrilla × semana + gráfica resumen por cuadrilla.

    Filtros GET (todos opcionales):
      - ``anio``         — año ISO a mostrar (default: año actual).
      - ``semana_desde`` — semana ISO inicial del rango (inclusive).
      - ``semana_hasta`` — semana ISO final del rango (inclusive).

    Edge cases:
      - Sin datos para el filtro → tabla/gráfica vacías con mensaje, HTTP 200.
      - Rango invertido (desde > hasta) → se normaliza (swap) en vez de devolver
        vacío silencioso.
      - Parámetros no numéricos → se ignoran (caen al default), no 500.
    """

    template_name = 'construccion/programacion_cuadrilla_dashboard.html'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'supervisor']

    def get_filtros(self):
        """Lee y normaliza los filtros del querystring."""
        params = self.request.GET
        anio = _parse_int(params.get('anio'), default=date.today().year)
        desde = _parse_int(params.get('semana_desde'))
        hasta = _parse_int(params.get('semana_hasta'))

        # Normalizar rango invertido (desde > hasta) → swap.
        if desde is not None and hasta is not None and desde > hasta:
            desde, hasta = hasta, desde

        return {'anio': anio, 'semana_desde': desde, 'semana_hasta': hasta}

    def get_queryset(self, filtros):
        qs = ProgramacionSemanalCuadrilla.objects.select_related(
            'cuadrilla', 'ejecucion'
        )
        if filtros['anio'] is not None:
            qs = qs.filter(anio=filtros['anio'])
        if filtros['semana_desde'] is not None:
            qs = qs.filter(semana__gte=filtros['semana_desde'])
        if filtros['semana_hasta'] is not None:
            qs = qs.filter(semana__lte=filtros['semana_hasta'])
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filtros = self.get_filtros()

        qs = self.get_queryset(filtros)
        filas = calculators_pc.rendimiento_por_cuadrilla(qs)
        resumen = calculators_pc.resumen_por_cuadrilla(filas)

        # Totales del periodo (cabecera).
        total_prog = sum(f['torres_programadas'] for f in filas)
        total_ejec = sum(f['torres_ejecutadas'] for f in filas)
        rendimiento_global = (
            round(total_ejec / total_prog * 100, 1) if total_prog > 0 else 0.0
        )

        # Payload para la gráfica: objeto Python crudo. El template lo serializa
        # con json_script (NO serializar acá → evita doble-encoding #139).
        chart_data = {
            'labels': [r['cuadrilla'] for r in resumen],
            'rendimiento': [r['rendimiento_pct'] for r in resumen],
        }

        context.update({
            'filas': filas,
            'resumen': resumen,
            'chart_data': chart_data,
            'filtros': filtros,
            'anio': filtros['anio'],
            'semana_desde': filtros['semana_desde'],
            'semana_hasta': filtros['semana_hasta'],
            'total_programadas': total_prog,
            'total_ejecutadas': total_ejec,
            'rendimiento_global': rendimiento_global,
            'total_cuadrillas': len(resumen),
        })
        return context
