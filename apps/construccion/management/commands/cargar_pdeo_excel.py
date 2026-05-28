"""Management command para cargar el Excel PDEO desde CLI (#103).

Uso:
    python manage.py cargar_pdeo_excel <ruta_xlsx> <proyecto_id>
"""
from django.core.management.base import BaseCommand, CommandError

from apps.construccion.models import ProyectoConstruccion
from apps.construccion.pdeo_importer import import_pdeo_workbook


class Command(BaseCommand):
    help = 'Carga el Excel PDEO al proyecto de construcción indicado.'

    def add_arguments(self, parser):
        parser.add_argument('xlsx_path', type=str,
                            help='Ruta al archivo .xlsx PDEO.')
        parser.add_argument('proyecto_id', type=str,
                            help='UUID del ProyectoConstruccion destino.')

    def handle(self, *args, **opts):
        try:
            proyecto = ProyectoConstruccion.objects.get(id=opts['proyecto_id'])
        except ProyectoConstruccion.DoesNotExist:
            raise CommandError(
                f"Proyecto {opts['proyecto_id']} no existe.")
        with open(opts['xlsx_path'], 'rb') as fh:
            stats = import_pdeo_workbook(fh, proyecto, usuario=None)
        self.stdout.write(self.style.SUCCESS(
            f"Cargado: {stats['transacciones_creadas']} nuevas, "
            f"{stats['transacciones_omitidas']} omitidas, "
            f"{stats['movimientos_actualizados']} movimientos actualizados. "
            f"Hojas: {', '.join(stats['hojas_procesadas'])}"))
