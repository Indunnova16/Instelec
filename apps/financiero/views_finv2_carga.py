"""Workflow de carga financiera, homologación y plano contable (#246, #247)."""
from __future__ import annotations

import csv
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.views.generic import TemplateView

from apps.contratos.models import Contrato
from apps.core.mixins import RoleRequiredMixin

from .forms_finv2_carga import CargaFinancieraForm
from .importers_finv2_carga import procesar_carga_financiera
from .models_finv2_carga import (
    CargaFinanciera,
    HomologacionProjectsContable,
    LineaCargaFinanciera,
)


ZERO = Decimal('0.00')


def _porcentaje(numerador, denominador):
    """Evita falsos indicadores cuando aún no existe una base comparable."""
    if not denominador:
        return None
    return (numerador / denominador * 100).quantize(Decimal('0.01'))


class CargaFinancieraView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Carga un libro por proyecto/período y conserva su auditoría inmutable."""

    template_name = 'financiero/carga_financiera.html'
    allowed_roles = ['admin', 'director', 'coordinador']

    def _proyecto_seleccionado(self):
        proyecto_id = self.request.GET.get('proyecto') or self.request.POST.get('proyecto')
        if not proyecto_id:
            return None
        return Contrato.objects.filter(pk=proyecto_id, estado=Contrato.Estado.ACTIVO).first()

    def _periodo(self):
        anio = self.request.GET.get('anio') or self.request.POST.get('anio') or timezone.now().year
        mes = self.request.GET.get('mes') or self.request.POST.get('mes') or timezone.now().month
        try:
            anio, mes = int(anio), int(mes)
        except (TypeError, ValueError):
            return timezone.now().year, timezone.now().month, False
        return anio, mes, 1 <= mes <= 12

    @staticmethod
    def _indicadores(carga):
        if not carga:
            return []
        lineas = carga.lineas.all()
        real = sum((linea.valor for linea in lineas.filter(tipo=LineaCargaFinanciera.Tipo.REAL)), ZERO)
        presupuesto = sum((linea.valor for linea in lineas.filter(tipo=LineaCargaFinanciera.Tipo.PRESUPUESTO)), ZERO)
        margen = real - presupuesto
        anterior = CargaFinanciera.objects.filter(
            proyecto=carga.proyecto,
        ).exclude(pk=carga.pk).order_by('-anio', '-mes', '-created_at').first()
        real_anterior = ZERO
        if anterior:
            real_anterior = sum(
                (linea.valor for linea in anterior.lineas.filter(tipo=LineaCargaFinanciera.Tipo.REAL)), ZERO
            )
        return [
            {'nombre': 'Facturación vs meta', 'valor': _porcentaje(real - presupuesto, presupuesto), 'unidad': '%', 'alerta': presupuesto > real},
            {'nombre': 'Margen bruto', 'valor': margen, 'unidad': '$', 'alerta': margen < ZERO},
            {'nombre': 'Ratio costos/facturación', 'valor': _porcentaje(presupuesto, real), 'unidad': '%', 'alerta': bool(real and presupuesto / real > Decimal('0.70'))},
            {'nombre': 'Rentabilidad operativa', 'valor': _porcentaje(margen, real), 'unidad': '%', 'alerta': margen < ZERO},
            {'nombre': 'Cumplimiento presupuesto', 'valor': _porcentaje(real, presupuesto), 'unidad': '%', 'alerta': bool(presupuesto and real > presupuesto)},
            {'nombre': 'Variación mes a mes', 'valor': _porcentaje(real - real_anterior, real_anterior), 'unidad': '%', 'alerta': bool(real_anterior and real < real_anterior)},
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        anio, mes, periodo_valido = self._periodo()
        proyecto = self._proyecto_seleccionado()
        carga = None
        if proyecto and periodo_valido:
            carga = CargaFinanciera.objects.filter(proyecto=proyecto, anio=anio, mes=mes).first()
        context.update({
            'carga_form': kwargs.get('carga_form') or CargaFinancieraForm(),
            'proyectos': Contrato.objects.filter(estado=Contrato.Estado.ACTIVO),
            'proyecto_seleccionado': proyecto,
            'anio': anio,
            'mes': mes,
            'periodo_valido': periodo_valido,
            'carga_actual': carga,
            'historial_cargas': CargaFinanciera.objects.select_related('proyecto', 'usuario').all()[:20],
            'homologaciones': HomologacionProjectsContable.objects.all()[:100],
            'indicadores': self._indicadores(carga),
        })
        return context

    def post(self, request, *args, **kwargs):
        accion = request.POST.get('accion')
        if accion == 'homologar':
            return self._crear_homologacion()
        if accion == 'eliminar_homologacion':
            return self._eliminar_homologacion()
        return self._cargar_archivo()

    def _redirect_periodo(self, proyecto=None, anio=None, mes=None):
        params = []
        if proyecto:
            params.append(f'proyecto={proyecto.pk}')
        if anio:
            params.append(f'anio={anio}')
        if mes:
            params.append(f'mes={mes}')
        return redirect(f'{self.request.path}?{"&".join(params)}')

    def _cargar_archivo(self):
        proyecto = self._proyecto_seleccionado()
        anio, mes, periodo_valido = self._periodo()
        form = CargaFinancieraForm(self.request.POST, self.request.FILES)
        if not proyecto:
            messages.error(self.request, 'Seleccione un proyecto activo antes de cargar el archivo.')
        elif not periodo_valido:
            messages.error(self.request, 'Seleccione un mes entre 1 y 12.')
        elif form.is_valid():
            resultado = procesar_carga_financiera(
                form.cleaned_data['archivo'], proyecto=proyecto, anio=anio, mes=mes, usuario=self.request.user,
            )
            if resultado.exito:
                messages.success(self.request, f'Carga procesada: {resultado.resumen["lineas_reales"] + resultado.resumen["lineas_presupuesto"]} líneas.')
            else:
                messages.error(self.request, resultado.error or 'No fue posible procesar el archivo.')
        else:
            messages.error(self.request, form.errors.get('archivo', ['Archivo inválido.'])[0])
        return self._redirect_periodo(proyecto, anio, mes)

    def _crear_homologacion(self):
        datos = {campo: (self.request.POST.get(campo) or '').strip() for campo in ('tipo', 'grupo', 'concepto', 'rubro', 'codigo_contable', 'centro_costo')}
        if not datos['tipo'] or not datos['concepto'] or not datos['codigo_contable']:
            messages.error(self.request, 'Tipo, concepto y código contable son obligatorios para homologar.')
        else:
            obj, creada = HomologacionProjectsContable.objects.update_or_create(
                tipo=datos['tipo'], grupo=datos['grupo'], concepto=datos['concepto'], rubro=datos['rubro'],
                defaults={'codigo_contable': datos['codigo_contable'], 'centro_costo': datos['centro_costo'], 'activo': True},
            )
            messages.success(self.request, 'Homologación creada.' if creada else f'Homologación {obj.concepto} actualizada.')
        return self._redirect_periodo(self._proyecto_seleccionado(), *self._periodo()[:2])

    def _eliminar_homologacion(self):
        eliminado, _ = HomologacionProjectsContable.objects.filter(pk=self.request.POST.get('pk')).delete()
        if eliminado:
            messages.success(self.request, 'Homologación eliminada.')
        else:
            messages.error(self.request, 'La homologación solicitada ya no existe.')
        return self._redirect_periodo(self._proyecto_seleccionado(), *self._periodo()[:2])


class PlanoFinancieroCsvView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Entrega el plano contable definitivo, agregado por código y trazable."""

    allowed_roles = ['admin', 'director', 'coordinador']

    def get(self, request, carga_id, *args, **kwargs):
        carga = CargaFinanciera.objects.select_related('proyecto').filter(pk=carga_id).first()
        if not carga:
            raise Http404('La carga solicitada no existe.')
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        nombre = f'Plano_{carga.proyecto.codigo}_{carga.anio}_{carga.mes:02d}.csv'
        response['Content-Disposition'] = f'attachment; filename="{nombre}"'
        response.write('\ufeff')
        writer = csv.writer(response)
        writer.writerow(['Código', 'Concepto', 'Centro', 'Proyecto', 'Mes', 'Valor', 'Referencia'])
        agrupadas = defaultdict(lambda: {'valor': ZERO, 'referencias': set()})
        for linea in carga.lineas.select_related('homologacion'):
            homologacion = linea.homologacion
            llave = (
                homologacion.codigo_contable if homologacion else 'SIN_HOMOLOGAR',
                homologacion.concepto if homologacion else linea.concepto,
                homologacion.centro_costo if homologacion else '',
            )
            agrupadas[llave]['valor'] += linea.valor
            if linea.referencia:
                agrupadas[llave]['referencias'].add(linea.referencia)
        for (codigo, concepto, centro), datos in sorted(agrupadas.items()):
            writer.writerow([codigo, concepto, centro, carga.proyecto.nombre, f'{carga.mes:02d}-{carga.anio}', datos['valor'], ' | '.join(sorted(datos['referencias']))])
        return response
