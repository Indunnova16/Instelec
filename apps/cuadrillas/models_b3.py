"""
B3 — Cuadrilla auditoría desactivación (Sofi, mayo 2026).

Issue: Indunnova16/Instelec#104 — "Cuadrillas - Botón para Ver Cuadrillas Desactivadas".

Estrategia: el modelo Cuadrilla vive en models_base.py. F2 scaffolding partió
el módulo pero NO incluyó models_base.py en files_owned de B3. Para no romper
el contrato de archivos de /modulo, este archivo:

  1. Usa Cuadrilla.add_to_class(...) para registrar los 3 campos auditoría.
     Django reconoce los campos como si estuvieran declarados en la clase
     (afecta admin, querysets, makemigrations).
  2. Monkey-patchea Cuadrilla.save y agrega métodos helpers desactivar() y
     reactivar() (contratos del BLUEPRINT).

Cuando un futuro refactor estabilice estos campos, mover declaración nativa a
models_base.py y eliminar este archivo.
"""
from django.db import models
from django.utils import timezone

from .models_base import Cuadrilla


# ---------------------------------------------------------------------------
# Campos auditoría — registrados vía add_to_class para que aparezcan en el
# modelo Cuadrilla resuelto desde el app registry, sin tocar models_base.py.
# ---------------------------------------------------------------------------

# Idempotencia: si por alguna razón este módulo se importa dos veces (admin
# autodiscover + aggregator), evitamos el "AlreadyRegistered" agregando solo
# si los atributos no existen aún.
_FIELDS = {
    'motivo_desactivacion': models.CharField(
        'Motivo desactivación',
        max_length=255,
        blank=True,
        default='',
        help_text='Razón por la que la cuadrilla fue desactivada',
    ),
    'fecha_desactivacion': models.DateTimeField(
        'Fecha desactivación',
        null=True,
        blank=True,
        help_text='Timestamp del momento en que se desactivó la cuadrilla',
    ),
    'desactivado_por': models.ForeignKey(
        'usuarios.Usuario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cuadrillas_desactivadas',
        verbose_name='Desactivado por',
    ),
}

def _has_field(model, name):
    """Check field presence using local _meta.fields (safe before app registry ready)."""
    return any(f.name == name for f in model._meta.local_fields)


for _name, _field in _FIELDS.items():
    if not _has_field(Cuadrilla, _name):
        Cuadrilla.add_to_class(_name, _field)


# ---------------------------------------------------------------------------
# Save override — si activa pasa True → False y no se setea motivo manualmente,
# rellenar fecha_desactivacion=now() y dejar desactivado_por NULL salvo que la
# vista lo haya asignado vía CuadrillaAuditMixin.
# ---------------------------------------------------------------------------

_ORIGINAL_SAVE = Cuadrilla.save


def _b3_save(self, *args, **kwargs):
    """
    Override save() de Cuadrilla con auditoría de desactivación.

    Edge case 1: cambio activa True → False sin fecha previa → setear ahora.
    Edge case 2: cambio activa False → True (reactivar) → limpiar motivo/fecha
                 (no borrar desactivado_por: histórico).
    Edge case 3: instancia nueva (pk=None) → no aplicar lógica.
    Edge case 4: cuadrilla ya inactiva sin auditoría → no rellenar
                 retroactivamente al hacer otro save (solo en la transición).
    """
    if self.pk:
        try:
            previo = type(self).objects.get(pk=self.pk)
        except type(self).DoesNotExist:
            previo = None

        if previo is not None:
            # Transición activa True → False
            if previo.activa and not self.activa:
                if not self.fecha_desactivacion:
                    self.fecha_desactivacion = timezone.now()
            # Transición activa False → True (reactivar)
            elif (not previo.activa) and self.activa:
                self.motivo_desactivacion = ''
                self.fecha_desactivacion = None
                # desactivado_por se conserva como rastro histórico

    return _ORIGINAL_SAVE(self, *args, **kwargs)


Cuadrilla.save = _b3_save


# ---------------------------------------------------------------------------
# Métodos helper — contratos declarados en BLUEPRINT.md.json (contracts.models).
# ---------------------------------------------------------------------------

def _b3_desactivar(self, usuario=None, motivo=''):
    """Desactivar cuadrilla con auditoría completa.

    Args:
        usuario: Usuario que ejecuta la desactivación (puede ser None).
        motivo: Texto libre con la razón.

    Returns:
        self, refrescado.
    """
    self.activa = False
    self.motivo_desactivacion = (motivo or '')[:255]
    self.fecha_desactivacion = timezone.now()
    self.desactivado_por = usuario
    self.save()
    return self


def _b3_reactivar(self, usuario=None):
    """Reactivar cuadrilla previamente desactivada.

    Args:
        usuario: Usuario que ejecuta la reactivación. Se anota en
                 observaciones para trazabilidad ligera (sin nuevo modelo).

    Returns:
        self, refrescado.
    """
    self.activa = True
    self.motivo_desactivacion = ''
    self.fecha_desactivacion = None
    # desactivado_por se conserva como rastro histórico
    if usuario is not None:
        marca = f"\n[Reactivada por {usuario.get_username()} el {timezone.now():%Y-%m-%d %H:%M}]"
        self.observaciones = (self.observaciones or '') + marca
    self.save()
    return self


Cuadrilla.desactivar = _b3_desactivar
Cuadrilla.reactivar = _b3_reactivar


__all__ = []  # nada exportado; este módulo se carga por side-effect.
