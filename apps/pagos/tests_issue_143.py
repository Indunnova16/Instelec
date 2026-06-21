"""Tests #143 — portal de pagos WOMPI + Alegra (portado de FundicionesMedellin)."""
from decimal import Decimal
from django.test import TestCase
from django.core.management import call_command
from apps.pagos.models import PlanServicio, Suscripcion, Pago, DatosFacturacion


class CrearPlanInstelecTests(TestCase):
    def test_crear_plan_instelec_precio_150k_idempotente(self):
        call_command('crear_plan_instelec')
        plan = PlanServicio.objects.get(nombre='Plan Instelec')
        self.assertEqual(plan.precio, Decimal('150000'))
        self.assertTrue(plan.activo)
        self.assertTrue(Suscripcion.objects.filter(plan=plan).exists())
        # idempotente: correr de nuevo no duplica
        call_command('crear_plan_instelec')
        self.assertEqual(PlanServicio.objects.filter(nombre='Plan Instelec').count(), 1)
        self.assertEqual(Suscripcion.objects.filter(plan=plan).count(), 1)

    def test_modelos_basicos(self):
        plan = PlanServicio.objects.create(nombre='X', precio=Decimal('150000'))
        sus = Suscripcion.objects.create(plan=plan, estado='PENDIENTE')
        pago = Pago.objects.create(suscripcion=sus, monto=Decimal('150000'), estado='APROBADO')
        self.assertEqual(pago.suscripcion.plan.precio, Decimal('150000'))
        self.assertIn('150,000', str(pago))


class PortalViewTests(TestCase):
    def test_portal_requiere_login(self):
        resp = self.client.get('/pagos/')
        self.assertIn(resp.status_code, (301, 302))  # redirige a login
