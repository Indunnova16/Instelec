"""Test factories for TransMaint."""

from tests.factories.usuarios import (
    UsuarioFactory,
    AdminFactory,
    CoordinadorFactory,
    IngenieroResidenteFactory,
    SupervisorFactory,
    LinieroFactory,
)
from tests.factories.lineas import (
    LineaFactory,
    TorreFactory,
    PoligonoServidumbreFactory,
)
from tests.factories.cuadrillas import (
    VehiculoFactory,
    CuadrillaFactory,
    CuadrillaMiembroFactory,
)
from tests.factories.actividades import (
    TipoActividadFactory,
    ProgramacionMensualFactory,
    ActividadFactory,
    ActividadEnCursoFactory,
    ActividadCompletadaFactory,
)
from tests.factories.campo import (
    RegistroCampoFactory,
    RegistroCampoCompletadoFactory,
    EvidenciaFactory,
    EvidenciaAntesFactory,
    EvidenciaDuranteFactory,
    EvidenciaDespuesFactory,
)

__all__ = [
    # Usuarios
    "UsuarioFactory",
    "AdminFactory",
    "CoordinadorFactory",
    "IngenieroResidenteFactory",
    "SupervisorFactory",
    "LinieroFactory",
    # Lineas
    "LineaFactory",
    "TorreFactory",
    "PoligonoServidumbreFactory",
    # Cuadrillas
    "VehiculoFactory",
    "CuadrillaFactory",
    "CuadrillaMiembroFactory",
    # Actividades
    "TipoActividadFactory",
    "ProgramacionMensualFactory",
    "ActividadFactory",
    "ActividadEnCursoFactory",
    "ActividadCompletadaFactory",
    # Campo
    "RegistroCampoFactory",
    "RegistroCampoCompletadoFactory",
    "EvidenciaFactory",
    "EvidenciaAntesFactory",
    "EvidenciaDuranteFactory",
    "EvidenciaDespuesFactory",
]
