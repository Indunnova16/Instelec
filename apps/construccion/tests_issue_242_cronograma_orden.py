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
import pytest

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
