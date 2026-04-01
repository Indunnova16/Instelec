"""
Comando para corregir actividades de ejemplo con datos inconsistentes.

Fix para issue del 1 abril 2026:
Algunas actividades tienen datos de ejemplo como "TO" en lugar de números reales.
Este comando identifica y opcionalmente corrige esos datos.

Uso:
    python manage.py fix_actividades_ejemplo [--dry-run] [--fix]
"""
from django.core.management.base import BaseCommand
from apps.actividades.models import Actividad


class Command(BaseCommand):
    help = 'Identifica y corrige actividades con datos de ejemplo inconsistentes'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostrar problemas sin aplicar correcciones',
        )
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Aplicar correcciones automáticas',
        )
        parser.add_argument(
            '--eliminar',
            action='store_true',
            help='Eliminar actividades con datos inválidos (USE CON PRECAUCIÓN)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        fix = options['fix']
        eliminar = options['eliminar']

        # Buscar actividades con avisos SAP sospechosos
        problematicas = []

        # Patrón 1: Aviso SAP contiene "TO" o "ejemplo"
        actividades_to = Actividad.objects.filter(
            aviso_sap__icontains='TO'
        ) | Actividad.objects.filter(
            aviso_sap__icontains='ejemplo'
        ) | Actividad.objects.filter(
            aviso_sap__icontains='test'
        )

        for act in actividades_to:
            problematicas.append({
                'actividad': act,
                'problema': 'Aviso SAP contiene datos de ejemplo',
                'aviso_sap': act.aviso_sap,
            })

        # Patrón 2: Actividades sin tipo_actividad
        sin_tipo = Actividad.objects.filter(tipo_actividad__isnull=True)
        for act in sin_tipo:
            problematicas.append({
                'actividad': act,
                'problema': 'Sin tipo de actividad asignado',
                'aviso_sap': act.aviso_sap,
            })

        # Patrón 3: Actividades sin línea
        sin_linea = Actividad.objects.filter(linea__isnull=True)
        for act in sin_linea:
            problematicas.append({
                'actividad': act,
                'problema': 'Sin línea asignada',
                'aviso_sap': act.aviso_sap,
            })

        total = len(problematicas)

        if total == 0:
            self.stdout.write(
                self.style.SUCCESS('✓ No se encontraron actividades problemáticas')
            )
            return

        self.stdout.write(
            self.style.WARNING(f'Encontradas {total} actividad(es) problemática(s):\n')
        )

        for item in problematicas:
            act = item['actividad']
            self.stdout.write(
                f"  - {act.id}: {item['problema']}"
            )
            self.stdout.write(
                f"    Aviso SAP: {item['aviso_sap']}"
            )
            self.stdout.write(
                f"    Línea: {act.linea.codigo if act.linea else 'N/A'}"
            )
            self.stdout.write(
                f"    Torre: {act.torre.numero if act.torre else 'N/A'}"
            )
            self.stdout.write('')

        if dry_run:
            self.stdout.write(
                self.style.WARNING('\n[DRY RUN] No se aplicaron cambios')
            )
            return

        if eliminar:
            confirmacion = input(
                f'\n⚠️  ¿CONFIRMA que desea ELIMINAR {total} actividad(es)? '
                'Esta acción NO es reversible. [escriba "CONFIRMAR"]: '
            )
            if confirmacion == 'CONFIRMAR':
                for item in problematicas:
                    item['actividad'].delete()
                self.stdout.write(
                    self.style.SUCCESS(f'\n✓ {total} actividad(es) eliminadas')
                )
            else:
                self.stdout.write(
                    self.style.WARNING('Operación cancelada')
                )
            return

        if fix:
            corregidas = 0
            from apps.actividades.models import TipoActividad

            # Obtener tipo de actividad genérico
            tipo_generico = TipoActividad.objects.filter(
                categoria='OTRO'
            ).first()

            if not tipo_generico:
                tipo_generico = TipoActividad.objects.first()

            if not tipo_generico:
                self.stdout.write(
                    self.style.ERROR(
                        'ERROR: No hay tipos de actividad en el sistema. '
                        'Cree al menos un tipo antes de ejecutar --fix'
                    )
                )
                return

            for item in problematicas:
                act = item['actividad']
                cambios = []

                # Corregir tipo de actividad
                if not act.tipo_actividad:
                    act.tipo_actividad = tipo_generico
                    cambios.append('tipo_actividad asignado')

                # Corregir aviso SAP
                if 'TO' in act.aviso_sap or 'ejemplo' in act.aviso_sap.lower():
                    from datetime import datetime
                    act.aviso_sap = f"CORREGIDO-{datetime.now().strftime('%Y%m%d%H%M%S')}-{act.id}"
                    cambios.append('aviso_sap corregido')

                if cambios:
                    act.save()
                    corregidas += 1
                    self.stdout.write(
                        f"  ✓ {act.id}: {', '.join(cambios)}"
                    )

            self.stdout.write(
                self.style.SUCCESS(f'\n✓ {corregidas} actividad(es) corregidas')
            )

        else:
            self.stdout.write(
                self.style.WARNING(
                    '\nPara corregir automáticamente, ejecute con --fix'
                )
            )
            self.stdout.write(
                self.style.WARNING(
                    'Para eliminar actividades problemáticas, ejecute con --eliminar'
                )
            )
