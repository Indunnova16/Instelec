"""B4 — Vista por torre CONSOLIDADA (cross-fase) + drill-down JSON (#139).

Reúne en una sola tabla, por torre, el avance de las TRES fases del proyecto
(Obra Civil / Montaje / Tendido) reusando el backbone S1 de B1
(``calculators_avance_real.vista_por_torre(proyecto, fase)``). Cada fila es una
torre con su % por fase + estado 100% / pendiente, y un % global por torre
(promedio de las fases con avance registrado).

Expone además un endpoint drill-down JSON reusable por B1/B2/B3 que, dado
``?torre=<id>&fase=<OOCC|MONTAJE|TENDIDO>``, devuelve el detalle de lo atrasado
(etapas pendientes) de esa torre en esa fase — "el punto bajo / lo atrasado".

GUARDS es-CO (memorias recurrentes del portafolio):
  - La tabla viaja en el contexto como dicts/listas (Django escapa); NO se
    inyectan floats crudos ni JSON crudo en JS inline. El payload para el JS
    viaja pre-serializado con ``json_script`` desde el template.
  - El drill-down responde ``JsonResponse`` (Content-Type application/json),
    no HTML con números localizados.
  - Edge: una torre sin avance en una fase → ``pct=0``, ``completa=False``,
    ``registrada=False`` (no error, no fila fantasma).
"""
from __future__ import annotations

import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.views.generic import TemplateView, View

from apps.core.mixins import RoleRequiredMixin

from . import calculators_avance_real as car
from .models import ProyectoConstruccion
from .views import ALL_ADMIN_ROLES, OPERARIO_ROLES

# Fases que componen la vista consolidada, en orden de presentación.
# (codigo backbone, label humano)
FASES_CONSOLIDADO = [
    (car.FASE_OOCC, 'Obra Civil'),
    (car.FASE_MONTAJE, 'Montaje'),
    (car.FASE_TENDIDO, 'Tendido'),
]
FASES_VALIDAS = {c for c, _ in FASES_CONSOLIDADO}


def _label_fase(codigo: str) -> str:
    """Etiqueta humana de una fase backbone (o el código si es desconocida)."""
    codigo = (codigo or '').upper()
    for c, label in FASES_CONSOLIDADO:
        if c == codigo:
            return label
    return codigo


def construir_vista_torres_consolidada(proyecto) -> dict:
    """Pivota ``vista_por_torre`` de las 3 fases a una matriz torre × fase.

    Devuelve::

        {
          'fases': [{'codigo','label'}, ...],            # encabezados de columna
          'torres': [                                    # una fila por torre
              {
                'torre_id', 'numero',
                'global_pct': float,                     # promedio de fases con avance
                'completa_global': bool,                 # todas las fases con avance al 100%
                'celdas': {
                    'OOCC':    {'pct','completa','registrada','pendientes':[...]},
                    'MONTAJE': {...},
                    'TENDIDO': {...},
                },
              }, ...
          ],
        }

    Una torre aparece si tiene avance registrado en AL MENOS una fase. Si una
    fase no tiene registro para esa torre, su celda es
    ``{'pct':0.0,'completa':False,'registrada':False,'pendientes':[]}`` —
    edge "torre sin avance en una fase" resuelto como pendiente, NO como error.
    """
    # 1. vista_por_torre por cada fase, indexado por torre_id.
    por_fase = {}
    numeros = {}
    for codigo, _label in FASES_CONSOLIDADO:
        filas = car.vista_por_torre(proyecto, codigo)
        idx = {}
        for fila in filas:
            tid = fila['torre_id']
            idx[tid] = fila
            # El número de torre es estable cross-fase; guardamos el primero.
            numeros.setdefault(tid, fila.get('numero', ''))
        por_fase[codigo] = idx

    # 2. Universo de torres = unión de las torres con avance en cualquier fase.
    torre_ids = set()
    for idx in por_fase.values():
        torre_ids.update(idx.keys())

    # 3. Construir una fila por torre con sus 3 celdas.
    torres_out = []
    for tid in torre_ids:
        celdas = {}
        pcts_con_avance = []
        completas_flags = []
        for codigo, _label in FASES_CONSOLIDADO:
            fila = por_fase[codigo].get(tid)
            if fila is None:
                # Torre sin avance registrado en esta fase.
                celdas[codigo] = {
                    'pct': 0.0,
                    'completa': False,
                    'registrada': False,
                    'pendientes': [],
                }
                completas_flags.append(False)
            else:
                pct = float(fila.get('pct', 0.0))
                celdas[codigo] = {
                    'pct': pct,
                    'completa': bool(fila.get('completa', False)),
                    'registrada': True,
                    'pendientes': list(fila.get('pendientes', [])),
                }
                pcts_con_avance.append(pct)
                completas_flags.append(bool(fila.get('completa', False)))

        global_pct = (round(sum(pcts_con_avance) / len(pcts_con_avance), 2)
                      if pcts_con_avance else 0.0)
        torres_out.append({
            'torre_id': tid,
            'numero': numeros.get(tid, ''),
            'global_pct': global_pct,
            # "completa_global" solo si TODAS las fases del consolidado están al 100%.
            'completa_global': all(completas_flags) and bool(completas_flags),
            'celdas': celdas,
        })

    # Orden por número de torre (igual criterio que el backbone).
    torres_out.sort(key=lambda r: str(r['numero']))

    return {
        'fases': [{'codigo': c, 'label': l} for c, l in FASES_CONSOLIDADO],
        'torres': torres_out,
    }


def detalle_drilldown_torre(proyecto, torre_id, fase) -> dict:
    """Detalle del "punto bajo / lo atrasado" de una torre en una fase.

    Reusa ``vista_por_torre`` (mismo origen que la tabla) y extrae la fila de la
    torre solicitada. Devuelve un dict serializable::

        {
          'torre_id', 'numero', 'fase', 'fase_label',
          'pct': float, 'completa': bool, 'registrada': bool,
          'pendientes': [labels],   # etapas atrasadas (lo que falta)
          'total_pendientes': int,
        }

    Edge:
      - fase inválida → ValueError (la view lo traduce a HTTP 400).
      - torre sin avance en la fase → ``registrada=False``, ``pendientes=[]``
        (no es un error: simplemente no hay registro de avance todavía).
    """
    fase = (fase or '').upper()
    if fase not in FASES_VALIDAS:
        raise ValueError(f"Fase inválida: {fase!r}. Use una de {sorted(FASES_VALIDAS)}.")

    # torre_id es un UUID (PK de TorreConstruccion). Llega como str por el
    # querystring; comparamos por su representación string contra el backbone
    # (cuyo torre_id puede ser UUID). NO forzar int (rompía con PK UUID).
    if torre_id in (None, ''):
        raise ValueError(f"torre inválida: {torre_id!r}")
    tid_str = str(torre_id)

    filas = car.vista_por_torre(proyecto, fase)
    fila = next((f for f in filas if str(f['torre_id']) == tid_str), None)

    if fila is None:
        # Torre sin avance registrado en esta fase → pendiente, no error.
        numero = ''
        from .models import TorreConstruccion
        torre = TorreConstruccion.objects.filter(
            proyecto=proyecto, id=tid_str).first()
        if torre is not None:
            numero = torre.numero
        return {
            'torre_id': tid_str,
            'numero': numero,
            'fase': fase,
            'fase_label': _label_fase(fase),
            'pct': 0.0,
            'completa': False,
            'registrada': False,
            'pendientes': [],
            'total_pendientes': 0,
        }

    pendientes = list(fila.get('pendientes', []))
    return {
        'torre_id': tid_str,
        'numero': fila.get('numero', ''),
        'fase': fase,
        'fase_label': _label_fase(fase),
        'pct': float(fila.get('pct', 0.0)),
        'completa': bool(fila.get('completa', False)),
        'registrada': True,
        'pendientes': pendientes,
        'total_pendientes': len(pendientes),
    }


class DashboardVistaTorresView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Dashboard consolidado: tabla torre × fase (OC / Montaje / Tendido).

    Una fila por torre con el % y estado (100% / pendiente) de cada fase y un %
    global. Cada celda enlaza al drill-down (lo atrasado por torre+fase).
    """
    template_name = 'construccion/dashboard_vista_torres.html'
    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = get_object_or_404(
            ProyectoConstruccion, id=self.kwargs['proyecto_id'])
        consolidado = construir_vista_torres_consolidada(proyecto)

        # Resumen por fase (para tarjetas / leyenda): cuántas torres al 100%.
        resumen_fases = []
        for f in consolidado['fases']:
            codigo = f['codigo']
            registradas = [t for t in consolidado['torres']
                           if t['celdas'][codigo]['registrada']]
            completas = sum(1 for t in registradas
                            if t['celdas'][codigo]['completa'])
            resumen_fases.append({
                'codigo': codigo,
                'label': f['label'],
                'completas': completas,
                'registradas': len(registradas),
            })

        from django.urls import reverse
        drilldown_url = reverse(
            'construccion:dashboard_drilldown_torre',
            kwargs={'proyecto_id': proyecto.id})

        ctx.update({
            'proyecto': proyecto,
            'active_tab': 'vista_torres',
            'fases': consolidado['fases'],
            'torres': consolidado['torres'],
            'resumen_fases': resumen_fases,
            'total_torres': proyecto.torres.count() or 0,
            'torres_con_avance': len(consolidado['torres']),
            # Guard es-CO: la config viaja pre-serializada vía json_script en el
            # template (NO JSON crudo en x-data / JS inline).
            'drilldown_cfg': json.dumps({'drilldown_url': drilldown_url}),
        })
        return ctx


class DrilldownTorreFaseView(LoginRequiredMixin, RoleRequiredMixin, View):
    """Endpoint drill-down JSON reusable: detalle de lo atrasado por torre+fase.

    GET ``?torre=<id>&fase=<OOCC|MONTAJE|TENDIDO>`` →
        200 JSON ``{ok:true, detalle:{torre_id,numero,fase,fase_label,pct,
               completa,registrada,pendientes:[...],total_pendientes}}``
        400 si falta/es inválido ``torre`` o ``fase``.

    Con ``&format=html`` devuelve el parcial ``_drilldown_torre.html`` ya
    renderizado (mismo ``detalle``) para que B1/B2/B3 lo inyecten directo en su
    panel vía htmx/fetch sin re-armar el HTML.

    Reusable por B1/B2/B3: cualquiera de los dashboards de fase puede pegarle
    para mostrar "el punto bajo / lo atrasado" de una torre sin recalcular.
    """
    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES

    def get(self, request, proyecto_id, *args, **kwargs):
        proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)

        torre_id = request.GET.get('torre')
        fase = request.GET.get('fase')
        quiere_html = request.GET.get('format') == 'html'

        if not torre_id:
            return self._error("Falta el parámetro 'torre'.", quiere_html)
        if not fase:
            return self._error("Falta el parámetro 'fase'.", quiere_html)

        try:
            detalle = detalle_drilldown_torre(proyecto, torre_id, fase)
        except ValueError as exc:
            return self._error(str(exc), quiere_html)

        if quiere_html:
            html = render_to_string(
                'construccion/partials/_drilldown_torre.html',
                {'detalle': detalle}, request=request)
            from django.http import HttpResponse
            return HttpResponse(html)

        return JsonResponse({'ok': True, 'detalle': detalle})

    @staticmethod
    def _error(mensaje, quiere_html):
        if quiere_html:
            from django.http import HttpResponse
            html = render_to_string(
                'construccion/partials/_drilldown_torre.html',
                {'detalle': None, 'error': mensaje})
            return HttpResponse(html, status=400)
        return JsonResponse({'ok': False, 'error': mensaje}, status=400)
