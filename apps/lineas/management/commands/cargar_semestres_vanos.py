"""
B2.1 — Datafix: cargar semestres de los vanos según tabla del issue #102.

Uso:
    python manage.py cargar_semestres_vanos              # usa tabla embebida
    python manage.py cargar_semestres_vanos --dry-run    # valida sin commit
    python manage.py cargar_semestres_vanos --file path  # tabla desde archivo
    python manage.py cargar_semestres_vanos --from-issue # fetch tabla via gh

Requisitos para `--from-issue`: tener `gh` autenticado en el host.
"""
from __future__ import annotations

import shutil
import subprocess

from django.core.management.base import BaseCommand, CommandError

from apps.lineas.importers_b21 import (
    TABLA_ISSUE_102,
    importar_tabla,
)


class Command(BaseCommand):
    help = "Carga la segmentación de Vanos por Semestre (S1/S2/TA) a partir de la tabla del issue #102."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="Parsea y simula la importación sin persistir.",
        )
        parser.add_argument(
            '--file',
            help="Ruta a un archivo .txt con la tabla (sobrescribe la embebida).",
        )
        parser.add_argument(
            '--from-issue',
            action='store_true',
            help="Trae la tabla actualizada via `gh issue view 102 --repo Indunnova16/Instelec`.",
        )
        parser.add_argument(
            '--repo',
            default='Indunnova16/Instelec',
            help="Repo para `--from-issue` (default Indunnova16/Instelec).",
        )
        parser.add_argument(
            '--issue',
            default='102',
            help="Issue number para `--from-issue` (default 102).",
        )

    def handle(self, *args, **opts):
        texto = self._cargar_texto(opts)

        self.stdout.write(self.style.NOTICE(
            f"Cargando semestres de vanos (dry-run={opts['dry_run']})..."
        ))
        try:
            resultado = importar_tabla(texto, dry_run=opts['dry_run'])
        except Exception as exc:
            raise CommandError(f"Falló la importación: {exc}") from exc

        self.stdout.write(self.style.SUCCESS(f"Resumen: {resultado}"))

        if resultado.lineas_no_encontradas:
            self.stdout.write(self.style.WARNING(
                "Líneas no encontradas (revisar mapping codigo/codigo_transelca):"
            ))
            for c in resultado.lineas_no_encontradas:
                self.stdout.write(f"  - {c}")

        if resultado.vanos_faltantes_por_linea:
            self.stdout.write(self.style.WARNING(
                "Líneas con menos vanos que la tabla pide (crear vanos faltantes):"
            ))
            for codigo, items in resultado.vanos_faltantes_por_linea.items():
                for it in items:
                    self.stdout.write(
                        f"  - {codigo} [{it['semestre']}]: pedidos={it['pedidos']} "
                        f"disponibles={it['disponibles']}"
                    )

        if opts['dry_run']:
            self.stdout.write(self.style.WARNING("Dry-run — sin persistir."))
        else:
            self.stdout.write(self.style.SUCCESS("Importación completada."))

    def _cargar_texto(self, opts) -> str:
        if opts.get('file'):
            with open(opts['file'], encoding='utf-8') as fh:
                return fh.read()
        if opts.get('from_issue'):
            if not shutil.which('gh'):
                raise CommandError("--from-issue requiere `gh` instalado en PATH.")
            self.stdout.write(f"Trayendo tabla desde {opts['repo']}#{opts['issue']}...")
            try:
                out = subprocess.check_output(
                    ['gh', 'issue', 'view', opts['issue'], '--repo', opts['repo']],
                    timeout=30,
                    text=True,
                )
            except subprocess.CalledProcessError as exc:
                raise CommandError(f"gh issue view falló: {exc}") from exc
            return out
        return TABLA_ISSUE_102
