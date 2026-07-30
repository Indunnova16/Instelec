"""Tests #197 -- RBAC admin-only del modulo Pagos + banner alerta_pago_vencido.

(a) usuario NO-admin recibe 403 en las 3 vistas admin-only (Portal, Historial,
    Datos de Facturacion). El webhook WOMPI (`WompiWebhookView`) NO se toco.
(b) admin (rol=='admin' o is_superuser) entra OK (200) en las 3 vistas.
(c) `Suscripcion.alerta_pago_vencido`: False el dia del vencimiento y los
    primeros 4 dias de mora, True desde el dia 5.
(d) el context processor `recordatorio_pago` NO expone `alerta_pago_vencido`
    a un usuario no-admin (ni a un anonimo).
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.pagos.context_processors import recordatorio_pago
from apps.pagos.models import PlanServicio, Suscripcion

User = get_user_model()


class AdminGateViewsTests(TestCase):
    """(a)/(b) -- Portal / Historial / Datos de Facturacion son admin-only."""

    VISTAS = ('pagos:portal', 'pagos:historial', 'pagos:facturacion')

    def setUp(self):
        self.admin = User.objects.create_user(
            email='admin_197@test.com',
            password='x',
            rol='admin',
        )
        self.no_admin = User.objects.create_user(email='operario_197@test.com', password='x')
        self.plan = PlanServicio.objects.create(nombre='Plan QA', precio=Decimal('150000'))
        self.suscripcion = Suscripcion.objects.create(plan=self.plan, estado='ACTIVA')

    def test_no_admin_recibe_403_en_las_3_vistas(self):
        self.client.force_login(self.no_admin)
        for name in self.VISTAS:
            with self.subTest(vista=name):
                resp = self.client.get(reverse(name))
                self.assertEqual(resp.status_code, 403, f'{name} no devolvio 403 a un no-admin')

    def test_anonimo_redirige_a_login_en_las_3_vistas(self):
        for name in self.VISTAS:
            with self.subTest(vista=name):
                resp = self.client.get(reverse(name))
                self.assertIn(resp.status_code, (301, 302), f'{name} no redirigio a un anonimo')

    def test_admin_entra_ok_en_las_3_vistas(self):
        self.client.force_login(self.admin)
        for name in self.VISTAS:
            with self.subTest(vista=name):
                resp = self.client.get(reverse(name))
                self.assertEqual(resp.status_code, 200, f'{name} no dejo entrar a un admin')

    def test_superuser_sin_rol_admin_tambien_entra(self):
        # is_admin = rol==ADMIN OR is_superuser -- cubre la rama is_superuser.
        superusuario = User.objects.create_user(email='superuser_197@test.com', password='x')
        superusuario.is_superuser = True
        superusuario.save(update_fields=['is_superuser'])
        self.client.force_login(superusuario)
        resp = self.client.get(reverse('pagos:portal'))
        self.assertEqual(resp.status_code, 200)


class AlertaPagoVencidoPropertyTests(TestCase):
    """(c) -- alerta_pago_vencido: 5 dias de gracia sobre fecha_proximo_pago."""

    def setUp(self):
        self.plan = PlanServicio.objects.create(nombre='Plan QA', precio=Decimal('150000'))

    def _suscripcion_vencida_hace(self, dias, estado='PENDIENTE'):
        fecha = timezone.localdate() - timedelta(days=dias)
        return Suscripcion.objects.create(plan=self.plan, estado=estado, fecha_proximo_pago=fecha)

    def test_false_el_dia_del_vencimiento(self):
        s = self._suscripcion_vencida_hace(0)
        self.assertFalse(s.alerta_pago_vencido)

    def test_false_los_primeros_4_dias_de_mora(self):
        for dias in (1, 2, 3, 4):
            with self.subTest(dias=dias):
                s = self._suscripcion_vencida_hace(dias)
                self.assertFalse(s.alerta_pago_vencido)

    def test_true_desde_el_dia_5(self):
        for dias in (5, 6, 30):
            with self.subTest(dias=dias):
                s = self._suscripcion_vencida_hace(dias)
                self.assertTrue(s.alerta_pago_vencido)

    def test_false_si_suscripcion_activa_aunque_la_fecha_este_en_el_pasado(self):
        # requiere_pago exige estado != ACTIVA -- no debe disparar si ya pago.
        s = self._suscripcion_vencida_hace(10, estado='ACTIVA')
        self.assertFalse(s.requiere_pago)
        self.assertFalse(s.alerta_pago_vencido)

    def test_false_sin_fecha_proximo_pago(self):
        s = Suscripcion.objects.create(plan=self.plan, estado='PENDIENTE', fecha_proximo_pago=None)
        self.assertFalse(s.alerta_pago_vencido)


class ContextProcessorAdminGateTests(TestCase):
    """(d) -- recordatorio_pago() no expone `alerta_pago_vencido` a un no-admin."""

    def setUp(self):
        self.factory = RequestFactory()
        self.admin = User.objects.create_user(
            email='admin_197_ctx@test.com',
            password='x',
            rol='admin',
        )
        self.no_admin = User.objects.create_user(email='operario_197_ctx@test.com', password='x')
        self.plan = PlanServicio.objects.create(nombre='Plan QA', precio=Decimal('150000'))
        fecha = timezone.localdate() - timedelta(days=6)
        self.suscripcion = Suscripcion.objects.create(
            plan=self.plan,
            estado='PENDIENTE',
            fecha_proximo_pago=fecha,
        )

    def _request_para(self, user):
        request = self.factory.get('/')
        request.user = user
        return request

    def test_admin_ve_alerta_pago_vencido_en_contexto(self):
        ctx = recordatorio_pago(self._request_para(self.admin))
        self.assertTrue(ctx.get('alerta_pago_vencido'))

    def test_no_admin_no_ve_alerta_pago_vencido_en_contexto(self):
        ctx = recordatorio_pago(self._request_para(self.no_admin))
        self.assertNotIn('alerta_pago_vencido', ctx)

    def test_anonimo_no_ve_nada(self):
        ctx = recordatorio_pago(self._request_para(AnonymousUser()))
        self.assertEqual(ctx, {})

    def test_no_expone_si_suscripcion_cancelada_aunque_sea_admin(self):
        self.suscripcion.estado = 'CANCELADA'
        self.suscripcion.save(update_fields=['estado'])
        ctx = recordatorio_pago(self._request_para(self.admin))
        self.assertNotIn('alerta_pago_vencido', ctx)
