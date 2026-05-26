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
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils import timezone
from django.views import View

from apps.core.mixins import RoleRequiredMixin
from . import views as _legacy_views
from .models import Cuadrilla, TrackingUbicacion


# ---------------------------------------------------------------------------
# Monkey-patch CuadrillaListView.get_queryset / get_context_data para incluir
# filtro=activas|inactivas|todas. Mantiene compatibilidad: sin parámetro →
# muestra solo activas (comportamiento legacy).
# ---------------------------------------------------------------------------

_ORIG_GET_QUERYSET = _legacy_views.CuadrillaListView.get_queryset
_ORIG_GET_CONTEXT = _legacy_views.CuadrillaListView.get_context_data


def _b3_get_queryset(self):
    """Filtro tri-state activas / inactivas / todas + búsqueda por código."""
    filtro = self.request.GET.get('filtro', 'activas').strip().lower()
    if filtro not in ('activas', 'inactivas', 'todas'):
        filtro = 'activas'

    qs = Cuadrilla.objects.all().select_related(
        'supervisor', 'vehiculo', 'linea_asignada', 'desactivado_por',
    ).prefetch_related('miembros__usuario')

    if filtro == 'activas':
        qs = qs.filter(activa=True)
    elif filtro == 'inactivas':
        qs = qs.filter(activa=False)

    # búsqueda por código (semana o prefix)
    semana_param = self.request.GET.get('semana', '').strip()
    if semana_param:
        try:
            parts = semana_param.split('-')
            sem = parts[0].zfill(2)
            ano = parts[1]
            qs = qs.filter(codigo__startswith=f'{sem}-{ano}-')
        except (IndexError, ValueError):
            pass

    codigo = self.request.GET.get('codigo', '').strip()
    if codigo:
        qs = qs.filter(codigo__icontains=codigo)

    # exposed para que get_context_data sepa el filtro actual sin re-parsear
    self._b3_filtro_actual = filtro
    return qs


def _b3_get_context_data(self, **kwargs):
    """Inyectar contadores y filtro actual al contexto."""
    context = _ORIG_GET_CONTEXT(self, **kwargs)
    filtro_actual = getattr(self, '_b3_filtro_actual', 'activas')

    # contadores globales (no afectados por filtros adicionales)
    total_activas = Cuadrilla.objects.filter(activa=True).count()
    total_inactivas = Cuadrilla.objects.filter(activa=False).count()
    total_todas = total_activas + total_inactivas

    context.update({
        'b3_filtro_actual': filtro_actual,
        'b3_total_activas': total_activas,
        'b3_total_inactivas': total_inactivas,
        'b3_total_todas': total_todas,
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

    # Stats ya regeneradas correctamente: usar nuestros contadores B3.
    context['total_cuadrillas'] = total_todas
    context['cuadrillas_activas'] = total_activas

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
