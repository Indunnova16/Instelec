"""
Comando para generar vanos para actividades existentes.

Los vanos son los espacios entre torres consecutivas. Este comando
crea registros de AvanceVano para cada par de torres en el tramo
asignado a una actividad.

Agregado: 1 abril 2026

Uso:
    python manage.py generar_vanos [--actividad-id=UUID] [--dry-run]
"""
from django.core.management.base import BaseCommand, CommandError
from apps.actividades.models import Actividad
from apps.campo.models import AvanceVano


class Command(BaseCommand):
    help = 'Genera vanos para actividades con tramos asignados'

    def add_arguments(self, parser):
        parser.add_argument(
            '--actividad-id',
            type=str,
            help='ID de actividad específica para generar vanos',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostrar cambios sin aplicarlos',
        )
        parser.add_argument(
            '--sobrescribir',
            action='store_true',
            help='Eliminar vanos existentes y regenerar',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        actividad_id = options.get('actividad_id')
        sobrescribir = options['sobrescribir']

        # Filtrar actividades
        if actividad_id:
            try:
                actividades = Actividad.objects.filter(id=actividad_id)
                if not actividades.exists():
                    raise CommandError(f'Actividad {actividad_id} no encontrada')
            except Exception as e:
                raise CommandError(f'Error: {str(e)}')
        else:
            # Todas las actividades con tramo asignado
            actividades = Actividad.objects.filter(tramo__isnull=False)

        total_actividades = actividades.count()
        if total_actividades == 0:
            self.stdout.write(
                self.style.WARNING('No se encontraron actividades con tramo asignado')
            )
            return

        self.stdout.write(
            f'Procesando {total_actividades} actividad(es)...\n'
        )

        vanos_creados = 0
        vanos_existentes = 0
        errores = []

        for actividad in actividades.select_related('tramo', 'linea').prefetch_related('cuadrillas'):
            try:
                # Verificar si ya tiene vanos
                vanos_actuales = actividad.avances_vanos.count()
                if vanos_actuales > 0:
                    if sobrescribir:
                        if not dry_run:
                            actividad.avances_vanos.all().delete()
                        self.stdout.write(
                            f'  Eliminados {vanos_actuales} vanos de {actividad.aviso_sap}'
                        )
                    else:
                        vanos_existentes += vanos_actuales
                        self.stdout.write(
                            f'  Actividad {actividad.aviso_sap} ya tiene {vanos_actuales} vanos (use --sobrescribir para regenerar)'
                        )
                        continue

                # Obtener torres del tramo
                torres = list(actividad.tramo.torres_incluidas.order_by('numero'))

                if len(torres) < 2:
                    errores.append(
                        f'Actividad {actividad.aviso_sap}: Tramo {actividad.tramo.codigo} '
                        f'tiene menos de 2 torres'
                    )
                    continue

                # Obtener cuadrilla asignada
                cuadrilla = actividad.cuadrillas.first()
                if not cuadrilla:
                    errores.append(
                        f'Actividad {actividad.aviso_sap}: Sin cuadrilla asignada'
                    )
                    continue

                # Generar vanos entre pares consecutivos de torres
                for i, (torre_inicio, torre_fin) in enumerate(zip(torres[:-1], torres[1:]), start=1):
                    if not dry_run:
                        AvanceVano.objects.create(
                            actividad=actividad,
                            numero_vano=i,
                            torre_inicio=torre_inicio,
                            torre_fin=torre_fin,
                            cuadrilla=cuadrilla,
                            cuadrilla_asignada_original=cuadrilla,
                        )
                    vanos_creados += 1

                self.stdout.write(
                    self.style.SUCCESS(
                        f'  ✓ Actividad {actividad.aviso_sap}: {len(torres) - 1} vanos creados'
                    )
                )

            except Exception as e:
                errores.append(
                    f'Actividad {actividad.aviso_sap}: {str(e)}'
                )

        # Resumen
        self.stdout.write('\n' + '=' * 60)
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'\n[DRY RUN] Se crearían {vanos_creados} vanos'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n✓ {vanos_creados} vanos creados exitosamente'
                )
            )

        if vanos_existentes > 0:
            self.stdout.write(
                f'  {vanos_existentes} vanos ya existían'
            )

        if errores:
            self.stdout.write(
                self.style.ERROR(
                    f'\n⚠ {len(errores)} error(es) encontrado(s):'
                )
            )
            for error in errores[:10]:
                self.stdout.write(f'  - {error}')
            if len(errores) > 10:
                self.stdout.write(f'  ... y {len(errores) - 10} más')
