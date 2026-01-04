"""Integration tests for KPI indicators."""

import pytest
from decimal import Decimal
from datetime import date, datetime, timedelta
from django.utils import timezone

from apps.indicadores.calculators import (
    calcular_gestion_mantenimiento,
    calcular_ejecucion_mantenimiento,
    calcular_gestion_ambiental,
    calcular_calidad_informacion,
    calcular_seguridad_industrial,
    calcular_cumplimiento_cronograma,
    calcular_indice_global,
    calcular_todos_indicadores,
)


@pytest.mark.django_db
class TestGestionMantenimiento:
    """Tests for maintenance management indicator."""

    def test_no_activities_returns_zero(self):
        """When no activities exist, should return 0."""
        from tests.factories import LineaFactory

        linea = LineaFactory()
        ejecutadas, total, valor = calcular_gestion_mantenimiento(
            linea.id, 2024, 1
        )

        assert ejecutadas == Decimal('0')
        assert total == Decimal('0')
        assert valor == Decimal('0')

    def test_all_activities_completed(self):
        """When all activities are completed, should return 100%."""
        from tests.factories import LineaFactory, ActividadFactory

        linea = LineaFactory()
        # Create 5 completed activities
        for _ in range(5):
            ActividadFactory(
                linea=linea,
                fecha_programada=date(2024, 1, 15),
                estado='COMPLETADA'
            )

        ejecutadas, total, valor = calcular_gestion_mantenimiento(
            linea.id, 2024, 1
        )

        assert ejecutadas == Decimal('5')
        assert total == Decimal('5')
        assert valor == Decimal('100')

    def test_partial_completion(self):
        """When some activities are pending, should calculate correct %."""
        from tests.factories import LineaFactory, ActividadFactory

        linea = LineaFactory()
        # 3 completed, 2 pending
        for _ in range(3):
            ActividadFactory(
                linea=linea,
                fecha_programada=date(2024, 1, 15),
                estado='COMPLETADA'
            )
        for _ in range(2):
            ActividadFactory(
                linea=linea,
                fecha_programada=date(2024, 1, 15),
                estado='PENDIENTE'
            )

        ejecutadas, total, valor = calcular_gestion_mantenimiento(
            linea.id, 2024, 1
        )

        assert ejecutadas == Decimal('3')
        assert total == Decimal('5')
        assert valor == Decimal('60')  # 3/5 * 100


@pytest.mark.django_db
class TestEjecucionMantenimiento:
    """Tests for maintenance execution indicator."""

    def test_no_completed_activities_returns_zero(self):
        """When no activities are completed, should return 0."""
        from tests.factories import LineaFactory

        linea = LineaFactory()
        a_tiempo, total, valor = calcular_ejecucion_mantenimiento(
            linea.id, 2024, 1
        )

        assert a_tiempo == Decimal('0')
        assert total == Decimal('0')
        assert valor == Decimal('0')

    def test_activities_completed_on_time(self):
        """Activities completed on scheduled date should count."""
        from tests.factories import LineaFactory, ActividadFactory, RegistroCampoFactory

        linea = LineaFactory()
        actividad = ActividadFactory(
            linea=linea,
            fecha_programada=date(2024, 1, 15),
            estado='COMPLETADA'
        )
        # Create field record that finished on schedule
        RegistroCampoFactory(
            actividad=actividad,
            fecha_inicio=timezone.make_aware(datetime(2024, 1, 15, 8, 0)),
            fecha_fin=timezone.make_aware(datetime(2024, 1, 15, 16, 0)),
            sincronizado=True
        )

        a_tiempo, total, valor = calcular_ejecucion_mantenimiento(
            linea.id, 2024, 1
        )

        assert a_tiempo == Decimal('1')
        assert total == Decimal('1')
        assert valor == Decimal('100')


@pytest.mark.django_db
class TestCalidadInformacion:
    """Tests for information quality indicator."""

    def test_no_records_returns_zero(self):
        """When no records exist, should return 0."""
        from tests.factories import LineaFactory

        linea = LineaFactory()
        completos, total, valor = calcular_calidad_informacion(
            linea.id, 2024, 1
        )

        assert completos == Decimal('0')
        assert total == Decimal('0')
        assert valor == Decimal('0')

    def test_complete_records(self):
        """Records with complete evidence should count."""
        from tests.factories import (
            LineaFactory, ActividadFactory, RegistroCampoFactory
        )

        linea = LineaFactory()
        actividad = ActividadFactory(
            linea=linea,
            fecha_programada=date(2024, 1, 15),
            estado='COMPLETADA'
        )
        # Complete record
        RegistroCampoFactory(
            actividad=actividad,
            fecha_inicio=timezone.make_aware(datetime(2024, 1, 15, 8, 0)),
            sincronizado=True,
            evidencias_completas=True,
            datos_formulario={'campo1': 'valor1'}
        )

        completos, total, valor = calcular_calidad_informacion(
            linea.id, 2024, 1
        )

        assert completos == Decimal('1')
        assert total == Decimal('1')
        assert valor == Decimal('100')


@pytest.mark.django_db
class TestSeguridadIndustrial:
    """Tests for industrial safety indicator."""

    def test_no_accidents_full_score(self):
        """When no accidents, should return 100%."""
        from tests.factories import LineaFactory, ActividadFactory, RegistroCampoFactory

        linea = LineaFactory()
        actividad = ActividadFactory(
            linea=linea,
            fecha_programada=date(2024, 1, 15),
            estado='COMPLETADA'
        )
        # Record without accidents
        RegistroCampoFactory(
            actividad=actividad,
            fecha_inicio=timezone.make_aware(datetime(2024, 1, 15, 8, 0)),
            datos_formulario={'accidente_reportado': False}
        )

        dias_sin, dias_total, valor = calcular_seguridad_industrial(
            linea.id, 2024, 1
        )

        # January 2024 has 23 working days (weekdays)
        assert dias_total == Decimal('23')
        assert valor == Decimal('100')


@pytest.mark.django_db
class TestCumplimientoCronograma:
    """Tests for schedule compliance indicator."""

    def test_activities_started_on_time(self):
        """Activities started on scheduled date should count."""
        from tests.factories import LineaFactory, ActividadFactory, RegistroCampoFactory

        linea = LineaFactory()
        actividad = ActividadFactory(
            linea=linea,
            fecha_programada=date(2024, 1, 15),
            estado='COMPLETADA'
        )
        # Started on schedule
        RegistroCampoFactory(
            actividad=actividad,
            fecha_inicio=timezone.make_aware(datetime(2024, 1, 15, 8, 0)),
        )

        a_tiempo, total, valor = calcular_cumplimiento_cronograma(
            linea.id, 2024, 1
        )

        assert a_tiempo == Decimal('1')
        assert total == Decimal('1')
        assert valor == Decimal('100')


@pytest.mark.django_db
class TestIndiceGlobal:
    """Tests for global performance index."""

    def test_calculates_weighted_average(self):
        """Should calculate weighted average of all indicators."""
        from tests.factories import LineaFactory

        linea = LineaFactory()

        indice, detalles = calcular_indice_global(linea.id, 2024, 1)

        # Should return details for all categories
        assert 'GESTION' in detalles
        assert 'EJECUCION' in detalles
        assert 'AMBIENTAL' in detalles
        assert 'CALIDAD' in detalles
        assert 'SEGURIDAD' in detalles
        assert 'CRONOGRAMA' in detalles

        # Each detail should have valor, peso, contribucion
        for cat, data in detalles.items():
            assert 'valor' in data
            assert 'peso' in data
            assert 'contribucion' in data


@pytest.mark.django_db
class TestCalcularTodosIndicadores:
    """Tests for calculating and saving all indicators."""

    def test_saves_to_database(self):
        """Should save measurements to database."""
        from tests.factories import LineaFactory
        from apps.indicadores.models import Indicador, MedicionIndicador

        linea = LineaFactory()

        # Create active indicators
        Indicador.objects.create(
            codigo='KPI-001',
            nombre='Gestión',
            categoria='GESTION',
            meta=Decimal('90'),
            umbral_alerta=Decimal('80'),
            activo=True
        )

        resultados = calcular_todos_indicadores(linea.id, 2024, 1)

        # Should return results
        assert len(resultados) >= 1

        # Should have saved to database
        mediciones = MedicionIndicador.objects.filter(
            linea=linea,
            anio=2024,
            mes=1
        )
        assert mediciones.exists()
