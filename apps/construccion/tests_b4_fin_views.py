"""B4 (#123) — Tests de las 6 vistas financieras de Construcción.

ESCRITOS pero NO corridos en F3 (no hay Django local en este entorno) —
``tests_passing``: ``deferred_to_f4_docker``. F4 los corre dentro del contenedor.

tests_e2e del BLUEPRINT:
  b4_fin_dashboard_200, b4_presupuesto_planeado_200, b4_presupuesto_real_200,
  b4_nomina_200, b4_costos_200, b4_facturacion_200.

Cobertura adicional:
- ProyectoFinMixin → 404 con proyecto inexistente.
- Context completo del dashboard (resumen_planeado/real, indicadores, ANS).
- Querystring anio/mes inválido no rompe (edge case _parse_periodo).
- Filtro por tipo_recurso en costos.
- Dato legacy: un ProyectoConstruccion sin presupuesto detallado abre el
  dashboard en ceros (sin 500).
"""
import uuid
from decimal import Decimal

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from apps.contratos.models import Contrato
from apps.construccion.models import ProyectoConstruccion
from apps.construccion.models_fin import (
    PresupuestoDetalladoConstruccion,
    CostosConstruccion,
    FacturacionConstruccion,
    IndicadorANSConstruccion,
)

# El modelo de usuario varía por proyecto (RBAC v2). Se obtiene dinámicamente.
from django.contrib.auth import get_user_model

User = get_user_model()


def _crear_proyecto(nombre='Proyecto LT 230kV test'):
    contrato = Contrato.objects.create(
        codigo=f"CONS-{uuid.uuid4().hex[:10]}",
        nombre='Contrato test construcción B4',
        unidad_negocio='CONSTRUCCION',
    )
    return ProyectoConstruccion.objects.create(contrato=contrato, nombre=nombre)


def _crear_usuario_admin():
    """Usuario que pasa RoleRequiredMixin + SubModuloRequiredMixin.

    Se usa superuser para garantizar acceso (RBAC v2: superuser pasa todos los
    gates). El campo username puede variar; se prueba defensivamente.
    """
    kwargs = {'is_superuser': True, 'is_staff': True}
    try:
        return User.objects.create_superuser(
            username='qa_b4', email='qa_b4@instelec.com', password='x',
        )
    except TypeError:
        # Modelos custom sin username (USERNAME_FIELD=email u otro).
        user = User(**kwargs)
        if hasattr(user, 'email'):
            user.email = 'qa_b4@instelec.com'
        user.set_password('x')
        user.save()
        return user


class _BaseFinViewTest(TestCase):
    def setUp(self):
        self.proyecto = _crear_proyecto()
        self.user = _crear_usuario_admin()
        self.client = Client()
        self.client.force_login(self.user)

    def _url(self, name):
        return reverse(f'construccion:{name}',
                       kwargs={'proyecto_id': self.proyecto.id})


class TestB4FinDashboard(_BaseFinViewTest):
    """tests_e2e: b4_fin_dashboard_200."""

    def test_b4_fin_dashboard_200(self):
        resp = self.client.get(self._url('fin_dashboard'))
        self.assertEqual(resp.status_code, 200)
        for key in ('proyecto', 'resumen_planeado', 'resumen_real',
                    'indicadores_tecnico_financieros', 'indicadores_ans',
                    'resumen_ans', 'anio', 'mes'):
            self.assertIn(key, resp.context)
        # 6 indicadores técnico-financieros (#122).
        self.assertEqual(len(resp.context['indicadores_tecnico_financieros']), 6)

    def test_dashboard_con_presupuesto_y_ans(self):
        PresupuestoDetalladoConstruccion.objects.create(
            proyecto=self.proyecto, anio=timezone.now().year,
            tipo=PresupuestoDetalladoConstruccion.Tipo.PLANEADO,
            datos={'ingreso': {'enero': 1000}, 'variables': {'enero': 400},
                   'fijos': {'enero': 200}},
        )
        IndicadorANSConstruccion.objects.create(
            proyecto=self.proyecto, nombre='Programación',
            meta_porcentaje=Decimal('95'), valor_actual=Decimal('50'),
            periodo_anio=timezone.now().year, periodo_mes=timezone.now().month,
        )
        resp = self.client.get(self._url('fin_dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['resumen_planeado']['ingreso'], Decimal('1000'))
        self.assertEqual(resp.context['resumen_planeado']['total_gastos'], Decimal('600'))
        self.assertEqual(len(resp.context['indicadores_ans']), 1)

    def test_proyecto_inexistente_404(self):
        url = reverse('construccion:fin_dashboard',
                      kwargs={'proyecto_id': uuid.uuid4()})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    def test_anio_mes_invalido_no_rompe(self):
        # Edge case: querystring inválido → fallback a hoy, no 500.
        resp = self.client.get(self._url('fin_dashboard') + '?anio=abc&mes=99')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['anio'], timezone.now().year)


class TestB4PresupuestoPlaneado(_BaseFinViewTest):
    """tests_e2e: b4_presupuesto_planeado_200."""

    def test_b4_presupuesto_planeado_200(self):
        resp = self.client.get(self._url('fin_presupuesto_planeado'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['tipo'], 'PLANEADO')
        self.assertTrue(resp.context['sin_datos'])  # sin presupuesto aún

    def test_planeado_con_datos(self):
        PresupuestoDetalladoConstruccion.objects.create(
            proyecto=self.proyecto, anio=timezone.now().year,
            tipo=PresupuestoDetalladoConstruccion.Tipo.PLANEADO,
            datos={'ingreso': {'enero': 500}},
        )
        resp = self.client.get(self._url('fin_presupuesto_planeado'))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context['sin_datos'])
        self.assertEqual(resp.context['resumen']['ingreso'], Decimal('500'))


class TestB4PresupuestoReal(_BaseFinViewTest):
    """tests_e2e: b4_presupuesto_real_200."""

    def test_b4_presupuesto_real_200(self):
        resp = self.client.get(self._url('fin_presupuesto_real'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['tipo'], 'REAL')
        self.assertIn('total_costos_registrados', resp.context)

    def test_real_cruza_costos(self):
        CostosConstruccion.objects.create(
            proyecto=self.proyecto, concepto='Cemento',
            cantidad=Decimal('10'), costo_unitario=Decimal('100'),
            fecha=timezone.now().date(),
        )
        resp = self.client.get(self._url('fin_presupuesto_real'))
        self.assertEqual(resp.status_code, 200)
        # costo_total = 10 * 100 = 1000 (auto en save()).
        self.assertEqual(resp.context['total_costos_registrados'], Decimal('1000.00'))


class TestB4Nomina(_BaseFinViewTest):
    """tests_e2e: b4_nomina_200."""

    def test_b4_nomina_200(self):
        resp = self.client.get(self._url('fin_nomina'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('costos_mano_obra', resp.context)
        self.assertTrue(resp.context['sin_datos'])

    def test_nomina_suma_mano_obra(self):
        CostosConstruccion.objects.create(
            proyecto=self.proyecto, concepto='Cuadrilla A',
            tipo_recurso=CostosConstruccion.TipoRecurso.MANO_OBRA,
            cantidad=Decimal('1'), costo_unitario=Decimal('2000'),
            fecha=timezone.now().date(),
        )
        # Un costo MATERIAL no debe contar en nómina.
        CostosConstruccion.objects.create(
            proyecto=self.proyecto, concepto='Acero',
            tipo_recurso=CostosConstruccion.TipoRecurso.MATERIAL,
            cantidad=Decimal('1'), costo_unitario=Decimal('9999'),
            fecha=timezone.now().date(),
        )
        resp = self.client.get(self._url('fin_nomina'))
        self.assertEqual(resp.context['total_nomina'], Decimal('2000.00'))
        self.assertEqual(len(resp.context['costos_mano_obra']), 1)


class TestB4Costos(_BaseFinViewTest):
    """tests_e2e: b4_costos_200."""

    def test_b4_costos_200(self):
        resp = self.client.get(self._url('fin_costos'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('costos', resp.context)
        self.assertIn('tipos_recurso', resp.context)

    def test_costos_filtro_tipo_recurso(self):
        CostosConstruccion.objects.create(
            proyecto=self.proyecto, concepto='Mat',
            tipo_recurso=CostosConstruccion.TipoRecurso.MATERIAL,
            cantidad=Decimal('1'), costo_unitario=Decimal('100'),
            fecha=timezone.now().date(),
        )
        CostosConstruccion.objects.create(
            proyecto=self.proyecto, concepto='Equipo',
            tipo_recurso=CostosConstruccion.TipoRecurso.EQUIPOS,
            cantidad=Decimal('1'), costo_unitario=Decimal('500'),
            fecha=timezone.now().date(),
        )
        resp = self.client.get(self._url('fin_costos') + '?tipo_recurso=MATERIAL')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['costos']), 1)
        self.assertEqual(resp.context['filtro_tipo_recurso'], 'MATERIAL')


class TestB4Facturacion(_BaseFinViewTest):
    """tests_e2e: b4_facturacion_200."""

    def test_b4_facturacion_200(self):
        resp = self.client.get(self._url('fin_facturacion'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('facturas', resp.context)
        self.assertTrue(resp.context['sin_datos'])

    def test_facturacion_totales_y_saldo(self):
        FacturacionConstruccion.objects.create(
            proyecto=self.proyecto, numero_factura='F-001',
            monto_facturado=Decimal('1000'), monto_pagado=Decimal('400'),
        )
        FacturacionConstruccion.objects.create(
            proyecto=self.proyecto, numero_factura='F-002',
            monto_facturado=Decimal('500'), monto_pagado=Decimal('500'),
        )
        resp = self.client.get(self._url('fin_facturacion'))
        self.assertEqual(resp.context['total_facturado'], Decimal('1500'))
        self.assertEqual(resp.context['total_pagado'], Decimal('900'))
        self.assertEqual(resp.context['saldo_total'], Decimal('600'))


class TestB4DatoLegacy(_BaseFinViewTest):
    """Dato legacy: proyecto preexistente sin datos financieros abre todo en 200."""

    def test_proyecto_legacy_abre_las_6_vistas(self):
        for name in ('fin_dashboard', 'fin_presupuesto_planeado',
                     'fin_presupuesto_real', 'fin_nomina', 'fin_costos',
                     'fin_facturacion'):
            resp = self.client.get(self._url(name))
            self.assertEqual(resp.status_code, 200, f'{name} debió dar 200')
