"""
Conftest local a apps/cuadrillas — issue #176 (Maestro 3, A6).

Autouse fixture que siembra el catálogo completo de `Cargo` (14 códigos,
la misma unión congelada que la migración 0019_seed_cargos) antes de CADA
test de este paquete. Necesario porque pytest corre con `--nomigrations`
(el schema de la BD de test se arma directo desde el estado actual de los
modelos, sin aplicar las migraciones reales, incluida la RunPython de
seed) — sin esto, cualquier test que cree un `PersonalCuadrilla` /
`CuadrillaMiembro` con un `rol_cuadrilla_id` revienta con `IntegrityError`
de FK contra la tabla `cargos` vacía (A3: `rol_cuadrilla` es ahora
FK(Cargo, to_field='codigo'), no CharField+choices).

`get_or_create` es idempotente — no interfiere con tests que ya siembran
explícitamente (p.ej. `TestMaestro3A1CargoModeloYSeed` en
tests_issue_176.py, que corre la migración 0019 directamente).
"""

import pytest

_CARGOS_SEED = [
    ("SUPERVISOR", "Supervisor"),
    ("LINIERO_I", "Liniero I"),
    ("LINIERO_II", "Liniero II"),
    ("AYUDANTE", "Ayudante"),
    ("CONDUCTOR", "Conductor"),
    ("ADMINISTRADOR_OBRA", "Administrador de Obra"),
    ("PROFESIONAL_SST", "Profesional SST"),
    ("ING_RESIDENTE", "Ingeniero Residente"),
    ("SERVICIO_GENERAL", "Servicio General"),
    ("ALMACENISTA", "Almacenista"),
    ("SUPERVISOR_FOREST", "Supervisor Forestal"),
    ("ASISTENTE_FOREST", "Asistente Forestal"),
    ("MALACATERO", "Malacatero"),
    ("COORDINADOR_HSQ", "Coordinador HSQ"),
]


@pytest.fixture(autouse=True)
def _seed_catalogo_cargos(db):
    """Autouse: garantiza que los 14 códigos de Cargo existan antes de
    cada test de apps/cuadrillas/ (ver docstring del módulo)."""
    from apps.cuadrillas.models import Cargo

    for codigo, nombre in _CARGOS_SEED:
        Cargo.objects.get_or_create(codigo=codigo, defaults={"nombre": nombre, "activo": True})
