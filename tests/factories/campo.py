"""Factories for campo app."""

import factory
from datetime import datetime, timedelta
from decimal import Decimal
from django.utils import timezone

from apps.campo.models import RegistroCampo, Evidencia
from tests.factories.actividades import ActividadEnCursoFactory
from tests.factories.usuarios import LinieroFactory


class RegistroCampoFactory(factory.django.DjangoModelFactory):
    """Factory for RegistroCampo model."""

    class Meta:
        model = RegistroCampo

    actividad = factory.SubFactory(ActividadEnCursoFactory)
    usuario = factory.SubFactory(LinieroFactory)
    fecha_inicio = factory.LazyFunction(timezone.now)
    fecha_fin = None
    latitud_inicio = factory.LazyFunction(
        lambda: Decimal(f"{factory.Faker._get_faker().pyfloat(min_value=4.0, max_value=12.0):.8f}")
    )
    longitud_inicio = factory.LazyFunction(
        lambda: Decimal(f"{factory.Faker._get_faker().pyfloat(min_value=-77.0, max_value=-72.0):.8f}")
    )
    dentro_poligono = True
    datos_formulario = factory.LazyFunction(lambda: {
        "observaciones": "Trabajo realizado correctamente",
        "estado_torre": "Bueno",
    })
    observaciones = factory.Faker("paragraph", locale="es_CO")
    sincronizado = False


class RegistroCampoCompletadoFactory(RegistroCampoFactory):
    """Factory for completed field record."""

    fecha_fin = factory.LazyAttribute(lambda obj: obj.fecha_inicio + timedelta(hours=4))
    latitud_fin = factory.LazyAttribute(lambda obj: obj.latitud_inicio)
    longitud_fin = factory.LazyAttribute(lambda obj: obj.longitud_inicio)
    sincronizado = True


class EvidenciaFactory(factory.django.DjangoModelFactory):
    """Factory for Evidencia model."""

    class Meta:
        model = Evidencia

    registro_campo = factory.SubFactory(RegistroCampoFactory)
    tipo = factory.Iterator(["ANTES", "DURANTE", "DESPUES"])
    url_original = factory.LazyAttribute(
        lambda obj: f"https://storage.googleapis.com/transmaint/evidencias/{obj.registro_campo.id}/{obj.tipo}/foto.jpg"
    )
    url_thumbnail = factory.LazyAttribute(
        lambda obj: f"https://storage.googleapis.com/transmaint/evidencias/{obj.registro_campo.id}/thumbs/{obj.tipo}.jpg"
    )
    latitud = factory.LazyAttribute(lambda obj: obj.registro_campo.latitud_inicio)
    longitud = factory.LazyAttribute(lambda obj: obj.registro_campo.longitud_inicio)
    fecha_captura = factory.LazyFunction(timezone.now)
    validacion_ia = factory.LazyFunction(lambda: {
        "nitidez": 0.95,
        "iluminacion": 0.88,
        "valida": True,
        "confianza": 0.92,
    })
    metadata_exif = factory.LazyFunction(lambda: {
        "make": "Samsung",
        "model": "Galaxy S23",
        "datetime": str(datetime.now()),
        "gps": True,
    })


class EvidenciaAntesFactory(EvidenciaFactory):
    """Factory for ANTES evidence."""

    tipo = "ANTES"


class EvidenciaDuranteFactory(EvidenciaFactory):
    """Factory for DURANTE evidence."""

    tipo = "DURANTE"


class EvidenciaDespuesFactory(EvidenciaFactory):
    """Factory for DESPUES evidence."""

    tipo = "DESPUES"
