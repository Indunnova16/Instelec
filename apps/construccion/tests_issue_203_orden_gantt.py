"""Contrato del selector de orden compartido por los dashboards de #203."""

from datetime import date

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


def test_203_motor_orden_natural_y_cronologico_desempata_por_torre():
    """El motor compartido no usa timestamps de edición para sus desempates."""
    from apps.construccion.calculators_avance_real import ordenar_filas_dashboard

    filas = [
        {'torre': 'T-10', 'fecha_orden': date(2025, 5, 3)},
        {'torre': 'T-2', 'fecha_orden': date(2025, 5, 1)},
        {'torre': 'T-1', 'fecha_orden': date(2025, 5, 1)},
    ]

    assert [fila['torre'] for fila in ordenar_filas_dashboard(filas)] == ['T-1', 'T-2', 'T-10']
    assert [fila['torre'] for fila in ordenar_filas_dashboard(filas, 'cronologico')] == [
        'T-1', 'T-2', 'T-10',
    ]


def test_203_motor_cronologico_deja_legacy_sin_fecha_al_final():
    """Una torre legacy sin fecha real queda visible y al final, nunca cae a updated_at."""
    from apps.construccion.calculators_avance_real import ordenar_filas_dashboard

    filas = [
        {'torre': 'T-10', 'fecha_orden': None},
        {'torre': 'T-2', 'fecha_orden': date(2025, 7, 2)},
        {'torre': 'T-1', 'fecha_orden': None},
    ]

    assert [fila['torre'] for fila in ordenar_filas_dashboard(filas, 'cronologico')] == [
        'T-2', 'T-1', 'T-10',
    ]


@pytest.mark.django_db
def test_203_gantt_consolidado_ordena_fechas_reales_de_los_tres_bloques(proyecto_203):
    """OC, Montaje y Tendido usan su fecha real, incluida una fila legacy NULL."""
    from apps.construccion.calculators_avance_real import gantt_consolidado
    from apps.construccion.models import FaseTorre, ObraCivilTorre, TorreConstruccion
    from apps.construccion.models_b3_mont_detalle import MontajeEstructuraTorreDetalle

    torre_oc = TorreConstruccion.objects.create(proyecto=proyecto_203, numero='T-2')
    torre_montaje = TorreConstruccion.objects.create(proyecto=proyecto_203, numero='T-3')
    torre_tendido = TorreConstruccion.objects.create(proyecto=proyecto_203, numero='T-1')
    # Registro legacy existente en el fixture: no tiene fecha final y debe quedar último.
    torre_legacy = proyecto_203.torres.get(numero='T-10')
    ObraCivilTorre.objects.create(
        proyecto=proyecto_203, torre=torre_oc,
        fecha_inicio=date(2025, 1, 1), fecha_final=date(2025, 1, 10),
    )
    ObraCivilTorre.objects.create(
        proyecto=proyecto_203, torre=torre_legacy, fecha_inicio=date(2025, 1, 1),
    )
    MontajeEstructuraTorreDetalle.objects.create(
        proyecto=proyecto_203, torre=torre_montaje, montaje_fecha_fin=date(2025, 2, 10),
    )
    FaseTorre.objects.create(
        proyecto=proyecto_203, torre=torre_tendido,
        tendido_conductor_a_fecha=date(2025, 3, 10),
    )

    filas = gantt_consolidado(proyecto_203, orden='cronologico')

    assert [(fila['bloque'], fila['torre']) for fila in filas] == [
        ('Obra Civil', 'T-2'),
        ('Montaje', 'T-3'),
        ('Tendido', 'T-1'),
        ('Obra Civil', 'T-10'),
    ]


@pytest.mark.django_db
def test_203_render_propagates_order_to_phase_views_and_consolidated_gantt(
        authenticated_client, proyecto_203):
    """Cada superficie renderiza el mismo contrato con dos torres reales.

    T-10 es anterior por fecha real y T-2 es anterior por número natural. El
    caso cubre los dos criterios en las vistas por torre de cada fase, el Gantt
    OC y el Gantt consolidado de #204, sin sustituir sus tarjetas/series.
    """
    from apps.construccion import calculators_avance_real as car
    from apps.construccion.models import (
        FaseTorre, ObraCivilTorre, TorreConstruccion, TendidoTorre,
    )
    from apps.construccion.models_b3_mont_detalle import MontajeEstructuraTorreDetalle
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle

    torre_10 = proyecto_203.torres.get(numero='T-10')  # dato legacy del fixture
    torre_2 = TorreConstruccion.objects.create(proyecto=proyecto_203, numero='T-2')

    for torre in (torre_10, torre_2):
        ObraCivilTorreDetalle.objects.create(
            proyecto=proyecto_203, torre=torre, pata='A',
        )
        TendidoTorre.objects.create(proyecto=proyecto_203, torre=torre)

    ObraCivilTorre.objects.update_or_create(
        proyecto=proyecto_203, torre=torre_10,
        defaults={'fecha_inicio': date(2025, 1, 1), 'fecha_final': date(2025, 1, 10)},
    )
    ObraCivilTorre.objects.update_or_create(
        proyecto=proyecto_203, torre=torre_2,
        defaults={'fecha_inicio': date(2025, 2, 1), 'fecha_final': date(2025, 2, 10)},
    )
    for torre, fecha in ((torre_10, date(2025, 1, 15)), (torre_2, date(2025, 2, 15))):
        MontajeEstructuraTorreDetalle.objects.create(
            proyecto=proyecto_203, torre=torre,
            montaje_fecha_inicio=fecha, montaje_fecha_fin=fecha,
        )
        FaseTorre.objects.create(
            proyecto=proyecto_203, torre=torre,
            tendido_conductor_a_fecha=fecha,
        )

    urls = _urls(proyecto_203)
    por_numero = [authenticated_client.get(url, {'orden': 'numero'}) for url in urls]
    cronologicos = [authenticated_client.get(url, {'orden': 'cronologico'}) for url in urls]
    assert all(response.status_code == 200 for response in por_numero + cronologicos)

    assert [fila['numero'] for fila in por_numero[0].context['vista_torres_oc']] == ['T-2', 'T-10']
    assert [fila['torre'] for fila in por_numero[0].context['gantt_oc_json']] == ['T-2', 'T-10']
    assert [fila['numero'] for fila in por_numero[1].context['vista_torres']] == ['T-2', 'T-10']
    assert [fila['numero'] for fila in por_numero[2].context['vista_torres']] == ['T-2', 'T-10']

    assert [fila['numero'] for fila in cronologicos[0].context['vista_torres_oc']] == ['T-10', 'T-2']
    assert [fila['torre'] for fila in cronologicos[0].context['gantt_oc_json']] == ['T-10', 'T-2']
    assert [fila['numero'] for fila in cronologicos[1].context['vista_torres']] == ['T-10', 'T-2']
    assert [fila['numero'] for fila in cronologicos[2].context['vista_torres']] == ['T-10', 'T-2']

    consolidado = cronologicos[3].context
    assert [fila['torre'] for fila in consolidado['gantt_consolidado']] == [
        'T-10', 'T-10', 'T-10', 'T-2', 'T-2', 'T-2',
    ]
    assert consolidado['avance_civil_ponderado'] == car.avance_modulos(proyecto_203)['obra_civil']
    assert consolidado['avance_montaje'] == car.avance_modulos(proyecto_203)['montaje']
    assert consolidado['avance_tendido'] == car.avance_modulos(proyecto_203)['tendido']
