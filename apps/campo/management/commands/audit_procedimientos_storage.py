"""Audit Procedimiento.archivo blobs vs storage; flag huérfanos.

Issue #118 — iterar `procedimientos_campo`, marcar `blob_disponible=False` los
que ya no tienen blob en GCS para que el listado los oculte/atenúe.

Uso:
    python manage.py audit_procedimientos_storage          # dry-run, solo reporta
    python manage.py audit_procedimientos_storage --apply  # persiste el flag
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.campo.models import Procedimiento


class Command(BaseCommand):
    help = 'Auditar blob_disponible vs storage para Procedimientos'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Persistir cambios. Sin este flag solo reporta.',
        )

    def handle(self, *args, **options):
        apply = options['apply']
        total = 0
        cambios = []
        for proc in Procedimiento.objects.all().iterator():
            total += 1
            try:
                existe = bool(proc.archivo) and proc.archivo.storage.exists(
                    proc.archivo.name
                )
            except Exception as exc:
                self.stderr.write(
                    self.style.WARNING(
                        f'[skip] {proc.id} ({proc.titulo}): error consultando storage: {exc}'
                    )
                )
                continue

            esperado = existe
            if proc.blob_disponible != esperado:
                cambios.append((proc, esperado))

        self.stdout.write(f'Revisados {total} procedimientos · {len(cambios)} cambios')
        for proc, nuevo in cambios:
            flecha = '✅ recuperado' if nuevo else '❌ huérfano'
            self.stdout.write(
                f'  {flecha} {proc.id} | {proc.titulo} | archivo={proc.archivo.name}'
            )

        if not cambios:
            return

        if not apply:
            self.stdout.write(self.style.WARNING('\nDry-run. Usar --apply para persistir.'))
            return

        for proc, nuevo in cambios:
            proc.blob_disponible = nuevo
            proc.save(update_fields=['blob_disponible'])
        self.stdout.write(self.style.SUCCESS(f'\nActualizados {len(cambios)} registros.'))
