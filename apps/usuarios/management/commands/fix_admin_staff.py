"""
Comando para corregir el flag is_staff en usuarios administrativos.

Fix para issue del 1 abril 2026:
Usuarios con roles admin, director y coordinador necesitan is_staff=True
para poder ver botones administrativos en templates.

Uso:
    python manage.py fix_admin_staff
"""
from django.core.management.base import BaseCommand
from apps.usuarios.models import Usuario


class Command(BaseCommand):
    help = 'Asigna is_staff=True a usuarios con roles administrativos (admin, director, coordinador)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostrar cambios sin aplicarlos',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # Roles que requieren is_staff=True
        roles_admin = ['admin', 'director', 'coordinador']

        # Buscar usuarios con roles administrativos sin is_staff
        usuarios_a_corregir = Usuario.objects.filter(
            rol__in=roles_admin,
            is_staff=False
        )

        total = usuarios_a_corregir.count()

        if total == 0:
            self.stdout.write(
                self.style.SUCCESS('✓ Todos los usuarios administrativos ya tienen is_staff=True')
            )
            return

        self.stdout.write(
            self.style.WARNING(f'Encontrados {total} usuario(s) a corregir:')
        )

        for usuario in usuarios_a_corregir:
            self.stdout.write(
                f'  - {usuario.get_full_name()} ({usuario.email}) - Rol: {usuario.get_rol_display()}'
            )

        if dry_run:
            self.stdout.write(
                self.style.WARNING('\n[DRY RUN] No se aplicaron cambios. Ejecute sin --dry-run para aplicar.')
            )
            return

        # Aplicar corrección
        usuarios_a_corregir.update(is_staff=True)

        self.stdout.write(
            self.style.SUCCESS(f'\n✓ {total} usuario(s) actualizados exitosamente')
        )

        # También verificar que ing_residente tenga is_staff (opcional)
        ing_residentes = Usuario.objects.filter(
            rol='ing_residente',
            is_staff=False
        )
        if ing_residentes.exists():
            self.stdout.write(
                self.style.WARNING(
                    f'\nNOTA: Hay {ing_residentes.count()} Ingeniero(s) Residente sin is_staff. '
                    'Si requieren acceso administrativo, actualice manualmente.'
                )
            )
