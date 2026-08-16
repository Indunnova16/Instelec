"""Contrato del selector de orden compartido por los dashboards de #203."""

import pytest
from django.urls import reverse


@pytest.fixture
def proyecto_203(db):
    """Proyecto con una torre legacy: el selector no depende de datos nuevos."""
    from apps.contratos.models import Contrato
    from apps.construccion.models import ProyectoConstruccion, TorreConstruccion

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-203-001', nombre='Contrato legado #203', cliente='Cliente test',
    )
    proyecto = ProyectoConstruccion.objects.create(
        contrato=contrato, nombre='Proyecto selector #203', estado='EJECUCION',
    )
    TorreConstruccion.objects.create(proyecto=proyecto, numero='T-10')
    return proyecto


def _urls(proyecto):
    kwargs = {'proyecto_id': proyecto.id}
    return [
        reverse('construccion:dashboard_obra_civil', kwargs=kwargs),
        reverse('construccion:dashboard_montaje', kwargs=kwargs),
        reverse('construccion:dashboard_tendido', kwargs=kwargs),
        reverse('construccion:dashboard_avance', kwargs=kwargs),
    ]


@pytest.mark.django_db
def test_203_selector_por_defecto_es_numero_en_las_cuatro_superficies(
        authenticated_client, proyecto_203):
    """Una URL sin parámetro conserva el contrato seguro para datos legacy."""
    for url in _urls(proyecto_203):
        response = authenticated_client.get(url)

        assert response.status_code == 200
        assert response.context['orden_gantt'] == 'numero'
        assert 'data-orden-selector' in response.content.decode()
        assert 'Número de torre' in response.content.decode()
        assert 'Cronológico por fecha real' in response.content.decode()


@pytest.mark.django_db
def test_203_selector_persiste_criterio_cronologico_en_url_y_estado(
        authenticated_client, proyecto_203):
    """Las cuatro superficies aceptan únicamente el segundo criterio válido."""
    for url in _urls(proyecto_203):
        response = authenticated_client.get(url, {'orden': 'cronologico'})

        assert response.status_code == 200
        assert response.context['orden_gantt'] == 'cronologico'
        html = response.content.decode()
        assert 'value="cronologico" selected' in html
        assert 'Orden aplicado: Cronológico por fecha real.' in html


@pytest.mark.django_db
def test_203_selector_rechaza_parametro_invalido_y_muestra_estado_error(
        authenticated_client, proyecto_203):
    """Un querystring manipulado hace fallback visible, sin romper el dashboard."""
    response = authenticated_client.get(
        reverse('construccion:dashboard_avance', kwargs={'proyecto_id': proyecto_203.id}),
        {'orden': 'porcentaje'},
    )

    assert response.status_code == 200
    assert response.context['orden_gantt'] == 'numero'
    assert response.context['orden_gantt_invalido'] is True
    assert 'Criterio no válido; se aplicó Número de torre.' in response.content.decode()
