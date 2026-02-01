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

from .models import CicloFacturacion, EjecucionCosto, Presupuesto


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

        # Chart data - Costs by category
        context['costos_categoria_data'] = json.dumps([
            {'value': float(costo_personal), 'name': 'Personal'},
            {'value': float(costo_equipos), 'name': 'Equipos/Vehículos'},
            {'value': float(presupuestos.aggregate(total=Sum('viaticos_planeados'))['total'] or 0), 'name': 'Viáticos'},
            {'value': float(presupuestos.aggregate(total=Sum('otros_costos'))['total'] or 0), 'name': 'Otros'},
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
