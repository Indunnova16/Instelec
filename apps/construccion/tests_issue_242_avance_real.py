"""Contrato de la matriz única de avance real de Instelec#242."""

import pytest

from apps.construccion import calculators_avance_real as car
from apps.construccion.models import (
    ProgramacionFase,
    ProyectoConstruccion,
    SPTTorre,
    TorreConstruccion,
)
from apps.contratos.models import Contrato


SECCIONES_242 = [
    'INGENIERIA', 'SOCIOPREDIAL', 'SOCIOAMBIENTAL', 'OBRA_CIVIL', 'MONTAJE',
    'SPT', 'TENDIDO', 'PROTECCIONES', 'PRUEBAS',
]


@pytest.fixture
def proyecto_242_avance(db):
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-242-AVANCE-001',
        nombre='Contrato avance 242',
        cliente='Cliente de prueba',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto avance 242',
        estado='EJECUCION',
    )


@pytest.mark.django_db
def test_242_matriz_cubre_las_nueve_secciones_del_cronograma(proyecto_242_avance):
    """Cada código del cronograma tiene una fuente rectora explícita."""
    assert [seccion for seccion, _label, _fuente in car.FASES_GENERAL] == SECCIONES_242

    fases = car.avance_general(proyecto_242_avance)['fases']
    assert [fase['seccion'] for fase in fases] == SECCIONES_242
    assert all(fase['pct'] is None for fase in fases), (
        'Sin filas de ejecución debe quedar SIN_DATA, no un 0% inventado.'
    )


@pytest.mark.django_db
def test_242_cero_capturado_se_preserva_y_no_aplica_no_entra_al_promedio(
    proyecto_242_avance,
):
    """0% real y ausencia de fuente son estados distintos; aplica=False no pesa."""
    torre_aplica = TorreConstruccion.objects.create(
        proyecto=proyecto_242_avance, numero='T-242-1', aplica=True,
    )
    SPTTorre.objects.create(
        proyecto=proyecto_242_avance, torre=torre_aplica, porcentaje_avance=0,
    )
    torre_no_aplica = TorreConstruccion.objects.create(
        proyecto=proyecto_242_avance, numero='T-242-2', aplica=False,
    )
    SPTTorre.objects.create(
        proyecto=proyecto_242_avance, torre=torre_no_aplica, porcentaje_avance=100,
    )

    fase = ProgramacionFase.objects.create(
        proyecto=proyecto_242_avance, seccion=ProgramacionFase.Seccion.SPT,
    )
    assert fase.pct_avance_real == 0.0
    assert car._pct_spt_pintura(proyecto_242_avance) == 0.0
