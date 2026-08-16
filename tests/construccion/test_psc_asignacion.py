"""Flujos HTTP de asignación manual PSC (#225, B6)."""
from datetime import date

import pytest
from django.urls import reverse

from apps.contratos.models import Contrato
from apps.construccion.models import (
    AsignacionPersonalProyectoConstruccion,
    ProgramacionSemanalConstruccion,
    ProgramacionSemanalConstruccionPersonal,
    ProgramacionSemanalConstruccionVehiculo,
    ProyectoConstruccion,
)
from apps.cuadrillas.models import Cargo, PersonalCuadrilla, Vehiculo


@pytest.fixture
def asignacion_data(db):
    contrato = Contrato.objects.create(
        codigo='PSC-B6-001', nombre='Contrato PSC B6', unidad_negocio='CONSTRUCCION',
    )
    proyecto = ProyectoConstruccion.objects.create(contrato=contrato, nombre='Proyecto PSC B6')
    cargo, _ = Cargo.objects.get_or_create(codigo='B6-COND', defaults={'nombre': 'Conductor B6'})
    personal = PersonalCuadrilla.objects.create(
        nombre='Carla Disponible', documento='PSC-B6-001', rol_cuadrilla=cargo,
        fecha_ingreso=date(2025, 1, 1),
    )
    no_elegible = PersonalCuadrilla.objects.create(
        nombre='Nora Sin Aprobación', documento='PSC-B6-002', rol_cuadrilla=cargo,
    )
    AsignacionPersonalProyectoConstruccion.objects.create(
        proyecto=proyecto, personal=personal, fecha_inicio=date(2026, 8, 1),
    )
    programacion = ProgramacionSemanalConstruccion.objects.create(
        proyecto=proyecto, tipo_actividad='OBRA_CIVIL', subactividad='Excavación B6',
        fecha_inicio=date(2026, 8, 17), fecha_fin=date(2026, 8, 21),
    )
    vehiculo = Vehiculo.objects.create(placa='PSC-B6-01', estado=Vehiculo.Estado.ACTIVO)
    return programacion, personal, no_elegible, vehiculo


@pytest.mark.django_db
def test_agregar_personal_elegible(admin_user, client, asignacion_data):
    programacion, personal, _, _ = asignacion_data
    client.force_login(admin_user)
    response = client.post(
        reverse('construccion:psc_personal_agregar', args=[programacion.pk]),
        {'personal_ids': [str(personal.pk)], 'categoria': 'ADMINISTRATIVO'},
    )
    assert response.status_code == 302
    asignacion = ProgramacionSemanalConstruccionPersonal.objects.get()
    assert asignacion.personal == personal
    assert asignacion.categoria == 'ADMINISTRATIVO'


@pytest.mark.django_db
def test_rechazar_personal_no_elegible(admin_user, client, asignacion_data):
    programacion, _, no_elegible, _ = asignacion_data
    client.force_login(admin_user)
    response = client.post(
        reverse('construccion:psc_personal_agregar', args=[programacion.pk]),
        {'personal_ids': [str(no_elegible.pk)]}, follow=True,
    )
    assert response.status_code == 200
    assert not ProgramacionSemanalConstruccionPersonal.objects.exists()
    assert 'no habilitado' in response.content.decode().lower()


@pytest.mark.django_db
def test_agregar_vehiculo_con_conductor(admin_user, client, asignacion_data):
    programacion, personal, _, vehiculo = asignacion_data
    ProgramacionSemanalConstruccionPersonal.objects.create(
        programacion=programacion, personal=personal,
    )
    client.force_login(admin_user)
    response = client.post(
        reverse('construccion:psc_vehiculo_agregar', args=[programacion.pk]),
        {'vehiculo_id': str(vehiculo.pk), 'conductor_id': str(personal.pk)},
    )
    assert response.status_code == 302
    asignacion = ProgramacionSemanalConstruccionVehiculo.objects.get()
    assert asignacion.vehiculo == vehiculo
    assert asignacion.conductor == personal


@pytest.mark.django_db
def test_quitar_personal_asignado(admin_user, client, asignacion_data):
    programacion, personal, _, _ = asignacion_data
    ProgramacionSemanalConstruccionPersonal.objects.create(
        programacion=programacion, personal=personal,
    )
    client.force_login(admin_user)
    response = client.post(
        reverse('construccion:psc_personal_quitar', args=[programacion.pk, personal.pk]),
    )
    assert response.status_code == 302
    assert not ProgramacionSemanalConstruccionPersonal.objects.exists()


@pytest.mark.django_db
def test_rechaza_conductor_ajeno_y_vehiculo_inactivo(admin_user, client, asignacion_data):
    programacion, _, no_elegible, vehiculo = asignacion_data
    client.force_login(admin_user)
    response = client.post(
        reverse('construccion:psc_vehiculo_agregar', args=[programacion.pk]),
        {'vehiculo_id': str(vehiculo.pk), 'conductor_id': str(no_elegible.pk)}, follow=True,
    )
    assert response.status_code == 200
    assert not ProgramacionSemanalConstruccionVehiculo.objects.exists()
    vehiculo.estado = Vehiculo.Estado.EN_MANTENIMIENTO
    vehiculo.save()
    response = client.post(
        reverse('construccion:psc_vehiculo_agregar', args=[programacion.pk]),
        {'vehiculo_id': str(vehiculo.pk)}, follow=True,
    )
    assert response.status_code == 200
    assert 'no existe o no está activo' in response.content.decode().lower()
