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
    ReporteDanoFactory,
    FotoDanoFactory,
)
from tests.factories.ambiental import (
    InformeAmbientalFactory,
    InformeAmbientalAprobadoFactory,
    PermisoServidumbreFactory,
    PermisoServidumbreVencidoFactory,
)
from tests.factories.financiero import (
    CostoRecursoFactory,
    CostoDiaHombreFactory,
    CostoVehiculoFactory,
    PresupuestoFactory,
    PresupuestoAprobadoFactory,
    PresupuestoEnEjecucionFactory,
    EjecucionCostoFactory,
    CicloFacturacionFactory,
    CicloFacturacionPagadoFactory,
)
from tests.factories.indicadores import (
    IndicadorFactory,
    IndicadorGestionFactory,
    IndicadorEjecucionFactory,
    IndicadorSeguridadFactory,
    MedicionIndicadorFactory,
    MedicionCumpleMeta,
    MedicionEnAlerta,
    ActaSeguimientoFactory,
    ActaSeguimientoFirmadaFactory,
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
    "ReporteDanoFactory",
    "FotoDanoFactory",
    # Ambiental
    "InformeAmbientalFactory",
    "InformeAmbientalAprobadoFactory",
    "PermisoServidumbreFactory",
    "PermisoServidumbreVencidoFactory",
    # Financiero
    "CostoRecursoFactory",
    "CostoDiaHombreFactory",
    "CostoVehiculoFactory",
    "PresupuestoFactory",
    "PresupuestoAprobadoFactory",
    "PresupuestoEnEjecucionFactory",
    "EjecucionCostoFactory",
    "CicloFacturacionFactory",
    "CicloFacturacionPagadoFactory",
    # Indicadores
    "IndicadorFactory",
    "IndicadorGestionFactory",
    "IndicadorEjecucionFactory",
    "IndicadorSeguridadFactory",
    "MedicionIndicadorFactory",
    "MedicionCumpleMeta",
    "MedicionEnAlerta",
    "ActaSeguimientoFactory",
    "ActaSeguimientoFirmadaFactory",
]
