"""
Views for financial management.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from apps.core.mixins import HTMXMixin, RoleRequiredMixin

from .models import (
    ArchivoChecklist,
    ArchivoPeriodoFacturacion,
    ChecklistFacturacion,
    CicloFacturacion,
    EjecucionCosto,
    Presupuesto,
    PresupuestoDetallado,
)


class DashboardFinancieroView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Financial dashboard."""
    template_name = 'financiero/dashboard.html'
    allowed_roles = ['admin', 'director', 'coordinador']

    def _get_period_filter(self, hoy):
        """Return (anio_filter, mes_filter_start, mes_filter_end) based on periodo param."""
        periodo = self.request.GET.get('periodo', 'mes')
        if periodo == 'trimestre':
            q = (hoy.month - 1) // 3
            mes_inicio = q * 3 + 1
            mes_fin = mes_inicio + 2
            return hoy.year, mes_inicio, mes_fin, periodo
        elif periodo == 'anio':
            return hoy.year, 1, 12, periodo
        else:
            return hoy.year, hoy.month, hoy.month, periodo

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        import json

        from django.db.models import Q
        from django.utils import timezone

        from apps.actividades.models import Actividad
        from apps.lineas.models import Linea

        hoy = timezone.now()
        anio, mes_inicio, mes_fin, periodo_actual = self._get_period_filter(hoy)

        # Budgets for the selected period
        presupuestos = Presupuesto.objects.filter(
            anio=anio,
            mes__gte=mes_inicio,
            mes__lte=mes_fin,
        )

        total_presupuestado = presupuestos.aggregate(
            total=Sum('total_presupuestado')
        )['total'] or Decimal('0')

        total_ejecutado = presupuestos.aggregate(
            total=Sum('total_ejecutado')
        )['total'] or Decimal('0')

        context['total_presupuestado'] = total_presupuestado
        context['total_ejecutado'] = total_ejecutado
        context['presupuesto'] = total_presupuestado
        context['ejecutado'] = total_ejecutado

        # Percentage executed
        if total_presupuestado > 0:
            context['porcentaje_ejecutado'] = float(total_ejecutado / total_presupuestado * 100)
        else:
            context['porcentaje_ejecutado'] = 0

        context['facturacion_esperada'] = presupuestos.aggregate(
            total=Sum('facturacion_esperada')
        )['total'] or 0

        # Billing cycles
        context['ciclos_pendientes'] = CicloFacturacion.objects.exclude(
            estado='PAGO_RECIBIDO'
        ).count()

        # Cost breakdown - all pillar aggregations in a single query
        pillar_aggs = presupuestos.aggregate(
            personal=Sum('costo_dias_hombre'),
            vehiculos=Sum('costo_vehiculos'),
            viaticos=Sum('viaticos_planeados'),
            herramientas=Sum('costo_herramientas'),
            ambientales=Sum('costo_ambientales'),
            subcontratistas=Sum('costo_subcontratistas'),
            transporte=Sum('costo_transporte'),
            materiales=Sum('costo_materiales'),
            garantia=Sum('costo_garantia'),
            otros=Sum('otros_costos'),
        )
        costo_personal = pillar_aggs['personal'] or Decimal('0')
        costo_equipos = pillar_aggs['vehiculos'] or Decimal('0')
        costo_viaticos = pillar_aggs['viaticos'] or Decimal('0')
        costo_herramientas = pillar_aggs['herramientas'] or Decimal('0')
        costo_ambientales = pillar_aggs['ambientales'] or Decimal('0')
        costo_subcontratistas = pillar_aggs['subcontratistas'] or Decimal('0')
        costo_transporte = pillar_aggs['transporte'] or Decimal('0')
        costo_materiales = pillar_aggs['materiales'] or Decimal('0')
        costo_garantia = pillar_aggs['garantia'] or Decimal('0')
        costo_otros = pillar_aggs['otros'] or Decimal('0')

        context['costo_personal'] = costo_personal
        context['costo_equipos'] = costo_equipos

        if total_ejecutado > 0:
            context['porcentaje_personal'] = float(costo_personal / total_ejecutado * 100)
            context['porcentaje_equipos'] = float(costo_equipos / total_ejecutado * 100)
        else:
            context['porcentaje_personal'] = 0
            context['porcentaje_equipos'] = 0

        # Cost per activity
        actividades_completadas = Actividad.objects.filter(
            fecha_programada__year=anio,
            fecha_programada__month__gte=mes_inicio,
            fecha_programada__month__lte=mes_fin,
            estado='COMPLETADA'
        ).count()

        if actividades_completadas > 0:
            context['costo_promedio_actividad'] = float(total_ejecutado / actividades_completadas)
        else:
            context['costo_promedio_actividad'] = 0

        # Month-over-month variation for cost per activity
        if periodo_actual == 'mes':
            prev_m = hoy.month - 1
            prev_y = hoy.year
            if prev_m <= 0:
                prev_m += 12
                prev_y -= 1
            prev_pres = Presupuesto.objects.filter(anio=prev_y, mes=prev_m)
            prev_ejecutado = prev_pres.aggregate(total=Sum('total_ejecutado'))['total'] or Decimal('0')
            prev_actividades = Actividad.objects.filter(
                fecha_programada__year=prev_y,
                fecha_programada__month=prev_m,
                estado='COMPLETADA'
            ).count()
            prev_costo_prom = float(prev_ejecutado / prev_actividades) if prev_actividades else 0
            if prev_costo_prom > 0 and context['costo_promedio_actividad'] > 0:
                context['variacion_costo'] = float(
                    (context['costo_promedio_actividad'] - prev_costo_prom) / prev_costo_prom * 100
                )
            else:
                context['variacion_costo'] = 0
        else:
            context['variacion_costo'] = 0

        # Period filters
        context['periodos'] = [
            {'value': 'mes', 'label': 'Este mes'},
            {'value': 'trimestre', 'label': 'Este trimestre'},
            {'value': 'anio', 'label': 'Este año'},
        ]
        context['periodo_actual'] = periodo_actual

        context['costo_herramientas'] = costo_herramientas
        context['costo_ambientales'] = costo_ambientales
        context['costo_subcontratistas'] = costo_subcontratistas
        context['costo_transporte'] = costo_transporte
        context['costo_garantia'] = costo_garantia
        context['costo_materiales'] = costo_materiales

        # Chart data - Costs by category (all pillars)
        context['costos_categoria_data'] = json.dumps([
            {'value': float(costo_personal), 'name': 'Personal'},
            {'value': float(costo_equipos), 'name': 'Equipos/Vehículos'},
            {'value': float(costo_viaticos), 'name': 'Viáticos'},
            {'value': float(costo_herramientas), 'name': 'Herramientas'},
            {'value': float(costo_ambientales), 'name': 'Ambientales'},
            {'value': float(costo_subcontratistas), 'name': 'Subcontratistas'},
            {'value': float(costo_transporte), 'name': 'Transporte'},
            {'value': float(costo_materiales), 'name': 'Materiales'},
            {'value': float(costo_garantia), 'name': 'Garantía'},
            {'value': float(costo_otros), 'name': 'Otros'},
        ])

        # Monthly trend (last 6 months)
        meses_labels = []
        presupuesto_mensual = []
        ejecutado_mensual = []
        meses_nombres = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

        for i in range(5, -1, -1):
            m = hoy.month - i
            a = hoy.year
            if m <= 0:
                m += 12
                a -= 1
            meses_labels.append(meses_nombres[m-1])
            pres_mes = Presupuesto.objects.filter(anio=a, mes=m)
            presupuesto_mensual.append(float(pres_mes.aggregate(total=Sum('total_presupuestado'))['total'] or 0))
            ejecutado_mensual.append(float(pres_mes.aggregate(total=Sum('total_ejecutado'))['total'] or 0))

        context['meses_labels'] = json.dumps(meses_labels)
        context['presupuesto_mensual'] = json.dumps(presupuesto_mensual)
        context['ejecutado_mensual'] = json.dumps(ejecutado_mensual)

        # Costs by line (uses the same period filter)
        lineas = Linea.objects.filter(activa=True)[:10]
        lineas_labels = []
        costos_linea = []
        presupuestos_linea = []
        for linea in lineas:
            lineas_labels.append(linea.codigo)
            pres_linea = Presupuesto.objects.filter(
                linea=linea, anio=anio,
                mes__gte=mes_inicio, mes__lte=mes_fin,
            )
            costos_linea.append(float(pres_linea.aggregate(total=Sum('total_ejecutado'))['total'] or 0))
            presupuestos_linea.append(float(pres_linea.aggregate(total=Sum('total_presupuestado'))['total'] or 0))

        context['lineas_labels'] = json.dumps(lineas_labels)
        context['costos_linea'] = json.dumps(costos_linea)
        context['presupuestos_linea'] = json.dumps(presupuestos_linea)

        # Cost detail table - all 6 budget pillars
        def _build_row(cat, concepto, valor):
            """Build a detail row. valor is the presupuestado amount (same as ejecutado for now)."""
            pres = float(valor)
            ejec = float(valor)  # until EjecucionCosto is linked per pillar
            return {
                'categoria': cat,
                'concepto': concepto,
                'presupuesto': pres,
                'ejecutado': ejec,
                'porcentaje': (ejec / pres * 100) if pres > 0 else 0,
                'disponible': pres - ejec,
            }

        context['detalle_costos'] = [
            {
                'categoria': 'Mano de Obra',
                'concepto': 'Días hombre',
                'presupuesto': float(costo_personal),
                'ejecutado': float(costo_personal),
                'porcentaje': 100 if costo_personal > 0 else 0,
                'disponible': 0,
            },
            {
                'categoria': 'Vehículos',
                'concepto': 'Equipos y vehículos',
                'presupuesto': float(costo_equipos),
                'ejecutado': float(costo_equipos),
                'porcentaje': 100 if costo_equipos > 0 else 0,
                'disponible': 0,
            },
            {
                'categoria': 'Viáticos',
                'concepto': 'Viáticos del personal',
                'presupuesto': float(costo_viaticos),
                'ejecutado': float(costo_viaticos),
                'porcentaje': 100 if costo_viaticos > 0 else 0,
                'disponible': 0,
            },
            {
                'categoria': 'Herramientas',
                'concepto': 'Herramientas y equipos menores',
                'presupuesto': float(costo_herramientas),
                'ejecutado': float(costo_herramientas),
                'porcentaje': 100 if costo_herramientas > 0 else 0,
                'disponible': 0,
            },
            {
                'categoria': 'Ambientales',
                'concepto': 'Gestión ambiental y permisos',
                'presupuesto': float(costo_ambientales),
                'ejecutado': float(costo_ambientales),
                'porcentaje': 100 if costo_ambientales > 0 else 0,
                'disponible': 0,
            },
            {
                'categoria': 'Subcontratistas',
                'concepto': 'Subcontratistas y terceros',
                'presupuesto': float(costo_subcontratistas),
                'ejecutado': float(costo_subcontratistas),
                'porcentaje': 100 if costo_subcontratistas > 0 else 0,
                'disponible': 0,
            },
            {
                'categoria': 'Transporte',
                'concepto': 'Transporte adicional',
                'presupuesto': float(costo_transporte),
                'ejecutado': float(costo_transporte),
                'porcentaje': 100 if costo_transporte > 0 else 0,
                'disponible': 0,
            },
            {
                'categoria': 'Materiales',
                'concepto': 'Materiales e insumos',
                'presupuesto': float(costo_materiales),
                'ejecutado': float(costo_materiales),
                'porcentaje': 100 if costo_materiales > 0 else 0,
                'disponible': 0,
            },
            {
                'categoria': 'Garantía',
                'concepto': 'Garantías y pólizas',
                'presupuesto': float(costo_garantia),
                'ejecutado': float(costo_garantia),
                'porcentaje': 100 if costo_garantia > 0 else 0,
                'disponible': 0,
            },
            {
                'categoria': 'Otros',
                'concepto': 'Otros costos',
                'presupuesto': float(costo_otros),
                'ejecutado': float(costo_otros),
                'porcentaje': 100 if costo_otros > 0 else 0,
                'disponible': 0,
            },
        ]
        # Filter out zero rows
        context['detalle_costos'] = [r for r in context['detalle_costos'] if r['presupuesto'] > 0]

        context['total_presupuesto'] = total_presupuestado
        context['porcentaje_total'] = context['porcentaje_ejecutado']
        context['total_disponible'] = float(total_presupuestado - total_ejecutado)

        # Budget alerts (Issue 7)
        alertas = []
        porcentaje = context['porcentaje_ejecutado']
        if porcentaje > 100:
            alertas.append({
                'tipo': 'danger',
                'icono': 'exclamation-triangle',
                'titulo': 'Presupuesto excedido',
                'mensaje': f'El ejecutado supera el presupuestado en {porcentaje - 100:.1f}%',
                'color': 'red',
            })
        elif porcentaje > 80:
            alertas.append({
                'tipo': 'warning',
                'icono': 'exclamation',
                'titulo': 'Presupuesto en zona de alerta',
                'mensaje': f'Se ha ejecutado el {porcentaje:.1f}% del presupuesto',
                'color': 'yellow',
            })

        # Check facturacion esperada vs real
        facturacion_esperada = context['facturacion_esperada'] or Decimal('0')
        ciclos_facturados = CicloFacturacion.objects.filter(
            presupuesto__anio=anio,
            presupuesto__mes__gte=mes_inicio,
            presupuesto__mes__lte=mes_fin,
        )
        facturacion_real = ciclos_facturados.aggregate(
            total=Sum('monto_facturado')
        )['total'] or Decimal('0')
        context['facturacion_real'] = facturacion_real

        if facturacion_esperada > 0:
            pct_facturacion = float(facturacion_real / facturacion_esperada * 100)
            context['porcentaje_facturacion'] = pct_facturacion
            if pct_facturacion < 50:
                alertas.append({
                    'tipo': 'warning',
                    'icono': 'currency-dollar',
                    'titulo': 'Facturacion rezagada',
                    'mensaje': f'Solo se ha facturado {pct_facturacion:.1f}% de lo esperado',
                    'color': 'yellow',
                })
        else:
            context['porcentaje_facturacion'] = 0

        # Check individual line budgets
        for pres in presupuestos.select_related('linea'):
            if pres.total_presupuestado > 0:
                pct = float(pres.total_ejecutado / pres.total_presupuestado * 100)
                if pct > 100:
                    alertas.append({
                        'tipo': 'danger',
                        'icono': 'exclamation-triangle',
                        'titulo': f'{pres.linea.codigo} - Sobrecosto',
                        'mensaje': f'Ejecutado {pct:.1f}% del presupuesto asignado',
                        'color': 'red',
                    })

        context['alertas'] = alertas

        return context


class ExportarDashboardExcelView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Export the financial dashboard detail as an Excel file."""
    template_name = 'financiero/dashboard.html'  # fallback, never rendered
    allowed_roles = ['admin', 'director', 'coordinador']

    def get(self, request, *args, **kwargs):
        import io
        from django.http import HttpResponse
        from django.utils import timezone
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter

        hoy = timezone.now()
        periodo = request.GET.get('periodo', 'mes')

        # Reuse dashboard logic for period
        if periodo == 'trimestre':
            q = (hoy.month - 1) // 3
            mes_inicio = q * 3 + 1
            mes_fin = mes_inicio + 2
        elif periodo == 'anio':
            mes_inicio, mes_fin = 1, 12
        else:
            mes_inicio = mes_fin = hoy.month

        anio = hoy.year
        presupuestos = Presupuesto.objects.filter(
            anio=anio, mes__gte=mes_inicio, mes__lte=mes_fin,
        )

        pillar_aggs = presupuestos.aggregate(
            personal=Sum('costo_dias_hombre'),
            vehiculos=Sum('costo_vehiculos'),
            viaticos=Sum('viaticos_planeados'),
            herramientas=Sum('costo_herramientas'),
            ambientales=Sum('costo_ambientales'),
            subcontratistas=Sum('costo_subcontratistas'),
            transporte=Sum('costo_transporte'),
            materiales=Sum('costo_materiales'),
            garantia=Sum('costo_garantia'),
            otros=Sum('otros_costos'),
        )

        rows = [
            ('Mano de Obra', 'Días hombre', pillar_aggs['personal']),
            ('Vehículos', 'Equipos y vehículos', pillar_aggs['vehiculos']),
            ('Viáticos', 'Viáticos del personal', pillar_aggs['viaticos']),
            ('Herramientas', 'Herramientas y equipos menores', pillar_aggs['herramientas']),
            ('Ambientales', 'Gestión ambiental y permisos', pillar_aggs['ambientales']),
            ('Subcontratistas', 'Subcontratistas y terceros', pillar_aggs['subcontratistas']),
            ('Transporte', 'Transporte adicional', pillar_aggs['transporte']),
            ('Materiales', 'Materiales e insumos', pillar_aggs['materiales']),
            ('Garantía', 'Garantías y pólizas', pillar_aggs['garantia']),
            ('Otros', 'Otros costos', pillar_aggs['otros']),
        ]
        rows = [(cat, conc, float(val or 0)) for cat, conc, val in rows if val]

        total_pres = float(presupuestos.aggregate(t=Sum('total_presupuestado'))['t'] or 0)
        total_ejec = float(presupuestos.aggregate(t=Sum('total_ejecutado'))['t'] or 0)

        wb = Workbook()
        ws = wb.active
        ws.title = 'Detalle Costos'

        # Styles
        header_font = Font(bold=True, color='FFFFFF', size=11)
        header_fill = PatternFill(start_color='1F4E79', end_color='1F4E79', fill_type='solid')
        total_fill = PatternFill(start_color='D6E4F0', end_color='D6E4F0', fill_type='solid')
        total_font = Font(bold=True, size=11)
        thin_border = Border(
            left=Side(style='thin'), right=Side(style='thin'),
            top=Side(style='thin'), bottom=Side(style='thin'),
        )
        money_fmt = '#,##0'
        pct_fmt = '0.0"%"'

        # Title
        meses_nombres = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                         'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
        if mes_inicio == mes_fin:
            titulo_periodo = f'{meses_nombres[mes_inicio - 1]} {anio}'
        else:
            titulo_periodo = f'{meses_nombres[mes_inicio - 1]} - {meses_nombres[mes_fin - 1]} {anio}'

        ws.merge_cells('A1:F1')
        title_cell = ws['A1']
        title_cell.value = f'Detalle de Ejecucion Presupuestal - {titulo_periodo}'
        title_cell.font = Font(bold=True, size=14)
        title_cell.alignment = Alignment(horizontal='center')

        ws.merge_cells('A2:F2')
        ws['A2'].value = f'Generado: {hoy.strftime("%d/%m/%Y %H:%M")}'
        ws['A2'].alignment = Alignment(horizontal='center')
        ws['A2'].font = Font(italic=True, color='666666')

        # Headers (row 4)
        headers = ['Categoría', 'Concepto', 'Presupuesto ($)', 'Ejecutado ($)', '% Ejecución', 'Disponible ($)']
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=4, column=col, value=h)
            cell.font = header_font
            cell.fill = header_fill
            cell.border = thin_border
            cell.alignment = Alignment(horizontal='right' if col > 2 else 'left')

        # Data rows
        for i, (cat, conc, val) in enumerate(rows, 5):
            pres = val
            ejec = val
            pct = 100.0 if pres > 0 else 0.0
            disp = pres - ejec

            ws.cell(row=i, column=1, value=cat).border = thin_border
            ws.cell(row=i, column=2, value=conc).border = thin_border
            c = ws.cell(row=i, column=3, value=pres)
            c.number_format = money_fmt
            c.border = thin_border
            c.alignment = Alignment(horizontal='right')
            c = ws.cell(row=i, column=4, value=ejec)
            c.number_format = money_fmt
            c.border = thin_border
            c.alignment = Alignment(horizontal='right')
            c = ws.cell(row=i, column=5, value=pct)
            c.number_format = pct_fmt
            c.border = thin_border
            c.alignment = Alignment(horizontal='right')
            c = ws.cell(row=i, column=6, value=disp)
            c.number_format = money_fmt
            c.border = thin_border
            c.alignment = Alignment(horizontal='right')

        # Total row
        total_row = 5 + len(rows)
        pct_total = (total_ejec / total_pres * 100) if total_pres > 0 else 0

        for col in range(1, 7):
            cell = ws.cell(row=total_row, column=col)
            cell.fill = total_fill
            cell.font = total_font
            cell.border = thin_border

        ws.cell(row=total_row, column=1, value='TOTAL')
        ws.cell(row=total_row, column=2, value='')
        c = ws.cell(row=total_row, column=3, value=total_pres)
        c.number_format = money_fmt
        c.alignment = Alignment(horizontal='right')
        c = ws.cell(row=total_row, column=4, value=total_ejec)
        c.number_format = money_fmt
        c.alignment = Alignment(horizontal='right')
        c = ws.cell(row=total_row, column=5, value=pct_total)
        c.number_format = pct_fmt
        c.alignment = Alignment(horizontal='right')
        c = ws.cell(row=total_row, column=6, value=total_pres - total_ejec)
        c.number_format = money_fmt
        c.alignment = Alignment(horizontal='right')

        # ---- Sheet 2: Detalle por Linea ----
        ws2 = wb.create_sheet('Por Linea')
        from apps.lineas.models import Linea
        lineas = Linea.objects.filter(activa=True)

        ws2.merge_cells('A1:G1')
        ws2['A1'].value = f'Presupuesto vs Ejecutado por Línea - {titulo_periodo}'
        ws2['A1'].font = Font(bold=True, size=14)
        ws2['A1'].alignment = Alignment(horizontal='center')

        headers2 = ['Línea', 'Código', 'Presupuestado ($)', 'Ejecutado ($)', '% Ejecución', 'Disponible ($)', 'Estado']
        for col, h in enumerate(headers2, 1):
            cell = ws2.cell(row=3, column=col, value=h)
            cell.font = header_font
            cell.fill = header_fill
            cell.border = thin_border

        row_num = 4
        for linea in lineas:
            pres_linea = Presupuesto.objects.filter(
                linea=linea, anio=anio,
                mes__gte=mes_inicio, mes__lte=mes_fin,
            )
            pres_val = float(pres_linea.aggregate(t=Sum('total_presupuestado'))['t'] or 0)
            ejec_val = float(pres_linea.aggregate(t=Sum('total_ejecutado'))['t'] or 0)
            if pres_val == 0 and ejec_val == 0:
                continue
            pct = (ejec_val / pres_val * 100) if pres_val > 0 else 0
            estado = 'OK' if pct <= 90 else ('Alerta' if pct <= 100 else 'Sobrecosto')

            ws2.cell(row=row_num, column=1, value=linea.nombre).border = thin_border
            ws2.cell(row=row_num, column=2, value=linea.codigo).border = thin_border
            c = ws2.cell(row=row_num, column=3, value=pres_val)
            c.number_format = money_fmt
            c.border = thin_border
            c = ws2.cell(row=row_num, column=4, value=ejec_val)
            c.number_format = money_fmt
            c.border = thin_border
            c = ws2.cell(row=row_num, column=5, value=pct)
            c.number_format = pct_fmt
            c.border = thin_border
            c = ws2.cell(row=row_num, column=6, value=pres_val - ejec_val)
            c.number_format = money_fmt
            c.border = thin_border
            ws2.cell(row=row_num, column=7, value=estado).border = thin_border
            row_num += 1

        # Auto-width for both sheets
        for sheet in [ws, ws2]:
            for col_idx in range(1, sheet.max_column + 1):
                max_len = 0
                col_letter = get_column_letter(col_idx)
                for row in sheet.iter_rows(min_col=col_idx, max_col=col_idx, values_only=False):
                    for cell in row:
                        if cell.value:
                            max_len = max(max_len, len(str(cell.value)))
                sheet.column_dimensions[col_letter].width = min(max_len + 4, 40)

        # Write to response
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        filename = f'detalle_costos_{anio}_{mes_inicio:02d}.xlsx'
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class PresupuestoListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    """List budgets."""
    model = Presupuesto
    template_name = 'financiero/presupuestos.html'
    context_object_name = 'presupuestos'
    allowed_roles = ['admin', 'director', 'coordinador']

    def get_queryset(self):
        return super().get_queryset().select_related('linea')


class PresupuestoDetailView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    """Budget detail view."""
    model = Presupuesto
    template_name = 'financiero/presupuesto_detalle.html'
    context_object_name = 'presupuesto'
    allowed_roles = ['admin', 'director', 'coordinador']

    def get_queryset(self):
        return super().get_queryset().select_related('linea').prefetch_related(
            'ejecuciones',
            'ejecuciones__actividad',
            'ejecuciones__actividad__torre',
            'ejecuciones__actividad__tipo_actividad'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # ejecuciones already prefetched via get_queryset
        context['ejecuciones'] = self.object.ejecuciones.all()
        return context


class PresupuestoCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    """Create a new budget."""
    model = Presupuesto
    template_name = 'financiero/presupuesto_form.html'
    allowed_roles = ['admin', 'director', 'coordinador']
    success_url = reverse_lazy('financiero:presupuestos')

    def get_form_class(self):
        from .forms import PresupuestoForm
        return PresupuestoForm


class PresupuestoUpdateView(LoginRequiredMixin, RoleRequiredMixin, UpdateView):
    """Edit an existing budget."""
    model = Presupuesto
    template_name = 'financiero/presupuesto_form.html'
    allowed_roles = ['admin', 'director', 'coordinador']

    def get_form_class(self):
        from .forms import PresupuestoForm
        return PresupuestoForm

    def get_success_url(self):
        return reverse_lazy('financiero:presupuesto_detalle', kwargs={'pk': self.object.pk})


class CuadroCostosView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Generate billing cost table."""
    template_name = 'financiero/cuadro_costos.html'
    allowed_roles = ['admin', 'director', 'coordinador']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        mes = self.request.GET.get('mes')
        anio = self.request.GET.get('anio')
        linea = self.request.GET.get('linea')

        if mes and anio and linea:
            ejecuciones = EjecucionCosto.objects.filter(
                presupuesto__mes=mes,
                presupuesto__anio=anio,
                presupuesto__linea_id=linea
            ).select_related('actividad__torre', 'actividad__tipo_actividad')

            context['ejecuciones'] = ejecuciones
            context['total'] = ejecuciones.aggregate(total=Sum('costo_total'))['total'] or 0

        return context


class FacturacionView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    """Billing cycles view."""
    model = CicloFacturacion
    template_name = 'financiero/facturacion.html'
    context_object_name = 'ciclos'
    allowed_roles = ['admin', 'director', 'coordinador']

    def get_queryset(self):
        return super().get_queryset().select_related('presupuesto__linea')


class CostosCuadrillaView(LoginRequiredMixin, RoleRequiredMixin, HTMXMixin, TemplateView):
    """View for crew costs filtered by day or week."""
    template_name = 'financiero/costos_cuadrilla.html'
    partial_template_name = 'financiero/partials/costos_cuadrilla_tabla.html'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente']

    def get_context_data(self, **kwargs):
        import json
        from collections import OrderedDict

        from apps.cuadrillas.models import Cuadrilla, CuadrillaMiembro

        context = super().get_context_data(**kwargs)

        filtro = self.request.GET.get('filtro', 'semana')  # 'dia' or 'semana'
        semana_param = self.request.GET.get('semana', '').strip()
        fecha_param = self.request.GET.get('fecha', '').strip()

        context['filtro'] = filtro
        context['semana_param'] = semana_param
        context['fecha_param'] = fecha_param

        cuadrillas_data = []
        gran_total_personal = Decimal('0')
        gran_total_vehiculo = Decimal('0')
        gran_total = Decimal('0')

        if filtro == 'dia' and fecha_param:
            # Filter cuadrillas by fecha field
            try:
                fecha_filtro = date.fromisoformat(fecha_param)
            except ValueError:
                fecha_filtro = None

            if fecha_filtro:
                cuadrillas = Cuadrilla.objects.filter(
                    activa=True, fecha=fecha_filtro
                ).select_related('supervisor', 'vehiculo').prefetch_related(
                    'miembros__usuario'
                )

                for cuadrilla in cuadrillas:
                    miembros = cuadrilla.miembros.filter(activo=True).select_related('usuario')
                    costo_personal = sum((m.costo_dia for m in miembros), Decimal('0'))
                    costo_vehiculo = cuadrilla.vehiculo.costo_dia if cuadrilla.vehiculo else Decimal('0')
                    total = costo_personal + costo_vehiculo

                    gran_total_personal += costo_personal
                    gran_total_vehiculo += costo_vehiculo
                    gran_total += total

                    miembros_list = [{
                        'nombre': m.usuario.get_full_name(),
                        'rol': m.get_rol_cuadrilla_display(),
                        'cargo': m.get_cargo_display(),
                        'costo_dia': m.costo_dia,
                    } for m in miembros]

                    cuadrillas_data.append({
                        'cuadrilla': cuadrilla,
                        'miembros': miembros_list,
                        'costo_personal': costo_personal,
                        'costo_vehiculo': costo_vehiculo,
                        'total': total,
                    })

        elif filtro == 'semana' and semana_param:
            # Filter by week code prefix (WW-YYYY)
            try:
                parts = semana_param.split('-')
                sem = parts[0].zfill(2)
                ano = parts[1]
                prefix = f'{sem}-{ano}-'
            except (IndexError, ValueError):
                prefix = None

            if prefix:
                cuadrillas = Cuadrilla.objects.filter(
                    activa=True, codigo__startswith=prefix
                ).select_related('supervisor', 'vehiculo').prefetch_related(
                    'miembros__usuario'
                )

                for cuadrilla in cuadrillas:
                    miembros = cuadrilla.miembros.filter(activo=True).select_related('usuario')
                    costo_personal = sum((m.costo_dia for m in miembros), Decimal('0'))
                    costo_vehiculo = cuadrilla.vehiculo.costo_dia if cuadrilla.vehiculo else Decimal('0')
                    total = costo_personal + costo_vehiculo

                    gran_total_personal += costo_personal
                    gran_total_vehiculo += costo_vehiculo
                    gran_total += total

                    miembros_list = [{
                        'nombre': m.usuario.get_full_name(),
                        'rol': m.get_rol_cuadrilla_display(),
                        'cargo': m.get_cargo_display(),
                        'costo_dia': m.costo_dia,
                    } for m in miembros]

                    cuadrillas_data.append({
                        'cuadrilla': cuadrilla,
                        'miembros': miembros_list,
                        'costo_personal': costo_personal,
                        'costo_vehiculo': costo_vehiculo,
                        'total': total,
                    })

        context['cuadrillas_data'] = cuadrillas_data
        context['gran_total_personal'] = gran_total_personal
        context['gran_total_vehiculo'] = gran_total_vehiculo
        context['gran_total'] = gran_total

        # Build list of available weeks for the filter
        todas = Cuadrilla.objects.filter(activa=True).values_list('codigo', flat=True)
        semanas_set = set()
        for codigo in todas:
            try:
                parts = codigo.split('-')
                if len(parts) >= 2:
                    semana = int(parts[0])
                    ano = int(parts[1])
                    if 1 <= semana <= 53 and 2000 <= ano <= 2100:
                        semanas_set.add((ano, semana))
            except (ValueError, IndexError):
                pass

        semanas_disponibles = sorted(semanas_set, reverse=True)
        context['semanas_disponibles'] = [
            {'value': f'{s[1]}-{s[0]}', 'label': f'Semana {s[1]} - {s[0]}'}
            for s in semanas_disponibles
        ]

        return context


class CostosVsProduccionDashboardView(LoginRequiredMixin, RoleRequiredMixin, HTMXMixin, TemplateView):
    """
    Dashboard de costos vs producción en tiempo real.
    Muestra: costo acumulado, producción estimada, desviación.
    """
    template_name = 'financiero/costos_vs_produccion.html'
    partial_template_name = 'financiero/partials/costos_vs_produccion_tabla.html'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.actividades.models import Actividad
        from apps.lineas.models import Linea

        from .models import CostoActividad

        # Filtros
        linea_id = self.request.GET.get('linea')
        fecha_inicio = self.request.GET.get('fecha_inicio')
        fecha_fin = self.request.GET.get('fecha_fin')

        # Obtener actividades en curso o completadas
        qs = Actividad.objects.filter(
            estado__in=['EN_CURSO', 'COMPLETADA']
        ).select_related(
            'linea', 'tipo_actividad', 'cuadrilla', 'tramo'
        )

        if linea_id:
            qs = qs.filter(linea_id=linea_id)

        if fecha_inicio:
            try:
                qs = qs.filter(fecha_programada__gte=date.fromisoformat(fecha_inicio))
            except ValueError:
                pass

        if fecha_fin:
            try:
                qs = qs.filter(fecha_programada__lte=date.fromisoformat(fecha_fin))
            except ValueError:
                pass

        # Calcular métricas por actividad
        actividades_data = []
        total_produccion = Decimal('0')
        total_costo = Decimal('0')

        for actividad in qs:
            produccion = actividad.produccion_proporcional

            try:
                costo = CostoActividad.objects.get(actividad=actividad)
                costo_acumulado = costo.costo_total
            except CostoActividad.DoesNotExist:
                costo_acumulado = Decimal('0')

            desviacion = produccion - costo_acumulado
            margen = (desviacion / produccion * 100) if produccion > 0 else Decimal('0')

            total_produccion += produccion
            total_costo += costo_acumulado

            actividades_data.append({
                'id': actividad.id,
                'linea': actividad.linea.codigo,
                'tipo': actividad.tipo_actividad.nombre,
                'cuadrilla': actividad.cuadrilla.codigo if actividad.cuadrilla else '-',
                'tramo': str(actividad.tramo) if actividad.tramo else '-',
                'avance': float(actividad.porcentaje_avance),
                'valor_facturacion': float(actividad.valor_facturacion),
                'produccion': float(produccion),
                'costo': float(costo_acumulado),
                'desviacion': float(desviacion),
                'margen': float(margen),
                'estado': 'positivo' if desviacion >= 0 else 'negativo',
            })

        # Totales
        desviacion_total = total_produccion - total_costo
        margen_total = (desviacion_total / total_produccion * 100) if total_produccion > 0 else Decimal('0')

        context['actividades'] = actividades_data
        context['totales'] = {
            'produccion': float(total_produccion),
            'costo': float(total_costo),
            'desviacion': float(desviacion_total),
            'margen': float(margen_total),
            'estado': 'positivo' if desviacion_total >= 0 else 'negativo',
        }

        # Filtros para el template
        context['lineas'] = Linea.objects.filter(activa=True)
        context['filtro_linea'] = linea_id
        context['filtro_fecha_inicio'] = fecha_inicio
        context['filtro_fecha_fin'] = fecha_fin

        return context


class CostosVsProduccionAPIView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """
    API endpoint para obtener datos de costos vs producción (JSON).
    Útil para actualizaciones AJAX/HTMX.
    """
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'supervisor']

    def get(self, request, *args, **kwargs):
        from apps.actividades.models import Actividad

        from .models import CostoActividad

        linea_id = request.GET.get('linea')
        actividad_id = request.GET.get('actividad')

        if actividad_id:
            # Datos de una actividad específica
            try:
                actividad = Actividad.objects.select_related(
                    'linea', 'tipo_actividad', 'cuadrilla'
                ).get(id=actividad_id)
            except Actividad.DoesNotExist:
                return JsonResponse({'error': 'Actividad no encontrada'}, status=404)

            produccion = actividad.produccion_proporcional

            try:
                costo = CostoActividad.objects.get(actividad=actividad)
                costo_acumulado = costo.costo_total
            except CostoActividad.DoesNotExist:
                costo_acumulado = Decimal('0')

            desviacion = produccion - costo_acumulado
            margen = (desviacion / produccion * 100) if produccion > 0 else Decimal('0')

            return JsonResponse({
                'actividad_id': str(actividad.id),
                'linea': actividad.linea.codigo,
                'tipo': actividad.tipo_actividad.nombre,
                'avance': float(actividad.porcentaje_avance),
                'produccion': float(produccion),
                'costo': float(costo_acumulado),
                'desviacion': float(desviacion),
                'margen': float(margen),
                'estado': 'positivo' if desviacion >= 0 else 'negativo',
            })

        # Resumen general o por línea
        qs = Actividad.objects.filter(
            estado__in=['EN_CURSO', 'COMPLETADA']
        )

        if linea_id:
            qs = qs.filter(linea_id=linea_id)

        total_produccion = Decimal('0')
        total_costo = Decimal('0')

        for actividad in qs:
            total_produccion += actividad.produccion_proporcional

            try:
                costo = CostoActividad.objects.get(actividad=actividad)
                total_costo += costo.costo_total
            except CostoActividad.DoesNotExist:
                pass

        desviacion_total = total_produccion - total_costo
        margen_total = (desviacion_total / total_produccion * 100) if total_produccion > 0 else Decimal('0')

        return JsonResponse({
            'total_actividades': qs.count(),
            'produccion': float(total_produccion),
            'costo': float(total_costo),
            'desviacion': float(desviacion_total),
            'margen': float(margen_total),
            'estado': 'positivo' if desviacion_total >= 0 else 'negativo',
        })


class ChecklistFacturacionView(LoginRequiredMixin, RoleRequiredMixin, HTMXMixin, TemplateView):
    """Checklist for tracking billing status of completed activities."""
    template_name = 'financiero/checklist_facturacion.html'
    allowed_roles = ['admin', 'director', 'coordinador']

    def get_context_data(self, **kwargs):
        from django.utils import timezone

        from apps.actividades.models import Actividad
        from apps.lineas.models import Linea

        context = super().get_context_data(**kwargs)

        hoy = timezone.now()
        mes = int(self.request.GET.get('mes', hoy.month))
        anio = int(self.request.GET.get('anio', hoy.year))
        linea_id = self.request.GET.get('linea', '')

        # Get completed activities for the selected month
        qs = Actividad.objects.filter(
            estado='COMPLETADA',
            fecha_programada__year=anio,
            fecha_programada__month=mes,
        ).select_related('linea', 'tipo_actividad', 'cuadrilla')

        if linea_id:
            qs = qs.filter(linea_id=linea_id)

        # Build checklist items (create if not exist)
        items = []
        total_facturado = 0
        total_pendiente = 0
        monto_total = Decimal('0')

        for actividad in qs:
            checklist, _ = ChecklistFacturacion.objects.get_or_create(
                actividad=actividad,
                defaults={'facturado': False}
            )
            monto = getattr(actividad, 'valor_facturacion', Decimal('0')) or Decimal('0')
            monto_total += monto

            if checklist.facturado:
                total_facturado += 1
            else:
                total_pendiente += 1

            items.append({
                'actividad': actividad,
                'checklist': checklist,
                'monto': monto,
            })

        context['items'] = items
        context['total_actividades'] = len(items)
        context['total_facturado'] = total_facturado
        context['total_pendiente'] = total_pendiente
        context['monto_total'] = monto_total

        # Period-level files
        archivos_periodo_qs = ArchivoPeriodoFacturacion.objects.filter(
            anio=anio, mes=mes
        )
        if linea_id:
            archivos_periodo_qs = archivos_periodo_qs.filter(linea_id=linea_id)
        context['archivos_periodo'] = archivos_periodo_qs

        from .forms import ArchivoPeriodoForm
        context['periodo_upload_form'] = ArchivoPeriodoForm()

        # Filters
        context['lineas'] = Linea.objects.filter(activa=True)
        context['filtro_mes'] = mes
        context['filtro_anio'] = anio
        context['filtro_linea'] = linea_id
        context['meses'] = [
            (1, 'Enero'), (2, 'Febrero'), (3, 'Marzo'), (4, 'Abril'),
            (5, 'Mayo'), (6, 'Junio'), (7, 'Julio'), (8, 'Agosto'),
            (9, 'Septiembre'), (10, 'Octubre'), (11, 'Noviembre'), (12, 'Diciembre'),
        ]
        context['anios'] = list(range(hoy.year - 1, hoy.year + 2))

        return context


class ToggleFacturadoView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    """Toggle billing status of a checklist item via HTMX."""
    model = ChecklistFacturacion
    allowed_roles = ['admin', 'director', 'coordinador']

    def post(self, request, *args, **kwargs):
        from django.http import HttpResponse

        checklist = self.get_object()
        checklist.facturado = not checklist.facturado
        if checklist.facturado:
            checklist.fecha_facturacion = date.today()
        else:
            checklist.fecha_facturacion = None
        checklist.save(update_fields=['facturado', 'fecha_facturacion', 'updated_at'])

        if checklist.facturado:
            html = (
                f'<button hx-post="/financiero/checklist-facturacion/{checklist.pk}/toggle/" '
                f'hx-target="closest .checklist-toggle" hx-swap="innerHTML" '
                f'class="px-3 py-1 bg-green-100 text-green-800 rounded-full text-xs font-medium hover:bg-green-200 transition">'
                f'Facturado</button>'
            )
        else:
            html = (
                f'<button hx-post="/financiero/checklist-facturacion/{checklist.pk}/toggle/" '
                f'hx-target="closest .checklist-toggle" hx-swap="innerHTML" '
                f'class="px-3 py-1 bg-red-100 text-red-800 rounded-full text-xs font-medium hover:bg-red-200 transition">'
                f'Pendiente</button>'
            )
        return HttpResponse(html)


class ChecklistDetallePartialView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    """HTMX partial: expanded detail for a checklist item."""
    model = ChecklistFacturacion
    template_name = 'financiero/partials/checklist_detalle.html'
    context_object_name = 'checklist'
    allowed_roles = ['admin', 'director', 'coordinador']

    def get_queryset(self):
        return super().get_queryset().select_related(
            'actividad__linea', 'actividad__tipo_actividad',
            'actividad__cuadrilla',
        ).prefetch_related('archivos')

    def get_context_data(self, **kwargs):
        from .forms import ChecklistEditForm

        context = super().get_context_data(**kwargs)
        context['edit_form'] = ChecklistEditForm(instance=self.object)
        context['archivos'] = self.object.archivos.all()
        return context


class ChecklistEditarView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    """Save numero_factura and observaciones via HTMX POST."""
    model = ChecklistFacturacion
    allowed_roles = ['admin', 'director', 'coordinador']

    def post(self, request, *args, **kwargs):
        import json

        from django.http import HttpResponse
        from django.shortcuts import render

        from .forms import ChecklistEditForm

        checklist = self.get_object()
        form = ChecklistEditForm(request.POST, instance=checklist)
        if form.is_valid():
            form.save()
            response = HttpResponse()
            response['HX-Trigger'] = json.dumps({
                'showToast': {'message': 'Datos guardados', 'type': 'success'},
            })
            # Re-render the edit form with saved data
            return render(request, 'financiero/partials/checklist_edit_form.html', {
                'edit_form': ChecklistEditForm(instance=checklist),
                'checklist': checklist,
            }, headers={'HX-Trigger': json.dumps({
                'showToast': {'message': 'Datos guardados', 'type': 'success'},
            })})
        return render(request, 'financiero/partials/checklist_edit_form.html', {
            'edit_form': form, 'checklist': checklist,
        })


class ChecklistSubirArchivoView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    """Upload files to a checklist item via HTMX POST."""
    model = ChecklistFacturacion
    allowed_roles = ['admin', 'director', 'coordinador']

    ALLOWED_EXTENSIONS = {'.pdf', '.xlsx', '.xls', '.jpg', '.jpeg', '.png', '.webp'}
    MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

    def post(self, request, *args, **kwargs):
        import json
        import os

        from django.http import HttpResponse
        from django.template.loader import render_to_string

        checklist = self.get_object()
        files = request.FILES.getlist('archivos')

        if not files:
            response = HttpResponse(status=400)
            response['HX-Trigger'] = json.dumps({
                'showToast': {'message': 'No se seleccionaron archivos', 'type': 'error'},
            })
            return response

        uploaded = 0
        for f in files:
            _, ext = os.path.splitext(f.name)
            if ext.lower() not in self.ALLOWED_EXTENSIONS:
                continue
            if f.size > self.MAX_FILE_SIZE:
                continue
            ArchivoChecklist.objects.create(
                checklist=checklist,
                archivo=f,
                nombre_original=f.name,
                tipo_archivo=f.content_type or '',
                tamanio=f.size,
            )
            uploaded += 1

        archivos = checklist.archivos.all()
        html = render_to_string('financiero/partials/checklist_archivos.html', {
            'archivos': archivos, 'checklist': checklist,
        }, request=request)

        response = HttpResponse(html)
        response['HX-Trigger'] = json.dumps({
            'showToast': {'message': f'{uploaded} archivo(s) subido(s)', 'type': 'success'},
        })
        return response


class ChecklistEliminarArchivoView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    """Delete a file from a checklist item via HTMX DELETE."""
    model = ArchivoChecklist
    allowed_roles = ['admin', 'director', 'coordinador']

    def delete(self, request, *args, **kwargs):
        import json

        from django.http import HttpResponse
        from django.template.loader import render_to_string

        archivo = self.get_object()
        checklist = archivo.checklist
        archivo.archivo.delete(save=False)
        archivo.delete()

        archivos = checklist.archivos.all()
        html = render_to_string('financiero/partials/checklist_archivos.html', {
            'archivos': archivos, 'checklist': checklist,
        }, request=request)

        response = HttpResponse(html)
        response['HX-Trigger'] = json.dumps({
            'showToast': {'message': 'Archivo eliminado', 'type': 'success'},
        })
        return response


class PeriodoSubirArchivoView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Upload general files for a billing period."""
    template_name = 'financiero/checklist_facturacion.html'
    allowed_roles = ['admin', 'director', 'coordinador']

    ALLOWED_EXTENSIONS = {'.pdf', '.xlsx', '.xls', '.jpg', '.jpeg', '.png', '.webp'}
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

    def post(self, request, *args, **kwargs):
        import json
        import os

        from django.http import HttpResponse
        from django.template.loader import render_to_string

        mes = int(request.POST.get('mes', 0))
        anio = int(request.POST.get('anio', 0))
        linea_id = request.POST.get('linea') or None
        descripcion = request.POST.get('descripcion', '')
        files = request.FILES.getlist('archivos')

        if not files or not mes or not anio:
            response = HttpResponse(status=400)
            response['HX-Trigger'] = json.dumps({
                'showToast': {'message': 'Datos incompletos', 'type': 'error'},
            })
            return response

        uploaded = 0
        for f in files:
            _, ext = os.path.splitext(f.name)
            if ext.lower() not in self.ALLOWED_EXTENSIONS:
                continue
            if f.size > self.MAX_FILE_SIZE:
                continue
            ArchivoPeriodoFacturacion.objects.create(
                anio=anio,
                mes=mes,
                linea_id=linea_id if linea_id else None,
                archivo=f,
                nombre_original=f.name,
                descripcion=descripcion,
                tipo_archivo=f.content_type or '',
                tamanio=f.size,
            )
            uploaded += 1

        archivos_periodo = ArchivoPeriodoFacturacion.objects.filter(
            anio=anio, mes=mes
        )
        if linea_id:
            archivos_periodo = archivos_periodo.filter(linea_id=linea_id)

        html = render_to_string('financiero/partials/periodo_archivos.html', {
            'archivos_periodo': archivos_periodo,
            'filtro_mes': mes, 'filtro_anio': anio, 'filtro_linea': linea_id or '',
        }, request=request)

        response = HttpResponse(html)
        response['HX-Trigger'] = json.dumps({
            'showToast': {'message': f'{uploaded} archivo(s) del periodo subido(s)', 'type': 'success'},
        })
        return response


class PeriodoEliminarArchivoView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    """Delete a period-level file via HTMX DELETE."""
    model = ArchivoPeriodoFacturacion
    allowed_roles = ['admin', 'director', 'coordinador']

    def delete(self, request, *args, **kwargs):
        import json

        from django.http import HttpResponse
        from django.template.loader import render_to_string

        archivo = self.get_object()
        mes = archivo.mes
        anio = archivo.anio
        linea_id = request.GET.get('linea', '')

        archivo.archivo.delete(save=False)
        archivo.delete()

        archivos_periodo = ArchivoPeriodoFacturacion.objects.filter(
            anio=anio, mes=mes
        )
        if linea_id:
            archivos_periodo = archivos_periodo.filter(linea_id=linea_id)

        html = render_to_string('financiero/partials/periodo_archivos.html', {
            'archivos_periodo': archivos_periodo,
            'filtro_mes': mes, 'filtro_anio': anio, 'filtro_linea': linea_id,
        }, request=request)

        response = HttpResponse(html)
        response['HX-Trigger'] = json.dumps({
            'showToast': {'message': 'Archivo del periodo eliminado', 'type': 'success'},
        })
        return response


# ---------------------------------------------------------------------------
# Cost structure constants (mirrors the Excel PRESUPUESTO sheet)
# ---------------------------------------------------------------------------
MESES = [
    'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
    'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
]

ESTRUCTURA_COSTOS = {
    'costos_variables': {
        'titulo': 'Costos Variables',
        'categorias': [
            {
                'codigo': 'MO',
                'nombre': 'Mano de Obra',
                'items': [
                    'Nómina operación',
                    'Tiempo extra operación',
                    'Tiempo festivo operación',
                    'Beneficios operación',
                    'Aportes y parafiscales operación',
                    'Prestaciones sociales operación',
                    'FIC operación',
                    'Seguro de vida operación',
                    'Viáticos reembolsables operación',
                    'Viáticos NO reembolsables operación',
                    'Viáticos descanso operación',
                    'Auxilio alimentación/alojamiento operación',
                    'Hidratación operación',
                    'Campamento operación',
                    'Alimentación operación',
                    'Celaduría campo',
                ],
            },
            {
                'codigo': 'SST',
                'nombre': 'SST y Ambiental',
                'items': [
                    'EPP consumibles',
                    'EPP alturas',
                    'EPP servidumbre',
                    'Seguridad grupal',
                    'Bioseguridad',
                    'Dotación operación',
                    'Examen médico operación',
                    'Certificación operación',
                    'Capacitaciones',
                    'Ambiental',
                ],
            },
            {
                'codigo': 'TA',
                'nombre': 'Transporte y Administración',
                'items': [
                    'Transporte operación',
                    'Transporte de materiales y herramientas',
                    'Transporte reembolsable',
                ],
            },
            {
                'codigo': 'MH',
                'nombre': 'Material y Herramientas',
                'items': [
                    'Material obra',
                    'Material fungible',
                    'Insumos maquinaria y equipos',
                    'Activos fijos',
                    'Herramientas menores',
                    'Gastos reembolsables',
                ],
            },
            {
                'codigo': 'SC',
                'nombre': 'Subcontratistas',
                'items': [
                    'Subcontratistas',
                ],
            },
        ],
    },
    'costos_fijos': {
        'titulo': 'Costos Fijos',
        'categorias': [
            {
                'codigo': 'MO',
                'nombre': 'Mano de Obra Administración',
                'items': [
                    'Nómina administración',
                    'Tiempo extra administración',
                    'Prestaciones sociales administración',
                    'FIC administración',
                    'Seguro de vida administración',
                    'Viáticos reembolsables administración',
                    'Viáticos NO reembolsables administración',
                    'Viáticos descanso administración',
                    'Auxilio alimentación/alojamiento administración',
                    'Hidratación administración',
                    'Campamento administración',
                    'Alimentación administración',
                ],
            },
            {
                'codigo': 'SST',
                'nombre': 'SST Administración',
                'items': [
                    'Dotación administración',
                    'Examen médico administración',
                    'Certificación administración',
                ],
            },
            {
                'codigo': 'TA',
                'nombre': 'Transporte y Gastos Administración',
                'items': [
                    'Transporte administración',
                    'Transporte ocasional',
                    'Arrendamiento oficina',
                    'Arrendamiento patio',
                    'Servicios públicos',
                    'Celular / internet',
                    'Seguridad privada',
                    'Gastos menores',
                    'Insumos oficina',
                    'Ingreso sitio torre',
                    'Actividades por garantía / imprevistos',
                ],
            },
            {
                'codigo': 'PFS',
                'nombre': 'Garantías, Fianzas y Seguros',
                'items': [
                    'Garantías, fianzas y seguros',
                ],
            },
        ],
    },
}


def _build_empty_datos():
    """Return an empty datos structure with all zeros."""
    zero_months = {m: 0 for m in MESES}
    datos = {'ingreso_proyectado': dict(zero_months)}
    for seccion_key, seccion in ESTRUCTURA_COSTOS.items():
        datos[seccion_key] = {}
        for cat in seccion['categorias']:
            datos[seccion_key][cat['codigo']] = {}
            for item in cat['items']:
                datos[seccion_key][cat['codigo']][item] = dict(zero_months)
    return datos


def _build_display_rows(datos):
    """Build structured rows for template rendering from stored datos JSON."""
    rows = []

    # Ingreso proyectado
    ing = datos.get('ingreso_proyectado', {})
    valores_ing = [ing.get(m, 0) for m in MESES]
    rows.append({
        'tipo': 'ingreso',
        'nombre': 'INGRESO PROYECTADO',
        'codigo': '',
        'valores': valores_ing,
        'total': sum(valores_ing),
    })

    gran_total_variables = [0] * 12
    gran_total_fijos = [0] * 12

    for seccion_key, seccion in ESTRUCTURA_COSTOS.items():
        is_variable = seccion_key == 'costos_variables'
        # Section header
        rows.append({
            'tipo': 'seccion',
            'nombre': seccion['titulo'],
            'codigo': '',
            'valores': None,
            'total': None,
        })

        seccion_totales = [0] * 12

        for cat in seccion['categorias']:
            # Category header
            cat_totales = [0] * 12
            rows.append({
                'tipo': 'categoria',
                'nombre': cat['nombre'],
                'codigo': cat['codigo'],
                'valores': None,
                'total': None,
            })

            cat_data = datos.get(seccion_key, {}).get(cat['codigo'], {})
            for item_name in cat['items']:
                item_data = cat_data.get(item_name, {})
                valores = [item_data.get(m, 0) for m in MESES]
                for i in range(12):
                    cat_totales[i] += valores[i]
                rows.append({
                    'tipo': 'item',
                    'nombre': item_name,
                    'codigo': cat['codigo'],
                    'seccion': seccion_key,
                    'valores': valores,
                    'total': sum(valores),
                })

            # Category subtotal
            rows.append({
                'tipo': 'subtotal',
                'nombre': f"Subtotal {cat['nombre']}",
                'codigo': cat['codigo'],
                'valores': cat_totales,
                'total': sum(cat_totales),
            })
            for i in range(12):
                seccion_totales[i] += cat_totales[i]

        # Section total
        rows.append({
            'tipo': 'total_seccion',
            'nombre': f"Total {seccion['titulo']}",
            'codigo': '',
            'valores': seccion_totales,
            'total': sum(seccion_totales),
        })

        if is_variable:
            gran_total_variables = seccion_totales[:]
        else:
            gran_total_fijos = seccion_totales[:]

    # Summary rows
    ing_vals = [ing.get(m, 0) for m in MESES]
    total_gastos = [gran_total_variables[i] + gran_total_fijos[i] for i in range(12)]
    resultado = [ing_vals[i] - total_gastos[i] for i in range(12)]

    rows.append({
        'tipo': 'total_seccion',
        'nombre': 'TOTAL GASTOS',
        'codigo': '',
        'valores': total_gastos,
        'total': sum(total_gastos),
    })
    rows.append({
        'tipo': 'resultado',
        'nombre': 'RESULTADO (Ingreso - Gastos)',
        'codigo': '',
        'valores': resultado,
        'total': sum(resultado),
    })

    total_ing = sum(ing_vals)
    total_gasto = sum(total_gastos)
    utilidad_pct = ((total_ing - total_gasto) / total_ing * 100) if total_ing else 0

    return rows, {
        'total_ingreso': total_ing,
        'total_variables': sum(gran_total_variables),
        'total_fijos': sum(gran_total_fijos),
        'total_gastos': total_gasto,
        'resultado': total_ing - total_gasto,
        'utilidad_pct': utilidad_pct,
    }


class PresupuestoDetalladoBaseView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Base view for detailed budget (Planeado / Real)."""
    template_name = 'financiero/presupuesto_detallado.html'
    allowed_roles = ['admin', 'director', 'coordinador']
    tipo_presupuesto = None  # Override in subclass

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from django.utils import timezone

        anio = int(self.request.GET.get('anio', timezone.now().year))

        obj, created = PresupuestoDetallado.objects.get_or_create(
            anio=anio,
            tipo=self.tipo_presupuesto,
            defaults={'datos': _build_empty_datos()},
        )

        rows, resumen = _build_display_rows(obj.datos)

        context['presupuesto_obj'] = obj
        context['tipo_presupuesto'] = self.tipo_presupuesto
        context['tipo_label'] = 'Planeado' if self.tipo_presupuesto == 'PLANEADO' else 'Real'
        context['anio'] = anio
        context['meses'] = MESES
        context['meses_cortos'] = [m[:3].title() for m in MESES]
        context['rows'] = rows
        context['resumen'] = resumen
        context['anios_disponibles'] = list(range(anio - 2, anio + 3))
        return context

    def post(self, request, *args, **kwargs):
        """Handle inline cell edits via HTMX."""
        import json
        from django.http import HttpResponse
        from django.utils import timezone

        anio = int(request.POST.get('anio', timezone.now().year))
        obj, _ = PresupuestoDetallado.objects.get_or_create(
            anio=anio,
            tipo=self.tipo_presupuesto,
            defaults={'datos': _build_empty_datos()},
        )

        seccion = request.POST.get('seccion', '')  # costos_variables / costos_fijos / ingreso_proyectado
        categoria = request.POST.get('categoria', '')  # MO, SST, etc.
        item = request.POST.get('item', '')  # Item name
        mes = request.POST.get('mes', '')  # enero, febrero, etc.
        valor_raw = request.POST.get('valor', '0').replace(',', '').replace('.', '').strip()

        try:
            valor = int(valor_raw)
        except (ValueError, TypeError):
            valor = 0

        datos = obj.datos or _build_empty_datos()

        if seccion == 'ingreso_proyectado':
            if 'ingreso_proyectado' not in datos:
                datos['ingreso_proyectado'] = {m: 0 for m in MESES}
            datos['ingreso_proyectado'][mes] = valor
        elif seccion in ('costos_variables', 'costos_fijos') and categoria and item:
            if seccion not in datos:
                datos[seccion] = {}
            if categoria not in datos[seccion]:
                datos[seccion][categoria] = {}
            if item not in datos[seccion][categoria]:
                datos[seccion][categoria][item] = {m: 0 for m in MESES}
            datos[seccion][categoria][item][mes] = valor

        obj.datos = datos
        obj.save(update_fields=['datos', 'updated_at'])

        return HttpResponse(
            f'<span class="text-right">{valor:,.0f}</span>',
            content_type='text/html',
        )


class PresupuestoPlaneadoView(PresupuestoDetalladoBaseView):
    """View for the planned budget tab."""
    tipo_presupuesto = 'PLANEADO'


class PresupuestoRealView(PresupuestoDetalladoBaseView):
    """View for the actual/real budget tab."""
    tipo_presupuesto = 'REAL'
