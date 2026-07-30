"""Tests #199 -- persistir Pago.n_meses + helper centralizado + meses_atraso +
grilla informativa "Estado por mes" (SOLO LECTURA, SIN selector -- decision
Miguel 2026-07-30: Instelec mantiene el pago forzado total, igual que
FundicionesMedellin/ObrajeCRM/FormasFuturo).

Sub-items cubiertos (PLAN_2026-07-30_199_pagos_multimes.md), agregados de
forma incremental (1 clase de tests por sub-item, en orden de dependencia):
- A1: CalcularNMesesTests
- A2: AvanzarFechaProximoPagoHelperTests, PagoNMesesPersistenceTests
- A3: MesesAtrasoPropertyTests
- A4: AlegraFacturaNMesesTests
- A5: GrillaEstadoPorMesContextTests
- A7: RegresionLocalE2ETests -- proxy local (Django test client, sin
  navegador) de las 4 asserts del journey E2E real
  (journeys/Instelec_199.yaml, corrido por F5 contra prod).
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.pagos.alegra import crear_factura
from apps.pagos.models import Pago, PlanServicio, Suscripcion, calcular_n_meses

User = get_user_model()


class CalcularNMesesTests(TestCase):
    """A1 -- happy path + edge cases del helper puro."""

    def test_happy_path_monto_exacto_un_mes(self):
        self.assertEqual(calcular_n_meses(Decimal('150000'), Decimal('150000')), 1)

    def test_happy_path_monto_exacto_multiples_meses(self):
        self.assertEqual(calcular_n_meses(Decimal('450000'), Decimal('150000')), 3)

    def test_monto_cero_retorna_minimo_1_mes(self):
        self.assertEqual(calcular_n_meses(0, Decimal('150000')), 1)

    def test_precio_cero_no_explota_y_retorna_1(self):
        # precio_mes<=0 (plan sin precio configurado) -- nunca ZeroDivisionError.
        self.assertEqual(calcular_n_meses(Decimal('150000'), 0), 1)

    def test_precio_negativo_retorna_1(self):
        self.assertEqual(calcular_n_meses(Decimal('150000'), Decimal('-10')), 1)

    def test_monto_no_divisible_redondea_hacia_arriba(self):
        # 140000/150000 = 0.9333.. -> redondea a 1 (ya era el minimo).
        self.assertEqual(calcular_n_meses(Decimal('140000'), Decimal('150000')), 1)

    def test_monto_no_divisible_redondea_al_mas_cercano(self):
        # 380000/150000 = 2.5333.. -> redondea a 3.
        self.assertEqual(calcular_n_meses(Decimal('380000'), Decimal('150000')), 3)

    def test_acepta_floats_como_los_call_sites_reales(self):
        # WOMPI entrega amount_in_cents/100 como float -- el helper debe
        # aceptarlo igual que un Decimal (via str() interno).
        self.assertEqual(calcular_n_meses(300000.0, 150000.0), 2)


class AvanzarFechaProximoPagoHelperTests(TestCase):
    """A2 -- _avanzar_fecha_proximo_pago ahora recibe el `pago` (con n_meses
    ya calculado) en vez de un monto suelto que recalculaba internamente."""

    def setUp(self):
        self.plan = PlanServicio.objects.create(nombre='Plan QA', precio=Decimal('150000'))
        self.suscripcion = Suscripcion.objects.create(plan=self.plan, estado='PENDIENTE')

    def test_avanza_1_mes_manteniendo_dia_20(self):
        from apps.pagos.views import _avanzar_fecha_proximo_pago

        self.suscripcion.fecha_proximo_pago = timezone.localdate().replace(day=20)
        self.suscripcion.save(update_fields=['fecha_proximo_pago'])
        fecha_antes = self.suscripcion.fecha_proximo_pago

        pago = Pago.objects.create(
            suscripcion=self.suscripcion, monto=Decimal('150000'), estado='APROBADO', n_meses=1,
        )
        _avanzar_fecha_proximo_pago(self.suscripcion, pago)
        self.suscripcion.refresh_from_db()

        self.assertEqual(self.suscripcion.fecha_proximo_pago.day, 20)
        meses_avanzados = (
            (self.suscripcion.fecha_proximo_pago.year - fecha_antes.year) * 12
            + (self.suscripcion.fecha_proximo_pago.month - fecha_antes.month)
        )
        self.assertEqual(meses_avanzados, 1)

    def test_avanza_n_meses_segun_pago_n_meses_no_segun_monto(self):
        # Regresion clave de A2: la fuente de verdad pasa a ser pago.n_meses
        # (ya persistido), NO un recalculo desde pago.monto en este helper.
        from apps.pagos.views import _avanzar_fecha_proximo_pago

        self.suscripcion.fecha_proximo_pago = timezone.localdate().replace(day=20)
        self.suscripcion.save(update_fields=['fecha_proximo_pago'])
        fecha_antes = self.suscripcion.fecha_proximo_pago

        # monto no coincide con 3 meses exactos, pero n_meses ya viene fijo.
        pago = Pago.objects.create(
            suscripcion=self.suscripcion, monto=Decimal('449999'), estado='APROBADO', n_meses=3,
        )
        _avanzar_fecha_proximo_pago(self.suscripcion, pago)
        self.suscripcion.refresh_from_db()

        meses_avanzados = (
            (self.suscripcion.fecha_proximo_pago.year - fecha_antes.year) * 12
            + (self.suscripcion.fecha_proximo_pago.month - fecha_antes.month)
        )
        self.assertEqual(meses_avanzados, 3)

    def test_plan_sin_precio_configurado_no_avanza_fecha(self):
        # Edge case real (Suscripcion.plan es FK obligatoria -- "sin plan" no
        # es alcanzable en la practica): un PlanServicio mal configurado con
        # precio=0 no debe avanzar fecha_proximo_pago ni reventar.
        from apps.pagos.views import _avanzar_fecha_proximo_pago

        plan_roto = PlanServicio.objects.create(nombre='Plan roto', precio=Decimal('0'))
        suscripcion = Suscripcion.objects.create(plan=plan_roto, estado='PENDIENTE')
        fecha_antes = suscripcion.fecha_proximo_pago
        pago = Pago.objects.create(suscripcion=suscripcion, monto=Decimal('0'), estado='APROBADO', n_meses=1)

        _avanzar_fecha_proximo_pago(suscripcion, pago)
        suscripcion.refresh_from_db()
        self.assertEqual(suscripcion.fecha_proximo_pago, fecha_antes)


class PagoNMesesPersistenceTests(TestCase):
    """A2 -- ambos call sites que crean Pago (redirect WOMPI + webhook)
    calculan y persisten n_meses con calcular_n_meses al crear el registro."""

    def setUp(self):
        self.plan = PlanServicio.objects.create(nombre='Plan Instelec', precio=Decimal('150000'))
        self.suscripcion = Suscripcion.objects.create(
            plan=self.plan, estado='PENDIENTE', fecha_proximo_pago=timezone.localdate(),
        )
        self.admin = User.objects.create_user(email='admin_199@test.com', password='x', rol='admin')

    def test_redirect_wompi_persiste_n_meses_calculado(self):
        from apps.pagos import views as pagos_views

        tx_data = {
            'data': {
                'id': 'TX-199-REDIRECT',
                'status': 'APPROVED',
                # 2 meses exactos a $150,000/mes.
                'amount_in_cents': 30000000,
                'reference': 'REF-199-REDIRECT',
            }
        }
        with patch.object(pagos_views.wompi, 'get_transaction', return_value=tx_data), \
                patch.object(pagos_views.alegra, 'generar_factura_desde_pago', return_value=None):
            self.client.force_login(self.admin)
            self.client.get(reverse('pagos:portal'), {'id': 'TX-199-REDIRECT'})

        pago = Pago.objects.get(wompi_transaction_id='TX-199-REDIRECT')
        self.assertEqual(pago.n_meses, 2)

    def test_webhook_persiste_n_meses_calculado(self):
        import json

        payload = {
            'event': 'transaction.updated',
            'data': {
                'transaction': {
                    'id': 'TX-199-WEBHOOK',
                    'reference': 'REF-199-WEBHOOK',
                    'status': 'APPROVED',
                    # 3 meses exactos a $150,000/mes.
                    'amount_in_cents': 45000000,
                }
            },
        }
        with patch('apps.pagos.views.wompi.verify_webhook_signature', return_value=True), \
                patch('apps.pagos.views.alegra.generar_factura_desde_pago', return_value=None):
            resp = self.client.post(
                reverse('pagos:webhook'), data=json.dumps(payload), content_type='application/json',
            )
        self.assertEqual(resp.status_code, 200)
        pago = Pago.objects.get(wompi_transaction_id='TX-199-WEBHOOK')
        self.assertEqual(pago.n_meses, 3)

    def test_n_meses_default_1_para_pagos_sin_calculo_explicito(self):
        # Cubre el dato legacy real: los 0 Pago historicos de prod no tenian
        # esta columna -- cualquier fila nueva sin n_meses explicito (ej.
        # creada por un flujo no cubierto) debe caer en el default seguro.
        pago = Pago.objects.create(suscripcion=self.suscripcion, monto=Decimal('150000'), estado='PENDIENTE')
        self.assertEqual(pago.n_meses, 1)


class MesesAtrasoPropertyTests(TestCase):
    """A3 -- Suscripcion.meses_atraso centraliza el calculo delta_dias//30+1
    (delta>=0) que antes vivia duplicado en context_processors.recordatorio_pago
    y en views.PagoPortalView.get_context_data."""

    def setUp(self):
        self.plan = PlanServicio.objects.create(nombre='Plan QA', precio=Decimal('150000'))

    def test_none_fecha_proximo_pago_retorna_cero(self):
        s = Suscripcion.objects.create(plan=self.plan, estado='PENDIENTE', fecha_proximo_pago=None)
        self.assertEqual(s.meses_atraso, 0)

    def test_estado_activa_retorna_cero_aunque_fecha_este_vencida(self):
        fecha = timezone.localdate() - timezone.timedelta(days=60)
        s = Suscripcion.objects.create(plan=self.plan, estado='ACTIVA', fecha_proximo_pago=fecha)
        self.assertEqual(s.meses_atraso, 0)

    def test_delta_negativo_no_vencida_retorna_cero(self):
        # Caso real de prod hoy: fecha_proximo_pago=2026-08-01, delta<0.
        fecha = timezone.localdate() + timezone.timedelta(days=2)
        s = Suscripcion.objects.create(plan=self.plan, estado='PENDIENTE', fecha_proximo_pago=fecha)
        self.assertEqual(s.meses_atraso, 0)

    def test_delta_cero_el_dia_del_vencimiento_retorna_1(self):
        fecha = timezone.localdate()
        s = Suscripcion.objects.create(plan=self.plan, estado='PENDIENTE', fecha_proximo_pago=fecha)
        self.assertEqual(s.meses_atraso, 1)

    def test_delta_positivo_multiples_meses(self):
        fecha = timezone.localdate() - timezone.timedelta(days=65)
        s = Suscripcion.objects.create(plan=self.plan, estado='PENDIENTE', fecha_proximo_pago=fecha)
        self.assertEqual(s.meses_atraso, 3)  # 65//30 + 1 = 3

    def test_context_processor_no_muestra_aviso_si_activa_con_fecha_vencida(self):
        # Regresion del edge case documentado en meses_atraso: si por dato
        # manual una Suscripcion queda ACTIVA con fecha_proximo_pago vencida,
        # el context processor NO debe mostrar el banner "vencido" con
        # meses=0 (antes de A3 esto no se chequeaba y podria mostrar un
        # aviso de "$0 COP" degenerado).
        from django.contrib.auth import get_user_model
        from django.test import RequestFactory

        from apps.pagos.context_processors import recordatorio_pago

        User = get_user_model()
        user = User.objects.create_user(email='admin_199_ctxproc@test.com', password='x', rol='admin')
        fecha = timezone.localdate() - timezone.timedelta(days=10)
        Suscripcion.objects.create(plan=self.plan, estado='ACTIVA', fecha_proximo_pago=fecha)

        request = RequestFactory().get('/')
        request.user = user
        ctx = recordatorio_pago(request)
        self.assertNotIn('recordatorio_pago', ctx)


class AlegraFacturaNMesesTests(TestCase):
    """A4 -- crear_factura lee pago.n_meses (fuente unica ya persistida) en
    vez de recalcular quantity/price de forma independiente desde
    monto/plan.precio."""

    def setUp(self):
        self.plan = PlanServicio.objects.create(nombre='Plan Instelec', precio=Decimal('150000'))
        self.suscripcion = Suscripcion.objects.create(plan=self.plan, estado='ACTIVA')

    @patch('apps.pagos.alegra.requests.post')
    def test_caso_exacto_quantity_y_price_reconcilian_con_precio_plan(self, mock_post):
        mock_post.return_value.status_code = 201
        mock_post.return_value.json.return_value = {'id': 1000}

        pago = Pago.objects.create(
            suscripcion=self.suscripcion, monto=Decimal('150000'), estado='APROBADO',
            wompi_transaction_id='TX-ALEGRA-199-EXACTO', n_meses=1,
        )
        crear_factura(contacto_id='123', plan=self.plan, pago=pago)

        _, kwargs = mock_post.call_args
        item = kwargs['json']['items'][0]
        self.assertEqual(item['quantity'], 1)
        self.assertEqual(item['price'], 150000.0)
        self.assertIn('Plan Instelec', item['description'])
        self.assertEqual(kwargs['json']['payments'][0]['amount'], 150000.0)

    @patch('apps.pagos.alegra.requests.post')
    def test_caso_fallback_monto_no_divisible_ya_no_sub_factura(self, mock_post):
        # Regresion del bug que A4 corrige: monto=$299,999 a $150,000/mes.
        # pago.n_meses=2 (calculado por calcular_n_meses -- A2, al momento
        # del pago). El calculo VIEJO de crear_factura (round + tolerancia
        # estricta <0.01) caia al fallback quantity=1 -- una factura de 2
        # meses mostrando "quantity: 1" (sub-facturacion potencial). Ahora
        # quantity SIEMPRE viene de pago.n_meses, sin ese fallback.
        mock_post.return_value.status_code = 201
        mock_post.return_value.json.return_value = {'id': 1001}

        pago = Pago.objects.create(
            suscripcion=self.suscripcion, monto=Decimal('299999'), estado='APROBADO',
            wompi_transaction_id='TX-ALEGRA-199-FALLBACK', n_meses=calcular_n_meses(Decimal('299999'), self.plan.precio),
        )
        self.assertEqual(pago.n_meses, 2, 'precondicion del test: calcular_n_meses debia dar 2')

        crear_factura(contacto_id='123', plan=self.plan, pago=pago)

        _, kwargs = mock_post.call_args
        item = kwargs['json']['items'][0]
        self.assertEqual(item['quantity'], 2, 'ya no debe caer al fallback quantity=1')
        self.assertAlmostEqual(item['price'] * item['quantity'], 299999.0, places=2)

    @patch('apps.pagos.alegra.requests.post')
    def test_precio_plan_cambio_no_afecta_n_meses_facturado(self, mock_post):
        # El pago se hizo cuando el plan costaba $150,000 (n_meses=2 ya
        # persistido). Si el precio del plan sube DESPUES (ej. a $180,000)
        # antes de facturar, la factura debe seguir mostrando 2 meses (el
        # dato historico real), no recalcular con el precio nuevo.
        mock_post.return_value.status_code = 201
        mock_post.return_value.json.return_value = {'id': 1002}

        pago = Pago.objects.create(
            suscripcion=self.suscripcion, monto=Decimal('300000'), estado='APROBADO',
            wompi_transaction_id='TX-ALEGRA-199-PRECIO-CAMBIO', n_meses=2,
        )
        self.plan.precio = Decimal('180000')
        self.plan.save(update_fields=['precio'])

        crear_factura(contacto_id='123', plan=self.plan, pago=pago)

        _, kwargs = mock_post.call_args
        item = kwargs['json']['items'][0]
        self.assertEqual(item['quantity'], 2)
