"""#150 (rebote): "no aplica" por CASILLA en Actividades Finales (además de por fila)."""
import pytest

from apps.contratos.models import Contrato
from apps.construccion.models import ProyectoConstruccion, TorreConstruccion
from apps.construccion.models_b1_actividades_finales import (
    ActividadFinalTorre, ACTIVIDAD_CAMPOS,
)


@pytest.fixture
def torre(db):
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo="CT-AF-150", nombre="AF", cliente="C", estado=Contrato.Estado.ACTIVO,
    )
    proyecto = ProyectoConstruccion.objects.create(
        contrato=contrato, nombre="AF", estado="EJECUCION")
    return TorreConstruccion.objects.create(proyecto=proyecto, numero="T001", tipo="A")


@pytest.mark.django_db
class TestNoAplicaPorCasilla150:
    def test_casilla_no_aplica_excluye_del_total(self, torre):
        af = ActividadFinalTorre.objects.create(torre=torre)
        assert af.total_actividades == len(ACTIVIDAD_CAMPOS)  # 13
        # Marcar una casilla como "no aplica" → baja el total a 12.
        af.empalmes_subestacion_no_aplica = True
        af.save()
        af.refresh_from_db()
        assert af.total_actividades == len(ACTIVIDAD_CAMPOS) - 1  # 12

    def test_completas_excluye_casilla_no_aplica(self, torre):
        af = ActividadFinalTorre.objects.create(torre=torre)
        # Completar 1 actividad y marcar OTRA como no aplica.
        af.empalmes_subestacion = True
        af.empalmes_intermedios_no_aplica = True
        af.save()
        af.refresh_from_db()
        # completas = 1 (la marcada no_aplica no cuenta aunque estuviera en True)
        assert af.actividades_completas == 1
        # pct = 1 / 12 (total excluye la no_aplica)
        assert round(af.pct_avance, 2) == round(100 / 12, 2)

    def test_no_aplica_en_true_no_cuenta_como_completa(self, torre):
        af = ActividadFinalTorre.objects.create(torre=torre)
        # Una casilla en True pero marcada no_aplica NO debe contar como completa.
        af.empalmes_subestacion = True
        af.empalmes_subestacion_no_aplica = True
        af.save()
        af.refresh_from_db()
        assert af.actividades_completas == 0

    def test_fila_aplica_sigue_funcionando(self, torre):
        # El flag de FILA (aplica=False) sigue dando 100% (no pendiente).
        af = ActividadFinalTorre.objects.create(torre=torre, aplica=False)
        assert af.pct_avance == 100.0
