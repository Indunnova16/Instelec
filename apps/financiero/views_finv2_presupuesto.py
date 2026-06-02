"""
Vistas financiero v2 — Presupuesto Planeado con carga de BD contable — B1 (#120).

- ``PresupuestoPlaneadoViewV2`` extiende la base existente
  ``PresupuestoDetalladoBaseView`` (reusa get_or_create / filtros de contrato /
  año) y renderiza ``presupuesto_planeado_v2.html`` con 2 pestañas:
    1. Cargar Base de Datos Contable  (POST → ContableCompleteImporter)
    2. Presupuesto Planeado (rubros)   (display jerárquico desde datos.finv2_bd)
- CRUD inline de ``MapeoCtaRubro`` (crear / editar / eliminar) via HTMX.
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views import View

from apps.core.mixins import RoleRequiredMixin

from .forms_finv2 import CargarBDContableForm, MapeoCtaRubroForm
from .importers_finv2 import ContableCompleteImporter, build_rubro_display_rows
from .models_finv2_mapeo import MapeoCtaRubro
from .views import PresupuestoDetalladoBaseView


class PresupuestoPlaneadoViewV2(PresupuestoDetalladoBaseView):
    """Pestañas Cargar BD Contable + Presupuesto Planeado (rubros)."""

    template_name = 'financiero/presupuesto_planeado_v2.html'
    tipo_presupuesto = 'PLANEADO'
    allowed_roles = ['admin', 'director', 'coordinador']

    # ------------------------------------------------------------------ #
    # GET / contexto
    # ------------------------------------------------------------------ #
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        obj = context['presupuesto_obj']
        rubro_rows, total_general = build_rubro_display_rows(obj.datos)

        # B1 (#120) — contexto para los partials _cargar_bd_contable.html y
        # _mapeo_cta_rubro.html (lección Consof#23: la view DEBE pasar las vars).
        context['cargar_bd_form'] = kwargs.get('cargar_bd_form') or CargarBDContableForm()
        context['rubro_rows'] = rubro_rows
        context['rubro_total'] = total_general
        bloque = (obj.datos or {}).get('finv2_bd') or {}
        context['cuentas_count'] = bloque.get('cuentas_count', 0)
        context['cuentas_no_mapeadas'] = bloque.get('cuentas_no_mapeadas', [])
        context['tiene_datos_bd'] = bool(bloque.get('rubros'))
        context['mapeos'] = MapeoCtaRubro.objects.all()
        context['mapeo_form'] = MapeoCtaRubroForm()
        context['active_tab'] = self.request.GET.get('tab', 'cargar')
        return context

    # ------------------------------------------------------------------ #
    # POST — carga de BD contable
    # ------------------------------------------------------------------ #
    def post(self, request, *args, **kwargs):
        action = request.POST.get('action', '')
        if action == 'cargar_bd':
            return self._handle_cargar_bd(request)
        # Acciones legacy de la base (edición de celda / import_excel).
        return super().post(request, *args, **kwargs)

    def _handle_cargar_bd(self, request):
        anio = int(request.POST.get('anio', timezone.now().year))
        contrato = self._get_contrato_filter()
        redirect_url = f'{request.path}?anio={anio}&tab=planeado'
        if contrato:
            redirect_url += f'&contrato={contrato.pk}'

        form = CargarBDContableForm(request.POST, request.FILES)
        if not form.is_valid():
            for err in form.errors.get('archivo', ['Archivo inválido.']):
                messages.error(request, err)
            return redirect(f'{request.path}?anio={anio}&tab=cargar')

        archivo = form.cleaned_data['archivo']
        importer = ContableCompleteImporter()
        resultado = importer.procesar_bd_completa(archivo)

        if not resultado['exito']:
            # ⚠️ advertencia o ❌ error según el importer.
            if resultado.get('advertencia'):
                messages.warning(request, resultado['advertencia'])
            else:
                messages.error(
                    request,
                    resultado.get('error')
                    or 'Archivo inválido. Verifique que sea .xlsx con '
                       'estructura correcta',
                )
            return redirect(f'{request.path}?anio={anio}&tab=cargar')

        # Guardar en PresupuestoDetallado.datos (preservando otras llaves).
        obj, _ = self._get_or_create_presupuesto(anio, contrato)
        datos = obj.datos or {}
        datos['finv2_bd'] = resultado['datos']['finv2_bd']
        obj.datos = datos
        obj.save(update_fields=['datos', 'updated_at'])

        messages.success(request, resultado['mensaje'])
        for w in resultado.get('warnings', []):
            messages.warning(request, w)
        return redirect(redirect_url)


class MapeoCtaRubroCrudView(LoginRequiredMixin, RoleRequiredMixin, View):
    """CRUD inline de MapeoCtaRubro via HTMX (crear / editar / eliminar)."""

    allowed_roles = ['admin', 'director', 'coordinador']

    def _render_lista(self, request, mapeo_form=None):
        return render(request, 'financiero/_mapeo_cta_rubro.html', {
            'mapeos': MapeoCtaRubro.objects.all(),
            'mapeo_form': mapeo_form or MapeoCtaRubroForm(),
        })

    def post(self, request, *args, **kwargs):
        accion = request.POST.get('accion', 'crear')

        if accion == 'eliminar':
            pk = request.POST.get('pk')
            MapeoCtaRubro.objects.filter(pk=pk).delete()
            return self._render_lista(request)

        if accion == 'editar':
            pk = request.POST.get('pk')
            try:
                instancia = MapeoCtaRubro.objects.get(pk=pk)
            except MapeoCtaRubro.DoesNotExist:
                return HttpResponse('Mapeo no encontrado.', status=404)
            form = MapeoCtaRubroForm(request.POST, instance=instancia)
        else:  # crear
            form = MapeoCtaRubroForm(request.POST)

        if form.is_valid():
            form.save()
            return self._render_lista(request)

        # Re-render con errores (HTMX swap del bloque).
        return self._render_lista(request, mapeo_form=form)

    # GET devuelve solo la lista (refresco HTMX).
    def get(self, request, *args, **kwargs):
        return self._render_lista(request)
