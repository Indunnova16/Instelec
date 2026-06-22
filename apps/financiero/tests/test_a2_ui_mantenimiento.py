"""A2 (#120) — UI Mantenimiento: vista bi-modal (matriz 12 meses + filtro mes).

Verifica la vista ``PresupuestoPlaneadoViewV2`` y el partial compartido
``_presupuesto_bimodal_tabla.html`` (también usado por Construcción en A3):

- happy: con datos contables bucketeados, ?vista=matriz renderiza la matriz
  rubro × 12 meses (encabezados julio..junio, contenedor [data-vista='matriz']).
- filtro mes: ?vista=mes&mes=julio renderiza el contenedor [data-vista='mes'] +
  el mes seleccionado en el select.
- edge (param inválido): ?vista=xxx cae a 'matriz'; ?mes=nofiscal cae a julio.
- empty state: sin datos contables → mensaje "Aún no hay datos contables".
- contexto: la view expone matrix_rows/meses_fiscales/mes_sel/vista coherentes.

Corre bajo dev_lite (spatialite). El partial reusa Alpine, no toca JS aparte.
"""
import pytest
from django.urls import reverse

from apps.financiero.importers_finv2 import MESES_FISCALES_KEYS
from apps.financiero.models import PresupuestoDetallado


def _datos_con_meses():
    """Estructura finv2_bd con buckets mensuales (como la deja A1)."""
    return {
        'finv2_bd': {
            'rubros': {
                'Ingresos Operacionales': {
                    'total': -175.0,
                    'meses': {'julio': -100.0, 'agosto': -50.0, 'enero': -25.0},
                    'cuentas': [],
                },
                'Personal': {
                    'total': 300.0,
                    'meses': {'septiembre': 200.0, 'marzo': 100.0},
                    'cuentas': [],
                },
            },
            'total': 125.0,
            'cuentas_count': 2,
            'cuentas_no_mapeadas': [],
            'filas_sin_mes': 0,
        }
    }


def _crear_presupuesto(anio, datos):
    return PresupuestoDetallado.objects.create(
        anio=anio, tipo='PLANEADO', contrato=None, datos=datos,
    )


@pytest.mark.django_db
class TestA2UIMantenimiento:

    def test_a2_happy_matriz_12_meses_render(self, client, admin_user):
        """?vista=matriz: render con contenedor matriz + encabezados fiscales."""
        client.force_login(admin_user)
        _crear_presupuesto(2026, _datos_con_meses())
        url = reverse('financiero:cargar_bd_contable')
        resp = client.get(f'{url}?anio=2026&tab=planeado&vista=matriz')
        assert resp.status_code == 200
        html = resp.content.decode()
        assert "data-vista=\"matriz\"" in html
        # Encabezados de los 12 meses fiscales (julio primero, junio último).
        assert 'Julio' in html and 'Junio' in html
        assert 'Ingresos Operacionales' in html
        # La columna TOTAL existe.
        assert 'TOTAL' in html

    def test_a2_filtro_mes_render(self, client, admin_user):
        """?vista=mes&mes=julio: render del contenedor de filtro mes."""
        client.force_login(admin_user)
        _crear_presupuesto(2026, _datos_con_meses())
        url = reverse('financiero:cargar_bd_contable')
        resp = client.get(f'{url}?anio=2026&tab=planeado&vista=mes&mes=julio')
        assert resp.status_code == 200
        html = resp.content.decode()
        assert "data-vista=\"mes\"" in html
        assert resp.context['vista'] == 'mes'
        assert resp.context['mes_sel'] == 'julio'
        # Solo Ingresos Operacionales tuvo movimiento en julio.
        assert any(r['rubro'] == 'Ingresos Operacionales'
                   for r in resp.context['mes_rows'])

    def test_a2_edge_vista_invalida_cae_a_matriz(self, client, admin_user):
        """?vista=xxx (no válida) → la view normaliza a 'matriz'."""
        client.force_login(admin_user)
        _crear_presupuesto(2026, _datos_con_meses())
        url = reverse('financiero:cargar_bd_contable')
        resp = client.get(f'{url}?anio=2026&tab=planeado&vista=xxx')
        assert resp.status_code == 200
        assert resp.context['vista'] == 'matriz'

    def test_a2_edge_mes_invalido_cae_a_primer_mes_fiscal(self, client, admin_user):
        """?mes=nofiscal → la view cae al primer mes fiscal (julio)."""
        client.force_login(admin_user)
        _crear_presupuesto(2026, _datos_con_meses())
        url = reverse('financiero:cargar_bd_contable')
        resp = client.get(f'{url}?anio=2026&tab=planeado&vista=mes&mes=nofiscal')
        assert resp.status_code == 200
        assert resp.context['mes_sel'] == MESES_FISCALES_KEYS[0]

    def test_a2_empty_state_sin_datos(self, client, admin_user):
        """Sin presupuesto cargado → empty state, sin matriz."""
        client.force_login(admin_user)
        url = reverse('financiero:cargar_bd_contable')
        resp = client.get(f'{url}?anio=2099&tab=planeado&vista=matriz')
        assert resp.status_code == 200
        assert resp.context['tiene_datos_bd'] is False
        html = resp.content.decode()
        assert 'Aún no hay datos contables' in html

    def test_a2_contexto_matrix_rows_coherente(self, client, admin_user):
        """La view expone matrix_rows con 12 valores por fila + totales_columna."""
        client.force_login(admin_user)
        _crear_presupuesto(2026, _datos_con_meses())
        url = reverse('financiero:cargar_bd_contable')
        resp = client.get(f'{url}?anio=2026&tab=planeado&vista=matriz')
        ctx = resp.context
        assert len(ctx['meses_fiscales']) == 12
        assert len(ctx['totales_columna']) == 12
        for fila in ctx['matrix_rows']:
            assert len(fila['meses']) == 12
        # Total de columna julio = -100 (solo Ingresos Operacionales).
        idx_julio = MESES_FISCALES_KEYS.index('julio')
        assert ctx['totales_columna'][idx_julio] == -100.0

    def test_a2_base_qs_preserva_anio_y_tab(self, client, admin_user):
        """bimodal_base_qs / hidden params preservan anio+tab al togglear."""
        client.force_login(admin_user)
        _crear_presupuesto(2026, _datos_con_meses())
        url = reverse('financiero:cargar_bd_contable')
        resp = client.get(f'{url}?anio=2026&tab=planeado&vista=matriz')
        base_qs = resp.context['bimodal_base_qs']
        assert 'anio=2026' in base_qs
        assert 'tab=planeado' in base_qs
        # vista/mes NO deben estar en el base (los agrega el enlace).
        assert 'vista=' not in base_qs
