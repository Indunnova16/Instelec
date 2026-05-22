"""Captura un snapshot del % avance de cada proyecto de construcción
activo. Pensado para correr el primer día del mes vía Celery beat o cron.

Uso:
    python manage.py snapshot_avance_proyectos
    python manage.py snapshot_avance_proyectos --proyecto <uuid>
    python manage.py snapshot_avance_proyectos --fecha 2026-05-01
"""
from datetime import date as date_cls

from django.core.management.base import BaseCommand

from apps.construccion.models import ProyectoConstruccion, SnapshotAvance


class Command(BaseCommand):
    help = 'Captura snapshot del % avance por proyecto (para curva S #61)'

    def add_arguments(self, parser):
        parser.add_argument('--proyecto', type=str, default=None,
                            help='UUID de un proyecto específico')
        parser.add_argument('--fecha', type=str, default=None,
                            help='YYYY-MM-DD (default: hoy)')
        parser.add_argument('--solo-activos', action='store_true',
                            help='Solo proyectos en PLANIFICACION o EJECUCION')

    def handle(self, *args, **opts):
        if opts['fecha']:
            fecha = date_cls.fromisoformat(opts['fecha'])
        else:
            fecha = date_cls.today()

        qs = ProyectoConstruccion.objects.all()
        if opts['proyecto']:
            qs = qs.filter(id=opts['proyecto'])
        if opts['solo_activos']:
            qs = qs.filter(estado__in=['PLANIFICACION', 'EJECUCION'])

        n = 0
        for proyecto in qs:
            snap = SnapshotAvance.capturar(proyecto, fecha=fecha)
            self.stdout.write(self.style.SUCCESS(
                f'  ✓ {proyecto.nombre[:50]} → {snap.pct_general}% '
                f'(C:{snap.pct_civil} M:{snap.pct_montaje} T:{snap.pct_tendido})'
            ))
            n += 1

        self.stdout.write(self.style.SUCCESS(
            f'\nTotal snapshots capturados para {fecha}: {n}'
        ))
