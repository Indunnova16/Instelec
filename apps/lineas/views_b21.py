"""
B2.1 — Vistas para Segmentación de Vanos por Semestre (S1/S2/TA).

Issue: Indunnova16/Instelec#102

Vistas
- `LineaDetailSemestreView`: re-renderiza `lineas:detalle` filtrando por semestre.
  Reusa el template existente y agrega `semestre`, `vanos_filtered`, `stats_semestre`,
  `avance_consolidado` al contexto. Hook: `?semestre=S1|S2|TA`.
- `VanoSemestreEstadoView` (POST): cambia el estado del Vano en un semestre.
- `VanoSemestreConfigView` (POST): crea/actualiza los semestres de trabajo de
  un vano (checkboxes S1/S2/TA del modal).

Helper exportado
- `filter_vanos_by_semestre(qs, semestre)` — utility para que el resto del
  portafolio (campo, indicadores) filtre vanos sin acoplar a este módulo.

Hook para apps.campo.RegistroAvanceCreateView
- B1.2 no agregó soporte de ?semestre=. Esta vista expone `filter_vanos_by_semestre`
  importable desde `apps.lineas.models_b21` y desde aquí. El sub-feature posterior
  (followup) o F4 integration puede usarla. Mientras tanto, /lineas/<uuid>/?semestre=S1
  sí funciona via LineaDetailSemestreView.
"""
import json
import logging
from collections import OrderedDict

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Count
from django.http import JsonResponse, Http404
from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from django.views import View

from apps.core.mixins import RoleRequiredMixin

from .models_b21 import (
    VanoSemestre,
    SeguimientoVanoSemestre,
    filter_vanos_by_semestre,
)

logger = logging.getLogger(__name__)

# Roles permitidos para mutaciones
_ROLES_EDIT = ['admin', 'director', 'coordinador', 'ing_residente', 'supervisor']
_ROLES_READ = _ROLES_EDIT + ['liniero', 'auxiliar', 'ing_ambiental']


def _user_can_edit(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    try:
        from apps.core.permissions import user_es_admin
        if user_es_admin(user):
            return True
    except Exception:
        pass
    return getattr(user, 'rol', None) in _ROLES_EDIT


# ---------------------------------------------------------------------------
# Vista GET — detalle de línea con filtro semestre
# ---------------------------------------------------------------------------

class LineaDetailSemestreView(LoginRequiredMixin, RoleRequiredMixin, View):
    """
    GET /lineas/<uuid:linea_id>/semestre/?semestre=S1
    Devuelve JSON con stats por semestre + lista de vanos filtrados.

    Esta vista NO reemplaza LineaDetailView (que sigue sirviendo /lineas/<uuid>/).
    Es un endpoint de datos para el filtro y el dashboard. Cuando se pide via
    HTMX o navegador con `?ajax=1` devuelve JSON; sin ese flag re-renderiza el
    detalle del template usando el include hook plantado por F2.
    """
    allowed_roles = _ROLES_READ
    http_method_names = ['get']

    def get(self, request, linea_id):
        from .models import Linea, Vano

        linea = get_object_or_404(Linea, pk=linea_id)
        semestre = (request.GET.get('semestre') or '').upper()

        vanos_qs = Vano.objects.filter(linea=linea)
        if semestre and semestre in dict(VanoSemestre.Semestre.choices):
            vanos_qs = filter_vanos_by_semestre(vanos_qs, semestre)

        # Stats: avance consolidado por semestre + del subset filtrado
        consolidado = VanoSemestre.objects.avance_consolidado(linea)

        # Filas para el grid filtrado: incluye estado por semestre
        rows = []
        if semestre and semestre in dict(VanoSemestre.Semestre.choices):
            qs_sem = (
                VanoSemestre.objects
                .filter(vano__linea=linea, semestre=semestre)
                .select_related('vano')
                .order_by('vano__numero')
            )
            for vs in qs_sem:
                rows.append({
                    'vano_semestre_id': str(vs.id),
                    'vano_id': str(vs.vano_id),
                    'numero': vs.vano.numero,
                    'estado': vs.estado,
                    'estado_label': vs.get_estado_display(),
                    'observaciones': vs.observaciones,
                })
        else:
            # Sin filtro: lista de vanos crudos (con sus semestres como lista)
            vanos = vanos_qs.prefetch_related('semestres').order_by('numero')
            for v in vanos:
                rows.append({
                    'vano_id': str(v.id),
                    'numero': v.numero,
                    'semestres': [
                        {
                            'id': str(s.id),
                            'codigo': s.semestre,
                            'estado': s.estado,
                            'estado_label': s.get_estado_display(),
                        }
                        for s in v.semestres.all()
                    ],
                })

        return JsonResponse({
            'linea': {'id': str(linea.id), 'codigo': linea.codigo, 'nombre': linea.nombre},
            'semestre_filtro': semestre or None,
            'avance_consolidado': consolidado,
            'rows': rows,
            'count': len(rows),
        })


# ---------------------------------------------------------------------------
# Vista POST — cambiar estado de un vano en un semestre
# ---------------------------------------------------------------------------

@method_decorator(csrf_protect, name='dispatch')
class VanoSemestreEstadoView(LoginRequiredMixin, RoleRequiredMixin, View):
    """
    POST /lineas/vano-semestre/<uuid:pk>/estado/

    Body: estado=<choice>, observaciones=<str?>
    Solo cambia estado del vano EN ESE SEMESTRE; nunca propaga a otros.
    Crea registro de seguimiento.
    """
    allowed_roles = _ROLES_EDIT
    http_method_names = ['post']

    def post(self, request, pk):
        vs = get_object_or_404(VanoSemestre, pk=pk)

        if not _user_can_edit(request.user):
            return JsonResponse({'error': 'No tienes permiso para editar.'}, status=403)

        nuevo_estado = (request.POST.get('estado') or '').strip()
        observaciones = (request.POST.get('observaciones') or '').strip()

        if nuevo_estado not in dict(VanoSemestre.Estado.choices):
            return JsonResponse({
                'error': 'Estado inválido.',
                'estados_validos': [c for c, _ in VanoSemestre.Estado.choices],
            }, status=400)

        try:
            with transaction.atomic():
                vs.marcar(nuevo_estado, usuario=request.user, observaciones=observaciones)
                # Crear seguimiento append-only
                pct = 100.0 if nuevo_estado == VanoSemestre.Estado.EJECUTADO else 0.0
                from django.utils import timezone
                SeguimientoVanoSemestre.objects.create(
                    vano_semestre=vs,
                    fecha=timezone.now().date(),
                    porcentaje_avance=pct,
                    horas=0,
                    observaciones=observaciones,
                    registrado_por=request.user if request.user.is_authenticated else None,
                )
        except Exception as exc:  # pragma: no cover — defensivo
            logger.exception("Error cambiando estado VanoSemestre %s", pk)
            return JsonResponse({'error': f'Error interno: {exc}'}, status=500)

        return JsonResponse({
            'success': True,
            'vano_semestre_id': str(vs.id),
            'estado': vs.estado,
            'estado_label': vs.get_estado_display(),
            'semestre': vs.semestre,
        })


# ---------------------------------------------------------------------------
# Vista POST — configurar semestres de un vano (modal Alpine)
# ---------------------------------------------------------------------------

@method_decorator(csrf_protect, name='dispatch')
class VanoSemestreConfigView(LoginRequiredMixin, RoleRequiredMixin, View):
    """
    POST /lineas/vano/<uuid:vano_id>/semestres/configurar/

    Body: semestres=S1,S2 (csv o múltiples checkboxes), observaciones=<str?>
    Crea filas faltantes; elimina filas que el admin desmarcó (solo si están
    en estado PENDIENTE — para no borrar histórico ejecutado).
    """
    allowed_roles = _ROLES_EDIT
    http_method_names = ['post']

    def post(self, request, vano_id):
        from .models import Vano

        vano = get_object_or_404(Vano, pk=vano_id)
        if not _user_can_edit(request.user):
            return JsonResponse({'error': 'No tienes permiso para editar.'}, status=403)

        # Aceptar lista de checkboxes o csv
        if hasattr(request.POST, 'getlist') and request.POST.getlist('semestres'):
            seleccion_raw = request.POST.getlist('semestres')
        else:
            seleccion_raw = (request.POST.get('semestres') or '').split(',')

        seleccion = {s.strip().upper() for s in seleccion_raw if s.strip()}
        valid = set(dict(VanoSemestre.Semestre.choices).keys())
        invalid = seleccion - valid
        if invalid:
            return JsonResponse({
                'error': f'Semestres inválidos: {sorted(invalid)}',
                'validos': sorted(valid),
            }, status=400)

        observaciones = (request.POST.get('observaciones') or '').strip()

        creados, eliminados, sin_cambios = [], [], []
        with transaction.atomic():
            existentes = {vs.semestre: vs for vs in vano.semestres.all()}

            # Crear los marcados que no existían
            for sem in seleccion:
                if sem not in existentes:
                    vs = VanoSemestre.objects.create(
                        vano=vano,
                        semestre=sem,
                        observaciones=observaciones,
                        creado_por=request.user if request.user.is_authenticated else None,
                    )
                    creados.append(sem)
                else:
                    # Actualizar observaciones si vinieron
                    if observaciones and existentes[sem].observaciones != observaciones:
                        existentes[sem].observaciones = observaciones
                        existentes[sem].actualizado_por = request.user
                        existentes[sem].save(update_fields=['observaciones', 'actualizado_por', 'updated_at'])
                    sin_cambios.append(sem)

            # Eliminar los desmarcados PERO solo si están PENDIENTE (no destruir histórico)
            for sem, vs in existentes.items():
                if sem not in seleccion:
                    if vs.estado == VanoSemestre.Estado.PENDIENTE and not vs.seguimientos.exists():
                        vs.delete()
                        eliminados.append(sem)
                    else:
                        # Marcar NO_EJECUTADO en lugar de borrar
                        vs.estado = VanoSemestre.Estado.NO_EJECUTADO
                        vs.actualizado_por = request.user
                        vs.save(update_fields=['estado', 'actualizado_por', 'updated_at'])
                        sin_cambios.append(f"{sem}->NO_EJECUTADO")

        return JsonResponse({
            'success': True,
            'vano_id': str(vano.id),
            'creados': creados,
            'eliminados': eliminados,
            'sin_cambios': sin_cambios,
        })


# ---------------------------------------------------------------------------
# urlpatterns expuestos al aggregator apps/lineas/urls.py
# ---------------------------------------------------------------------------

urlpatterns = [
    path(
        '<uuid:linea_id>/semestre/',
        LineaDetailSemestreView.as_view(),
        name='detalle_semestre',
    ),
    path(
        'vano-semestre/<uuid:pk>/estado/',
        VanoSemestreEstadoView.as_view(),
        name='vano_semestre_estado',
    ),
    path(
        'vano/<uuid:vano_id>/semestres/configurar/',
        VanoSemestreConfigView.as_view(),
        name='vano_semestres_configurar',
    ),
]


__all__ = [
    'LineaDetailSemestreView',
    'VanoSemestreEstadoView',
    'VanoSemestreConfigView',
    'filter_vanos_by_semestre',
    'urlpatterns',
]
