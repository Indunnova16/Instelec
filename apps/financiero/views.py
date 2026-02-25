"""
Views for financial management.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.http import JsonResponse
from django.views.generic import DetailView, ListView, TemplateView

from apps.core.mixins import HTMXMixin, RoleRequiredMixin

from .models import (
    ArchivoChecklist,
    ArchivoPeriodoFacturacion,
    ChecklistFacturacion,
    CicloFacturacion,
    EjecucionCosto,
    Presupuesto,
)


class DashboardFinancieroView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Financial dashboard."""
    template_name = 'financiero/dashboard.html'
    allowed_roles = ['admin', 'director', 'coordinador']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        import json

        from django.utils import timezone

        from apps.actividades.models import Actividad
        from apps.lineas.models import Linea

        hoy = timezone.now()

        # Current month budgets
        presupuestos = Presupuesto.objects.filter(
            anio=hoy.year,
            mes=hoy.month
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

        # Cost breakdown
        costo_personal = presupuestos.aggregate(total=Sum('costo_dias_hombre'))['total'] or Decimal('0')
        costo_equipos = presupuestos.aggregate(total=Sum('costo_vehiculos'))['total'] or Decimal('0')

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
            fecha_programada__year=hoy.year,
            fecha_programada__month=hoy.month,
            estado='COMPLETADA'
        ).count()

        if actividades_completadas > 0:
            context['costo_promedio_actividad'] = float(total_ejecutado / actividades_completadas)
        else:
            context['costo_promedio_actividad'] = 0

        context['variacion_costo'] = 0  # Placeholder for month-over-month variation

        # Period filters
        context['periodos'] = [
            {'value': 'mes', 'label': 'Este mes'},
            {'value': 'trimestre', 'label': 'Este trimestre'},
            {'value': 'anio', 'label': 'Este año'},
        ]
        context['periodo_actual'] = self.request.GET.get('periodo', 'mes')

        # Additional budget pillars
        costo_herramientas = presupuestos.aggregate(total=Sum('costo_herramientas'))['total'] or Decimal('0')
        costo_ambientales = presupuestos.aggregate(total=Sum('costo_ambientales'))['total'] or Decimal('0')
        costo_subcontratistas = presupuestos.aggregate(total=Sum('costo_subcontratistas'))['total'] or Decimal('0')
        costo_transporte = presupuestos.aggregate(total=Sum('costo_transporte'))['total'] or Decimal('0')
        costo_garantia = presupuestos.aggregate(total=Sum('costo_garantia'))['total'] or Decimal('0')
        costo_materiales = presupuestos.aggregate(total=Sum('costo_materiales'))['total'] or Decimal('0')
        costo_viaticos = presupuestos.aggregate(total=Sum('viaticos_planeados'))['total'] or Decimal('0')
        costo_otros = presupuestos.aggregate(total=Sum('otros_costos'))['total'] or Decimal('0')

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

        # Costs by line
        lineas = Linea.objects.filter(activa=True)[:10]
        lineas_labels = []
        costos_linea = []
        for linea in lineas:
            lineas_labels.append(linea.codigo)
            pres_linea = Presupuesto.objects.filter(
                linea=linea,
                anio=hoy.year,
                mes=hoy.month
            )
            costos_linea.append(float(pres_linea.aggregate(total=Sum('total_ejecutado'))['total'] or 0))

        context['lineas_labels'] = json.dumps(lineas_labels)
        context['costos_linea'] = json.dumps(costos_linea)

        # Cost detail table
        context['detalle_costos'] = [
            {
                'categoria': 'Personal',
                'concepto': 'Días hombre',
                'presupuesto': float(presupuestos.aggregate(total=Sum('costo_dias_hombre'))['total'] or 0),
                'ejecutado': float(costo_personal),
                'porcentaje': float(costo_personal / (presupuestos.aggregate(total=Sum('costo_dias_hombre'))['total'] or 1) * 100),
                'disponible': float((presupuestos.aggregate(total=Sum('costo_dias_hombre'))['total'] or 0) - costo_personal),
            },
            {
                'categoria': 'Equipos',
                'concepto': 'Vehículos',
                'presupuesto': float(presupuestos.aggregate(total=Sum('costo_vehiculos'))['total'] or 0),
                'ejecutado': float(costo_equipos),
                'porcentaje': float(costo_equipos / (presupuestos.aggregate(total=Sum('costo_vehiculos'))['total'] or 1) * 100),
                'disponible': float((presupuestos.aggregate(total=Sum('costo_vehiculos'))['total'] or 0) - costo_equipos),
            },
        ]

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
            presupuesto__anio=hoy.year,
            presupuesto__mes=hoy.month,
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
