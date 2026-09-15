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
        periodo = self.request.GET.get('periodo') or self.request.POST.get('periodo')
        if periodo:
            try:
                anio, mes = int(periodo[:4]), int(periodo[4:])
            except (TypeError, ValueError):
                return timezone.now().year, timezone.now().month, False
        else:
            anio = self.request.GET.get('anio') or self.request.POST.get('anio') or timezone.now().year
            mes = self.request.GET.get('mes') or self.request.POST.get('mes') or timezone.now().month
        try:
            anio, mes = int(anio), int(mes)
        except (TypeError, ValueError):
            return timezone.now().year, timezone.now().month, False
        return anio, mes, 1 <= mes <= 12

    def _filtros(self):
        """Valores GET validados después de período y proyecto."""
        return (
            (self.request.GET.get('tipo') or self.request.POST.get('tipo') or '').strip(),
            (self.request.GET.get('centro_costo') or self.request.POST.get('centro_costo') or '').strip(),
        )

    @staticmethod
    def _indicadores(carga, *, tipo_operacional='', centro_costo=''):
        if not carga:
            return []
        lineas = carga.lineas.all()
        if tipo_operacional:
            lineas = lineas.filter(tipo_operacional=tipo_operacional)
        if centro_costo:
            lineas = lineas.filter(centro_costo=centro_costo)
        real = sum((linea.valor for linea in lineas.filter(tipo=LineaCargaFinanciera.Tipo.REAL)), ZERO)
        presupuesto = sum((linea.valor for linea in lineas.filter(tipo=LineaCargaFinanciera.Tipo.PRESUPUESTO)), ZERO)
        margen = real - presupuesto
        anterior = CargaFinanciera.objects.filter(
            proyecto=carga.proyecto,
        ).exclude(pk=carga.pk).order_by('-anio', '-mes', '-created_at').first()
        real_anterior = ZERO
        if anterior:
            anteriores = anterior.lineas.all()
            if tipo_operacional:
                anteriores = anteriores.filter(tipo_operacional=tipo_operacional)
            if centro_costo:
                anteriores = anteriores.filter(centro_costo=centro_costo)
            real_anterior = sum((linea.valor for linea in anteriores.filter(tipo=LineaCargaFinanciera.Tipo.REAL)), ZERO)
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
        tipo_operacional, centro_costo = self._filtros()
        cargas_vigentes = CargaFinanciera.objects.filter(vigente=True)
        periodos_disponibles = list(cargas_vigentes.order_by('-anio', '-mes').values_list('anio', 'mes'))
        proyectos_disponibles = Contrato.objects.filter(estado=Contrato.Estado.ACTIVO)
        if periodo_valido:
            proyectos_disponibles = proyectos_disponibles.filter(
                cargas_financieras__vigente=True, cargas_financieras__anio=anio, cargas_financieras__mes=mes,
            ).distinct()
        carga = None
        if proyecto and periodo_valido:
            carga = CargaFinanciera.objects.filter(
                proyecto=proyecto, anio=anio, mes=mes, vigente=True,
            ).first()
        base_lineas = carga.lineas.all() if carga else LineaCargaFinanciera.objects.none()
        tipos_disponibles = list(base_lineas.order_by('tipo_operacional').values_list('tipo_operacional', flat=True).distinct())
        if tipo_operacional and tipo_operacional not in tipos_disponibles:
            tipo_operacional = ''
        lineas_por_tipo = base_lineas.filter(tipo_operacional=tipo_operacional) if tipo_operacional else base_lineas
        centros_disponibles = list(lineas_por_tipo.exclude(centro_costo='').order_by('centro_costo').values_list('centro_costo', flat=True).distinct())
        if centro_costo and centro_costo not in centros_disponibles:
            centro_costo = ''
        context.update({
            'carga_form': kwargs.get('carga_form') or CargaFinancieraForm(),
            'proyectos': Contrato.objects.filter(estado=Contrato.Estado.ACTIVO),
            'proyectos_disponibles': proyectos_disponibles,
            'periodos_disponibles': periodos_disponibles,
            'proyecto_seleccionado': proyecto,
            'anio': anio,
            'mes': mes,
            'periodo_valido': periodo_valido,
            'carga_actual': carga,
            'tipo_seleccionado': tipo_operacional,
            'centro_costo_seleccionado': centro_costo,
            'tipos_disponibles': tipos_disponibles,
            'centros_disponibles': centros_disponibles,
            'historial_cargas': CargaFinanciera.objects.select_related('proyecto', 'usuario').all()[:20],
            'homologaciones': HomologacionProjectsContable.objects.all()[:100],
            'indicadores': self._indicadores(carga, tipo_operacional=tipo_operacional, centro_costo=centro_costo),
        })
        return context

    def post(self, request, *args, **kwargs):
        accion = request.POST.get('accion')
        if accion == 'homologar':
            return self._crear_homologacion()
        if accion == 'eliminar_homologacion':
            return self._eliminar_homologacion()
        return self._cargar_archivo()

    def _redirect_periodo(self, proyecto=None, anio=None, mes=None, tipo_operacional=None, centro_costo=None):
        params = []
        if proyecto:
            params.append(f'proyecto={proyecto.pk}')
        if anio:
            params.append(f'anio={anio}')
        if mes:
            params.append(f'mes={mes}')
        tipo_operacional = tipo_operacional if tipo_operacional is not None else self._filtros()[0]
        centro_costo = centro_costo if centro_costo is not None else self._filtros()[1]
        if tipo_operacional:
            params.append(f'tipo={tipo_operacional}')
        if centro_costo:
            params.append(f'centro_costo={centro_costo}')
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
