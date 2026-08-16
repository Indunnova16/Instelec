"""Regression tests for the real module percentages in issue #204."""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse


@pytest.fixture
def proyecto_204(db):
    from apps.contratos.models import Contrato
    from apps.construccion.models import ProyectoConstruccion, TorreConstruccion

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-204-001', nombre='Proyecto issue 204', cliente='Cliente test',
    )
    proyecto = ProyectoConstruccion.objects.create(
        contrato=contrato, nombre='Proyecto issue 204', estado='EJECUCION',
    )
    torre = TorreConstruccion.objects.create(proyecto=proyecto, numero='T1')

    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle
    ObraCivilTorreDetalle.objects.create(
        proyecto=proyecto, torre=torre, pata='A',
        cerr_finalizado_ok=True,
        exc_ejecutada_pct=Decimal('1'), sol_ejecutado_pct=Decimal('1'),
        ace_instalacion_pct=Decimal('1'), vac_ejecutado_pct=Decimal('1'),
        com_finalizada_pct=Decimal('1'),
    )

    from apps.construccion.models_b3_mont_detalle import MontajeEstructuraTorreDetalle
    MontajeEstructuraTorreDetalle.objects.create(
        proyecto=proyecto, torre=torre,
        estructura_en_sitio_ok=True, prearmada_ok=True,
        torre_montada_ok=True, revisada_ok=True,
    )

    from apps.construccion.models import TendidoTorre
    TendidoTorre.objects.create(
        proyecto=proyecto, torre=torre,
        riega_manila_conductor=True, riega_guaya_conductor=True,
        tendido_conductor=True, grapado_amarre_conductor=True,
        accesorios_puentes=True, balizas_desviadores=True,
        riega_manila_fibra=True, riega_guaya_opgw=True, tendido_opgw=True,
        grapado_amarre_fibra=True, empalmes_opgw=True,
    )
    return proyecto


@pytest.mark.django_db
def test_avance_modulos_usa_registros_legacy(proyecto_204):
    """Los registros reales del módulo alimentan las tres tarjetas."""
    from apps.construccion.calculators_avance_real import avance_modulos

    assert avance_modulos(proyecto_204) == {
        'obra_civil': 100.0, 'montaje': 100.0, 'tendido': 100.0,
    }


@pytest.mark.django_db
def test_avance_modulos_sin_torres_y_sin_fase_es_cero(db):
    """Proyecto nuevo o fase sin registros: fallback seguro a 0.0."""
    from apps.contratos.models import Contrato
    from apps.construccion.models import ProyectoConstruccion
    from apps.construccion.calculators_avance_real import avance_modulos

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-204-002', nombre='Proyecto vacío issue 204', cliente='Cliente test',
    )
    proyecto = ProyectoConstruccion.objects.create(
        contrato=contrato, nombre='Proyecto vacío issue 204', estado='PLANIFICACION',
    )

    assert avance_modulos(proyecto) == {
        'obra_civil': 0.0, 'montaje': 0.0, 'tendido': 0.0,
    }


@pytest.mark.django_db
def test_dashboard_avance_expone_porcentajes_reales(authenticated_client, proyecto_204):
    """El HTML servido muestra los porcentajes reales en las tarjetas."""
    response = authenticated_client.get(
        reverse('construccion:dashboard_avance',
                kwargs={'proyecto_id': proyecto_204.id})
    )

    assert response.status_code == 200
    html = response.content.decode()
    assert html.count('100') >= 3


@pytest.mark.django_db
def test_dashboard_avance_alinea_planeado_y_ejecutado_del_backbone_oc(
        authenticated_client, proyecto_204):
    """La Curva S consolidada reutiliza el payload real de Obra Civil (#204)."""
    from apps.construccion.models import ObraCivilTorre

    torre = proyecto_204.torres.get(numero='T1')
    ObraCivilTorre.objects.update_or_create(
        proyecto=proyecto_204, torre=torre,
        defaults={
            'fecha_inicio': date(2025, 1, 2),
            'fecha_esperada': date(2025, 1, 10),
            'fecha_final': date(2025, 1, 15),
        },
    )

    response = authenticated_client.get(
        reverse('construccion:dashboard_avance', kwargs={'proyecto_id': proyecto_204.id})
    )

    assert response.status_code == 200
    curva = response.context['curva_s']
    assert curva['labels'] == sorted(curva['labels'])
    assert len(curva['labels']) == len(curva['planeado']) == len(curva['ejecutado'])
    assert curva['planeado'][-1] == 100.0
    assert curva['ejecutado'][-1] == 100.0
    html = response.content.decode()
    assert 'id="curva-s-data"' in html
    assert 'Planeado vs. Ejecutado acumulado' in html
    assert 'Ejecutado %' in html


@pytest.mark.django_db
def test_dashboard_avance_sin_cronograma_muestra_estado_vacio(
        authenticated_client, db):
    """Edge: un proyecto sin fechas planeadas orienta a cargar el cronograma."""
    from apps.contratos.models import Contrato
    from apps.construccion.models import ProyectoConstruccion

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-204-003', nombre='Sin cronograma', cliente='Cliente test',
    )
    proyecto = ProyectoConstruccion.objects.create(
        contrato=contrato, nombre='Proyecto sin cronograma', estado='PLANIFICACION',
    )

    response = authenticated_client.get(
        reverse('construccion:dashboard_avance', kwargs={'proyecto_id': proyecto.id})
    )

    assert response.status_code == 200
    assert response.context['curva_s'] == {'labels': [], 'planeado': [], 'ejecutado': []}
    html = response.content.decode()
    assert 'Aún no hay cronograma planeado para la Curva S' in html
    assert 'Aún no hay avance real finalizado para graficar' in html
    assert 'id="curvaS"' not in html


@pytest.mark.django_db
def test_dashboard_avance_sin_avance_real_conserva_planeado_y_lo_indica(
        authenticated_client, proyecto_204):
    """Edge: fechas planeadas sin cierre real conservan el gráfico y el aviso."""
    from apps.construccion.models import ObraCivilTorre

    torre = proyecto_204.torres.get(numero='T1')
    ObraCivilTorre.objects.update_or_create(
        proyecto=proyecto_204, torre=torre,
        defaults={'fecha_esperada': date(2025, 2, 10), 'fecha_final': None},
    )

    response = authenticated_client.get(
        reverse('construccion:dashboard_avance', kwargs={'proyecto_id': proyecto_204.id})
    )

    assert response.status_code == 200
    assert response.context['curva_s_planeado_disponible'] is True
    assert response.context['curva_s_ejecutado_disponible'] is False
    html = response.content.decode()
    assert 'id="curvaS"' in html
    assert 'Aún no hay avance real finalizado para graficar' in html
