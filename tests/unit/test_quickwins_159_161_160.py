"""#159 (orden numérico), #161 (pendiente@100), #160 (torre no aplica)."""
import pytest
from decimal import Decimal

from apps.construccion.calculators_avance_real import vista_por_torre, FASE_OOCC
from apps.construccion.tests_b1_dashboard_oc import (
    proyecto_oc, _torre, _oc_detalle, _torre_oc_completa,
)


@pytest.mark.django_db
class TestQuickWins:
    def test_159_orden_numerico_natural(self, proyecto_oc):
        # Crear en desorden: E10, E2, E1 → debe salir E1, E2, E10 (no E1,E10,E2).
        for n in ('E10', 'E2', 'E1'):
            t = _torre(proyecto_oc, n)
            _oc_detalle(proyecto_oc, t, 'A')  # pata sin avance
        filas = vista_por_torre(proyecto_oc, FASE_OOCC)
        numeros = [f['numero'] for f in filas]
        assert numeros == ['E1', 'E2', 'E10'], numeros

    def test_161_torre_100_sin_pendientes(self, proyecto_oc):
        _torre_oc_completa(proyecto_oc, 'E1')
        filas = vista_por_torre(proyecto_oc, FASE_OOCC)
        f = [x for x in filas if x['numero'] == 'E1'][0]
        assert f['completa'] is True
        assert f['pct'] >= 100.0
        assert f['pendientes'] == []   # #161: nada pendiente al 100%

    def test_161_torre_incompleta_si_muestra_pendientes(self, proyecto_oc):
        t = _torre(proyecto_oc, 'E1')
        _oc_detalle(proyecto_oc, t, 'A', cerr_finalizado_ok=True)  # solo cerramiento
        filas = vista_por_torre(proyecto_oc, FASE_OOCC)
        f = [x for x in filas if x['numero'] == 'E1'][0]
        assert f['completa'] is False
        assert len(f['pendientes']) > 0

    def test_160_torre_no_aplica_excluida(self, proyecto_oc):
        t1 = _torre_oc_completa(proyecto_oc, 'E1')
        t2 = _torre_oc_completa(proyecto_oc, 'E2')
        # Marcar E2 como "no aplica" → no debe aparecer en la vista por torre.
        t2.aplica = False
        t2.save(update_fields=['aplica'])
        filas = vista_por_torre(proyecto_oc, FASE_OOCC)
        numeros = [f['numero'] for f in filas]
        assert 'E1' in numeros
        assert 'E2' not in numeros
