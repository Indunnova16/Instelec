from django.core.management.base import BaseCommand
from apps.lineas.models import Linea, Vano


class Command(BaseCommand):
    help = 'Add sample vanos for testing avances feature'

    def handle(self, *args, **options):
        linea = Linea.objects.filter(activa=True).first()

        if not linea:
            self.stdout.write(self.style.ERROR('No active lines found'))
            return

        self.stdout.write(f'Adding vanos to line: {linea.codigo}')

        estados = ['pendiente', 'ejecutado', 'sin_permiso', 'no_ejecutado', 'en_espera']
        created_count = 0

        for i in range(1, 13):
            estado = estados[(i - 1) % len(estados)]
            vano, created = Vano.objects.get_or_create(
                linea=linea,
                numero=str(i),
                defaults={
                    'estado': estado,
                    'observaciones': f'Vano {i} - Estado: {estado}'
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'✓ Vano {i}: {estado}'))
                created_count += 1
            else:
                self.stdout.write(f'→ Vano {i}: ya existe')

        self.stdout.write(self.style.SUCCESS(f'\n{created_count} new vanos created'))
        self.stdout.write(self.style.SUCCESS(f'Total vanos: {linea.vanos.count()}'))
