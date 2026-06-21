from django.core.management.base import BaseCommand
from apps.pagos.models import PlanServicio, Suscripcion


class Command(BaseCommand):
    help = 'Crea el plan de servicio y suscripcion inicial para Instelec'

    def handle(self, *args, **options):
        plan, created = PlanServicio.objects.get_or_create(
            nombre='Plan Instelec',
            defaults={
                'precio': 150000,
                'descripcion': (
                    'Plan mensual Sistema de Gestion Instelec (construccion y '
                    'mantenimiento de lineas de transmision).\n'
                    'Precio: $150,000 COP/mes.\n\n'
                    'Incluye: Plataforma 24/7, hosting Google Cloud, base de datos '
                    'PostgreSQL con backups diarios, certificado SSL, soporte por '
                    'WhatsApp, actualizaciones mensuales.'
                ),
                'activo': True,
            }
        )
        self.stdout.write(self.style.SUCCESS(f"Plan {'creado' if created else 'ya existe'}: {plan}"))

        suscripcion, created = Suscripcion.objects.get_or_create(
            plan=plan,
            defaults={'estado': 'PENDIENTE'}
        )
        self.stdout.write(self.style.SUCCESS(f"Suscripcion {'creada' if created else 'ya existe'}: {suscripcion}"))
