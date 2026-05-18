"""Importa líneas y torres desde un archivo KMZ/KML via CLI (issue #41).

Wrapper del `KMZImporter` existente para pipelines y carga inicial Transelca.
"""
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from apps.contratos.models import Contrato
from apps.lineas.importers import KMZImporter
from apps.lineas.models import Linea


class Command(BaseCommand):
    help = 'Importa torres desde un archivo KMZ/KML hacia una línea existente.'

    def add_arguments(self, parser):
        parser.add_argument('--archivo', required=True, help='Ruta al archivo KMZ/KML')
        parser.add_argument('--linea-codigo', help='Código de la Línea destino (modo single-linea)')
        parser.add_argument('--linea-nombre', help='Nombre para crear la Línea si no existe')
        parser.add_argument('--contrato-codigo', help='Código del Contrato (opcional, para asociar la línea)')
        parser.add_argument(
            '--multi-linea', action='store_true',
            help='Importar TODAS las líneas (<Document>) del KMZ creando/recuperando '
                 'cada una por su código LN### extraído del nombre.',
        )
        parser.add_argument('--actualizar-existentes', action='store_true')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        ruta = Path(options['archivo']).expanduser()
        if not ruta.exists():
            raise CommandError(f'Archivo no encontrado: {ruta}')

        if options.get('multi_linea'):
            self._handle_multi(ruta, options)
            return

        codigo = options.get('linea_codigo')
        nombre = options.get('linea_nombre')

        linea = None
        if codigo:
            linea = Linea.objects.filter(codigo=codigo).first()

        if not linea and nombre:
            contrato = None
            if options.get('contrato_codigo'):
                contrato = Contrato.objects.filter(codigo=options['contrato_codigo']).first()
                if not contrato:
                    raise CommandError(f"Contrato {options['contrato_codigo']} no existe")
            if options['dry_run']:
                self.stdout.write(f'[dry-run] crearía Línea codigo={codigo} nombre={nombre}')
            else:
                linea = Linea.objects.create(
                    codigo=codigo or ruta.stem[:20],
                    nombre=nombre,
                    contrato=contrato,
                )
                self.stdout.write(self.style.SUCCESS(f'Línea creada: {linea.codigo}'))

        if not linea:
            raise CommandError(
                'Debe proveer --linea-codigo (existente), --linea-nombre (nueva) o --multi-linea.'
            )

        with ruta.open('rb') as fh:
            archivo = File(fh, name=ruta.name)
            importer = KMZImporter()
            resultado = importer.importar(
                archivo, linea,
                opciones={'actualizar_existentes': options['actualizar_existentes']},
            )

        if not resultado.get('exito'):
            raise CommandError(f"Importación falló: {resultado.get('error')}")

        self.stdout.write(self.style.SUCCESS(
            f"Importación OK → creadas: {resultado['torres_creadas']}, "
            f"actualizadas: {resultado['torres_actualizadas']}, "
            f"advertencias: {len(resultado.get('advertencias', []))}"
        ))
        for adv in resultado.get('advertencias', [])[:10]:
            self.stdout.write(self.style.WARNING(f'  ⚠ {adv}'))

    def _handle_multi(self, ruta, options):
        """Modo --multi-linea: KMZ con N Documents (40 líneas Transelca, etc.)."""
        with ruta.open('rb') as fh:
            archivo = File(fh, name=ruta.name)
            importer = KMZImporter()
            resultado = importer.importar_multilinea(
                archivo,
                opciones={'actualizar_existentes': options['actualizar_existentes']},
            )

        if not resultado.get('exito'):
            raise CommandError(f"Importación falló: {resultado.get('error')}")

        self.stdout.write(self.style.SUCCESS(
            f"Multi-línea OK → líneas creadas: {resultado['lineas_creadas']}, "
            f"existentes: {resultado['lineas_existentes']}, "
            f"torres creadas: {resultado['torres_creadas']}, "
            f"actualizadas: {resultado['torres_actualizadas']}, "
            f"saltadas: {resultado['torres_saltadas']}"
        ))
        for adv in resultado.get('advertencias', [])[:10]:
            self.stdout.write(self.style.WARNING(f'  ⚠ {adv}'))
        for err in resultado.get('errores', [])[:5]:
            self.stdout.write(self.style.ERROR(f'  ✗ {err}'))
