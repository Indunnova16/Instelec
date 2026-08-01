"""Tests (#205) — comando `limpiar_datos_prueba_mantenimiento`.

Cubre:
  - dry-run por defecto no escribe nada (BD igual antes/después).
  - --commit borra las tablas 100% exclusivas de Mantenimiento
    (Actividad/ProgramacionMensual/HistorialIntervencion/InformeDiario).
  - --commit borra Cuadrilla+Asistencia "seguras" pero NUNCA una Cuadrilla
    cuyo nombre colisiona con un campo de texto libre de Construcción
    (cuadrilla_civil/montaje/tendido en TorreConstruccion o sus
    relacionados pata_obra/fase) — ese es el escenario de riesgo real que
    motivó separar este comando de un DELETE a mano.
  - --commit en Colaboradores: borra solo `activo=False`, deja intactos los
    activos que ya tienen `area` asignada, y backfillea `area=''` ->
    `MANTENIMIENTO` solo en los activos sin área.
  - Vano/VanoSemestre nunca se importan ni se tocan (el comando no debe
    fallar ni siquiera si esas tablas no existen en el settings de test).

Nombre de archivo ``tests_*`` por paridad con el resto del repo (ver
``apps/core/tests_context_processor_proyectos.py``).
"""

from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.actividades.models import (
    Actividad,
    HistorialIntervencion,
    InformeDiario,
    ProgramacionMensual,
)
from apps.core.permissions import AREA_MANTENIMIENTO
from apps.cuadrillas.models import Asistencia, Cuadrilla, PersonalCuadrilla
from tests.factories.actividades import ActividadFactory
from tests.factories.cuadrillas import CuadrillaFactory
from tests.factories.usuarios import LinieroFactory


@pytest.fixture(autouse=True)
def _seed_cargo_liniero_i(db):
    """PersonalCuadrilla.rol_cuadrilla es FK(Cargo, to_field='codigo') con
    default 'LINIERO_I'. Sin la migración de seed (deshabilitada por
    --nomigrations), Postgres rechaza el insert. Mismo auto-seed que usa
    CuadrillaMiembroFactory._create (tests/factories/cuadrillas.py)."""
    from apps.cuadrillas.models import Cargo

    Cargo.objects.get_or_create(
        codigo="LINIERO_I", defaults={"nombre": "Liniero I", "activo": True}
    )


def _run(commit=False):
    out = StringIO()
    call_command(
        "limpiar_datos_prueba_mantenimiento",
        commit=commit,
        stdout=out,
    )
    return out.getvalue()


def _make_torre_construccion(numero="T-1"):
    from apps.construccion.models import ProyectoConstruccion, TorreConstruccion
    from apps.contratos.models import Contrato

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo=f"CTR-{numero}",
        nombre=f"Contrato {numero}",
        cliente="Cliente test #205",
    )
    proyecto = ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre=f"Proyecto {numero}",
        estado="EJECUCION",
    )
    return TorreConstruccion.objects.create(proyecto=proyecto, numero=numero)


@pytest.mark.django_db
class TestDryRunNoEscribeNada:
    def test_dry_run_no_borra_actividades(self):
        ActividadFactory()
        assert Actividad.objects.count() == 1

        _run(commit=False)

        assert Actividad.objects.count() == 1

    def test_dry_run_no_borra_cuadrillas_ni_personal(self):
        CuadrillaFactory()
        PersonalCuadrilla.objects.create(nombre="Prueba Inactivo", documento="TEST-1", activo=False)

        _run(commit=False)

        assert Cuadrilla.objects.count() == 1
        assert PersonalCuadrilla.objects.count() == 1

    def test_dry_run_reporta_conteos_en_stdout(self):
        ActividadFactory()
        salida = _run(commit=False)

        assert "DRY-RUN" in salida
        assert "actividades.Actividad: 1 fila" in salida


@pytest.mark.django_db
class TestCommitTablasExclusivasMantenimiento:
    def test_commit_borra_actividad_y_programacion_mensual(self):
        actividad = ActividadFactory()
        programacion_id = actividad.programacion_id

        _run(commit=True)

        assert Actividad.objects.count() == 0
        assert ProgramacionMensual.objects.filter(id=programacion_id).count() == 0

    def test_commit_borra_historial_e_informe_diario(self):
        from tests.factories.lineas import LineaFactory, TorreFactory

        linea = LineaFactory()
        torre = TorreFactory(linea=linea)
        actividad = ActividadFactory(linea=linea, torre=torre)

        HistorialIntervencion.objects.create(
            linea=linea,
            actividad=actividad,
            fecha_intervencion=timezone.now(),
            tipo_intervencion="Poda",
        )
        InformeDiario.objects.create(
            fecha="2026-07-01",
            cuadrilla=actividad.cuadrilla,
            linea=linea,
        )

        assert HistorialIntervencion.objects.count() == 1
        assert InformeDiario.objects.count() == 1

        _run(commit=True)

        assert HistorialIntervencion.objects.count() == 0
        assert InformeDiario.objects.count() == 0


@pytest.mark.django_db
class TestCommitCuadrillaConRiesgoDeColision:
    def test_commit_borra_cuadrilla_segura_y_su_asistencia(self):
        cuadrilla = CuadrillaFactory(nombre="Cuadrilla de prueba Alcides")
        usuario = LinieroFactory()
        Asistencia.objects.create(usuario=usuario, cuadrilla=cuadrilla, fecha="2026-07-01")

        _run(commit=True)

        assert Cuadrilla.objects.count() == 0
        assert Asistencia.objects.count() == 0

    def test_commit_NO_borra_cuadrilla_referenciada_en_torreconstruccion_directo(self):
        """Riesgo real: si una Cuadrilla de prueba comparte nombre con una
        cuadrilla real de Construcción (campo de texto libre, no FK), un
        DELETE ciego rompería el filtrado de operarios de Construcción.
        El comando debe excluirla del --commit."""
        cuadrilla = CuadrillaFactory(nombre="Cuadrilla Civil Norte")
        torre = _make_torre_construccion("T-100")
        torre.cuadrilla_civil = "Cuadrilla Civil Norte"
        torre.save(update_fields=["cuadrilla_civil"])

        salida = _run(commit=True)

        assert Cuadrilla.objects.filter(id=cuadrilla.id).exists(), (
            "Una Cuadrilla referenciada por nombre en Construcción NO debe borrarse"
        )
        assert "riesgo" in salida.lower()

    def test_commit_NO_borra_cuadrilla_referenciada_en_pata_obra(self):
        from apps.construccion.models import PataObra

        cuadrilla = CuadrillaFactory(nombre="Cuadrilla Sur")
        torre = _make_torre_construccion("T-101")
        PataObra.objects.create(torre=torre, pata="A", cuadrilla_civil="Cuadrilla Sur")

        _run(commit=True)

        assert Cuadrilla.objects.filter(id=cuadrilla.id).exists()

    def test_commit_borra_otras_cuadrillas_aunque_una_este_en_riesgo(self):
        """El riesgo de UNA cuadrilla no debe bloquear el borrado de las demás."""
        segura = CuadrillaFactory(nombre="Cuadrilla Segura 205")
        en_riesgo = CuadrillaFactory(nombre="Cuadrilla Compartida 205")
        torre = _make_torre_construccion("T-102")
        torre.cuadrilla_civil = "Cuadrilla Compartida 205"
        torre.save(update_fields=["cuadrilla_civil"])

        _run(commit=True)

        assert not Cuadrilla.objects.filter(id=segura.id).exists()
        assert Cuadrilla.objects.filter(id=en_riesgo.id).exists()


@pytest.mark.django_db
class TestCommitColaboradores:
    def test_commit_borra_solo_inactivos(self):
        activo = PersonalCuadrilla.objects.create(
            nombre="Colaborador Activo", documento="DOC-ACT-205", activo=True
        )
        inactivo = PersonalCuadrilla.objects.create(
            nombre="Colaborador Inactivo", documento="DOC-INACT-205", activo=False
        )

        _run(commit=True)

        assert PersonalCuadrilla.objects.filter(id=activo.id).exists()
        assert not PersonalCuadrilla.objects.filter(id=inactivo.id).exists()

    def test_commit_backfillea_area_solo_si_esta_en_blanco(self):
        sin_area = PersonalCuadrilla.objects.create(
            nombre="Sin Area", documento="DOC-SINAREA-205", activo=True, area=""
        )
        con_area = PersonalCuadrilla.objects.create(
            nombre="Con Area", documento="DOC-CONAREA-205", activo=True, area="CONSTRUCCION"
        )

        _run(commit=True)

        sin_area.refresh_from_db()
        con_area.refresh_from_db()
        assert sin_area.area == AREA_MANTENIMIENTO
        assert con_area.area == "CONSTRUCCION", "No debe pisar un área ya asignada"


@pytest.mark.django_db
def test_comando_no_importa_ni_toca_vano_ni_vanosemestre():
    """Guard-rail duro del issue #205: aunque existan Vano/VanoSemestre
    cargados, el comando no debe consultarlos ni borrarlos. Se verifica
    indirectamente: crear un Vano/VanoSemestre y confirmar que sigue
    existiendo intacto después de --commit."""
    from apps.lineas.models import Vano
    from tests.factories.lineas import LineaFactory, TorreFactory

    linea = LineaFactory()
    torre_a = TorreFactory(linea=linea)
    torre_b = TorreFactory(linea=linea)
    vano = Vano.objects.create(linea=linea, numero="V-1", torre_inicio=torre_a, torre_fin=torre_b)

    _run(commit=True)

    vano.refresh_from_db()
    assert vano.pk is not None
