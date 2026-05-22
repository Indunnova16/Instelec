"""Celery tasks para construccion (#61 snapshots avance)."""
from celery import shared_task


@shared_task(name='construccion.snapshot_avance_diario')
def snapshot_avance_diario():
    """Captura snapshot del avance de todos los proyectos CONSTRUCCION
    activos. Programar día 1 de cada mes vía django-celery-beat
    DatabaseScheduler con cron(day_of_month=1, hour=0, minute=5).

    También puede correrse manualmente:
        python manage.py snapshot_avance_proyectos --solo-activos
    """
    from datetime import date as date_cls
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
            import logging
            logging.getLogger(__name__).exception(
                f'Error snapshot proyecto {proyecto.id}: {e}')
    return {'fecha': fecha.isoformat(), 'snapshots': count}
