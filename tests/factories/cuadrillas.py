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
    tipo = factory.Iterator(["CAMIONETA", "CAMION", "GRUA"])
    marca = factory.Iterator(["Toyota", "Chevrolet", "Ford", "Nissan"])
    modelo = factory.Faker("year")
    capacidad_personas = factory.LazyAttribute(
        lambda obj: 5 if obj.tipo == "CAMIONETA" else 2 if obj.tipo == "GRUA" else 10
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
    """Factory for CuadrillaMiembro model.

    Issue #176 (Maestro 3, A6): `rol_cuadrilla` pasó de CharField+choices a
    FK(Cargo, to_field='codigo') (A3). `rol_cuadrilla_id` (attname del FK)
    reemplaza el `rol_cuadrilla` anterior -- factory_boy soporta asignar
    directo al attname. El default también se corrige de "LINIERO" (código
    que NUNCA existió en el enum viejo -- ni LINIERO_I ni LINIERO_II, solo
    "funcionaba" porque CharField+choices no validaba en `.create()`) a
    "LINIERO_I" (código real).

    `_create` se sobreescribe para garantizar que el `Cargo` referenciado
    exista ANTES de crear el `CuadrillaMiembro` -- con la FK real, Postgres
    exige la fila padre; como cada test corre en su propia transacción
    (rollback al final), no hay una siembra global persistente equivalente
    a la migración 0019_seed_cargos, así que se auto-siembra bajo demanda.
    """

    class Meta:
        model = CuadrillaMiembro

    cuadrilla = factory.SubFactory(CuadrillaFactory)
    usuario = factory.SubFactory(LinieroFactory)
    rol_cuadrilla_id = "LINIERO_I"
    fecha_inicio = factory.Faker("date_this_year")
    activo = True

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        from apps.cuadrillas.models import Cargo

        rol_id = kwargs.get("rol_cuadrilla_id") or "LINIERO_I"
        Cargo.objects.get_or_create(
            codigo=rol_id,
            defaults={"nombre": rol_id.replace("_", " ").title(), "activo": True},
        )
        return super()._create(model_class, *args, **kwargs)
