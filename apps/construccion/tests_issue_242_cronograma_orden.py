"""Tests Instelec#242 — el Cronograma del Proyecto debe mostrar las fases en
el orden lógico/cronológico de un proyecto de construcción (Ingeniería →
Sociopredial → Socioambiental → Obra Civil → Montaje → SPT y Pintura →
Tendido → Trinchos y Cunetas → Pruebas y Actividades Finales), no en orden
alfabético del valor guardado en BD.

Causa raíz: `CronogramaView.get_context_data()` usaba
`ProgramacionFase.objects.filter(...).order_by('seccion')`, que en un
CharField ordena por el STRING (ej. 'MONTAJE' < 'OBRA_CIVIL' < 'TENDIDO'
alfabéticamente), ignorando el orden real de declaración de
`ProgramacionFase.Seccion.choices` (que ya coincide con el orden pedido por
el cliente). Fix: anotar un ranking explícito vía `Case/When` sobre ese
mismo orden de choices y ordenar por el ranking, no por el string.
"""
from unittest.mock import patch

import pytest

from apps.construccion import calculators_avance_real as car
from apps.construccion.models import ProgramacionFase, ProyectoConstruccion
from apps.construccion.views import CronogramaView
from apps.contratos.models import Contrato

ORDEN_ESPERADO = [
    'INGENIERIA', 'SOCIOPREDIAL', 'SOCIOAMBIENTAL', 'OBRA_CIVIL', 'MONTAJE',
    'SPT', 'TENDIDO', 'PROTECCIONES', 'PRUEBAS',
]


@pytest.fixture
def proyecto_242(db):
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo="TEST-242-CRONO-ORDEN-001",
        nombre="Contrato test 242 orden cronograma",
        cliente="Test Cliente 242",
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre="Proyecto 242 orden cronograma test",
        estado="EJECUCION",
    )


@pytest.mark.django_db
class TestOrdenCronograma242:
    def test_choices_ya_declaradas_en_el_orden_pedido_por_el_cliente(self):
        """Ancla contra un futuro reordenamiento accidental del enum: si
        alguien reordena `Seccion.choices`, este test explicita cuál es el
        orden de negocio correcto (issue #242) para que el cambio sea
        intencional, no un desliz."""
        assert [v for v, _ in ProgramacionFase.Seccion.choices] == ORDEN_ESPERADO

    def test_queryset_de_la_vista_respeta_el_orden_logico_no_alfabetico(self, proyecto_242):
        """Creá las fases en un orden DELIBERADAMENTE distinto (inverso) al
        lógico, para que un `order_by('seccion')` alfabético y un
        `order_by(ranking_logico)` correcto den resultados DIFERENTES —
        si el test pasara igual con ambos, no probaría nada."""
        for seccion in reversed(ORDEN_ESPERADO):
            ProgramacionFase.objects.create(proyecto=proyecto_242, seccion=seccion)

        # Alfabético (el bug): NO coincide con el orden esperado -- confirma
        # que este dataset SÍ distingue ambos criterios de orden.
        alfabetico = list(
            ProgramacionFase.objects.filter(proyecto=proyecto_242)
            .order_by('seccion').values_list('seccion', flat=True)
        )
        assert alfabetico != ORDEN_ESPERADO

        view = CronogramaView()
        view.kwargs = {'proyecto_id': proyecto_242.id}
        ctx = view.get_context_data()
        obtenido = list(ctx['fases'].values_list('seccion', flat=True))
        assert obtenido == ORDEN_ESPERADO

    def test_orden_estable_entre_dos_cargas_sucesivas(self, proyecto_242):
        """'El orden se persiste al guardar/recargar' (criterio de aceptación
        del issue): como el orden depende del catálogo fijo de secciones (no
        de un campo editable por el usuario), dos lecturas sucesivas del
        cronograma deben devolver EXACTAMENTE el mismo orden."""
        for seccion in ORDEN_ESPERADO:
            ProgramacionFase.objects.create(proyecto=proyecto_242, seccion=seccion)

        view = CronogramaView()
        view.kwargs = {'proyecto_id': proyecto_242.id}
        primera = list(view.get_context_data()['fases'].values_list('seccion', flat=True))
        segunda = list(view.get_context_data()['fases'].values_list('seccion', flat=True))
        assert primera == segunda == ORDEN_ESPERADO


@pytest.mark.django_db
class TestMatrizLegacyCronograma242:
    """Regresión de la forma de datos que recibe el cronograma.

    Cada fuente se mantiene independiente porque los proyectos existentes no
    necesariamente tienen cargados todos los módulos a la vez.  En particular,
    ``0.0`` es un avance real registrado, mientras ``None`` significa que la
    fuente todavía no tiene filas y debe renderizarse como ``Sin datos``.
    """

    def test_nueve_fuentes_conservan_valor_y_orden_en_registro_legacy(
        self, proyecto_242,
    ):
        """Un proyecto existente puede mezclar avances, cero y módulos vacíos."""
        valores_legacy = {
            'INGENIERIA': 100.0,
            'SOCIOPREDIAL': 0.0,
            'SOCIOAMBIENTAL': 50.0,
            'OBRA_CIVIL': 25.0,
            'MONTAJE': 75.0,
            'SPT': 0.0,
            'TENDIDO': 62.5,
            'PROTECCIONES': None,
            'PRUEBAS': 100.0,
        }
        fuentes = {
            '_pct_ingenieria': valores_legacy['INGENIERIA'],
            '_pct_sociopredial': valores_legacy['SOCIOPREDIAL'],
            '_pct_socioambiental': valores_legacy['SOCIOAMBIENTAL'],
            '_pct_obra_civil': valores_legacy['OBRA_CIVIL'],
            '_pct_montaje': valores_legacy['MONTAJE'],
            '_pct_spt_pintura': valores_legacy['SPT'],
            '_pct_tendido': valores_legacy['TENDIDO'],
            '_pct_protecciones': valores_legacy['PROTECCIONES'],
            '_pct_detalles_finales': valores_legacy['PRUEBAS'],
        }

        # ``FASES_GENERAL`` guarda referencias a las funciones. Se reemplaza
        # temporalmente por las nueve fuentes que un proyecto legado puede
        # entregar, sin consultar ni fabricar datos de producción.
        matriz_legacy = [
            (seccion, etiqueta, lambda _proyecto, valor=fuentes[nombre]: valor)
            for (seccion, etiqueta, _fn), nombre in zip(
                car.FASES_GENERAL,
                fuentes,
            )
        ]
        with patch.object(car, 'FASES_GENERAL', matriz_legacy):
            fases = car.avance_general(proyecto_242)['fases']

        assert [fase['seccion'] for fase in fases] == ORDEN_ESPERADO
        assert {fase['seccion']: fase['pct'] for fase in fases} == valores_legacy

    def test_sin_fuentes_en_legacy_no_se_convierte_en_cero(self, proyecto_242):
        """Borde: un proyecto anterior sin módulo conserva ``SIN_DATA``."""
        resultado = car.avance_general(proyecto_242)

        assert all(fase['pct'] is None for fase in resultado['fases'])
        assert resultado['global_pct'] is None
