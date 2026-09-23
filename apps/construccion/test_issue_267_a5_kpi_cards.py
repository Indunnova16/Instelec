"""Instelec#267 — A5: 4 KPI Cards ejecutivos (Ingreso/Costos Fijos/Costos
Variables/Resultado) por Clasificación real (issue Fase 4).

``PresupuestoPlaneadoConstruccionView._resumen_presupuesto``/``_sumar_seccion``
agrupan por las secciones LEGACY ``ingreso``/``variables``/``fijos`` del
formato de columnas-por-mes (``PresupuestoConstruccionExcelImporter``) — el
formato plano nuevo del cliente (A2, ``PresupuestoPlanoConstruccionExcelImporter``)
NO produce esas secciones, solo ``finv2_bd`` (agregado por rubro, sin
Clasificación) + ``filas_detalle`` (crudo, CON Clasificación por fila).

A5 agrega ``_kpi_cards_finv2_bd`` — agrupa ``filas_detalle`` por Clasificación
real:
    INGRESO          = SUM(valor) Clasificacion == 'Ingresos'
    COSTOS_FIJOS      = SUM(valor) Clasificacion == 'Fijo'
    COSTOS_VARIABLES  = SUM(valor) Clasificacion == 'Variable'
    RESULTADO         = INGRESO - (COSTOS_FIJOS + COSTOS_VARIABLES)

Cobertura:
- Unit (sin BD): caso EXACTO del issue (Fase 4, 4 valores literales),
  agregación de ≥2 filas por Clasificación, normalización de Clasificación
  (mayúsculas/acentos/espacios — filas_detalle persiste el texto TAL CUAL lo
  tipeó el cliente, confirmado en test_issue_267_a2_importador_plano.py),
  Clasificación desconocida no rompe ni suma a ninguna card, sin
  filas_detalle (dato legacy) → ceros + tiene_filas_detalle=False.
- Integración (GET real): la vista de Construcción (Planeado) renderiza las
  4 etiquetas literales en mayúsculas (INGRESO/COSTOS FIJOS/COSTOS
  VARIABLES/RESULTADO) exigidas por el journey i267_a4_a5_pct_semaforo_kpi_cards,
  con los valores del caso EXACTO del issue.
- Regresión / dato legacy: un presupuesto SIN finv2_bd (formato legacy
  ingreso/variables/fijos, dato real pre-existente antes de #267) sigue
  respondiendo 200 y NO pinta las cards nuevas (nada que agrupar por
  Clasificación real).
"""
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from apps.construccion.models import ProyectoConstruccion
from apps.construccion.models_fin import PresupuestoDetalladoConstruccion
from apps.construccion.views_fin import _kpi_cards_finv2_bd
from apps.contratos.models import Contrato

User = get_user_model()


# ===========================================================================
# Unit — _kpi_cards_finv2_bd (sin BD)
# ===========================================================================
class KpiCardsFinv2BdTests(SimpleTestCase):
    def test_caso_exacto_del_issue_fase_4(self):
        """#267 Fase 4 — 4 valores LITERALES del ejemplo del issue.

        INGRESO: -$23.511.292.673 | COSTOS VARIABLES: +$2.813.662.061
        COSTOS FIJOS: +$4.243.284.093 | RESULTADO: -$30.568.238.827
        (Ingreso - Costos)
        """
        datos = {
            'finv2_bd': {
                'filas_detalle': [
                    {'rubro': 'Ingresos Operacionales', 'clasificacion': 'Ingresos',
                     'valor': -23_511_292_673.0, 'mes': 9, 'anio': 2026, 'ciudad': 'Barranquilla'},
                    {'rubro': 'Gastos de Personal', 'clasificacion': 'Fijo',
                     'valor': 4_243_284_093.0, 'mes': 9, 'anio': 2026, 'ciudad': 'Barranquilla'},
                    {'rubro': 'Materiales', 'clasificacion': 'Variable',
                     'valor': 2_813_662_061.0, 'mes': 9, 'anio': 2026, 'ciudad': 'Barranquilla'},
                ],
            }
        }
        kpi = _kpi_cards_finv2_bd(datos)
        self.assertEqual(kpi['ingreso'], Decimal('-23511292673.0'))
        self.assertEqual(kpi['costos_fijos'], Decimal('4243284093.0'))
        self.assertEqual(kpi['costos_variables'], Decimal('2813662061.0'))
        self.assertEqual(kpi['resultado'], Decimal('-30568238827.0'))
        self.assertTrue(kpi['tiene_filas_detalle'])

    def test_agrega_multiples_filas_de_la_misma_clasificacion(self):
        """≥2 filas 'Fijo' de rubros distintos se SUMAN en costos_fijos."""
        datos = {
            'finv2_bd': {
                'filas_detalle': [
                    {'rubro': 'Gastos de Personal', 'clasificacion': 'Fijo', 'valor': 1000.0},
                    {'rubro': 'Servicios Publicos', 'clasificacion': 'Fijo', 'valor': 500.0},
                    {'rubro': 'Arriendos', 'clasificacion': 'Variable', 'valor': 200.0},
                ],
            }
        }
        kpi = _kpi_cards_finv2_bd(datos)
        self.assertEqual(kpi['costos_fijos'], Decimal('1500.0'))
        self.assertEqual(kpi['costos_variables'], Decimal('200.0'))
        self.assertEqual(kpi['ingreso'], Decimal('0'))
        self.assertEqual(kpi['resultado'], Decimal('-1700.0'))

    def test_clasificacion_se_normaliza_mayusculas_acentos_espacios(self):
        """La Clasificación persiste TAL CUAL el cliente la tipeó (A2 no la
        normaliza al guardar) — el agrupador de A5 SÍ debe tolerar variaciones
        de mayúsculas/espacios/acentos, no solo el valor canónico 'Fijo'."""
        datos = {
            'finv2_bd': {
                'filas_detalle': [
                    {'rubro': 'R1', 'clasificacion': 'INGRESOS', 'valor': -100.0},
                    {'rubro': 'R2', 'clasificacion': '  fijo  ', 'valor': 40.0},
                    {'rubro': 'R3', 'clasificacion': 'Variable', 'valor': 10.0},
                ],
            }
        }
        kpi = _kpi_cards_finv2_bd(datos)
        self.assertEqual(kpi['ingreso'], Decimal('-100.0'))
        self.assertEqual(kpi['costos_fijos'], Decimal('40.0'))
        self.assertEqual(kpi['costos_variables'], Decimal('10.0'))

    def test_clasificacion_desconocida_no_rompe_ni_suma(self):
        """Dato legacy/corrupto con una Clasificación fuera del vocabulario
        fijo no lanza y no contamina ninguna de las 3 cards de entrada."""
        datos = {
            'finv2_bd': {
                'filas_detalle': [
                    {'rubro': 'R1', 'clasificacion': 'OtraCosa', 'valor': 999.0},
                    {'rubro': 'R2', 'clasificacion': 'Fijo', 'valor': 10.0},
                ],
            }
        }
        kpi = _kpi_cards_finv2_bd(datos)
        self.assertEqual(kpi['ingreso'], Decimal('0'))
        self.assertEqual(kpi['costos_fijos'], Decimal('10.0'))
        self.assertEqual(kpi['costos_variables'], Decimal('0'))

    def test_sin_filas_detalle_dato_legacy_ceros_y_flag_false(self):
        """Presupuesto legacy (secciones ingreso/variables/fijos, SIN
        finv2_bd) → 4 ceros + tiene_filas_detalle=False (el template NO
        pinta las cards nuevas)."""
        kpi = _kpi_cards_finv2_bd({'ingreso': {}, 'variables': {}, 'fijos': {}})
        self.assertEqual(kpi['ingreso'], Decimal('0'))
        self.assertEqual(kpi['costos_fijos'], Decimal('0'))
        self.assertEqual(kpi['costos_variables'], Decimal('0'))
        self.assertEqual(kpi['resultado'], Decimal('0'))
        self.assertFalse(kpi['tiene_filas_detalle'])

    def test_finv2_bd_sin_filas_detalle_key(self):
        """finv2_bd presente (rubros del contable, #120) pero SIN
        filas_detalle (importador contable no la produce) → mismo default
        seguro que el legacy."""
        kpi = _kpi_cards_finv2_bd({'finv2_bd': {'rubros': {'X': {'total': 1.0}}, 'total': 1.0}})
        self.assertFalse(kpi['tiene_filas_detalle'])
        self.assertEqual(kpi['ingreso'], Decimal('0'))

    def test_datos_none_no_rompe(self):
        kpi = _kpi_cards_finv2_bd(None)
        self.assertFalse(kpi['tiene_filas_detalle'])
        self.assertEqual(kpi['resultado'], Decimal('0'))


# ===========================================================================
# Integración — GET real (4 KPI cards renderizadas en la vista de Construcción)
# ===========================================================================
def _crear_proyecto(nombre='Proyecto A5 test #267'):
    contrato = Contrato.objects.create(
        codigo=f"CONS-{uuid.uuid4().hex[:10]}",
        nombre='Contrato test construcción #267 A5',
        unidad_negocio='CONSTRUCCION',
    )
    return ProyectoConstruccion.objects.create(contrato=contrato, nombre=nombre)


def _crear_usuario_admin():
    try:
        return User.objects.create_superuser(
            username=f'qa_267a5_{uuid.uuid4().hex[:6]}',
            email=f'qa_267a5_{uuid.uuid4().hex[:6]}@instelec.com', password='x',
        )
    except TypeError:
        user = User(is_superuser=True, is_staff=True)
        if hasattr(user, 'email'):
            user.email = f'qa_267a5_{uuid.uuid4().hex[:6]}@instelec.com'
        user.set_password('x')
        user.save()
        return user


def _filas_detalle_caso_issue():
    return [
        {'rubro': 'Ingresos Operacionales', 'clasificacion': 'Ingresos',
         'valor': -23_511_292_673.0, 'mes': 9, 'anio': 2026, 'ciudad': 'Barranquilla'},
        {'rubro': 'Gastos de Personal', 'clasificacion': 'Fijo',
         'valor': 4_243_284_093.0, 'mes': 9, 'anio': 2026, 'ciudad': 'Barranquilla'},
        {'rubro': 'Materiales', 'clasificacion': 'Variable',
         'valor': 2_813_662_061.0, 'mes': 9, 'anio': 2026, 'ciudad': 'Barranquilla'},
    ]


class PresupuestoPlaneadoKpiCardsRenderTests(TestCase):
    """GET real a la vista de Construcción con el caso EXACTO del issue (Fase 4)."""

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
            datos={'finv2_bd': {
                'rubros': {
                    'Ingresos Operacionales': {'total': -23_511_292_673.0, 'meses': {}, 'cuentas': []},
                    'Gastos de Personal': {'total': 4_243_284_093.0, 'meses': {}, 'cuentas': []},
                    'Materiales': {'total': 2_813_662_061.0, 'meses': {}, 'cuentas': []},
                },
                'total': -16_454_346_519.0,
                'filas_detalle': _filas_detalle_caso_issue(),
            }},
        )

    def test_4_kpi_cards_con_etiquetas_y_valores_del_issue(self):
        resp = self.client.get(self.url, {'anio': 2026})
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        # Etiquetas literales EXACTAS que el journey i267_a4_a5_pct_semaforo_kpi_cards
        # exige (assert_contains: INGRESO/COSTOS FIJOS/COSTOS VARIABLES/RESULTADO).
        self.assertIn('INGRESO', content)
        self.assertIn('COSTOS FIJOS', content)
        self.assertIn('COSTOS VARIABLES', content)
        self.assertIn('RESULTADO', content)
        # Selectores estables para QA/journeys futuros.
        self.assertIn('data-kpi="ingreso"', content)
        self.assertIn('data-kpi="costos_fijos"', content)
        self.assertIn('data-kpi="costos_variables"', content)
        self.assertIn('data-kpi="resultado"', content)
        # Valores formateados (es-co: punto como separador de miles).
        self.assertIn('23.511.292.673', content)
        self.assertIn('4.243.284.093', content)
        self.assertIn('2.813.662.061', content)
        self.assertIn('30.568.238.827', content)

    def test_dato_legacy_sin_finv2_bd_no_pinta_cards_pero_no_rompe(self):
        """Presupuesto legacy real pre-existente (secciones ingreso/variables/
        fijos, SIN finv2_bd/filas_detalle) sigue en 200 y NO muestra las 4
        cards nuevas (nada que agrupar por Clasificación real)."""
        PresupuestoDetalladoConstruccion.objects.filter(
            proyecto=self.proyecto, anio=2026,
        ).update(datos={'ingreso': {'Ventas': {'enero': 100}}, 'variables': {}, 'fijos': {}})
        resp = self.client.get(self.url, {'anio': 2026})
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertNotIn('data-kpi="ingreso"', content)

    def test_presupuesto_real_view_tambien_responde_200_sin_finv2_bd(self):
        """Espejo en la vista REAL (mismo partial compartido): sin finv2_bd
        propio, responde 200 y no rompe por kpi_cards ausente en el contexto
        de una vista que hoy no recibe cargas del formato plano."""
        url_real = reverse('construccion:fin_presupuesto_real',
                            kwargs={'proyecto_id': self.proyecto.pk})
        resp = self.client.get(url_real, {'anio': 2026})
        self.assertEqual(resp.status_code, 200)
