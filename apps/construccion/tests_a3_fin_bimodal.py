"""A3 (#120) — UI Construcción: espejo bi-modal (matriz 12 meses + filtro mes).

``PresupuestoPlaneadoConstruccionView`` debe exponer el MISMO contrato bi-modal
que el lado Mantenimiento (A2), alimentando el partial COMPARTIDO
``financiero/_presupuesto_bimodal_tabla.html``. Cubre:

- happy: con datos finv2_bd bucketeados, ?vista=matriz renderiza la matriz +
  contenedor [data-vista='matriz'] + meses fiscales.
- filtro mes: ?vista=mes&mes=julio → contenedor [data-vista='mes'] + mes_sel.
- edge: ?vista=xxx → 'matriz'; ?mes=nofiscal → primer mes fiscal.
- empty state: presupuesto sin finv2_bd → tiene_datos_bd False (empty).
- contexto: matrix_rows con 12 valores/fila + totales_columna de 12.

Mismo estilo que tests_b4_fin_views.py (TestCase + superuser que pasa
RoleRequiredMixin + SubModuloRequiredMixin). Archivo por-issue (flat, no toca
el tests.py compartido).
"""
import uuid

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.contratos.models import Contrato
from apps.construccion.models import ProyectoConstruccion
from apps.construccion.models_fin import PresupuestoDetalladoConstruccion
from apps.financiero.importers_finv2 import MESES_FISCALES_KEYS

User = get_user_model()


def _datos_con_meses():
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


class TestA3FinBimodalConstruccion(TestCase):
    ANIO = 2026

    def setUp(self):
        contrato = Contrato.objects.create(
            codigo=f"CONS-{uuid.uuid4().hex[:10]}",
            nombre='Contrato test A3 #120',
            unidad_negocio='CONSTRUCCION',
        )
        self.proyecto = ProyectoConstruccion.objects.create(
            contrato=contrato, nombre='Proyecto A3 bi-modal',
        )
        try:
            self.user = User.objects.create_superuser(
                username='qa_a3', email='qa_a3@instelec.com', password='x',
            )
        except TypeError:
            self.user = User(is_superuser=True, is_staff=True)
            if hasattr(self.user, 'email'):
                self.user.email = 'qa_a3@instelec.com'
            self.user.set_password('x')
            self.user.save()
        self.client = Client()
        self.client.force_login(self.user)

    def _url(self):
        return reverse('construccion:fin_presupuesto_planeado',
                       kwargs={'proyecto_id': self.proyecto.id})

    def _crear_presupuesto(self, datos):
        return PresupuestoDetalladoConstruccion.objects.create(
            proyecto=self.proyecto, anio=self.ANIO,
            tipo=PresupuestoDetalladoConstruccion.Tipo.PLANEADO, datos=datos,
        )

    # ----- happy --------------------------------------------------------- #
    def test_a3_happy_matriz_render(self):
        self._crear_presupuesto(_datos_con_meses())
        resp = self.client.get(f'{self._url()}?anio={self.ANIO}&vista=matriz')
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('data-vista="matriz"', html)
        self.assertIn('Julio', html)
        self.assertIn('Junio', html)
        self.assertIn('Ingresos Operacionales', html)
        self.assertEqual(resp.context['vista'], 'matriz')

    def test_a3_filtro_mes_render(self):
        self._crear_presupuesto(_datos_con_meses())
        resp = self.client.get(
            f'{self._url()}?anio={self.ANIO}&vista=mes&mes=julio')
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('data-vista="mes"', html)
        self.assertEqual(resp.context['mes_sel'], 'julio')
        self.assertTrue(any(r['rubro'] == 'Ingresos Operacionales'
                            for r in resp.context['mes_rows']))

    # ----- edge ---------------------------------------------------------- #
    def test_a3_edge_vista_invalida_cae_a_matriz(self):
        self._crear_presupuesto(_datos_con_meses())
        resp = self.client.get(f'{self._url()}?anio={self.ANIO}&vista=zzz')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['vista'], 'matriz')

    def test_a3_edge_mes_invalido_cae_a_primer_mes(self):
        self._crear_presupuesto(_datos_con_meses())
        resp = self.client.get(
            f'{self._url()}?anio={self.ANIO}&vista=mes&mes=nofiscal')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['mes_sel'], MESES_FISCALES_KEYS[0])

    # ----- empty --------------------------------------------------------- #
    def test_a3_empty_sin_finv2_bd(self):
        """Presupuesto sin finv2_bd → tiene_datos_bd False (empty del partial)."""
        self._crear_presupuesto({'ingreso': {'enero': 100}})
        resp = self.client.get(f'{self._url()}?anio={self.ANIO}&vista=matriz')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context['tiene_datos_bd'])
        self.assertEqual(resp.context['matrix_rows'], [])

    # ----- contexto ------------------------------------------------------ #
    def test_a3_contexto_matrix_coherente(self):
        self._crear_presupuesto(_datos_con_meses())
        resp = self.client.get(f'{self._url()}?anio={self.ANIO}&vista=matriz')
        ctx = resp.context
        self.assertEqual(len(ctx['meses_fiscales']), 12)
        self.assertEqual(len(ctx['totales_columna']), 12)
        for fila in ctx['matrix_rows']:
            self.assertEqual(len(fila['meses']), 12)
        idx_julio = MESES_FISCALES_KEYS.index('julio')
        self.assertEqual(ctx['totales_columna'][idx_julio], -100.0)

    def test_a3_proyecto_inexistente_404(self):
        url = reverse('construccion:fin_presupuesto_planeado',
                      kwargs={'proyecto_id': uuid.uuid4()})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)
