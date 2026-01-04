"""Factories for actividades app."""

import factory
from datetime import date, timedelta

from apps.actividades.models import TipoActividad, ProgramacionMensual, Actividad
from tests.factories.lineas import LineaFactory, TorreFactory
from tests.factories.cuadrillas import CuadrillaFactory


class TipoActividadFactory(factory.django.DjangoModelFactory):
    """Factory for TipoActividad model."""

    class Meta:
        model = TipoActividad

    codigo = factory.Sequence(lambda n: f"ACT-{n:03d}")
    nombre = factory.Iterator([
        "Poda de vegetación",
        "Cambio de herrajes",
        "Inspección visual",
        "Limpieza de aisladores",
        "Medición de resistencia",
    ])
    categoria = factory.Iterator(["PODA", "HERRAJES", "INSPECCION", "LIMPIEZA"])
    requiere_fotos_antes = True
    requiere_fotos_durante = True
    requiere_fotos_despues = True
    campos_formulario = factory.LazyFunction(lambda: {
        "fields": [
            {"name": "observaciones", "type": "text", "required": True},
            {"name": "estado_torre", "type": "select", "options": ["Bueno", "Regular", "Malo"]},
        ]
    })
    activo = True


class ProgramacionMensualFactory(factory.django.DjangoModelFactory):
    """Factory for ProgramacionMensual model."""

    class Meta:
        model = ProgramacionMensual

    linea = factory.SubFactory(LineaFactory)
    anio = factory.LazyFunction(lambda: date.today().year)
    mes = factory.LazyFunction(lambda: date.today().month)
    estado = "BORRADOR"


class ActividadFactory(factory.django.DjangoModelFactory):
    """Factory for Actividad model."""

    class Meta:
        model = Actividad

    linea = factory.SubFactory(LineaFactory)
    torre = factory.SubFactory(TorreFactory)
    tipo_actividad = factory.SubFactory(TipoActividadFactory)
    cuadrilla = factory.SubFactory(CuadrillaFactory)
    fecha_programada = factory.LazyFunction(lambda: date.today() + timedelta(days=7))
    estado = "PENDIENTE"
    prioridad = "NORMAL"
    observaciones_programacion = factory.Faker("sentence", locale="es_CO")

    @factory.lazy_attribute
    def programacion(self):
        return ProgramacionMensualFactory(
            linea=self.linea,
            anio=self.fecha_programada.year,
            mes=self.fecha_programada.month
        )


class ActividadEnCursoFactory(ActividadFactory):
    """Factory for activity in progress."""

    estado = "EN_CURSO"


class ActividadCompletadaFactory(ActividadFactory):
    """Factory for completed activity."""

    estado = "COMPLETADA"
    fecha_programada = factory.LazyFunction(lambda: date.today() - timedelta(days=1))
