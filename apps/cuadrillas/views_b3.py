"""
B3 — Filtro cuadrillas desactivadas + reactivar.

Issue: Indunnova16/Instelec#104.

Estrategia: el `path('', views.CuadrillaListView.as_view(), name='lista')`
ya está cableado en `urls.py` de cuadrillas y no podemos reemplazarlo
(orden de resolución de Django). Por eso parchamos en runtime:

  - `CuadrillaListView.get_queryset` para leer `?filtro=activas|inactivas|todas`
    (default `activas` por retro-compatibilidad).
  - `CuadrillaListView.get_context_data` para inyectar contadores y el filtro
    actual al template.

Y agregamos rutas nuevas:

  - `POST /cuadrillas/<uuid>/reactivar/` → CuadrillaReactivateView
  - `POST /cuadrillas/<uuid>/desactivar/` → CuadrillaDeactivateView (auditoría)
"""
from collections import OrderedDict
import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Case, IntegerField, Q, Value, When
from django.db.models.functions import Cast, Substr
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils import timezone
from django.views import View

from apps.core.mixins import RoleRequiredMixin
from . import views as _legacy_views
from .filtros import (
    aplicar_filtros_queryset,
    choices_actividades,
    choices_lineas,
    resolver_filtros,
)
from .models import Cuadrilla, TrackingUbicacion


# ---------------------------------------------------------------------------
# Monkey-patch CuadrillaListView.get_queryset / get_context_data para incluir
# filtro=activas|inactivas|todas. Mantiene compatibilidad: sin parámetro →
# muestra solo activas (comportamiento legacy).
# ---------------------------------------------------------------------------

_ORIG_GET_QUERYSET = _legacy_views.CuadrillaListView.get_queryset
_ORIG_GET_CONTEXT = _legacy_views.CuadrillaListView.get_context_data


def _b3_get_queryset(self):
    """Listado actual/futuro + filtros de estado, código y programación.

    ``/cuadrillas/`` es el tablero operativo: no debe volver a mostrar
    cuadrillas de semanas ISO pasadas. El historial queda deliberadamente en
    ``/cuadrillas/semanal/<anio>/<semana>/``; por eso el corte se hace en el
    queryset de esta vista y no en los helpers de programación semanal.
    """
    filtro = self.request.GET.get('filtro', 'activas').strip().lower()
    if filtro not in ('activas', 'inactivas', 'todas'):
        filtro = 'activas'

    qs = Cuadrilla.objects.all().select_related(
        'supervisor', 'vehiculo', 'linea_asignada', 'tipo_actividad', 'desactivado_por',
    ).prefetch_related('miembros__usuario')

    if filtro == 'activas':
        qs = qs.filter(activa=True)
    elif filtro == 'inactivas':
        qs = qs.filter(activa=False)

    codigo = self.request.GET.get('codigo', '').strip()
    if codigo:
        qs = qs.filter(codigo__icontains=codigo)

    # Issue #218 (A2-A6): semana/línea/actividad/fecha, sistema de filtros
    # ÚNICO compartido con la pantalla de importación (ver apps/cuadrillas/
    # filtros.py). Se combinan con AND (intersección), no OR.
    filtros = resolver_filtros(self.request.GET)
    qs = aplicar_filtros_queryset(qs, filtros)

    # Issue #223: conservar únicamente semanas ISO actual/futuras. Extraemos
    # año y semana del código ``WW-YYYY-...`` para que el límite siga siendo
    # correcto al pasar de diciembre a enero; comparar el código como texto
    # produciría falsos positivos (p. ej. 52-2025 > 32-2026).
    #
    # Códigos legacy/especiales (``28-Apoyo Sede-011``, ``28-Avisos SC-010``,
    # ``NN-ACTIVIDAD-00#``) NO siguen el formato ``WW-YYYY-...`` — castear su
    # substring a INTEGER revienta la query completa con un error SQL real
    # (500 en /cuadrillas/, no un 0 resultados). ``Case/When`` con Postgres
    # NO evalúa la rama no tomada (mismo mecanismo que evita división por
    # cero en SQL) — los códigos malformados nunca llegan al Cast y quedan
    # con año=9999 (siempre "futuro", visibles por default en vez de ocultos).
    iso_hoy = timezone.localdate().isocalendar()
    formato_semana_valido = Q(codigo__regex=r'^\d{2}-\d{4}-')
    qs = qs.annotate(
        _b3_semana_iso=Case(
            When(formato_semana_valido, then=Cast(Substr("codigo", 1, 2), IntegerField())),
            default=Value(0),
            output_field=IntegerField(),
        ),
        _b3_anio_iso=Case(
            When(formato_semana_valido, then=Cast(Substr("codigo", 4, 4), IntegerField())),
            default=Value(9999),
            output_field=IntegerField(),
        ),
    ).filter(
        Q(_b3_anio_iso__gt=iso_hoy.year)
        | Q(_b3_anio_iso=iso_hoy.year, _b3_semana_iso__gte=iso_hoy.week)
    )

    # exposed para que get_context_data sepa el filtro actual sin re-parsear
    self._b3_filtro_actual = filtro
    self._b3_filtros_cuadrilla = filtros
    return qs


def _b3_get_context_data(self, **kwargs):
    """Inyectar contadores y filtro actual al contexto."""
    context = _ORIG_GET_CONTEXT(self, **kwargs)
    filtro_actual = getattr(self, '_b3_filtro_actual', 'activas')
    filtros_cuadrilla = getattr(self, '_b3_filtros_cuadrilla', resolver_filtros(self.request.GET))

    # contadores globales del tri-state activas/inactivas/todas (NO afectados
    # por semana/línea/actividad/fecha -- son las etiquetas de los 3 tabs de
    # _filtro_estado.html, deben seguir mostrando el universo completo).
    total_activas = Cuadrilla.objects.filter(activa=True).count()
    total_inactivas = Cuadrilla.objects.filter(activa=False).count()
    total_todas = total_activas + total_inactivas

    context.update({
        'b3_filtro_actual': filtro_actual,
        'b3_total_activas': total_activas,
        'b3_total_inactivas': total_inactivas,
        'b3_total_todas': total_todas,
        # Issue #218 (A3-A6): filtros activos + choices para los <select> de
        # línea/actividad y el carry-forward de hidden inputs.
        'filtros_cuadrilla': filtros_cuadrilla,
        'lineas_disponibles': choices_lineas(),
        'actividades_disponibles': choices_actividades(),
    })

    # Regenerar el agrupamiento por semana del queryset filtrado actual,
    # incluyendo cuadrillas inactivas si fuera el caso (el original solo
    # mira activas en el helper). Re-uso el mismo helper `_parse_semana`.
    cuadrillas = list(context.get('cuadrillas') or [])
    cuadrillas_por_semana = OrderedDict()
    sin_semana = []
    parse = _legacy_views.CuadrillaListView._parse_semana
    for cuadrilla in cuadrillas:
        sem, ano = parse(cuadrilla.codigo)
        if sem is not None:
            key = f'Semana {sem} - {ano}'
            cuadrillas_por_semana.setdefault(key, []).append(cuadrilla)
        else:
            sin_semana.append(cuadrilla)
    if sin_semana:
        cuadrillas_por_semana['Otras'] = sin_semana
    context['cuadrillas_por_semana'] = cuadrillas_por_semana

    # Issue #218 (A8): las 3 tarjetas de stats (Total/Activas/Semanas) pasan
    # a reflejar el queryset FILTRADO actual (semana+línea+actividad+fecha
    # además del tri-state B3), no el total global de 227 -- decisión de
    # diseño declarada en el PLAN. `b3_total_*` arriba se conservan intactos
    # porque alimentan los contadores de los tabs (esos SÍ deben ser
    # globales, o el tab "Inactivas" nunca mostraría cuántas hay para poder
    # cambiar a esa vista).
    context['total_cuadrillas'] = len(cuadrillas)
    context['cuadrillas_activas'] = sum(1 for c in cuadrillas if c.activa)
    context['semanas_en_filtro_actual'] = len(cuadrillas_por_semana)

    # ubicaciones: el original solo construye para activas porque el queryset
    # estaba filtrado. Replicar con el queryset actual del contexto.
    ubicaciones = []
    for cuadrilla in cuadrillas:
        if not cuadrilla.activa:
            continue
        ultima = TrackingUbicacion.objects.filter(
            cuadrilla=cuadrilla
        ).order_by('-created_at').first()
        if ultima:
            ubicaciones.append({
                'cuadrilla_id': str(cuadrilla.id),
                'cuadrilla_codigo': cuadrilla.codigo,
                'lat': float(ultima.latitud),
                'lng': float(ultima.longitud),
            })
    context['cuadrillas_ubicaciones_json'] = json.dumps(ubicaciones)

    return context


_legacy_views.CuadrillaListView.get_queryset = _b3_get_queryset
_legacy_views.CuadrillaListView.get_context_data = _b3_get_context_data


# ---------------------------------------------------------------------------
# Mixin de view: si la request muta activa, registra desactivado_por antes de
# que el save() del modelo decida el timestamp. (Lo usa CuadrillaDeactivateView
# explícitamente; para edits genéricos via CuadrillaEditView, lo cubre el
# protocolo de update — fuera de scope de B3, se respeta files_owned.)
# ---------------------------------------------------------------------------


class CuadrillaReactivateView(LoginRequiredMixin, RoleRequiredMixin, View):
    """POST /cuadrillas/<uuid>/reactivar/.

    Permisos RBAC: admin, director, coordinador (igual que ListView).
    """
    allowed_roles = ['admin', 'director', 'coordinador']

    def post(self, request, pk, *args, **kwargs):
        cuadrilla = get_object_or_404(Cuadrilla, pk=pk)

        # Edge case: cuadrilla ya activa → no-op idempotente.
        if cuadrilla.activa:
            if request.headers.get('HX-Request'):
                return HttpResponse(status=204)
            messages.info(request, f'Cuadrilla {cuadrilla.codigo} ya estaba activa.')
            return redirect('cuadrillas:lista')

        cuadrilla.reactivar(usuario=request.user)
        messages.success(
            request,
            f'Cuadrilla {cuadrilla.codigo} reactivada correctamente.'
        )

        if request.headers.get('HX-Request'):
            return JsonResponse({
                'status': 'ok',
                'cuadrilla_id': str(cuadrilla.id),
                'codigo': cuadrilla.codigo,
                'activa': True,
            })

        next_url = request.POST.get('next') or request.GET.get('next')
        if next_url:
            return redirect(next_url)
        return redirect('cuadrillas:lista')


class CuadrillaDeactivateView(LoginRequiredMixin, RoleRequiredMixin, View):
    """POST /cuadrillas/<uuid>/desactivar/ — desactiva con motivo.

    Body params: `motivo` (texto, opcional pero recomendado).
    """
    allowed_roles = ['admin', 'director', 'coordinador']

    def post(self, request, pk, *args, **kwargs):
        cuadrilla = get_object_or_404(Cuadrilla, pk=pk)

        # Edge case: cuadrilla ya inactiva → no-op (preservar auditoría existente).
        if not cuadrilla.activa:
            if request.headers.get('HX-Request'):
                return HttpResponse(status=204)
            messages.info(request, f'Cuadrilla {cuadrilla.codigo} ya estaba inactiva.')
            return redirect('cuadrillas:lista')

        motivo = (request.POST.get('motivo') or '').strip()
        cuadrilla.desactivar(usuario=request.user, motivo=motivo)
        messages.success(
            request,
            f'Cuadrilla {cuadrilla.codigo} desactivada correctamente.'
        )

        if request.headers.get('HX-Request'):
            return JsonResponse({
                'status': 'ok',
                'cuadrilla_id': str(cuadrilla.id),
                'codigo': cuadrilla.codigo,
                'activa': False,
                'motivo': motivo,
            })

        next_url = request.POST.get('next') or request.GET.get('next')
        if next_url:
            return redirect(next_url)
        return redirect('cuadrillas:lista')


# ---------------------------------------------------------------------------
# URL patterns exportados — el aggregator urls.py hace `urlpatterns += views_b3.urlpatterns`.
# ---------------------------------------------------------------------------

urlpatterns = [
    path(
        '<uuid:pk>/reactivar/',
        CuadrillaReactivateView.as_view(),
        name='reactivar',
    ),
    path(
        '<uuid:pk>/desactivar/',
        CuadrillaDeactivateView.as_view(),
        name='desactivar',
    ),
]
