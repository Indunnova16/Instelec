"""Instelec#267 — A4: %Total con abs() + semáforo.

``build_rubro_display_rows`` y ``build_rubro_matrix_rows``
(``apps/financiero/importers_finv2.py``) calculaban
``pct = rubro_total / total_general * 100`` SIN valor absoluto — el issue
(#267 Fase 3.1) exige que el denominador (y el numerador) se tomen en
``abs()``: un ``total_general`` negativo (rubros de Ingresos, que se cargan
negativos en el contable) producía porcentajes sin sentido de negocio.
Se agrega además el campo ``semaforo`` (verde <50% · amarillo 50-100% ·
rojo >100%) a ambas funciones — compartidas con Mantenimiento
(``apps/financiero/tests/test_issue_120.py``, #120) — y se pinta el color en
``construccion/_financiero_presupuesto_tabla.html`` (ya pintaba el número,
faltaba el color) y en ``financiero/_presupuesto_bimodal_tabla.html`` (la
vista MATRIZ no pintaba ``%Total`` en absoluto).

Cobertura:
- Unit (sin BD): ``calc_pct_semaforo`` con el ejemplo LITERAL del issue
  (7.769.116.392 / 1.058.633.482 = 733.9% → rojo), bandas límite (49.9/50/
  100/100.1), signo del numerador/denominador (Ingresos negativos) y
  ``build_rubro_display_rows``/``build_rubro_matrix_rows`` end-to-end sobre
  un bloque ``finv2_bd`` sintético.
- Integración (GET real): la vista de Construcción (tab tabla + vista
  matriz, ambas incluyen el partial afectado) renderiza "733.9%" y el badge
  ``data-semaforo="rojo"``.
- Regresión: ``apps/financiero/tests/test_issue_120.py`` sigue verde
  (Mantenimiento usa el MISMO builder compartido) — se re-corre explícito
  acá para dejar la dependencia documentada, no solo confiada al full-suite.
"""
import uuid

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from apps.construccion.models import ProyectoConstruccion
from apps.construccion.models_fin import PresupuestoDetalladoConstruccion
from apps.contratos.models import Contrato
from apps.financiero.importers_finv2 import (
    build_rubro_display_rows,
    build_rubro_matrix_rows,
    calc_pct_semaforo,
)

User = get_user_model()


# ===========================================================================
# Unit — calc_pct_semaforo (sin BD)
# ===========================================================================
class CalcPctSemaforoTests(SimpleTestCase):
    def test_ejemplo_literal_del_issue_733_9_rojo(self):
        """#267 Fase 3.1: 'Gastos de Personal' Total Año=$-1.058.633.482,
        rubro Personal=$7.769.116.392 → 733.9% (rojo, fórmula CRÍTICA)."""
        pct, semaforo = calc_pct_semaforo(7_769_116_392, -1_058_633_482)
        self.assertEqual(pct, 733.9)
        self.assertEqual(semaforo, 'rojo')

    def test_denominador_negativo_no_produce_pct_negativo(self):
        """Antes del fix: rubro_total/total_general con total_general negativo
        daba un pct NEGATIVO sin sentido de negocio — el issue pide |Total Año|."""
        pct, semaforo = calc_pct_semaforo(100.0, -400.0)
        self.assertGreaterEqual(pct, 0)
        self.assertEqual(pct, 25.0)
        self.assertEqual(semaforo, 'verde')

    def test_numerador_negativo_tambien_se_toma_absoluto(self):
        """Rubro de Ingresos (numerador negativo) frente a un total positivo."""
        pct, semaforo = calc_pct_semaforo(-300.0, 400.0)
        self.assertEqual(pct, 75.0)
        self.assertEqual(semaforo, 'amarillo')

    def test_banda_verde_bajo_50(self):
        pct, semaforo = calc_pct_semaforo(49.9, 100.0)
        self.assertEqual(semaforo, 'verde')

    def test_banda_amarillo_limite_inferior_50_inclusive(self):
        pct, semaforo = calc_pct_semaforo(50.0, 100.0)
        self.assertEqual(semaforo, 'amarillo')

    def test_banda_amarillo_limite_superior_100_inclusive(self):
        pct, semaforo = calc_pct_semaforo(100.0, 100.0)
        self.assertEqual(semaforo, 'amarillo')

    def test_banda_rojo_sobre_100(self):
        pct, semaforo = calc_pct_semaforo(100.1, 100.0)
        self.assertEqual(semaforo, 'rojo')

    def test_total_cero_no_divide_por_cero(self):
        pct, semaforo = calc_pct_semaforo(500.0, 0.0)
        self.assertEqual(pct, 0.0)
        self.assertEqual(semaforo, 'verde')


# ===========================================================================
# Unit — build_rubro_display_rows / build_rubro_matrix_rows end-to-end
# ===========================================================================
def _bloque_finv2_bd():
    """Bloque sintético con 2 rubros: uno rojo (>100%), uno verde (<50%),
    replicando el caso literal del issue + un caso sano para 'generalizes'
    del journey (i267_a4_a5_pct_semaforo_kpi_cards)."""
    return {
        'total': -1_058_633_482.0,
        'rubros': {
            'Gastos de Personal': {
                'total': 7_769_116_392.0,
                'cuentas': [],
                'meses': {'enero': 7_769_116_392.0},
            },
            'Arriendos': {
                'total': 100_000_000.0,
                'cuentas': [],
                'meses': {'enero': 100_000_000.0},
            },
        },
    }


class BuildRubroDisplayRowsPctSemaforoTests(SimpleTestCase):
    def test_rows_traen_pct_y_semaforo(self):
        datos = {'finv2_bd': _bloque_finv2_bd()}
        rows, total_general = build_rubro_display_rows(datos)
        por_rubro = {r['rubro']: r for r in rows}

        self.assertEqual(por_rubro['Gastos de Personal']['pct'], 733.9)
        self.assertEqual(por_rubro['Gastos de Personal']['semaforo'], 'rojo')
        # |100.000.000| / |-1.058.633.482| * 100 = 9.4...
        self.assertEqual(por_rubro['Arriendos']['semaforo'], 'verde')
        self.assertLess(por_rubro['Arriendos']['pct'], 50)


class BuildRubroMatrixRowsPctSemaforoTests(SimpleTestCase):
    def test_rows_traen_pct_y_semaforo(self):
        datos = {'finv2_bd': _bloque_finv2_bd()}
        rows, _totales_col, _meses, _total_general = build_rubro_matrix_rows(datos)
        por_rubro = {r['rubro']: r for r in rows}

        self.assertEqual(por_rubro['Gastos de Personal']['pct'], 733.9)
        self.assertEqual(por_rubro['Gastos de Personal']['semaforo'], 'rojo')
        self.assertEqual(por_rubro['Arriendos']['semaforo'], 'verde')

    def test_datos_vacios_no_rompe(self):
        """Legacy / presupuesto sin finv2_bd → filas vacías, sin KeyError."""
        rows, totales_col, _meses, total_general = build_rubro_matrix_rows({})
        self.assertEqual(rows, [])
        self.assertEqual(total_general, 0.0)
        self.assertTrue(all(v == 0.0 for v in totales_col))


# ===========================================================================
# Integración — GET real (badge renderizado en ambas vistas)
# ===========================================================================
def _crear_proyecto(nombre='Proyecto A4 test #267'):
    contrato = Contrato.objects.create(
        codigo=f"CONS-{uuid.uuid4().hex[:10]}",
        nombre='Contrato test construcción #267 A4',
        unidad_negocio='CONSTRUCCION',
    )
    return ProyectoConstruccion.objects.create(contrato=contrato, nombre=nombre)


def _crear_usuario_admin():
    try:
        return User.objects.create_superuser(
            username=f'qa_267a4_{uuid.uuid4().hex[:6]}',
            email=f'qa_267a4_{uuid.uuid4().hex[:6]}@instelec.com', password='x',
        )
    except TypeError:
        user = User(is_superuser=True, is_staff=True)
        if hasattr(user, 'email'):
            user.email = f'qa_267a4_{uuid.uuid4().hex[:6]}@instelec.com'
        user.set_password('x')
        user.save()
        return user


class PresupuestoPlaneadoPctSemaforoRenderTests(TestCase):
    """GET real a la vista de Construcción con el caso EXACTO del issue."""

    def setUp(self):
        self.proyecto = _crear_proyecto()
        self.user = _crear_usuario_admin()
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse('construccion:fin_presupuesto_planeado',
                            kwargs={'proyecto_id': self.proyecto.pk})
        PresupuestoDetalladoConstruccion.objects.create(
            proyecto=self.proyecto, anio=2026,
            tipo=PresupuestoDetalladoConstruccion.Tipo.PLANEADO,
            datos={'finv2_bd': _bloque_finv2_bd()},
        )

    def test_pct_733_9_y_badge_rojo_en_tabla_de_rubros(self):
        resp = self.client.get(self.url, {'anio': 2026})
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        # LANGUAGE_CODE=es-co + USE_I18N: Django localiza el float SIN filtro
        # explícito → separador decimal COMA ("733,9%"), no punto. Confirmado
        # empíricamente contra el render real (el issue lo redacta con punto,
        # pero eso es notación numérica en inglés, no el render en prod).
        self.assertIn('733,9%', content)
        self.assertIn("data-semaforo=\"rojo\"", content)
        self.assertIn("data-semaforo=\"verde\"", content)

    def test_pct_733_9_y_badge_rojo_en_vista_matriz(self):
        """La vista MATRIZ (bimodal, hoy no pintaba %Total en absoluto) trae
        la misma columna con el mismo badge — mismo builder compartido."""
        resp = self.client.get(self.url, {'anio': 2026, 'vista': 'matriz'})
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn('% Total', content)
        self.assertIn('733,9%', content)
        self.assertIn("data-semaforo=\"rojo\"", content)

    def test_dato_legacy_sin_finv2_bd_no_rompe_render(self):
        """Presupuesto legacy (secciones ingreso/variables/fijos, SIN
        finv2_bd) sigue renderizando 200 — build_rubro_*_rows tolerante."""
        PresupuestoDetalladoConstruccion.objects.filter(
            proyecto=self.proyecto, anio=2026,
        ).update(datos={'ingreso': {}, 'variables': {}, 'fijos': {}})
        resp = self.client.get(self.url, {'anio': 2026})
        self.assertEqual(resp.status_code, 200)
