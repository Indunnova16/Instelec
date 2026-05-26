"""B2b (#74) — Vistas paridad Obra Civil CANT OOCC.

Tres CBVs principales:
  - `ObraCivilResumenView`: re-propósito del legacy `ObraCivilMatrizView`.
    Matriz torre × 6 secciones **read-only**, % derivado del cache
    `ObraCivilTorre.avance_*`. Cada celda enlaza al detalle por pata.
    Mantiene el panel de pesos editable (el endpoint legacy
    `obra_civil_pesos_update` sigue operativo).
  - `ObraCivilDetalleView`: TemplateView por torre con tabs verticales
    (4 patas A/B/C/D) + tabs horizontales (6 secciones). Renderiza el
    partial de la sección activa con un form `ModelForm` ligado al
    `ObraCivilTorreDetalle` filtrado por (torre, pata).
  - `ObraCivilDetalleSeccionView`: POST AJAX, recibe form de UNA sección,
    valida y persiste con `update_or_create(torre=t, pata=p, defaults=...)`.
    El signal `recalcular_obra_civil_torre` (B2a) refresca el cache
    `ObraCivilTorre.avance_*` automáticamente en `post_save`.

Adicional:
  - `OCAvanceLegacy410View`: reemplaza el endpoint AJAX matriz
    `obra_civil_avance_update` con un HTTP 410 Gone explicativo.
"""
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from apps.construccion.forms_b3_oc_detalle import (
    SECCIONES, SECCION_LABELS, SECCION_SLUGS, form_para_seccion,
)
from apps.construccion.models import (
    ObraCivilTorre, ProyectoConstruccion, TorreConstruccion,
)
from apps.construccion.models_b3_oc_detalle import (
    PATA_CHOICES, ObraCivilTorreDetalle,
)
from apps.core.mixins import RoleRequiredMixin


# Reutilizar las listas de roles ya definidas en views.py (evita drift).
# Import perezoso para evitar dependencia circular durante import time.
def _roles():
    from apps.construccion.views import ALL_ADMIN_ROLES, OPERARIO_ROLES
    return ALL_ADMIN_ROLES, OPERARIO_ROLES


def _filtrar_torres_por_cuadrilla(qs, user):
    from apps.construccion.views import filtrar_torres_por_cuadrilla
    return filtrar_torres_por_cuadrilla(qs, user)


PATA_SLUGS = [p[0] for p in PATA_CHOICES]  # ['A','B','C','D']


# ===========================================================================
# 1. ObraCivilResumenView — re-propósito de la matriz legacy (read-only)
# ===========================================================================


class ObraCivilResumenView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Matriz Obra Civil del proyecto: torres × 6 columnas (Cerramiento,
    Excavación, Solado, Acero, Vaciado, Compactación) — **read-only**,
    derivada del cache `ObraCivilTorre.avance_*` que el signal de B2a
    refresca a partir del detalle por pata.

    Cada celda es link a la vista de detalle pata-por-pata. El panel de
    pesos sigue editable (POST a `obra_civil_pesos_update` legacy).
    """
    template_name = 'construccion/obra_civil_matriz.html'

    @property
    def allowed_roles(self):
        admins, operarios = _roles()
        return admins + operarios

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = get_object_or_404(
            ProyectoConstruccion, id=self.kwargs['proyecto_id'],
        )
        torres_qs = TorreConstruccion.objects.filter(proyecto=proyecto)
        torres_qs = _filtrar_torres_por_cuadrilla(torres_qs, self.request.user)
        torres_qs = torres_qs.select_related().order_by('numero')

        existentes = {
            oc.torre_id: oc
            for oc in ObraCivilTorre.objects.filter(proyecto=proyecto)
        }
        filas = []
        for torre in torres_qs:
            oc = existentes.get(torre.id)
            if oc is None:
                oc = ObraCivilTorre.objects.create(proyecto=proyecto, torre=torre)
            filas.append({
                'torre': torre,
                'torre_legacy': oc,  # expone avance_<seccion>
                'avance_ponderado_pct': round(float(oc.avance_ponderado) * 100, 1),
            })

        pesos = {
            'cerramiento': proyecto.peso_cerramiento_pct,
            'excavacion': proyecto.peso_excavacion_pct,
            'solado': proyecto.peso_solado_pct,
            'acero': proyecto.peso_acero_pct,
            'vaciado': proyecto.peso_vaciado_pct,
            'compactacion': proyecto.peso_compactacion_pct,
        }
        suma_pesos = sum(pesos.values())

        # Totales por columna (promedio entre torres del cache).
        if filas:
            totales = {
                k: round(
                    sum(float(getattr(f['torre_legacy'], f'avance_{k}'))
                        for f in filas) / len(filas) * 100,
                    1,
                )
                for k in pesos
            }
            avance_general = round(
                sum(float(f['torre_legacy'].avance_ponderado) for f in filas)
                / len(filas) * 100,
                1,
            )
        else:
            totales = {k: 0 for k in pesos}
            avance_general = 0

        ctx.update({
            'proyecto': proyecto,
            'filas': filas,
            'pesos': pesos,
            'suma_pesos': suma_pesos,
            'suma_pesos_ok': suma_pesos == 100,
            'totales': totales,
            'avance_general': avance_general,
            'columnas': ObraCivilTorre.COLUMNAS,
            'secciones': SECCIONES,  # (slug, label, FormClass)
            'active_tab': 'obra-civil',
        })
        return ctx


# ===========================================================================
# 2. ObraCivilDetalleView — TemplateView por torre con tabs patas/secciones
# ===========================================================================


class ObraCivilDetalleView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Detalle por pata (tabs verticales A/B/C/D) × sección (tabs horizontales).

    Query params:
      - `?pata=A|B|C|D` (default: A)
      - `?seccion=cerramiento|excavacion|solado|acero|vaciado|compactacion`
        (default: cerramiento)

    Renderiza el partial `oc_seccion_<slug>.html` con el form correspondiente.
    """
    template_name = 'construccion/obra_civil_detalle.html'

    @property
    def allowed_roles(self):
        admins, operarios = _roles()
        return admins + operarios

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = get_object_or_404(
            ProyectoConstruccion, id=self.kwargs['proyecto_id'],
        )
        # Cross-proyecto: 404 si la torre no pertenece a este proyecto.
        torre = get_object_or_404(
            TorreConstruccion,
            id=self.kwargs['torre_id'],
            proyecto=proyecto,
        )

        # Pata activa (default A)
        pata_qs = self.request.GET.get('pata', 'A').upper()
        if pata_qs not in PATA_SLUGS:
            pata_qs = 'A'

        # Sección activa (default cerramiento)
        seccion = self.request.GET.get('seccion', 'cerramiento').lower()
        if seccion not in SECCION_SLUGS:
            seccion = 'cerramiento'

        # Detalle de la pata activa (crear vacío si no existe)
        detalle, _ = ObraCivilTorreDetalle.objects.get_or_create(
            torre=torre, pata=pata_qs,
            defaults={'proyecto': proyecto},
        )

        # Form de la sección activa
        FormClass = form_para_seccion(seccion)
        form = FormClass(instance=detalle)

        # Datos de tabs
        pestanas_patas = [
            {
                'slug': p[0],
                'label': p[1],
                'url': (
                    reverse(
                        'construccion:obra_civil_detalle',
                        kwargs={
                            'proyecto_id': proyecto.id,
                            'torre_id': torre.id,
                        },
                    ) + f'?pata={p[0]}&seccion={seccion}'
                ),
                'active': p[0] == pata_qs,
            }
            for p in PATA_CHOICES
        ]
        pestanas_secciones = [
            {
                'slug': s[0],
                'label': s[1],
                'url': (
                    reverse(
                        'construccion:obra_civil_detalle',
                        kwargs={
                            'proyecto_id': proyecto.id,
                            'torre_id': torre.id,
                        },
                    ) + f'?pata={pata_qs}&seccion={s[0]}'
                ),
                'active': s[0] == seccion,
            }
            for s in SECCIONES
        ]

        # URL POST de la sección
        url_post_seccion = reverse(
            'construccion:obra_civil_detalle_seccion',
            kwargs={
                'proyecto_id': proyecto.id,
                'torre_id': torre.id,
                'pata': pata_qs,
                'seccion': seccion,
            },
        )

        ctx.update({
            'proyecto': proyecto,
            'torre': torre,
            'pata_activa': pata_qs,
            'seccion_activa': seccion,
            'seccion_label': SECCION_LABELS[seccion],
            'detalle': detalle,
            'form': form,
            'avance_ponderado_pct': detalle.avance_ponderado_pct,
            'pestanas_patas': pestanas_patas,
            'pestanas_secciones': pestanas_secciones,
            'partial_template': f'construccion/partials/oc_seccion_{seccion}.html',
            'url_post_seccion': url_post_seccion,
            'url_resumen': reverse(
                'construccion:obra_civil_lista',
                kwargs={'proyecto_id': proyecto.id},
            ),
            'active_tab': 'obra-civil',
        })
        return ctx


# ===========================================================================
# 3. ObraCivilDetalleSeccionView — POST AJAX por sección
# ===========================================================================


class ObraCivilDetalleSeccionView(LoginRequiredMixin, RoleRequiredMixin, View):
    """POST: persiste UNA sección del detalle pata-por-pata.

    URL: `/<proyecto>/obra-civil/<torre>/detalle/<pata>/<seccion>/`

    Body: campos del Form correspondiente. Devuelve JSON con
    `{ok, avance_ponderado_pct, redirect_url?}` o 400 + `errors`.
    El signal `recalcular_obra_civil_torre` (B2a) actualiza el cache.
    """

    @property
    def allowed_roles(self):
        admins, operarios = _roles()
        return admins + operarios

    def post(self, request, proyecto_id, torre_id, pata, seccion, *args, **kwargs):
        proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)
        torre = get_object_or_404(
            TorreConstruccion, id=torre_id, proyecto=proyecto,
        )

        pata = (pata or '').upper()
        if pata not in PATA_SLUGS:
            return JsonResponse(
                {'ok': False, 'error': f'Pata inválida: {pata!r}'}, status=400,
            )

        seccion = (seccion or '').lower()
        if seccion not in SECCION_SLUGS:
            return JsonResponse(
                {'ok': False, 'error': f'Sección inválida: {seccion!r}'},
                status=400,
            )

        # Cargar / crear instancia para esta pata
        detalle, _ = ObraCivilTorreDetalle.objects.get_or_create(
            torre=torre, pata=pata,
            defaults={'proyecto': proyecto},
        )

        FormClass = form_para_seccion(seccion)
        form = FormClass(request.POST, instance=detalle)
        if not form.is_valid():
            return JsonResponse(
                {'ok': False, 'errors': form.errors.get_json_data()},
                status=400,
            )

        detalle = form.save()
        # Forzar refresco para tomar el avance ponderado actualizado
        detalle.refresh_from_db()

        return JsonResponse({
            'ok': True,
            'pata': pata,
            'seccion': seccion,
            'avance_ponderado': float(detalle.avance_ponderado),
            'avance_ponderado_pct': detalle.avance_ponderado_pct,
        })


# ===========================================================================
# 4. OCAvanceLegacy410View — endpoint legacy retirado
# ===========================================================================


class OCAvanceLegacy410View(LoginRequiredMixin, View):
    """Endpoint legacy `obra_civil_avance_update` — retirado.

    Antes recibía POST AJAX con `columna` + `valor` 0–1 sobre
    `ObraCivilTorre.avance_*`. Ahora la fuente de verdad es el detalle
    por pata (`ObraCivilTorreDetalle`); el cache se actualiza vía signal.

    Devuelve HTTP 410 Gone con instrucción para usar el detalle.
    """

    def _gone(self, request, proyecto_id, torre_id, **_):
        mensaje = (
            'Este endpoint fue reemplazado. Editá directamente en '
            f'/construccion/{proyecto_id}/obra-civil/{torre_id}/detalle/. '
            'El avance por columna se calcula a partir del detalle por pata.'
        )
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or \
                'application/json' in request.headers.get('Accept', ''):
            return JsonResponse(
                {'ok': False, 'error': mensaje, 'gone': True},
                status=410,
            )
        return HttpResponse(mensaje, status=410, content_type='text/plain')

    def get(self, request, proyecto_id, torre_id, *args, **kwargs):
        return self._gone(request, proyecto_id, torre_id)

    def post(self, request, proyecto_id, torre_id, *args, **kwargs):
        return self._gone(request, proyecto_id, torre_id)
