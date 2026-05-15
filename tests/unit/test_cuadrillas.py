"""Unit tests for cuadrillas app."""

import pytest
from datetime import date, timedelta
from decimal import Decimal

from apps.cuadrillas.models import Vehiculo, Cuadrilla, CuadrillaMiembro, TrackingUbicacion


@pytest.mark.django_db
class TestVehiculoModel:
    """Tests for Vehiculo model."""

    def test_create_vehiculo(self):
        """Test creating a vehicle."""
        vehiculo = Vehiculo.objects.create(
            placa="ABC-123",
            tipo=Vehiculo.TipoVehiculo.CAMIONETA,
            marca="Toyota",
            modelo="Hilux",
            ano=2023,
            capacidad_personas=5,
            costo_dia=Decimal("180000.00"),
        )
        assert vehiculo.placa == "ABC-123"
        assert vehiculo.tipo == "CAMIONETA"
        assert vehiculo.costo_dia == Decimal("180000.00")
        assert vehiculo.activo

    def test_vehiculo_str(self):
        """Test vehicle string representation."""
        vehiculo = Vehiculo.objects.create(
            placa="XYZ-789",
            tipo=Vehiculo.TipoVehiculo.CAMION,
            marca="Ford",
            modelo="F-150",
        )
        assert "XYZ-789" in str(vehiculo)
        assert "Ford" in str(vehiculo)
        assert "F-150" in str(vehiculo)

    def test_vehiculo_unique_placa(self):
        """Test that placa is unique."""
        Vehiculo.objects.create(
            placa="UNIQUE-01",
            tipo=Vehiculo.TipoVehiculo.CAMIONETA,
        )
        with pytest.raises(Exception):
            Vehiculo.objects.create(
                placa="UNIQUE-01",
                tipo=Vehiculo.TipoVehiculo.CAMION,
            )

    def test_tipos_vehiculo(self):
        """Test all vehicle types."""
        tipos = [
            Vehiculo.TipoVehiculo.CAMIONETA,
            Vehiculo.TipoVehiculo.CAMION,
            Vehiculo.TipoVehiculo.GRUA,
            Vehiculo.TipoVehiculo.OTRO,
        ]
        for i, tipo in enumerate(tipos):
            vehiculo = Vehiculo.objects.create(
                placa=f"TIPO-{i:03d}",
                tipo=tipo,
            )
            assert vehiculo.tipo == tipo


@pytest.mark.django_db
class TestCuadrillaModel:
    """Tests for Cuadrilla model."""

    def test_create_cuadrilla(self):
        """Test creating a crew."""
        from tests.factories import CuadrillaFactory

        cuadrilla = CuadrillaFactory()
        assert cuadrilla.codigo
        assert cuadrilla.nombre
        assert cuadrilla.activa

    def test_cuadrilla_str(self):
        """Test crew string representation."""
        from tests.factories import CuadrillaFactory

        cuadrilla = CuadrillaFactory(codigo="CUA-001", nombre="Cuadrilla Norte")
        assert "CUA-001" in str(cuadrilla)
        assert "Cuadrilla Norte" in str(cuadrilla)

    def test_cuadrilla_unique_codigo(self):
        """Test that codigo is unique."""
        from tests.factories import CuadrillaFactory

        CuadrillaFactory(codigo="UNIQUE-CUA")
        with pytest.raises(Exception):
            CuadrillaFactory(codigo="UNIQUE-CUA")

    def test_miembros_activos(self):
        """Test active members property."""
        from tests.factories import CuadrillaFactory, CuadrillaMiembroFactory, LinieroFactory

        cuadrilla = CuadrillaFactory()

        # Create active members
        for _ in range(3):
            CuadrillaMiembroFactory(cuadrilla=cuadrilla, activo=True)

        # Create inactive member
        CuadrillaMiembroFactory(cuadrilla=cuadrilla, activo=False)

        assert cuadrilla.miembros_activos.count() == 3

    def test_total_miembros(self):
        """Test total members property."""
        from tests.factories import CuadrillaFactory, CuadrillaMiembroFactory

        cuadrilla = CuadrillaFactory()
        CuadrillaMiembroFactory.create_batch(4, cuadrilla=cuadrilla, activo=True)
        CuadrillaMiembroFactory(cuadrilla=cuadrilla, activo=False)

        assert cuadrilla.total_miembros == 4


@pytest.mark.django_db
class TestCuadrillaMiembroModel:
    """Tests for CuadrillaMiembro model."""

    def test_create_cuadrilla_miembro(self):
        """Test creating a crew member."""
        from tests.factories import CuadrillaMiembroFactory

        miembro = CuadrillaMiembroFactory()
        assert miembro.cuadrilla
        assert miembro.usuario
        assert miembro.rol_cuadrilla
        assert miembro.fecha_inicio
        assert miembro.activo

    def test_cuadrilla_miembro_str(self):
        """Test crew member string representation."""
        from tests.factories import CuadrillaMiembroFactory

        miembro = CuadrillaMiembroFactory()
        str_repr = str(miembro)
        assert miembro.cuadrilla.codigo in str_repr

    def test_roles_cuadrilla(self):
        """Test all crew roles."""
        from tests.factories import CuadrillaMiembroFactory

        roles = [
            CuadrillaMiembro.RolCuadrilla.SUPERVISOR,
            CuadrillaMiembro.RolCuadrilla.LINIERO_I,
            CuadrillaMiembro.RolCuadrilla.LINIERO_II,
            CuadrillaMiembro.RolCuadrilla.AYUDANTE,
        ]
        for rol in roles:
            miembro = CuadrillaMiembroFactory(rol_cuadrilla=rol)
            assert miembro.rol_cuadrilla == rol

    def test_miembro_con_fecha_fin(self):
        """Test crew member with end date."""
        from tests.factories import CuadrillaMiembroFactory

        fecha_inicio = date.today() - timedelta(days=30)
        fecha_fin = date.today() - timedelta(days=5)

        miembro = CuadrillaMiembroFactory(
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            activo=False,
        )
        assert miembro.fecha_fin == fecha_fin
        assert not miembro.activo


@pytest.mark.django_db
class TestTrackingUbicacionModel:
    """Tests for TrackingUbicacion model."""

    def test_create_tracking(self):
        """Test creating location tracking."""
        from tests.factories import CuadrillaFactory, LinieroFactory

        cuadrilla = CuadrillaFactory()
        usuario = LinieroFactory()

        tracking = TrackingUbicacion.objects.create(
            cuadrilla=cuadrilla,
            usuario=usuario,
            latitud=Decimal("10.12345678"),
            longitud=Decimal("-74.87654321"),
            precision_metros=Decimal("15.50"),
            velocidad=Decimal("45.00"),
            bateria=85,
        )
        assert tracking.latitud == Decimal("10.12345678")
        assert tracking.longitud == Decimal("-74.87654321")
        assert tracking.precision_metros == Decimal("15.50")
        assert tracking.velocidad == Decimal("45.00")
        assert tracking.bateria == 85

    def test_tracking_str(self):
        """Test tracking string representation."""
        from tests.factories import CuadrillaFactory, LinieroFactory

        cuadrilla = CuadrillaFactory(codigo="CUA-TRACK")
        usuario = LinieroFactory()

        tracking = TrackingUbicacion.objects.create(
            cuadrilla=cuadrilla,
            usuario=usuario,
            latitud=Decimal("10.0"),
            longitud=Decimal("-74.0"),
        )
        assert "CUA-TRACK" in str(tracking)


@pytest.mark.django_db
class TestCuadrillasFactories:
    """Tests for cuadrillas factories."""

    def test_vehiculo_factory(self):
        """Test VehiculoFactory."""
        from tests.factories import VehiculoFactory

        vehiculo = VehiculoFactory()
        assert vehiculo.placa
        assert vehiculo.tipo
        assert vehiculo.activo

    def test_cuadrilla_factory(self):
        """Test CuadrillaFactory."""
        from tests.factories import CuadrillaFactory

        cuadrilla = CuadrillaFactory()
        assert cuadrilla.codigo
        assert cuadrilla.nombre
        assert cuadrilla.activa

    def test_cuadrilla_miembro_factory(self):
        """Test CuadrillaMiembroFactory."""
        from tests.factories import CuadrillaMiembroFactory

        miembro = CuadrillaMiembroFactory()
        assert miembro.cuadrilla
        assert miembro.usuario
        assert miembro.rol_cuadrilla
        assert miembro.fecha_inicio
