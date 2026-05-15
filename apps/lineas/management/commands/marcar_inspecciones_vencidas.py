"""Marca Líneas y Torres con `inspection_status='VENCIDA'` cuando su
`last_inspection_date` excede el umbral. Pensado para Celery beat diario.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.lineas.models import Linea, Torre


class Command(BaseCommand):
    help = 'Marca inspecciones vencidas (>30d) y próximas a vencer (>20d).'

    def add_arguments(self, parser):
        parser.add_argument('--vencida-dias', type=int, default=30)
        parser.add_argument('--proxima-dias', type=int, default=20)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        hoy = timezone.now().date()
        vencida_corte = hoy - timedelta(days=options['vencida_dias'])
        proxima_corte = hoy - timedelta(days=options['proxima_dias'])
        dry = options['dry_run']

        total_vencidas_l = 0
        total_proximas_l = 0
        for modelo, label in [(Linea, 'Líneas'), (Torre, 'Torres')]:
            vencidas = modelo.objects.filter(
                last_inspection_date__lte=vencida_corte,
            ).exclude(inspection_status='CRITICA')
            proximas = modelo.objects.filter(
                last_inspection_date__lte=proxima_corte,
                last_inspection_date__gt=vencida_corte,
            ).exclude(inspection_status__in=['VENCIDA', 'CRITICA'])

            n_v = vencidas.count()
            n_p = proximas.count()
            self.stdout.write(f"{label}: {n_v} a marcar como VENCIDA, {n_p} como PROXIMA")

            if not dry:
                vencidas.update(inspection_status='VENCIDA')
                proximas.update(inspection_status='PROXIMA')

            if modelo is Linea:
                total_vencidas_l = n_v
                total_proximas_l = n_p

        self.stdout.write(self.style.SUCCESS(
            f"Listo. Líneas → VENCIDAS: {total_vencidas_l}, PROXIMAS: {total_proximas_l}"
        ))
