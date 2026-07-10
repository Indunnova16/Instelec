"""Integration tests for activity workflow."""

import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone

from apps.actividades.models import Actividad


@pytest.mark.django_db
class TestFlujoActividadRegistroCampo:
    """Integration tests for Activity -> Field Record flow."""

    def test_iniciar_actividad_crea_registro_campo(self):
        """Starting an activity should allow creating field records."""
        from tests.factories import ActividadFactory, LinieroFactory, RegistroCampoFactory

        actividad = ActividadFactory(estado=Actividad.Estado.PENDIENTE)
        liniero = LinieroFactory()

        # Start activity
        actividad.iniciar(liniero)
        actividad.refresh_from_db()
        assert actividad.estado == Actividad.Estado.EN_CURSO

        # Create field record
        registro = RegistroCampoFactory(
            actividad=actividad,
            usuario=liniero,
        )
        assert registro.actividad == actividad
        assert registro.usuario == liniero

    def test_completar_actividad_con_registro_campo(self):
        """Completing an activity should work when field record exists."""
        from tests.factories import (
            ActividadEnCursoFactory,
            RegistroCampoCompletadoFactory,
            EvidenciaAntesFactory,
            EvidenciaDuranteFactory,
            EvidenciaDespuesFactory,
        )

        actividad = ActividadEnCursoFactory()

        # Create complete field record with all evidence
        registro = RegistroCampoCompletadoFactory(actividad=actividad)
        EvidenciaAntesFactory(registro_campo=registro)
        EvidenciaDuranteFactory(registro_campo=registro)
        EvidenciaDespuesFactory(registro_campo=registro)

        # Complete activity
        actividad.completar()
        actividad.refresh_from_db()

        assert actividad.estado == Actividad.Estado.COMPLETADA
        assert registro.sincronizado

    def test_actividad_cuadrilla_asignacion(self):
        """Activity should be assigned to a crew with members."""
        from tests.factories import (
            ActividadFactory,
            CuadrillaFactory,
            CuadrillaMiembroFactory,
            LinieroFactory,
        )

        # Create crew with members
        cuadrilla = CuadrillaFactory()
        supervisor = LinieroFactory()
        liniero1 = LinieroFactory()
        liniero2 = LinieroFactory()

        CuadrillaMiembroFactory(cuadrilla=cuadrilla, usuario=supervisor, rol_cuadrilla_id='SUPERVISOR')
        CuadrillaMiembroFactory(cuadrilla=cuadrilla, usuario=liniero1, rol_cuadrilla_id='LINIERO_I')
        CuadrillaMiembroFactory(cuadrilla=cuadrilla, usuario=liniero2, rol_cuadrilla_id='LINIERO_I')

        # Create activity assigned to crew
        actividad = ActividadFactory(cuadrilla=cuadrilla)

        assert actividad.cuadrilla == cuadrilla
        assert actividad.cuadrilla.total_miembros == 3


@pytest.mark.django_db
class TestFlujoActividadTorre:
    """Integration tests for Activity -> Tower flow."""

    def test_actividad_pertenece_a_torre_de_linea(self):
        """Activity should be linked to a tower that belongs to the same line."""
        from tests.factories import LineaFactory, TorreFactory, ActividadFactory

        linea = LineaFactory()
        torre = TorreFactory(linea=linea)

        actividad = ActividadFactory(linea=linea, torre=torre)

        assert actividad.linea == torre.linea
        assert actividad.torre.linea == actividad.linea

    def test_multiples_actividades_por_torre(self):
        """Multiple activities can be scheduled for the same tower."""
        from tests.factories import LineaFactory, TorreFactory, ActividadFactory

        linea = LineaFactory()
        torre = TorreFactory(linea=linea)

        # Create multiple activities for same tower
        actividades = []
        for i in range(3):
            actividad = ActividadFactory(
                linea=linea,
                torre=torre,
                fecha_programada=date.today() + timedelta(days=i * 7),
            )
            actividades.append(actividad)

        assert torre.actividades.count() == 3


@pytest.mark.django_db
class TestFlujoProgramacionActividad:
    """Integration tests for Monthly Programming -> Activity flow."""

    def test_actividades_vinculadas_a_programacion(self):
        """Activities should be linked to monthly programming."""
        from tests.factories import (
            LineaFactory,
            ProgramacionMensualFactory,
            ActividadFactory,
        )

        linea = LineaFactory()
        programacion = ProgramacionMensualFactory(
            linea=linea,
            anio=2025,
            mes=6,
        )

        # Create activities for this programming
        for _ in range(10):
            ActividadFactory(
                linea=linea,
                programacion=programacion,
                fecha_programada=date(2025, 6, 15),
            )

        assert programacion.actividades.count() == 10

    def test_aprobar_programacion(self):
        """Approving programming should update related activities."""
        from tests.factories import (
            LineaFactory,
            ProgramacionMensualFactory,
            CoordinadorFactory,
        )

        linea = LineaFactory()
        coordinador = CoordinadorFactory()
        programacion = ProgramacionMensualFactory(linea=linea, aprobado=False)

        # Approve programming
        programacion.aprobado = True
        programacion.aprobado_por = coordinador
        programacion.fecha_aprobacion = timezone.now()
        programacion.save()

        programacion.refresh_from_db()
        assert programacion.aprobado
        assert programacion.aprobado_por == coordinador


@pytest.mark.django_db
class TestFlujoEvidenciasRegistro:
    """Integration tests for Evidence -> Field Record flow."""

    def test_registro_con_todas_evidencias(self):
        """Field record should track all evidence types."""
        from tests.factories import (
            RegistroCampoFactory,
            EvidenciaAntesFactory,
            EvidenciaDuranteFactory,
            EvidenciaDespuesFactory,
            TipoActividadFactory,
            ActividadEnCursoFactory,
        )

        tipo = TipoActividadFactory(
            requiere_fotos_antes=True,
            requiere_fotos_durante=True,
            requiere_fotos_despues=True,
        )
        actividad = ActividadEnCursoFactory(tipo_actividad=tipo)
        registro = RegistroCampoFactory(actividad=actividad)

        # Add all evidence types
        EvidenciaAntesFactory.create_batch(2, registro_campo=registro)
        EvidenciaDuranteFactory.create_batch(3, registro_campo=registro)
        EvidenciaDespuesFactory.create_batch(2, registro_campo=registro)

        assert registro.total_evidencias == 7
        assert registro.evidencias.filter(tipo='ANTES').count() == 2
        assert registro.evidencias.filter(tipo='DURANTE').count() == 3
        assert registro.evidencias.filter(tipo='DESPUES').count() == 2
        assert registro.evidencias_completas

    def test_evidencia_con_validacion_ia(self):
        """Evidence should store AI validation results."""
        from tests.factories import EvidenciaFactory

        validacion = {
            "nitidez": 0.92,
            "iluminacion": 0.88,
            "valida": True,
            "confianza": 0.95,
            "mensaje": "Imagen válida",
        }
        evidencia = EvidenciaFactory(validacion_ia=validacion)

        assert evidencia.es_valida
        assert evidencia.puntaje_nitidez == 0.92
        assert evidencia.puntaje_iluminacion == 0.88
