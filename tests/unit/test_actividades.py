"""Unit tests for actividades app."""

import pytest
from datetime import date, timedelta
from decimal import Decimal

from apps.actividades.models import TipoActividad, ProgramacionMensual, Actividad


@pytest.mark.django_db
class TestTipoActividadModel:
    """Tests for TipoActividad model."""

    def test_create_tipo_actividad(self):
        """Test creating an activity type."""
        tipo = TipoActividad.objects.create(
            codigo="PODA-001",
            nombre="Poda de vegetación",
            categoria=TipoActividad.Categoria.PODA,
            requiere_fotos_antes=True,
            requiere_fotos_durante=True,
            requiere_fotos_despues=True,
            min_fotos=3,
            tiempo_estimado_horas=Decimal("4.00"),
        )
        assert tipo.codigo == "PODA-001"
        assert tipo.categoria == "PODA"
        assert tipo.min_fotos == 3
        assert tipo.activo

    def test_tipo_actividad_str(self):
        """Test activity type string representation."""
        tipo = TipoActividad.objects.create(
            codigo="INSP-001",
            nombre="Inspección visual",
            categoria=TipoActividad.Categoria.INSPECCION,
        )
        assert str(tipo) == "INSP-001 - Inspección visual"

    def test_tipo_actividad_unique_codigo(self):
        """Test that codigo is unique."""
        TipoActividad.objects.create(
            codigo="UNIQUE-001",
            nombre="Primera actividad",
            categoria=TipoActividad.Categoria.OTRO,
        )
        with pytest.raises(Exception):
            TipoActividad.objects.create(
                codigo="UNIQUE-001",
                nombre="Segunda actividad",
                categoria=TipoActividad.Categoria.OTRO,
            )

    def test_campos_formulario_json(self):
        """Test JSON field for form configuration."""
        campos = {
            "fields": [
                {"name": "observaciones", "type": "text", "required": True},
                {"name": "metros_podados", "type": "number", "min": 0},
            ]
        }
        tipo = TipoActividad.objects.create(
            codigo="JSON-001",
            nombre="Actividad con formulario",
            categoria=TipoActividad.Categoria.PODA,
            campos_formulario=campos,
        )
        assert tipo.campos_formulario["fields"][0]["name"] == "observaciones"
        assert len(tipo.campos_formulario["fields"]) == 2


@pytest.mark.django_db
class TestProgramacionMensualModel:
    """Tests for ProgramacionMensual model."""

    def test_create_programacion(self):
        """Test creating monthly programming."""
        from tests.factories import LineaFactory

        linea = LineaFactory()
        prog = ProgramacionMensual.objects.create(
            anio=2025,
            mes=1,
            linea=linea,
            total_actividades=50,
        )
        assert prog.anio == 2025
        assert prog.mes == 1
        assert prog.total_actividades == 50
        assert not prog.aprobado

    def test_programacion_str(self):
        """Test programming string representation."""
        from tests.factories import LineaFactory

        linea = LineaFactory(codigo="LT-TEST")
        prog = ProgramacionMensual.objects.create(
            anio=2025,
            mes=6,
            linea=linea,
        )
        assert "LT-TEST" in str(prog)
        assert "6/2025" in str(prog)

    def test_programacion_unique_together(self):
        """Test that anio, mes, linea must be unique together."""
        from tests.factories import LineaFactory

        linea = LineaFactory()
        ProgramacionMensual.objects.create(
            anio=2025,
            mes=3,
            linea=linea,
        )
        with pytest.raises(Exception):
            ProgramacionMensual.objects.create(
                anio=2025,
                mes=3,
                linea=linea,
            )


@pytest.mark.django_db
class TestActividadModel:
    """Tests for Actividad model."""

    def test_create_actividad(self):
        """Test creating an activity."""
        from tests.factories import ActividadFactory

        actividad = ActividadFactory()
        assert actividad.estado == Actividad.Estado.PENDIENTE
        assert actividad.prioridad == Actividad.Prioridad.NORMAL
        assert actividad.linea is not None
        assert actividad.torre is not None
        assert actividad.tipo_actividad is not None

    def test_actividad_str(self):
        """Test activity string representation."""
        from tests.factories import ActividadFactory

        actividad = ActividadFactory()
        str_repr = str(actividad)
        assert actividad.tipo_actividad.nombre in str_repr
        assert str(actividad.torre) in str_repr  # __str__ normaliza T-001→T-1 (#100)

    def test_fecha_efectiva_sin_reprogramacion(self):
        """Test effective date without rescheduling."""
        from tests.factories import ActividadFactory

        actividad = ActividadFactory(fecha_programada=date(2025, 6, 15))
        assert actividad.fecha_efectiva == date(2025, 6, 15)

    def test_fecha_efectiva_con_reprogramacion(self):
        """Test effective date with rescheduling."""
        from tests.factories import ActividadFactory

        actividad = ActividadFactory(
            fecha_programada=date(2025, 6, 15),
            fecha_reprogramada=date(2025, 6, 20),
        )
        assert actividad.fecha_efectiva == date(2025, 6, 20)

    def test_esta_atrasada_true(self):
        """Test overdue detection."""
        from tests.factories import ActividadFactory

        actividad = ActividadFactory(
            fecha_programada=date.today() - timedelta(days=5),
            estado=Actividad.Estado.PENDIENTE,
        )
        assert actividad.esta_atrasada

    def test_esta_atrasada_false_completada(self):
        """Test completed activities are not overdue."""
        from tests.factories import ActividadFactory

        actividad = ActividadFactory(
            fecha_programada=date.today() - timedelta(days=5),
            estado=Actividad.Estado.COMPLETADA,
        )
        assert not actividad.esta_atrasada

    def test_iniciar_actividad(self):
        """Test starting an activity."""
        from tests.factories import ActividadFactory, LinieroFactory

        actividad = ActividadFactory(estado=Actividad.Estado.PENDIENTE)
        usuario = LinieroFactory()
        actividad.iniciar(usuario)

        actividad.refresh_from_db()
        assert actividad.estado == Actividad.Estado.EN_CURSO

    def test_completar_actividad(self):
        """Test completing an activity."""
        from tests.factories import ActividadFactory

        actividad = ActividadFactory(estado=Actividad.Estado.EN_CURSO)
        actividad.completar()

        actividad.refresh_from_db()
        assert actividad.estado == Actividad.Estado.COMPLETADA

    def test_cancelar_actividad(self):
        """Test canceling an activity."""
        from tests.factories import ActividadFactory

        actividad = ActividadFactory(estado=Actividad.Estado.PENDIENTE)
        actividad.cancelar("Condiciones climáticas adversas")

        actividad.refresh_from_db()
        assert actividad.estado == Actividad.Estado.CANCELADA
        assert actividad.motivo_cancelacion == "Condiciones climáticas adversas"

    def test_reprogramar_actividad(self):
        """Test rescheduling an activity."""
        from tests.factories import ActividadFactory

        nueva_fecha = date.today() + timedelta(days=7)
        actividad = ActividadFactory(estado=Actividad.Estado.PENDIENTE)
        actividad.reprogramar(nueva_fecha, "Falta de personal")

        actividad.refresh_from_db()
        assert actividad.estado == Actividad.Estado.REPROGRAMADA
        assert actividad.fecha_reprogramada == nueva_fecha
        assert actividad.motivo_reprogramacion == "Falta de personal"


@pytest.mark.django_db
class TestActividadesFactory:
    """Tests for actividades factories."""

    def test_tipo_actividad_factory(self):
        """Test TipoActividadFactory."""
        from tests.factories import TipoActividadFactory

        tipo = TipoActividadFactory()
        assert tipo.codigo
        assert tipo.nombre
        assert tipo.categoria
        assert tipo.activo

    def test_programacion_mensual_factory(self):
        """Test ProgramacionMensualFactory."""
        from tests.factories import ProgramacionMensualFactory

        prog = ProgramacionMensualFactory()
        assert prog.anio
        assert prog.mes
        assert prog.linea

    def test_actividad_factory(self):
        """Test ActividadFactory."""
        from tests.factories import ActividadFactory

        actividad = ActividadFactory()
        assert actividad.linea
        assert actividad.torre
        assert actividad.tipo_actividad
        assert actividad.cuadrilla
        assert actividad.fecha_programada

    def test_actividad_en_curso_factory(self):
        """Test ActividadEnCursoFactory."""
        from tests.factories import ActividadEnCursoFactory

        actividad = ActividadEnCursoFactory()
        assert actividad.estado == Actividad.Estado.EN_CURSO

    def test_actividad_completada_factory(self):
        """Test ActividadCompletadaFactory."""
        from tests.factories import ActividadCompletadaFactory

        actividad = ActividadCompletadaFactory()
        assert actividad.estado == Actividad.Estado.COMPLETADA
        assert actividad.fecha_programada <= date.today()
