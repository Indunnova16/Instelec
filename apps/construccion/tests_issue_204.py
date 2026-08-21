"""Regression tests for the real module percentages in issue #204."""

from datetime import date
from decimal import Decimal
from pathlib import Path

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
def test_dashboard_avance_conserva_ambas_series_en_hitos_intercalados(
        authenticated_client, proyecto_204):
    """Regresión: los hitos planeados y reales distintos comparten eje sin
    adelantar el ejecutado al siguiente hito planeado.

    Con dos torres legacy, el dashboard debe aplicar carry-forward a cada
    serie de forma independiente. Es el caso que el canvas consume en cliente:
    Planeado alcanza 50% antes que Ejecutado y ambos llegan a 100% después.
    """
    from apps.construccion.models import ObraCivilTorre, TorreConstruccion

    primera = proyecto_204.torres.get(numero='T1')
    segunda = TorreConstruccion.objects.create(proyecto=proyecto_204, numero='T2')
    ObraCivilTorre.objects.update_or_create(
        proyecto=proyecto_204, torre=primera,
        defaults={
            'fecha_esperada': date(2025, 1, 10),
            'fecha_final': date(2025, 1, 15),
        },
    )
    ObraCivilTorre.objects.create(
        proyecto=proyecto_204, torre=segunda,
        fecha_esperada=date(2025, 1, 20), fecha_final=date(2025, 1, 25),
    )

    response = authenticated_client.get(
        reverse('construccion:dashboard_avance', kwargs={'proyecto_id': proyecto_204.id})
    )

    assert response.status_code == 200
    assert response.context['curva_s'] == {
        'labels': ['2025-01-10', '2025-01-15', '2025-01-20', '2025-01-25'],
        'planeado': [50.0, 50.0, 100.0, 100.0],
        'ejecutado': [0.0, 50.0, 50.0, 100.0],
    }
    html = response.content.decode()
    assert 'id="curva-s-data"' in html
    assert 'Planeado %' in html and 'Ejecutado %' in html


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


@pytest.mark.django_db
def test_gantt_consolidado_usa_fechas_parciales_de_los_tres_bloques(proyecto_204):
    """Una fecha aislada sigue siendo una barra válida de un día."""
    from apps.construccion.calculators_avance_real import gantt_consolidado
    from apps.construccion.models import FaseTorre, ObraCivilTorre
    from apps.construccion.models_b3_mont_detalle import MontajeEstructuraTorreDetalle

    torre = proyecto_204.torres.get(numero='T1')
    ObraCivilTorre.objects.update_or_create(
        proyecto=proyecto_204, torre=torre,
        defaults={'fecha_inicio': date(2025, 1, 2), 'fecha_final': None},
    )
    montaje = MontajeEstructuraTorreDetalle.objects.get(proyecto=proyecto_204, torre=torre)
    montaje.montaje_fecha_fin = date(2025, 2, 4)
    montaje.save(update_fields=['montaje_fecha_fin'])
    fase, _ = FaseTorre.objects.get_or_create(proyecto=proyecto_204, torre=torre)
    fase.tendido_conductor_a_fecha = date(2025, 3, 6)
    fase.save(update_fields=['tendido_conductor_a_fecha'])

    filas = gantt_consolidado(proyecto_204)

    filas_torre = {fila['bloque']: fila for fila in filas if fila['torre'] == torre.numero_display}
    assert set(filas_torre) == {'Obra Civil', 'Montaje', 'Tendido'}
    assert filas_torre['Montaje']['inicio'] == filas_torre['Montaje']['final'] == '2025-02-04'
    assert filas_torre['Tendido']['inicio'] == filas_torre['Tendido']['final'] == '2025-03-06'


@pytest.mark.django_db
def test_gantt_consolidado_excluye_torres_no_aplicables(proyecto_204):
    """Las tres fuentes respetan aplica=False aun cuando tengan fechas."""
    from apps.construccion.calculators_avance_real import gantt_consolidado
    from apps.construccion.models import FaseTorre, ObraCivilTorre, TorreConstruccion
    from apps.construccion.models_b3_mont_detalle import MontajeEstructuraTorreDetalle

    torre = TorreConstruccion.objects.create(
        proyecto=proyecto_204, numero='T-no-aplica', aplica=False,
    )
    ObraCivilTorre.objects.create(
        proyecto=proyecto_204, torre=torre, fecha_inicio=date(2025, 1, 1),
    )
    MontajeEstructuraTorreDetalle.objects.create(
        proyecto=proyecto_204, torre=torre, montaje_fecha_inicio=date(2025, 2, 1),
    )
    FaseTorre.objects.create(
        proyecto=proyecto_204, torre=torre, fecha_riega_manila=date(2025, 3, 1),
    )

    assert 'T-no-aplica' not in [fila['torre'] for fila in gantt_consolidado(proyecto_204)]


@pytest.mark.django_db
def test_dashboard_avance_renderiza_gantt_y_estado_vacio(authenticated_client, proyecto_204, db):
    """El canvas recibe JSON seguro; un proyecto sin fechas obtiene orientación."""
    from apps.contratos.models import Contrato
    from apps.construccion.models import ObraCivilTorre, ProyectoConstruccion

    torre = proyecto_204.torres.get(numero='T1')
    ObraCivilTorre.objects.update_or_create(
        proyecto=proyecto_204, torre=torre,
        defaults={'fecha_inicio': date(2025, 1, 2)},
    )
    response = authenticated_client.get(
        reverse('construccion:dashboard_avance', kwargs={'proyecto_id': proyecto_204.id})
    )
    html = response.content.decode()
    assert response.status_code == 200
    assert 'id="gantt-consolidado-data"' in html
    assert 'id="gantt-consolidado-chart"' in html

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-204-004', nombre='Sin Gantt', cliente='Cliente test',
    )
    vacio = ProyectoConstruccion.objects.create(
        contrato=contrato, nombre='Proyecto sin fechas', estado='PLANIFICACION',
    )
    response_vacio = authenticated_client.get(
        reverse('construccion:dashboard_avance', kwargs={'proyecto_id': vacio.id})
    )
    assert response_vacio.status_code == 200
    assert 'Aún no hay fechas de avance para mostrar el Gantt consolidado.' in response_vacio.content.decode()


def test_sidebar_exposes_dashboard_consolidado_after_cronograma():
    """#204: the existing dashboard must be reachable for an active project."""
    sidebar = (Path(__file__).resolve().parents[2] / 'templates/components/sidebar.html')
    contenido = sidebar.read_text(encoding='utf-8')
    cronograma = contenido.index("catUrl('cronograma')")
    dashboard = contenido.index("catUrl('dashboard-avance')")

    assert cronograma < dashboard
    bloque_dashboard = contenido[dashboard:dashboard + 800]
    assert 'Dashboard Consolidado' in bloque_dashboard
    assert '@click="catClick($event)"' in bloque_dashboard
    assert ':class="proyectoId ?' in bloque_dashboard
