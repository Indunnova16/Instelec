"""Factories for lineas app."""

import factory
from decimal import Decimal

from apps.lineas.models import Linea, Torre, PoligonoServidumbre


class LineaFactory(factory.django.DjangoModelFactory):
    """Factory for Linea model."""

    class Meta:
        model = Linea

    codigo = factory.Sequence(lambda n: f"LT-{n:03d}")
    nombre = factory.Faker("sentence", nb_words=4, locale="es_CO")
    cliente = factory.Iterator(["TRANSELCA", "INTERCOLOMBIA"])
    longitud_km = factory.LazyFunction(lambda: Decimal(f"{factory.Faker._get_faker().random_int(10, 200)}.{factory.Faker._get_faker().random_int(0, 99):02d}"))
    tension_kv = factory.Iterator([110, 220, 500])
    activa = True


class TorreFactory(factory.django.DjangoModelFactory):
    """Factory for Torre model."""

    class Meta:
        model = Torre

    linea = factory.SubFactory(LineaFactory)
    numero = factory.Sequence(lambda n: f"T-{n:03d}")
    tipo = factory.Iterator(["SUSPENSION", "ANCLAJE", "TERMINAL"])
    latitud = factory.LazyFunction(
        lambda: Decimal(f"{factory.Faker._get_faker().pyfloat(min_value=4.0, max_value=12.0):.8f}")
    )
    longitud = factory.LazyFunction(
        lambda: Decimal(f"{factory.Faker._get_faker().pyfloat(min_value=-77.0, max_value=-72.0):.8f}")
    )
    altitud = factory.LazyFunction(
        lambda: Decimal(f"{factory.Faker._get_faker().random_int(100, 3000)}.{factory.Faker._get_faker().random_int(0, 99):02d}")
    )


class PoligonoServidumbreFactory(factory.django.DjangoModelFactory):
    """Factory for PoligonoServidumbre model."""

    class Meta:
        model = PoligonoServidumbre

    linea = factory.SubFactory(LineaFactory)
    torre = factory.SubFactory(TorreFactory)
    nombre = factory.Faker("sentence", nb_words=3, locale="es_CO")
    area_hectareas = factory.LazyFunction(
        lambda: Decimal(f"{factory.Faker._get_faker().random_int(1, 50)}.{factory.Faker._get_faker().random_int(0, 9999):04d}")
    )

    @factory.lazy_attribute
    def geometria(self):
        """Generate a simple polygon around Colombia coordinates."""
        from django.contrib.gis.geos import Polygon

        # Generate a small polygon in Colombia region
        base_lat = float(factory.Faker._get_faker().pyfloat(min_value=5.0, max_value=10.0))
        base_lon = float(factory.Faker._get_faker().pyfloat(min_value=-76.0, max_value=-73.0))
        size = 0.01  # ~1km

        return Polygon((
            (base_lon, base_lat),
            (base_lon + size, base_lat),
            (base_lon + size, base_lat + size),
            (base_lon, base_lat + size),
            (base_lon, base_lat),
        ), srid=4326)
