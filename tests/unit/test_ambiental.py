"""Unit tests for ambiental app."""

import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.utils import timezone

from apps.ambiental.models import InformeAmbiental, PermisoServidumbre


@pytest.mark.django_db
class TestInformeAmbientalModel:
    """Tests for InformeAmbiental model."""

    def test_create_informe_ambiental(self):
        """Test creating an environmental report."""
        from tests.factories import InformeAmbientalFactory

        informe = InformeAmbientalFactory()
        assert informe.periodo_mes
        assert informe.periodo_anio
        assert informe.linea
        assert informe.estado == InformeAmbiental.Estado.BORRADOR

    def test_informe_ambiental_str(self):
        """Test report string representation."""
        from tests.factories import InformeAmbientalFactory, LineaFactory

        linea = LineaFactory(codigo="LT-ENV-001")
        informe = InformeAmbientalFactory(
            linea=linea,
            periodo_mes=6,
            periodo_anio=2025,
        )
        str_repr = str(informe)
        assert "LT-ENV-001" in str_repr
        assert "6/2025" in str_repr

    def test_informe_estados(self):
        """Test all report states."""
        from tests.factories import InformeAmbientalFactory

        estados = [
            InformeAmbiental.Estado.BORRADOR,
            InformeAmbiental.Estado.EN_REVISION,
            InformeAmbiental.Estado.APROBADO,
            InformeAmbiental.Estado.ENVIADO,
            InformeAmbiental.Estado.RECHAZADO,
        ]
        for estado in estados:
            informe = InformeAmbientalFactory(estado=estado)
            assert informe.estado == estado

    def test_informe_unique_together(self):
        """Test that periodo_mes, periodo_anio, linea must be unique together."""
        from tests.factories import InformeAmbientalFactory, LineaFactory

        linea = LineaFactory()
        InformeAmbientalFactory(
            linea=linea,
            periodo_mes=6,
            periodo_anio=2025,
        )
        with pytest.raises(Exception):
            InformeAmbientalFactory(
                linea=linea,
                periodo_mes=6,
                periodo_anio=2025,
            )

    def test_informe_datos_vegetacion(self):
        """Test vegetation data fields."""
        from tests.factories import InformeAmbientalFactory

        informe = InformeAmbientalFactory(
            total_actividades=45,
            total_podas=30,
            hectareas_intervenidas=Decimal("25.50"),
            m3_vegetacion=Decimal("150.75"),
        )
        assert informe.total_actividades == 45
        assert informe.total_podas == 30
        assert informe.hectareas_intervenidas == Decimal("25.50")
        assert informe.m3_vegetacion == Decimal("150.75")

    def test_informe_workflow_aprobacion(self):
        """Test approval workflow."""
        from tests.factories import (
            InformeAmbientalFactory,
            CoordinadorFactory,
        )

        elaborador = CoordinadorFactory()
        revisor = CoordinadorFactory()
        aprobador = CoordinadorFactory()

        informe = InformeAmbientalFactory(
            estado=InformeAmbiental.Estado.APROBADO,
            elaborado_por=elaborador,
            revisado_por=revisor,
            aprobado_por=aprobador,
            fecha_elaboracion=timezone.now() - timedelta(days=5),
            fecha_revision=timezone.now() - timedelta(days=3),
            fecha_aprobacion=timezone.now() - timedelta(days=1),
        )
        assert informe.elaborado_por == elaborador
        assert informe.revisado_por == revisor
        assert informe.aprobado_por == aprobador
        assert informe.fecha_aprobacion is not None


@pytest.mark.django_db
class TestPermisoServidumbreModel:
    """Tests for PermisoServidumbre model."""

    def test_create_permiso(self):
        """Test creating an easement permission."""
        from tests.factories import PermisoServidumbreFactory

        permiso = PermisoServidumbreFactory()
        assert permiso.torre
        assert permiso.propietario_nombre
        assert permiso.fecha_autorizacion
        assert permiso.actividades_autorizadas

    def test_permiso_str(self):
        """Test permission string representation."""
        from tests.factories import PermisoServidumbreFactory, TorreFactory

        torre = TorreFactory(numero="T-001")
        permiso = PermisoServidumbreFactory(
            torre=torre,
            propietario_nombre="Juan Pérez",
        )
        str_repr = str(permiso)
        assert "Juan Pérez" in str_repr
        assert "T-1" in str_repr  # __str__ normaliza T-001→T-1 (#100)

    def test_permiso_vigente_true(self):
        """Test valid permission detection."""
        from tests.factories import PermisoServidumbreFactory

        permiso = PermisoServidumbreFactory(
            fecha_autorizacion=date.today() - timedelta(days=30),
            fecha_vencimiento=date.today() + timedelta(days=335),
        )
        assert permiso.vigente

    def test_permiso_vigente_false(self):
        """Test expired permission detection."""
        from tests.factories import PermisoServidumbreFactory

        permiso = PermisoServidumbreFactory(
            fecha_autorizacion=date.today() - timedelta(days=400),
            fecha_vencimiento=date.today() - timedelta(days=35),
        )
        assert not permiso.vigente

    def test_permiso_vigente_sin_vencimiento(self):
        """Test permission without expiration is always valid."""
        from tests.factories import PermisoServidumbreFactory

        permiso = PermisoServidumbreFactory(
            fecha_autorizacion=date.today() - timedelta(days=1000),
            fecha_vencimiento=None,
        )
        assert permiso.vigente

    def test_permiso_datos_propietario(self):
        """Test property owner data."""
        from tests.factories import PermisoServidumbreFactory

        permiso = PermisoServidumbreFactory(
            propietario_nombre="María García",
            propietario_documento="12345678",
            propietario_telefono="+57 3101234567",
        )
        assert permiso.propietario_nombre == "María García"
        assert permiso.propietario_documento == "12345678"
        assert permiso.propietario_telefono == "+57 3101234567"

    def test_permiso_datos_predio(self):
        """Test property data."""
        from tests.factories import PermisoServidumbreFactory

        permiso = PermisoServidumbreFactory(
            predio_nombre="Finca El Roble",
            predio_matricula="050-123456",
        )
        assert permiso.predio_nombre == "Finca El Roble"
        assert permiso.predio_matricula == "050-123456"


@pytest.mark.django_db
class TestAmbientalFactories:
    """Tests for ambiental factories."""

    def test_informe_ambiental_factory(self):
        """Test InformeAmbientalFactory."""
        from tests.factories import InformeAmbientalFactory

        informe = InformeAmbientalFactory()
        assert informe.periodo_mes
        assert informe.periodo_anio
        assert informe.linea
        assert informe.estado == InformeAmbiental.Estado.BORRADOR

    def test_informe_ambiental_aprobado_factory(self):
        """Test InformeAmbientalAprobadoFactory."""
        from tests.factories import InformeAmbientalAprobadoFactory

        informe = InformeAmbientalAprobadoFactory()
        assert informe.estado == InformeAmbiental.Estado.APROBADO
        assert informe.aprobado_por
        assert informe.fecha_aprobacion

    def test_permiso_servidumbre_factory(self):
        """Test PermisoServidumbreFactory."""
        from tests.factories import PermisoServidumbreFactory

        permiso = PermisoServidumbreFactory()
        assert permiso.torre
        assert permiso.propietario_nombre
        assert permiso.fecha_autorizacion
        assert permiso.vigente

    def test_permiso_servidumbre_vencido_factory(self):
        """Test PermisoServidumbreVencidoFactory."""
        from tests.factories import PermisoServidumbreVencidoFactory

        permiso = PermisoServidumbreVencidoFactory()
        assert not permiso.vigente
