"""Celery tasks para construccion (#61 snapshots avance + #98 indicadores)."""
import logging
from datetime import date as date_cls, timedelta
from decimal import Decimal

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name='construccion.snapshot_avance_diario')
def snapshot_avance_diario():
    """Captura snapshot del avance de todos los proyectos CONSTRUCCION
    activos. Programar día 1 de cada mes vía django-celery-beat
    DatabaseScheduler con cron(day_of_month=1, hour=0, minute=5).

    También puede correrse manualmente:
        python manage.py snapshot_avance_proyectos --solo-activos
    """
    from .models import ProyectoConstruccion, SnapshotAvance

    fecha = date_cls.today()
    qs = ProyectoConstruccion.objects.filter(
        estado__in=['PLANIFICACION', 'EJECUCION']
    )
    count = 0
    for proyecto in qs:
        try:
            SnapshotAvance.capturar(proyecto, fecha=fecha)
            count += 1
        except Exception as e:
            logger.exception(
                f'Error snapshot proyecto {proyecto.id}: {e}')
    return {'fecha': fecha.isoformat(), 'snapshots': count}


# ===========================================================================
# B2 (#98) — Sync semanal de indicadores de construcción
# ===========================================================================

@shared_task(name='construccion.indicadores_construccion_sync_semanal')
def indicadores_construccion_sync_semanal():
    """Sync semanal de indicadores de construcción.

    Programar lunes 6am hora Colombia via django-celery-beat DatabaseScheduler:
        crontab(day_of_week=1, hour=11, minute=0)   # 11 UTC = 6am COL

    Para cada proyecto activo:
    1. Extrae datos de apps.actividades (actividades completadas/planificadas),
       apps.campo (avance vano/torres), apps.financiero (ingresos/costos).
    2. Crea/actualiza IndicadorFinancieroConstruccion para la fecha (lunes).
    3. Crea/actualiza IndicadorTecnicoConstruccion para la fecha.
    4. Los save() de los modelos auto-recalculan los campos derivados.

    Diseño defensivo: si falta algún input (ej. un proyecto sin actividades),
    captura el error por proyecto y sigue con los demás. Loguea en
    django logger 'apps.construccion.tasks'.
    """
    from .models import ProyectoConstruccion
    from .models_b2_indicadores import (
        IndicadorFinancieroConstruccion,
        IndicadorTecnicoConstruccion,
    )

    fecha = date_cls.today()
    # Normalizar al lunes de la semana (si la task corre el lunes a las 6am,
    # ya estamos en el lunes; protege ejecuciones manuales otro día).
    fecha_lunes = fecha - timedelta(days=fecha.weekday())

    proyectos = ProyectoConstruccion.objects.filter(
        estado__in=['PLANIFICACION', 'EJECUCION']
    )
    fin_creados = tec_creados = errores = 0

    for proyecto in proyectos:
        try:
            agregados_fin = _extraer_inputs_financieros(proyecto, fecha_lunes)
            ind_fin, _ = IndicadorFinancieroConstruccion.objects.update_or_create(
                proyecto=proyecto,
                fecha=fecha_lunes,
                defaults=agregados_fin,
            )
            fin_creados += 1
        except Exception as e:
            logger.exception(
                f'Sync financiero proyecto {proyecto.id}: {e}'
            )
            errores += 1

        try:
            agregados_tec = _extraer_inputs_tecnicos(proyecto, fecha_lunes)
            IndicadorTecnicoConstruccion.objects.update_or_create(
                proyecto=proyecto,
                fecha=fecha_lunes,
                defaults=agregados_tec,
            )
            tec_creados += 1
        except Exception as e:
            logger.exception(
                f'Sync técnico proyecto {proyecto.id}: {e}'
            )
            errores += 1

    return {
        'fecha': fecha_lunes.isoformat(),
        'proyectos_procesados': proyectos.count(),
        'financieros_upserted': fin_creados,
        'tecnicos_upserted': tec_creados,
        'errores': errores,
    }


def _extraer_inputs_financieros(proyecto, fecha_lunes):
    """Extrae inputs financieros de apps.financiero (defensivo)."""
    from django.db.models import Sum

    inicio_semana = fecha_lunes
    fin_semana = fecha_lunes + timedelta(days=6)

    ingresos = costos = gastos = costo_real = costo_pres = Decimal('0')

    try:
        from apps.financiero.models import EjecucionCosto
        ej = EjecucionCosto.objects.filter(
            actividad__proyecto=proyecto,
            fecha__range=(inicio_semana, fin_semana),
        ).aggregate(total=Sum('costo_real'))
        costo_real = ej.get('total') or Decimal('0')
    except Exception:
        pass

    try:
        from apps.financiero.models import Presupuesto
        pre = Presupuesto.objects.filter(
            proyecto=proyecto,
        ).aggregate(total=Sum('valor_total'))
        costo_pres = pre.get('total') or Decimal('0')
    except Exception:
        pass

    return {
        'ingresos_ejecutados': ingresos,
        'costos_directos': costos,
        'gastos': gastos,
        'costo_real': costo_real,
        'costo_presupuestado': costo_pres,
    }


def _extraer_inputs_tecnicos(proyecto, fecha_lunes):
    """Extrae inputs técnicos de apps.actividades + apps.campo (defensivo)."""
    from django.db.models import Count, Sum

    inicio_semana = fecha_lunes
    fin_semana = fecha_lunes + timedelta(days=6)

    ac = ap = 0
    obra_ejec = obra_prog = Decimal('0')
    cant_ejec = horas = 0.0

    try:
        from apps.actividades.models import Actividad
        acts = Actividad.objects.filter(
            proyecto=proyecto,
            fecha_planeada__range=(inicio_semana, fin_semana),
        )
        ap = acts.count()
        ac = acts.filter(estado='COMPLETADA').count()
    except Exception:
        pass

    try:
        from apps.campo.models import RegistroAvance
        ra = RegistroAvance.objects.filter(
            actividad__proyecto=proyecto,
            fecha__range=(inicio_semana, fin_semana),
        ).aggregate(
            ejec=Sum('cantidad_ejecutada'),
            hh=Sum('horas_hombre'),
        )
        cant_ejec = float(ra.get('ejec') or 0)
        horas = float(ra.get('hh') or 0)
    except Exception:
        pass

    return {
        'presupuesto_ejecutado_pct': 0.0,
        'presupuesto_planeado_pct': 0.0,
        'obra_ejecutada': obra_ejec,
        'obra_programada': obra_prog,
        'actividades_completadas': ac,
        'actividades_planificadas': ap,
        'cantidad_ejecutada': cant_ejec,
        'horas_hombre': horas,
    }
