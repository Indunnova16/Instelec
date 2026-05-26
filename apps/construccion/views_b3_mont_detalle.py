"""B3b - Views para UX completa de Montaje paridad Excel CANT MONTAJE (#76).

Tres CBVs:

  1. MontajeResumenView (TemplateView) - GET /construccion/<p>/montaje/
     Matriz read-only torres x 4 etapas (Estructura sitio / Prearmada / Torre
     montada / Revisada), % derivado del cache legacy `MontajeEstructuraTorre`
     que el signal de B3a mantiene fresco desde el detalle. Celdas son links
     a `montaje_detalle?seccion=montaje`. El panel pesos sigue editable
     (legacy `MontajePesosUpdateView` preservado).
     Re-proposito del legacy `MontajeMatrizView`.

  2. MontajeDetalleView (TemplateView) - GET /construccion/<p>/montaje/<t>/detalle/
     Una sola torre, 7 secciones como tabs horizontales (NO patas -
     granularidad OneToOne con TorreConstruccion). Renderiza el partial de la
     seccion activa con el ModelForm correspondiente ligado a
     `MontajeEstructuraTorreDetalle`.
     Query param ?seccion=general|recepcion|prearmado|montaje|controles|pesos|facturacion
     (default: general).

  3. MontajeDetalleSaveView (View con POST) - POST /construccion/<p>/montaje/<t>/detalle/<seccion>/save/
     Recibe el form de una sola seccion, valida, aplica
     `update_or_create(torre=t, defaults=cleaned_data)`. Devuelve JSON
     enriquecido con campos derivados de la seccion: `avance_ponderado_pct`
     siempre; ademas `funcion` (general), `peso_alerta` + `peso_desviacion_pct`
     (pesos), `dias_montaje` (montaje).

El endpoint legacy `MontajeAvanceUpdateView` (matriz inline edit) queda
deprecado: en su lugar se levanta una view 410 Gone con mensaje pidiendo
usar el detalle.
"""
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from apps.core.mixins import RoleRequiredMixin
from .forms_b3_mont_detalle import form_para_seccion
from .models import (
    MontajeEstructuraTorre,
    ProyectoConstruccion,
    TorreConstruccion,
)
from .models_b3_mont_detalle import MontajeEstructuraTorreDetalle


# Roles canonicos copiados de views.py (no se reusan via import para
# evitar acoplamiento ciclico en este split B3b).
ALL_ADMIN_ROLES_B3B = [
    'admin', 'director', 'coordinador', 'ing_residente',
    'admin_general', 'coordinador_general', 'admin_construccion',
]
OPERARIO_ROLES_B3B = [
    'operario_construccion', 'operario_general',
    'supervisor', 'liniero', 'auxiliar',
]


# ===========================================================================
# Catalogo de las 7 secciones (slug -> label). Sincronizado con
# forms_b3_mont_detalle.SECCION_FORM_MAP.
# ===========================================================================

SECCIONES = [
    ('general', 'Info General'),
    ('recepcion', 'Recepcion Patio'),
    ('prearmado', 'Pre-armado'),
    ('montaje', 'Montaje'),
    ('controles', 'Controles Calidad'),
    ('pesos', 'Pesos'),
    ('facturacion', 'Facturacion'),
]
SECCIONES_VALIDAS = {slug for slug, _ in SECCIONES}
SECCION_DEFAULT = 'general'


def _filtrar_torres_por_cuadrilla(qs, user):
    """Helper local - replica la regla de filtros por cuadrilla del modulo
    legacy. Admin / superuser ven todo; operarios solo sus cuadrillas."""
    if getattr(user, 'is_superuser', False):
        return qs
    if not getattr(user, 'es_operario_campo', False):
        return qs
    cuadrillas = getattr(user, 'cuadrillas_activas', None) or []
    if not cuadrillas:
        return qs.none()
    try:
        from apps.cuadrillas.models import Cuadrilla
        nombres = list(
            Cuadrilla.objects.filter(id__in=cuadrillas).values_list('nombre', flat=True)
        )
    except Exception:
        return qs
    return qs.filter(cuadrilla_montaje__in=nombres) if nombres else qs.none()


# ===========================================================================
# 1. MontajeResumenView - re-proposito de MontajeMatrizView
# ===========================================================================

class MontajeResumenView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Vista resumen (matriz read-only) del modulo Montaje.

    Reemplaza la edicion inline de la matriz legacy: los valores de las 4
    columnas vienen del cache `MontajeEstructuraTorre` (mantenido por signal
    de B3a desde el detalle) y las celdas son links al detalle por torre.
    El panel pesos del proyecto sigue editable (endpoint legacy
    `montaje_pesos_update` preservado).
    """
    template_name = 'construccion/montaje_matriz.html'
    allowed_roles = ALL_ADMIN_ROLES_B3B + OPERARIO_ROLES_B3B

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = get_object_or_404(
            ProyectoConstruccion, id=self.kwargs['proyecto_id'])
        torres_qs = TorreConstruccion.objects.filter(proyecto=proyecto)
        torres_qs = _filtrar_torres_por_cuadrilla(torres_qs, self.request.user)
        torres_qs = torres_qs.select_related().order_by('numero')

        existentes = {
            m.torre_id: m
            for m in MontajeEstructuraTorre.objects.filter(proyecto=proyecto)
        }
        filas = []
        for torre in torres_qs:
            m = existentes.get(torre.id)
            if m is None:
                m = MontajeEstructuraTorre.objects.create(
                    proyecto=proyecto, torre=torre)
            filas.append(m)

        pesos = {
            'estructura_sitio': proyecto.peso_mont_estructura_sitio_pct,
            'prearamada': proyecto.peso_mont_prearamada_pct,
            'torre_montada': proyecto.peso_mont_torre_montada_pct,
            'revisada': proyecto.peso_mont_revisada_pct,
        }
        suma_pesos = sum(pesos.values())

        if filas:
            totales = {
                k: round(
                    sum(float(getattr(m, f'avance_{k}')) for m in filas)
                    / len(filas) * 100, 1)
                for k in pesos
            }
            avance_general = round(
                sum(float(m.avance_ponderado) for m in filas) / len(filas) * 100, 1
            )
        else:
            totales = {k: 0 for k in pesos}
            avance_general = 0

        ctx['proyecto'] = proyecto
        ctx['filas'] = filas
        ctx['pesos'] = pesos
        ctx['suma_pesos'] = suma_pesos
        ctx['suma_pesos_ok'] = suma_pesos == 100
        ctx['totales'] = totales
        ctx['avance_general'] = avance_general
        ctx['columnas'] = MontajeEstructuraTorre.COLUMNAS
        ctx['active_tab'] = 'montaje'
        ctx['is_resumen_readonly'] = True
        return ctx


# ===========================================================================
# 2. MontajeDetalleView - 7 secciones tab horizontal
# ===========================================================================

class MontajeDetalleView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Detalle por torre: 7 secciones como tabs horizontales.

    ?seccion=<slug> selecciona el tab activo. Cualquier slug fuera del
    catalogo cae al default `general`.
    """
    template_name = 'construccion/montaje_detalle.html'
    allowed_roles = ALL_ADMIN_ROLES_B3B + OPERARIO_ROLES_B3B

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = get_object_or_404(
            ProyectoConstruccion, id=self.kwargs['proyecto_id'])
        torre = get_object_or_404(
            TorreConstruccion,
            id=self.kwargs['torre_id'],
            proyecto=proyecto,
        )

        # Detalle (crear vacio si no existe - el signal mantendra el cache).
        detalle, _ = MontajeEstructuraTorreDetalle.objects.get_or_create(
            torre=torre,
            defaults={'proyecto': proyecto},
        )

        # Resolver seccion activa.
        seccion_param = self.request.GET.get('seccion', SECCION_DEFAULT)
        seccion = seccion_param if seccion_param in SECCIONES_VALIDAS else SECCION_DEFAULT

        form_cls = form_para_seccion(seccion)
        form = form_cls(instance=detalle) if form_cls else None

        # Pestanas para _tabs_navegacion.html (orientacion horizontal).
        pestanas = []
        for slug, label in SECCIONES:
            pestanas.append({
                'slug': slug,
                'label': label,
                'url': reverse(
                    'construccion:montaje_detalle',
                    kwargs={'proyecto_id': proyecto.id, 'torre_id': torre.id},
                ) + f'?seccion={slug}',
                'active': (slug == seccion),
            })

        save_url = reverse(
            'construccion:montaje_detalle_save',
            kwargs={
                'proyecto_id': proyecto.id,
                'torre_id': torre.id,
                'seccion': seccion,
            },
        )

        ctx['proyecto'] = proyecto
        ctx['torre'] = torre
        ctx['detalle'] = detalle
        ctx['seccion_activa'] = seccion
        ctx['seccion_form'] = form
        ctx['pestanas'] = pestanas
        ctx['save_url'] = save_url
        ctx['secciones'] = SECCIONES
        ctx['active_tab'] = 'montaje'
        ctx['avance_ponderado_pct'] = detalle.avance_ponderado_pct
        ctx['peso_alerta'] = detalle.peso_alerta
        ctx['peso_desviacion_pct'] = detalle.peso_desviacion_pct
        ctx['funcion'] = detalle.funcion
        ctx['dias_montaje'] = detalle.dias_montaje
        return ctx


# ===========================================================================
# 3. MontajeDetalleSaveView - POST AJAX por seccion
# ===========================================================================

class MontajeDetalleSaveView(LoginRequiredMixin, RoleRequiredMixin, View):
    """POST AJAX que aplica los campos de una seccion al detalle.

    Devuelve JSON. Campos siempre presentes:
      - ok: True
      - avance_ponderado_pct: float

    Campos condicionales segun seccion:
      - general:     funcion (str: 'Suspension'/'Retencion'/'')
      - pesos:       peso_alerta (bool), peso_desviacion_pct (float|None)
      - montaje:     dias_montaje (int|None)

    Errores -> status 400 con {ok: False, errors: {...}}.
    """
    allowed_roles = ALL_ADMIN_ROLES_B3B + OPERARIO_ROLES_B3B

    def post(self, request, proyecto_id, torre_id, seccion, *args, **kwargs):
        proyecto = get_object_or_404(ProyectoConstruccion, id=proyecto_id)
        torre = get_object_or_404(
            TorreConstruccion, id=torre_id, proyecto=proyecto)

        if seccion not in SECCIONES_VALIDAS:
            return JsonResponse(
                {'ok': False, 'error': f'Seccion invalida: {seccion!r}'},
                status=400,
            )

        form_cls = form_para_seccion(seccion)
        if form_cls is None:  # defensivo (no deberia ocurrir si catalogo coincide)
            return JsonResponse(
                {'ok': False, 'error': f'Seccion sin form: {seccion!r}'},
                status=400,
            )

        # Detalle existente o nuevo (OneToOne con torre).
        detalle, _ = MontajeEstructuraTorreDetalle.objects.get_or_create(
            torre=torre,
            defaults={'proyecto': proyecto},
        )

        form = form_cls(request.POST, instance=detalle)
        if not form.is_valid():
            return JsonResponse(
                {'ok': False, 'errors': form.errors.get_json_data()},
                status=400,
            )

        instance = form.save(commit=False)
        # proyecto se preserva (no se expone en ningun form); reasegurar.
        instance.proyecto = proyecto
        instance.save()

        # Respuesta base
        data = {
            'ok': True,
            'seccion': seccion,
            'avance_ponderado_pct': instance.avance_ponderado_pct,
        }

        # Campos derivados condicionales
        if seccion == 'general':
            data['funcion'] = instance.funcion
        if seccion == 'pesos':
            data['peso_alerta'] = instance.peso_alerta
            desv = instance.peso_desviacion_pct
            data['peso_desviacion_pct'] = (
                float(desv) if isinstance(desv, Decimal) else desv
            )
        if seccion == 'montaje':
            data['dias_montaje'] = instance.dias_montaje

        return JsonResponse(data)


# ===========================================================================
# Legacy endpoint -> 410 Gone
# ===========================================================================

class MontajeAvanceUpdateGoneView(LoginRequiredMixin, View):
    """Reemplaza el legacy `MontajeAvanceUpdateView`. Devuelve 410 Gone con
    mensaje claro: la edicion ahora es por seccion via detalle."""

    def _gone(self, *args, **kwargs):
        msg = (
            'Endpoint deprecado. La edicion de Montaje se hace por seccion '
            'en /construccion/<proyecto>/montaje/<torre>/detalle/. '
            'La matriz es ahora solo de resumen.'
        )
        return JsonResponse({'ok': False, 'error': msg}, status=410)

    def get(self, *args, **kwargs):
        return self._gone(*args, **kwargs)

    def post(self, *args, **kwargs):
        return self._gone(*args, **kwargs)
