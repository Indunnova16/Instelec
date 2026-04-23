from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from apps.lineas.models import Vano, PendienteVano
from apps.usuarios.models import Usuario


class Command(BaseCommand):
    help = 'Add sample pendientes for testing'

    def handle(self, *args, **options):
        vanos = Vano.objects.all()[:3]  # Get first 3 vanos

        if not vanos.exists():
            self.stdout.write(self.style.ERROR('No vanos found'))
            return

        usuario = Usuario.objects.filter(rol__in=['admin', 'director']).first()

        self.stdout.write('Adding sample pendientes...')

        descripciones = [
            'Revisar medidas de seguridad',
            'Instalar herraje de aislamiento',
            'Prueba de continuidad',
            'Limpieza del área',
            'Inspección final',
        ]

        created_count = 0
        for vano in vanos:
            for i, desc in enumerate(descripciones[:2]):
                fecha = timezone.now().date() + timedelta(days=i + 1)
                pendiente, created = PendienteVano.objects.get_or_create(
                    vano=vano,
                    descripcion=desc,
                    defaults={
                        'fecha_vencimiento': fecha,
                        'responsable': usuario,
                    }
                )
                if created:
                    self.stdout.write(self.style.SUCCESS(f'✓ Pendiente para Vano {vano.numero}: {desc}'))
                    created_count += 1

        self.stdout.write(self.style.SUCCESS(f'\n{created_count} new pendientes created'))
