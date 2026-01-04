"""Unit tests for lineas app."""

import pytest
from decimal import Decimal
from django.contrib.gis.geos import Point, Polygon

from apps.lineas.models import Linea, Torre, PoligonoServidumbre


@pytest.mark.django_db
class TestLineaModel:
    """Tests for Linea model."""

    def test_create_linea(self):
        """Test creating a transmission line."""
        linea = Linea.objects.create(
            codigo="LT-TEST-001",
            nombre="Línea de prueba",
            cliente="TRANSELCA",
            longitud_km=Decimal("150.50"),
            tension_kv=220,
        )
        assert linea.codigo == "LT-TEST-001"
        assert linea.cliente == "TRANSELCA"
        assert linea.tension_kv == 220
        assert linea.activa

    def test_linea_str(self):
        """Test linea string representation."""
        linea = Linea.objects.create(
            codigo="LT-STR-001",
            nombre="Línea String Test",
            cliente="INTERCOLOMBIA",
        )
        assert str(linea) == "LT-STR-001 - Línea String Test"

    def test_linea_ordering(self):
        """Test lineas are ordered by codigo."""
        Linea.objects.create(codigo="LT-003", nombre="Tercera", cliente="TRANSELCA")
        Linea.objects.create(codigo="LT-001", nombre="Primera", cliente="TRANSELCA")
        Linea.objects.create(codigo="LT-002", nombre="Segunda", cliente="TRANSELCA")

        lineas = list(Linea.objects.values_list("codigo", flat=True))
        assert lineas == ["LT-001", "LT-002", "LT-003"]


@pytest.mark.django_db
class TestTorreModel:
    """Tests for Torre model."""

    def test_create_torre(self):
        """Test creating a tower."""
        linea = Linea.objects.create(
            codigo="LT-TORRE-001",
            nombre="Línea para torres",
            cliente="TRANSELCA",
        )
        torre = Torre.objects.create(
            linea=linea,
            numero="T-001",
            tipo="SUSPENSION",
            latitud=Decimal("10.12345678"),
            longitud=Decimal("-74.87654321"),
            altitud=Decimal("150.50"),
        )
        assert torre.numero == "T-001"
        assert torre.tipo == "SUSPENSION"
        assert torre.linea == linea

    def test_torre_geometry_auto_created(self):
        """Test that geometry is automatically created from lat/lon."""
        linea = Linea.objects.create(
            codigo="LT-GEO-001",
            nombre="Línea geometría",
            cliente="TRANSELCA",
        )
        torre = Torre.objects.create(
            linea=linea,
            numero="T-GEO-001",
            latitud=Decimal("10.00000000"),
            longitud=Decimal("-75.00000000"),
        )
        assert torre.geometria is not None
        assert isinstance(torre.geometria, Point)
        assert torre.geometria.x == -75.0
        assert torre.geometria.y == 10.0

    def test_torre_unique_together(self):
        """Test that linea + numero must be unique."""
        linea = Linea.objects.create(
            codigo="LT-UNIQUE-001",
            nombre="Línea unique",
            cliente="TRANSELCA",
        )
        Torre.objects.create(
            linea=linea,
            numero="T-001",
            latitud=Decimal("10.0"),
            longitud=Decimal("-75.0"),
        )
        with pytest.raises(Exception):  # IntegrityError
            Torre.objects.create(
                linea=linea,
                numero="T-001",
                latitud=Decimal("10.1"),
                longitud=Decimal("-75.1"),
            )


@pytest.mark.django_db
class TestPoligonoServidumbreModel:
    """Tests for PoligonoServidumbre model."""

    def test_create_poligono(self):
        """Test creating a polygon."""
        linea = Linea.objects.create(
            codigo="LT-POLI-001",
            nombre="Línea polígono",
            cliente="TRANSELCA",
        )
        polygon = Polygon((
            (-75.0, 10.0),
            (-74.99, 10.0),
            (-74.99, 10.01),
            (-75.0, 10.01),
            (-75.0, 10.0),
        ), srid=4326)

        poligono = PoligonoServidumbre.objects.create(
            linea=linea,
            nombre="Servidumbre test",
            geometria=polygon,
        )
        assert poligono.geometria is not None
        # Area is auto-calculated from geometry in save() method
        assert poligono.area_hectareas is not None
        assert poligono.area_hectareas > 0

    def test_punto_dentro(self):
        """Test point containment check."""
        linea = Linea.objects.create(
            codigo="LT-DENTRO-001",
            nombre="Línea punto dentro",
            cliente="TRANSELCA",
        )
        polygon = Polygon((
            (-75.0, 10.0),
            (-74.99, 10.0),
            (-74.99, 10.01),
            (-75.0, 10.01),
            (-75.0, 10.0),
        ), srid=4326)

        poligono = PoligonoServidumbre.objects.create(
            linea=linea,
            geometria=polygon,
        )

        # Point inside
        assert poligono.punto_dentro(10.005, -74.995)

        # Point outside
        assert not poligono.punto_dentro(10.02, -74.995)


@pytest.mark.django_db
class TestLineasFactory:
    """Tests for lineas factories."""

    def test_linea_factory(self):
        """Test LineaFactory creates valid lineas."""
        from tests.factories import LineaFactory

        linea = LineaFactory()
        assert linea.codigo
        assert linea.nombre
        assert linea.cliente in ["TRANSELCA", "INTERCOLOMBIA"]

    def test_torre_factory(self):
        """Test TorreFactory creates valid torres."""
        from tests.factories import TorreFactory

        torre = TorreFactory()
        assert torre.numero
        assert torre.linea is not None
        assert torre.latitud is not None
        assert torre.longitud is not None
