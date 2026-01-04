"""Factories for cuadrillas app."""

import factory
from decimal import Decimal

from apps.cuadrillas.models import Vehiculo, Cuadrilla, CuadrillaMiembro
from tests.factories.usuarios import SupervisorFactory, LinieroFactory


class VehiculoFactory(factory.django.DjangoModelFactory):
    """Factory for Vehiculo model."""

    class Meta:
        model = Vehiculo

    placa = factory.Sequence(lambda n: f"ABC{n:03d}")
    tipo = factory.Iterator(["CAMIONETA", "CAMION", "MOTO"])
    marca = factory.Iterator(["Toyota", "Chevrolet", "Ford", "Nissan"])
    modelo = factory.Faker("year")
    capacidad_pasajeros = factory.LazyAttribute(
        lambda obj: 5 if obj.tipo == "CAMIONETA" else 2 if obj.tipo == "MOTO" else 10
    )
    costo_dia = factory.LazyFunction(
        lambda: Decimal(f"{factory.Faker._get_faker().random_int(150000, 500000)}.00")
    )
    activo = True


class CuadrillaFactory(factory.django.DjangoModelFactory):
    """Factory for Cuadrilla model."""

    class Meta:
        model = Cuadrilla

    codigo = factory.Sequence(lambda n: f"CUA-{n:03d}")
    nombre = factory.LazyAttribute(lambda obj: f"Cuadrilla {obj.codigo}")
    supervisor = factory.SubFactory(SupervisorFactory)
    vehiculo = factory.SubFactory(VehiculoFactory)
    activa = True


class CuadrillaMiembroFactory(factory.django.DjangoModelFactory):
    """Factory for CuadrillaMiembro model."""

    class Meta:
        model = CuadrillaMiembro

    cuadrilla = factory.SubFactory(CuadrillaFactory)
    usuario = factory.SubFactory(LinieroFactory)
    rol_cuadrilla = "liniero"
    activo = True
