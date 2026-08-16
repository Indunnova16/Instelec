from datetime import date, time

import pytest
from django.urls import reverse

from apps.contratos.models import Contrato
from apps.construccion.models import ProyectoConstruccion, ProgramacionSemanalConstruccion


@pytest.fixture
def proyecto_psc(db):
    contrato = Contrato.objects.create(
        codigo='PSC-B2-TEST', nombre='Contrato PSC B2', unidad_negocio='CONSTRUCCION',
    )
    return ProyectoConstruccion.objects.create(contrato=contrato, nombre='Proyecto PSC B2')


def _payload(proyecto, **overrides):
    data = {
        'proyecto': str(proyecto.pk),
        'tipo_actividad': 'OBRA_CIVIL',
        'subactividad': 'Excavación de fundación',
        'actividad_complementaria': '',
        'fecha_inicio': '2026-08-17',
        'fecha_fin': '2026-08-21',
        'hora_inicio': '07:00',
        'hora_fin': '16:00',
        'observaciones': 'Programación semanal de prueba',
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_tipo_subactividad(admin_user, client, proyecto_psc):
    client.force_login(admin_user)
    response = client.post(reverse('construccion:psc_programacion_crear'), _payload(proyecto_psc))
    assert response.status_code == 302
    creada = ProgramacionSemanalConstruccion.objects.get(proyecto=proyecto_psc)
    assert creada.tipo_actividad == 'OBRA_CIVIL'
    assert creada.subactividad == 'Excavación de fundación'


@pytest.mark.django_db
def test_complementaria_libre(admin_user, client, proyecto_psc):
    client.force_login(admin_user)
    response = client.post(
        reverse('construccion:psc_programacion_crear'),
        _payload(proyecto_psc, tipo_actividad='COMPLEMENTARIAS', subactividad='', actividad_complementaria='Capacitación SST'),
    )
    assert response.status_code == 302
    assert ProgramacionSemanalConstruccion.objects.get().actividad_complementaria == 'Capacitación SST'


@pytest.mark.django_db
def test_complementaria_requiere_descripcion(admin_user, client, proyecto_psc):
    client.force_login(admin_user)
    response = client.post(
        reverse('construccion:psc_programacion_crear'),
        _payload(proyecto_psc, tipo_actividad='COMPLEMENTARIAS', subactividad='', actividad_complementaria=''),
    )
    assert response.status_code == 200
    assert 'Describa la actividad complementaria' in response.content.decode()
    assert not ProgramacionSemanalConstruccion.objects.exists()


@pytest.mark.django_db
def test_guardar_detalle_y_validar_intervalo(admin_user, client, proyecto_psc):
    client.force_login(admin_user)
    response = client.post(
        reverse('construccion:psc_programacion_crear'),
        _payload(proyecto_psc, fecha_inicio='2026-08-22', fecha_fin='2026-08-21'),
    )
    assert response.status_code == 200
    assert 'fecha final no puede ser anterior' in response.content.decode().lower()

    programacion = ProgramacionSemanalConstruccion.objects.create(
        proyecto=proyecto_psc, tipo_actividad='TENDIDO', subactividad='Tendido conductor',
        fecha_inicio=date(2026, 8, 17), fecha_fin=date(2026, 8, 21),
        hora_inicio=time(7), hora_fin=time(16),
    )
    detail = client.get(reverse('construccion:psc_programacion_detalle', args=[programacion.pk]))
    assert detail.status_code == 200
    assert 'Tendido conductor' in detail.content.decode()
