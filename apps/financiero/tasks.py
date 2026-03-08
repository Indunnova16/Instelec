"""
Celery tasks for financial reports and cost tracking.
"""
from celery import shared_task
from celery.utils.log import get_task_logger
from datetime import date
from decimal import Decimal
from django.db.models import Sum

logger = get_task_logger(__name__)


@shared_task(bind=True, max_retries=3)
def generar_cuadro_costos_mensual(self, anio: int, mes: int, linea_id: str = None):
    """
    Generate monthly cost table for billing.
    Runs on the 1st of each month for the previous month.
    """
    from .reports import CuadroCostosGenerator
    from django.core.files.base import ContentFile
    from .models import CuadroCostos

    try:
        logger.info(f"Generating cost table for {mes}/{anio}")

        generator = CuadroCostosGenerator(anio, mes, linea_id)
        excel_content = generator.generar_excel()

        # Save to database
        filename = f"cuadro_costos_{anio}_{mes:02d}"
        if linea_id:
            filename += f"_{linea_id}"
        filename += ".xlsx"

        cuadro, created = CuadroCostos.objects.update_or_create(
            anio=anio,
            mes=mes,
            defaults={
                'estado': 'GENERADO',
                'total_ejecutado': generator.data.get('total_ejecutado', Decimal('0')),
            }
        )
        cuadro.archivo.save(filename, ContentFile(excel_content))

        logger.info(f"Cost table generated: {filename}")
        return {'status': 'success', 'filename': filename, 'id': str(cuadro.id)}

    except (IOError, OSError) as exc:
        logger.error(f"I/O error generating cost table: {exc}")
        raise self.retry(exc=exc, countdown=60 * 5)
    except (ValueError, TypeError) as exc:
        logger.error(f"Data error generating cost table: {exc}")
        raise self.retry(exc=exc, countdown=60 * 5)
    except CuadroCostos.DoesNotExist as exc:
        logger.error(f"Cost table record not found: {exc}")
        raise


@shared_task
def calcular_costos_actividades(anio: int, mes: int):
    """
    Calculate costs for all completed activities in the period.
    """
    from apps.actividades.models import Actividad
    from apps.cuadrillas.models import AsignacionCuadrilla
    from .models import CostoActividad

    actividades = Actividad.objects.filter(
        fecha_programada__year=anio,
        fecha_programada__month=mes,
        estado='COMPLETADA'
    ).select_related('cuadrilla', 'tipo_actividad', 'linea')

    costos_calculados = []

    for actividad in actividades:
        costo = calcular_costo_individual(actividad)

        CostoActividad.objects.update_or_create(
            actividad=actividad,
            defaults={
                'costo_personal': costo['personal'],
                'costo_vehiculos': costo['vehiculos'],
                'costo_materiales': costo['materiales'],
                'costo_total': costo['total'],
            }
        )

        costos_calculados.append({
            'actividad_id': str(actividad.id),
            'total': float(costo['total'])
        })

    logger.info(f"Calculated costs for {len(costos_calculados)} activities")
    return costos_calculados


def calcular_costo_individual(actividad):
    """Calculate cost for a single activity."""
    from apps.campo.models import RegistroCampo
    from .models import TarifaPersonal, TarifaVehiculo

    costo_personal = Decimal('0')
    costo_vehiculos = Decimal('0')
    costo_materiales = Decimal('0')

    # Get field records
    registros = actividad.registros_campo.all()

    for registro in registros:
        # Calculate hours worked
        if registro.fecha_inicio and registro.fecha_fin:
            horas = (registro.fecha_fin - registro.fecha_inicio).total_seconds() / 3600

            # Personnel cost
            try:
                tarifa = TarifaPersonal.objects.get(
                    cargo=registro.usuario.cargo,
                    vigente=True
                )
                costo_personal += tarifa.valor_hora * Decimal(str(horas))
            except TarifaPersonal.DoesNotExist:
                pass

        # Materials from form data
        if registro.datos_formulario.get('materiales_usados'):
            for material in registro.datos_formulario['materiales_usados']:
                try:
                    costo_materiales += Decimal(str(material.get('costo', 0)))
                except (ValueError, TypeError):
                    pass

    # Vehicle cost (from assigned crew)
    if actividad.cuadrilla:
        for vehiculo in actividad.cuadrilla.vehiculos.all():
            try:
                tarifa = TarifaVehiculo.objects.get(
                    tipo=vehiculo.tipo,
                    vigente=True
                )
                # Assume half day per activity
                costo_vehiculos += tarifa.valor_dia / 2
            except TarifaVehiculo.DoesNotExist:
                pass

    return {
        'personal': costo_personal,
        'vehiculos': costo_vehiculos,
        'materiales': costo_materiales,
        'total': costo_personal + costo_vehiculos + costo_materiales
    }


@shared_task
def generar_reporte_presupuestal():
    """
    Generate budget execution report.
    Runs weekly on Mondays.
    """
    from .models import Presupuesto, CostoActividad
    from apps.lineas.models import Linea

    hoy = date.today()
    anio = hoy.year

    lineas = Linea.objects.filter(activa=True)
    reporte = []

    for linea in lineas:
        try:
            presupuesto = Presupuesto.objects.get(linea=linea, anio=anio)
        except Presupuesto.DoesNotExist:
            continue

        # Calculate executed
        ejecutado = CostoActividad.objects.filter(
            actividad__linea=linea,
            actividad__fecha_programada__year=anio
        ).aggregate(
            total=Sum('costo_total')
        )['total'] or Decimal('0')

        porcentaje = (ejecutado / presupuesto.monto_total * 100) if presupuesto.monto_total > 0 else Decimal('0')

        reporte.append({
            'linea': linea.codigo,
            'presupuesto': float(presupuesto.monto_total),
            'ejecutado': float(ejecutado),
            'disponible': float(presupuesto.monto_total - ejecutado),
            'porcentaje': float(porcentaje),
            'alerta': porcentaje > 90
        })

    logger.info(f"Budget report generated for {len(reporte)} lines")
    return reporte


@shared_task
def consolidar_costos_mensuales(anio: int, mes: int):
    """
    Consolidate monthly costs by category.
    """
    from django.db.models import Sum
    from .models import CostoActividad
    from apps.actividades.models import Actividad

    costos = CostoActividad.objects.filter(
        actividad__fecha_programada__year=anio,
        actividad__fecha_programada__month=mes
    ).aggregate(
        personal=Sum('costo_personal'),
        vehiculos=Sum('costo_vehiculos'),
        materiales=Sum('costo_materiales'),
        total=Sum('costo_total')
    )

    # By activity type
    por_tipo = {}
    actividades = Actividad.objects.filter(
        fecha_programada__year=anio,
        fecha_programada__month=mes,
        estado='COMPLETADA'
    ).select_related('tipo_actividad')

    for act in actividades:
        tipo = act.tipo_actividad.nombre
        if tipo not in por_tipo:
            por_tipo[tipo] = {'cantidad': 0, 'costo': Decimal('0')}
        por_tipo[tipo]['cantidad'] += 1
        try:
            costo = act.costo.costo_total
            por_tipo[tipo]['costo'] += costo
        except CostoActividad.DoesNotExist:
            pass

    consolidado = {
        'periodo': f"{mes}/{anio}",
        'totales': {
            'personal': float(costos['personal'] or 0),
            'vehiculos': float(costos['vehiculos'] or 0),
            'materiales': float(costos['materiales'] or 0),
            'total': float(costos['total'] or 0)
        },
        'por_tipo': {k: {'cantidad': v['cantidad'], 'costo': float(v['costo'])} for k, v in por_tipo.items()}
    }

    logger.info(f"Monthly costs consolidated: ${consolidado['totales']['total']}")
    return consolidado


@shared_task
def calcular_produccion_diaria(actividad_id: str):
    """
    Calcula la producción proporcional de una actividad.
    Producción = porcentaje_avance × valor_facturacion
    """
    from apps.actividades.models import Actividad

    try:
        actividad = Actividad.objects.get(id=actividad_id)
        produccion = actividad.produccion_proporcional

        logger.info(
            f"Production calculated for activity {actividad_id}: "
            f"{actividad.porcentaje_avance}% x ${actividad.valor_facturacion} = ${produccion}"
        )

        return {
            'actividad_id': actividad_id,
            'porcentaje_avance': float(actividad.porcentaje_avance),
            'valor_facturacion': float(actividad.valor_facturacion),
            'produccion_proporcional': float(produccion)
        }
    except Actividad.DoesNotExist:
        logger.error(f"Activity not found: {actividad_id}")
        return {'error': 'Activity not found', 'actividad_id': actividad_id}


@shared_task
def calcular_costo_vs_produccion(actividad_id: str):
    """
    Calcula la relación costo vs producción para una actividad.
    Útil para monitoreo de rentabilidad en tiempo real.
    """
    from apps.actividades.models import Actividad
    from .models import CostoActividad

    try:
        actividad = Actividad.objects.get(id=actividad_id)
        produccion = actividad.produccion_proporcional

        # Get accumulated cost
        try:
            costo = CostoActividad.objects.get(actividad=actividad)
            costo_acumulado = costo.costo_total
        except CostoActividad.DoesNotExist:
            costo_acumulado = Decimal('0')

        desviacion = produccion - costo_acumulado
        margen = (desviacion / produccion * 100) if produccion > 0 else Decimal('0')

        resultado = {
            'actividad_id': actividad_id,
            'produccion': float(produccion),
            'costo_acumulado': float(costo_acumulado),
            'desviacion': float(desviacion),
            'margen_porcentaje': float(margen),
            'estado': 'positivo' if desviacion >= 0 else 'negativo'
        }

        logger.info(
            f"Cost vs Production for {actividad_id}: "
            f"Production=${produccion}, Cost=${costo_acumulado}, "
            f"Deviation=${desviacion} ({margen:.1f}%)"
        )

        return resultado

    except Actividad.DoesNotExist:
        logger.error(f"Activity not found: {actividad_id}")
        return {'error': 'Activity not found', 'actividad_id': actividad_id}


