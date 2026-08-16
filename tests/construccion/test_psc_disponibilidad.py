from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.contratos.models import Contrato
from apps.construccion.models import (
    AsignacionPersonalProyectoConstruccion,
    ProgramacionSemanalConstruccion,
    ProgramacionSemanalConstruccionPersonal,
    ProgramacionSemanalConstruccionVehiculo,
    ProyectoConstruccion,
)
from apps.construccion.services_psc_disponibilidad import (
    personal_elegible,
    validar_personal_elegible,
)
from apps.cuadrillas.models import Cargo, PersonalCuadrilla
from apps.cuadrillas.models import Vehiculo


@pytest.fixture
def psc_data(db):
    contrato = Contrato.objects.create(codigo='PSC-B3', nombre='Contrato B3', unidad_negocio='CONSTRUCCION')
    proyecto = ProyectoConstruccion.objects.create(contrato=contrato, nombre='Proyecto B3')
    cargo, _ = Cargo.objects.get_or_create(
        codigo='CONDUCTOR', defaults={'nombre': 'Conductor'},
    )
    persona = PersonalCuadrilla.objects.create(
        nombre='Carlos Conductor', documento='PSC-B3-001', rol_cuadrilla=cargo,
        fecha_ingreso=date(2025, 1, 1),
    )
    AsignacionPersonalProyectoConstruccion.objects.create(
        proyecto=proyecto, personal=persona, fecha_inicio=date(2026, 8, 1), fecha_fin=None,
    )
    return proyecto, persona


@pytest.mark.django_db
def test_filtro_intervalo(psc_data):
    proyecto, persona = psc_data
    disponibles = personal_elegible(proyecto.pk, date(2026, 8, 17), date(2026, 8, 23))
    assert list(disponibles) == [persona]


@pytest.mark.django_db
def test_placa_conductor(psc_data):
    proyecto, persona = psc_data
    programacion = ProgramacionSemanalConstruccion.objects.create(
        proyecto=proyecto, tipo_actividad='OBRA_CIVIL', subactividad='Excavación',
        fecha_inicio=date(2026, 8, 17), fecha_fin=date(2026, 8, 23),
    )
    vehiculo = Vehiculo.objects.create(placa='PSC225')
    ProgramacionSemanalConstruccionVehiculo.objects.create(
        programacion=programacion, vehiculo=vehiculo, conductor=persona,
    )
    assert not personal_elegible(proyecto.pk, date(2026, 8, 17), date(2026, 8, 23)).exists()


@pytest.mark.django_db
def test_sin_programar(psc_data):
    proyecto, persona = psc_data
    programacion = ProgramacionSemanalConstruccion.objects.create(
        proyecto=proyecto, tipo_actividad='OBRA_CIVIL', subactividad='Excavación',
        fecha_inicio=date(2026, 8, 17), fecha_fin=date(2026, 8, 23),
    )
    ProgramacionSemanalConstruccionPersonal.objects.create(programacion=programacion, personal=persona)
    assert not personal_elegible(proyecto.pk, date(2026, 8, 17), date(2026, 8, 23)).exists()


@pytest.mark.django_db
def test_rechaza_fecha_invertida_y_personal_duplicado(psc_data):
    proyecto, persona = psc_data
    with pytest.raises(ValidationError, match='final'):
        personal_elegible(proyecto.pk, date(2026, 8, 23), date(2026, 8, 17))
    programacion = ProgramacionSemanalConstruccion.objects.create(
        proyecto=proyecto, tipo_actividad='OBRA_CIVIL', subactividad='Excavación',
        fecha_inicio=date(2026, 8, 17), fecha_fin=date(2026, 8, 23),
    )
    with pytest.raises(ValidationError, match='misma persona'):
        validar_personal_elegible(programacion, [persona.pk, persona.pk])
