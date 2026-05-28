"""Complemento al módulo financiero PDEO (#103).

Agrega lo que faltaba sobre la implementación de #69/#66/#70:
  - TransaccionesListView: lista global de TransaccionContable con filtros.
  - TransaccionesUploadView: carga del Excel PDEO (4 hojas).
  - ReportesFinancierosView: 3 reportes + export CSV.
  - PyGDrillDownView: drill-down dedicado del estado de resultados por proyecto.
"""
from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import FormView, ListView, TemplateView

from apps.core.mixins import RoleRequiredMixin

from .forms import CargarPDEOForm
from .models import (
    CategoriaFinanciera,
    MovimientoFinanciero,
    PeriodoFinanciero,
    ProyectoConstruccion,
    TransaccionContable,
)
from .pdeo_importer import import_pdeo_workbook


ALL_ADMIN_ROLES = [
    'admin', 'director', 'coordinador', 'ing_residente',
    'admin_general', 'coordinador_general', 'admin_construccion',
]


class TransaccionesListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    """Lista global de TransaccionContable con filtros (#103).

    URL: /construccion/financiero/transacciones/

    Filtros vía querystring:
      proyecto, categoria, periodo, nit, fecha_desde, fecha_hasta, q (texto libre)
    """
    model = TransaccionContable
    template_name = 'construccion/transacciones_list.html'
    context_object_name = 'transacciones'
    paginate_by = 50
    allowed_roles = ALL_ADMIN_ROLES

    def get_queryset(self):
        qs = TransaccionContable.objects.select_related(
            'movimiento__categoria',
            'movimiento__periodo__proyecto',
        )
        params = self.request.GET
        if params.get('proyecto'):
            qs = qs.filter(movimiento__periodo__proyecto_id=params['proyecto'])
        if params.get('categoria'):
            qs = qs.filter(movimiento__categoria_id=params['categoria'])
        if params.get('periodo'):
            qs = qs.filter(movimiento__periodo_id=params['periodo'])
        if params.get('nit'):
            qs = qs.filter(nit_proveedor__icontains=params['nit'])
        if params.get('fecha_desde'):
            qs = qs.filter(fecha__gte=params['fecha_desde'])
        if params.get('fecha_hasta'):
            qs = qs.filter(fecha__lte=params['fecha_hasta'])
        if params.get('q'):
            q = params['q']
            qs = qs.filter(
                Q(descripcion__icontains=q)
                | Q(nombre_proveedor__icontains=q)
                | Q(numero_factura__icontains=q)
            )
        return qs.order_by('-fecha', '-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['active_tab'] = 'financiero_transacciones'
        ctx['proyectos'] = ProyectoConstruccion.objects.exclude(
            estado='FINALIZADO').order_by('nombre')
        ctx['categorias'] = CategoriaFinanciera.objects.filter(
            activa=True).order_by('orden')
        ctx['filtros'] = {k: self.request.GET.get(k, '')
                          for k in ['proyecto', 'categoria', 'periodo',
                                    'nit', 'fecha_desde', 'fecha_hasta', 'q']}
        # Total agregado del queryset filtrado (sin paginación)
        agg = self.get_queryset().aggregate(
            total=Sum('valor'), cnt=Count('id'))
        ctx['total_valor'] = agg['total'] or Decimal('0')
        ctx['total_count'] = agg['cnt'] or 0
        return ctx


class TransaccionesUploadView(LoginRequiredMixin, RoleRequiredMixin, FormView):
    """Carga del Excel PDEO 4-hojas (#103).

    URL: /construccion/financiero/transacciones/upload/

    El parser es idempotente: identifica transacciones por
    (numero_factura, nit_proveedor, fecha, valor) y omite duplicados.
    """
    template_name = 'construccion/transacciones_upload.html'
    form_class = CargarPDEOForm
    allowed_roles = ALL_ADMIN_ROLES
    success_url = reverse_lazy('construccion:transacciones_list')

    def form_valid(self, form):
        proyecto = form.cleaned_data['proyecto']
        archivo = form.cleaned_data['archivo']
        try:
            stats = import_pdeo_workbook(
                archivo, proyecto, usuario=self.request.user)
        except Exception as exc:
            messages.error(self.request,
                           f'Error al procesar el Excel PDEO: {exc}')
            return self.form_invalid(form)
        messages.success(
            self.request,
            f"PDEO cargado: {stats['transacciones_creadas']} transacciones nuevas, "
            f"{stats['transacciones_omitidas']} omitidas por duplicado, "
            f"{stats['movimientos_actualizados']} movimientos actualizados.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['active_tab'] = 'financiero_transacciones'
        return ctx


class ReportesFinancierosView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """3 reportes financieros (#103):
      1. PyG por trimestre (cross-proyecto)
      2. Top 10 proveedores por valor (filtrable por año)
      3. Alertas de variación >50% (qué categorías están fuera de presupuesto)

    Soporta ?export=csv&reporte=<nombre> para descargar.
    """
    template_name = 'construccion/reportes_financieros.html'
    allowed_roles = ALL_ADMIN_ROLES

    def get(self, request, *args, **kwargs):
        export = request.GET.get('export')
        if export == 'csv':
            return self._export_csv(request.GET.get('reporte', 'pyg_trimestre'))
        return super().get(request, *args, **kwargs)

    def _build_reportes(self, anio_filtro=None):
        # 1. PyG por trimestre (sumarizado cross-proyecto)
        movs = MovimientoFinanciero.objects.select_related(
            'categoria', 'periodo').all()
        if anio_filtro:
            movs = movs.filter(periodo__anio=anio_filtro)

        trimestres = {}
        for m in movs:
            trim = f"{m.periodo.anio}-Q{((m.periodo.mes - 1) // 3) + 1}"
            key = (trim, m.categoria.tipo)
            entry = trimestres.setdefault(
                key, {'trimestre': trim, 'tipo': m.categoria.tipo,
                      'presupuesto': Decimal('0'), 'real': Decimal('0')})
            if m.tipo == 'PRESUPUESTO':
                entry['presupuesto'] += m.valor
            else:
                entry['real'] += m.valor
        pyg_trimestre = []
        for entry in sorted(trimestres.values(),
                            key=lambda e: (e['trimestre'], e['tipo'])):
            entry['variacion'] = entry['real'] - entry['presupuesto']
            entry['pct'] = (
                round(entry['variacion'] / entry['presupuesto'] * 100, 1)
                if entry['presupuesto'] else None)
            pyg_trimestre.append(entry)

        # 2. Top 10 proveedores por valor
        proveedores_qs = TransaccionContable.objects.values(
            'nit_proveedor', 'nombre_proveedor'
        ).annotate(
            total=Sum('valor'), cnt=Count('id')
        ).order_by('-total')
        if anio_filtro:
            proveedores_qs = TransaccionContable.objects.filter(
                fecha__year=anio_filtro
            ).values(
                'nit_proveedor', 'nombre_proveedor'
            ).annotate(
                total=Sum('valor'), cnt=Count('id')
            ).order_by('-total')
        top_proveedores = list(proveedores_qs[:10])

        # 3. Alertas variación >50% (por categoría agregada)
        alertas = []
        cat_agg = {}
        for m in movs:
            entry = cat_agg.setdefault(
                m.categoria_id, {'categoria': m.categoria,
                                 'presupuesto': Decimal('0'),
                                 'real': Decimal('0')})
            if m.tipo == 'PRESUPUESTO':
                entry['presupuesto'] += m.valor
            else:
                entry['real'] += m.valor
        for entry in cat_agg.values():
            if entry['presupuesto']:
                pct = (entry['real'] - entry['presupuesto']) / entry['presupuesto'] * 100
                if abs(pct) >= 50:
                    alertas.append({
                        'categoria': entry['categoria'],
                        'presupuesto': entry['presupuesto'],
                        'real': entry['real'],
                        'variacion': entry['real'] - entry['presupuesto'],
                        'pct': round(pct, 1),
                    })
        alertas.sort(key=lambda a: abs(a['pct']), reverse=True)

        return {
            'pyg_trimestre': pyg_trimestre,
            'top_proveedores': top_proveedores,
            'alertas': alertas,
        }

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        anio = self.request.GET.get('anio')
        anio_int = int(anio) if anio and anio.isdigit() else None
        ctx['active_tab'] = 'financiero_reportes'
        ctx['anio_filtro'] = anio_int
        ctx['anios_disponibles'] = list(
            PeriodoFinanciero.objects.values_list(
                'anio', flat=True).distinct().order_by('-anio'))
        ctx.update(self._build_reportes(anio_int))
        return ctx

    def _export_csv(self, reporte):
        anio = self.request.GET.get('anio')
        anio_int = int(anio) if anio and anio.isdigit() else None
        data = self._build_reportes(anio_int)
        resp = HttpResponse(content_type='text/csv')
        resp['Content-Disposition'] = (
            f'attachment; filename="reporte_{reporte}_{date.today()}.csv"')
        writer = csv.writer(resp)
        if reporte == 'pyg_trimestre':
            writer.writerow(['Trimestre', 'Tipo', 'Presupuesto', 'Real',
                             'Variación', '%'])
            for r in data['pyg_trimestre']:
                writer.writerow([r['trimestre'], r['tipo'],
                                 r['presupuesto'], r['real'],
                                 r['variacion'], r['pct']])
        elif reporte == 'top_proveedores':
            writer.writerow(['NIT', 'Razón social', 'Total COP',
                             'Transacciones'])
            for r in data['top_proveedores']:
                writer.writerow([r['nit_proveedor'], r['nombre_proveedor'],
                                 r['total'], r['cnt']])
        elif reporte == 'alertas':
            writer.writerow(['Categoría', 'Presupuesto', 'Real',
                             'Variación', '%'])
            for r in data['alertas']:
                writer.writerow([str(r['categoria']), r['presupuesto'],
                                 r['real'], r['variacion'], r['pct']])
        else:
            resp.status_code = 400
            resp.content = f'reporte desconocido: {reporte}'.encode()
        return resp


class PyGDrillDownView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """PyG drill-down dedicado por proyecto (#103 item 4 opcional).

    URL: /construccion/<uuid:proyecto_id>/pyg/

    Cada categoría se puede expandir para ver transacciones que la componen.
    """
    template_name = 'construccion/pyg_drilldown.html'
    allowed_roles = ALL_ADMIN_ROLES

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        proyecto = get_object_or_404(
            ProyectoConstruccion, id=self.kwargs['proyecto_id'])
        ctx['proyecto'] = proyecto
        ctx['active_tab'] = 'pyg_drilldown'
        ctx['totales'] = proyecto.pyg_totales
        ctx['resumen'] = proyecto.pyg_resumen_ejecutivo()
        # Si se pidió expandir una categoría, traer sus transacciones
        categoria_id = self.request.GET.get('expandir')
        if categoria_id:
            ctx['categoria_expandida_id'] = categoria_id
            ctx['transacciones_expandidas'] = TransaccionContable.objects.filter(
                movimiento__periodo__proyecto=proyecto,
                movimiento__categoria_id=categoria_id,
            ).select_related('movimiento__periodo').order_by(
                '-fecha')[:200]
        return ctx
