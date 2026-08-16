"""Regresiones del catálogo de subactividades PSC (#225, B7)."""
from datetime import date

import pytest
from django.urls import reverse

from apps.contratos.models import Contrato
from apps.construccion.models import ProyectoConstruccion
from apps.construccion.subactividades_psc import SUBACTIVIDADES_POR_TIPO
from apps.construccion.views_psc_programacion import ProgramacionSemanalConstruccionForm


@pytest.fixture
def proyecto_psc_subactividades(db):
    contrato = Contrato.objects.create(
        codigo='PSC-B7-TEST', nombre='Contrato PSC B7', unidad_negocio='CONSTRUCCION',
    )
    return ProyectoConstruccion.objects.create(contrato=contrato, nombre='Proyecto PSC B7')


def _form_data(proyecto, **overrides):
    data = {
        'proyecto': str(proyecto.pk),
        'tipo_actividad': 'OBRA_CIVIL',
        'subactividad': 'Excavación',
        'actividad_complementaria': '',
        'fecha_inicio': date(2026, 8, 17).isoformat(),
        'fecha_fin': date(2026, 8, 21).isoformat(),
        'hora_inicio': '07:00',
        'hora_fin': '16:00',
        'supervisor': '',
        'observaciones': '',
    }
    data.update(overrides)
    return data


def test_catalogo_obra_civil():
    assert SUBACTIVIDADES_POR_TIPO['OBRA_CIVIL'] == [
        'Cerramiento', 'Excavación', 'Solado', 'Acero', 'Vaciado',
        'Compactación', 'Obras de Protección (Cunetas, Trinchos)',
    ]


def test_catalogo_preliminares():
    assert SUBACTIVIDADES_POR_TIPO['PRELIMINARES'] == [
        'Ahuyentamiento', 'Fauna y Flora', 'Arqueología', 'Accesos',
        'Liberación Predial', 'Replanteo', 'PDO (Permisos)', 'Semáforos',
    ]


@pytest.mark.django_db
def test_form_renderiza_select_dinamico(admin_user, client):
    client.force_login(admin_user)

    response = client.get(reverse('construccion:psc_programacion_crear'))

    content = response.content.decode()
    assert response.status_code == 200
    assert '<select id="id_subactividad"' in content
    assert 'id="psc-subactividades-data"' in content
    assert '"OBRA_CIVIL": ["Cerramiento", "Excavaci\\u00f3n"' in content


@pytest.mark.django_db
def test_rechaza_subactividad_fuera_de_catalogo(proyecto_psc_subactividades):
    form = ProgramacionSemanalConstruccionForm(
        data=_form_data(proyecto_psc_subactividades, subactividad='Torre Montada'),
    )

    assert not form.is_valid()
    assert form.errors['subactividad'] == [
        'Seleccione una subactividad válida para el tipo elegido.',
    ]


@pytest.mark.django_db
def test_complementarias_no_exige_subactividad(proyecto_psc_subactividades):
    form = ProgramacionSemanalConstruccionForm(data=_form_data(
        proyecto_psc_subactividades,
        tipo_actividad='COMPLEMENTARIAS',
        subactividad='',
        actividad_complementaria='Capacitación SST',
    ))

    assert form.is_valid(), form.errors
