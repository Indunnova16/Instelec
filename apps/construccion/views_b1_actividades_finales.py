"""B1 — Views para la matriz de Actividades Finales.

URLs (registradas en urls_b1_actividades_finales.py):
- /construccion/<uuid:proyecto_id>/actividades-finales/                       (lista matriz)
- /construccion/<uuid:proyecto_id>/actividades-finales/<uuid:torre_id>/toggle/  (HTMX toggle de un campo)
- /construccion/<uuid:proyecto_id>/actividades-finales/<uuid:torre_id>/obs/      (POST observaciones)

La vista matriz reemplaza el placeholder eliminado por F2.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Prefetch
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_POST

from apps.core.mixins import RoleRequiredMixin

from .models import ProyectoConstruccion, TorreConstruccion
from .models_b1_actividades_finales import (
    ACTIVIDAD_CAMPOS,
    SECCIONES_ACTIVIDADES,
    ActividadFinalTorre,
)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _ensure_actividades(torre: TorreConstruccion) -> ActividadFinalTorre:
    """Devuelve (creando si no existe) el ActividadFinalTorre de la torre.
    Para que torres legacy (creadas antes de B1) funcionen sin migration de datos.
    """
    af, _ = ActividadFinalTorre.objects.get_or_create(torre=torre)
    return af


def _filas_proyecto(proyecto: ProyectoConstruccion, filtros: dict | None = None):
    """Lista de dicts [{torre, af, celdas}] lista para renderizar la matriz.
    Aplica filtros (estructura/estado) si vienen del querystring.
    """
    filtros = filtros or {}
    torres_qs = (
        proyecto.torres
        .all()
        .prefetch_related(
            Prefetch(
                'actividades_finales',
                queryset=ActividadFinalTorre.objects.all(),
            )
        )
        .order_by('numero')
    )

    estructura_filtro = (filtros.get('estructura') or '').strip()
    if estructura_filtro:
        torres_qs = torres_qs.filter(numero__icontains=estructura_filtro)

    filas = []
    for torre in torres_qs:
        af = _ensure_actividades(torre)
        celdas = [
            {
                'campo': campo,
                'valor': getattr(af, campo),
                'letra': letra,
                'label': label,
            }
            for _sec, _seclabel, columnas in SECCIONES_ACTIVIDADES
            for (campo, label, letra) in columnas
        ]
        filas.append({'torre': torre, 'af': af, 'celdas': celdas})

    estado_filtro = (filtros.get('estado') or '').strip().upper()
    if estado_filtro:
        filas = [f for f in filas if f['af'].estado_semaforo == estado_filtro]

    return filas


def _resumen(filas) -> dict:
    """% global + conteos por estado."""
    if not filas:
        return {
            'total_torres': 0,
            'pct_global': 0.0,
            'completadas': 0,
            'no_iniciadas': 0,
            'en_proceso': 0,
            'bloqueadas': 0,
        }
    total = len(filas)
    suma_pct = sum(f['af'].pct_avance for f in filas)
    completadas = sum(1 for f in filas if f['af'].estado_semaforo == 'COMPLETADO')
    no_iniciadas = sum(1 for f in filas if f['af'].estado_semaforo == 'NO_INICIADO')
    en_proceso = sum(1 for f in filas if f['af'].estado_semaforo == 'EN_PROCESO')
    bloqueadas = sum(1 for f in filas if f['af'].estado_semaforo == 'BLOQUEADO')
    return {
        'total_torres': total,
        'pct_global': suma_pct / total if total else 0.0,
        'completadas': completadas,
        'no_iniciadas': no_iniciadas,
        'en_proceso': en_proceso,
        'bloqueadas': bloqueadas,
    }


# ----------------------------------------------------------------------
# Vistas
# ----------------------------------------------------------------------

class ActividadesFinalesMatrizView(LoginRequiredMixin, RoleRequiredMixin, View):
    """Matriz 14 columnas × N torres con headers de sección colspan y toggle HTMX."""

    template_name = 'construccion/actividades_finales.html'

    def get(self, request, proyecto_id, *args, **kwargs):
        proyecto = get_object_or_404(ProyectoConstruccion, pk=proyecto_id)
        filtros = {
            'estructura': request.GET.get('estructura', ''),
            'estado': request.GET.get('estado', ''),
        }
        filas = _filas_proyecto(proyecto, filtros)
        context = {
            'proyecto': proyecto,
            'filas': filas,
            'secciones': SECCIONES_ACTIVIDADES,
            'resumen': _resumen(filas),
            'filtros': filtros,
            'estados_choices': [
                ('', 'Todos'),
                ('NO_INICIADO', 'No iniciado'),
                ('EN_PROCESO', 'En proceso'),
                ('BLOQUEADO', 'Bloqueado'),
                ('COMPLETADO', 'Completado'),
            ],
        }
        return render(request, self.template_name, context)


@method_decorator(require_POST, name='dispatch')
class ActividadFinalToggleView(LoginRequiredMixin, RoleRequiredMixin, View):
    """HTMX toggle de un campo BooleanField del ActividadFinalTorre.
    Espera POST con campo `campo` (slug del campo) y opcionalmente `valor`.
    Si `valor` no viene, alterna el booleano.

    Devuelve el partial de la fila completa (`_actividades_finales_row.html`)
    para que HTMX reemplace toda la fila — así el % avance y el badge de
    estado se actualizan junto con la celda toggleada.

    Errores de validación (ej. G sin F) → HTTP 400 con mensaje legible.
    """

    template_name = 'construccion/_actividades_finales_row.html'

    def post(self, request, proyecto_id, torre_id, *args, **kwargs):
        proyecto = get_object_or_404(ProyectoConstruccion, pk=proyecto_id)
        torre = get_object_or_404(TorreConstruccion, pk=torre_id, proyecto=proyecto)
        af = _ensure_actividades(torre)

        campo = request.POST.get('campo', '').strip()
        if campo not in ACTIVIDAD_CAMPOS:
            return HttpResponseBadRequest(f"Campo desconocido: {campo}")

        # Si `valor` no viene → toggle. Si viene → set explícito.
        raw = request.POST.get('valor')
        if raw is None:
            nuevo = not getattr(af, campo)
        else:
            nuevo = raw in ('1', 'true', 'True', 'on', 'yes')

        setattr(af, campo, nuevo)
        try:
            af.save()
        except ValidationError as e:
            # Mensaje legible para HTMX response
            mensaje = ' / '.join(
                f"{k}: {' '.join(v) if isinstance(v, list) else v}"
                for k, v in e.message_dict.items()
            ) if hasattr(e, 'message_dict') else str(e)
            resp = HttpResponse(
                f'<div class="text-red-600 text-xs p-2 bg-red-50 dark:bg-red-900/30 rounded">'
                f'⚠️ {mensaje}</div>',
                status=400,
            )
            # HTMX trigger para mostrar toast
            resp['HX-Trigger'] = '{"showError":' + repr(mensaje).replace("'", '"') + '}'
            return resp

        # Render fila refrescada
        celdas = [
            {
                'campo': c,
                'valor': getattr(af, c),
                'letra': letra,
                'label': label,
            }
            for _sec, _seclabel, columnas in SECCIONES_ACTIVIDADES
            for (c, label, letra) in columnas
        ]
        fila = {'torre': torre, 'af': af, 'celdas': celdas}
        return render(request, self.template_name, {
            'fila': fila,
            'proyecto': proyecto,
            'secciones': SECCIONES_ACTIVIDADES,
        })


@method_decorator(require_POST, name='dispatch')
class ActividadFinalObservacionesView(LoginRequiredMixin, RoleRequiredMixin, View):
    """POST de observaciones libres (textarea inline)."""

    def post(self, request, proyecto_id, torre_id, *args, **kwargs):
        torre = get_object_or_404(
            TorreConstruccion, pk=torre_id, proyecto_id=proyecto_id,
        )
        af = _ensure_actividades(torre)
        af.observaciones = request.POST.get('observaciones', '')[:5000]
        af.save()
        return HttpResponse(
            f'<span class="text-xs text-green-600 dark:text-green-400">Guardado ✓</span>'
        )
