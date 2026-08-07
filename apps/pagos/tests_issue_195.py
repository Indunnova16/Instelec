"""Tests #195 — hardening pagos WOMPI (paridad con ObrajeCRM#11):
1) wompi_reference con granularidad de microsegundos (no colisiona en el mismo mes)
2) UniqueConstraint parcial en wompi_reference/wompi_transaction_id
3) Guard ya_estaba_aprobado en el webhook (idempotencia real ante redelivery)
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apps.pagos.models import Pago, PlanServicio, Suscripcion

User = get_user_model()


class WompiReferenceGranularidadTests(TestCase):
    """Gap #1: dos GETs del portal en el mismo mes deben generar referencias
    WOMPI distintas (antes usaban `%Y%m`, colisionaban)."""

    def setUp(self):
        # Issue #197: el portal de pagos ahora es admin-only (is_admin) -- este
        # test siempre necesito un usuario logueado con acceso, no exercitaba el
        # gate en si (eso lo cubre tests_issue_197.py), asi que se vuelve admin.
        self.user = User.objects.create_user(
            email='qa_pagos_195@test.com', password='x', rol='admin',
        )
        self.plan = PlanServicio.objects.create(nombre='Plan QA', precio=Decimal('150000'))
        self.suscripcion = Suscripcion.objects.create(plan=self.plan, estado='PENDIENTE')
        self.client.force_login(self.user)

    def test_dos_gets_mismo_mes_generan_referencias_distintas(self):
        url = reverse('pagos:portal')
        resp1 = self.client.get(url)
        resp2 = self.client.get(url)
        ref1 = resp1.context['wompi_reference']
        ref2 = resp2.context['wompi_reference']
        self.assertNotEqual(
            ref1, ref2,
            'Dos GETs en el mismo mes generaron la MISMA referencia WOMPI '
            '(granularidad %Y%m) — WOMPI rechazaria el 2do intento.'
        )


class PagoUniqueConstraintTests(TestCase):
    """Gap #2: Pago.Meta debe tener UniqueConstraint parcial (excluye '') en
    wompi_reference y wompi_transaction_id."""

    def setUp(self):
        self.plan = PlanServicio.objects.create(nombre='Plan QA', precio=Decimal('150000'))
        self.suscripcion = Suscripcion.objects.create(plan=self.plan, estado='PENDIENTE')

    def test_wompi_transaction_id_duplicado_rechazado(self):
        Pago.objects.create(
            suscripcion=self.suscripcion, monto=Decimal('150000'),
            estado='APROBADO', wompi_transaction_id='TX-DUP', wompi_reference='REF-1',
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Pago.objects.create(
                    suscripcion=self.suscripcion, monto=Decimal('150000'),
                    estado='APROBADO', wompi_transaction_id='TX-DUP', wompi_reference='REF-2',
                )

    def test_wompi_reference_duplicado_rechazado(self):
        Pago.objects.create(
            suscripcion=self.suscripcion, monto=Decimal('150000'),
            estado='APROBADO', wompi_transaction_id='TX-1', wompi_reference='REF-DUP',
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Pago.objects.create(
                    suscripcion=self.suscripcion, monto=Decimal('150000'),
                    estado='APROBADO', wompi_transaction_id='TX-2', wompi_reference='REF-DUP',
                )

    def test_wompi_reference_vacio_no_bloquea_multiples(self):
        # La condicion parcial excluye '' — no debe romper filas sin referencia.
        Pago.objects.create(
            suscripcion=self.suscripcion, monto=Decimal('150000'),
            estado='PENDIENTE', wompi_transaction_id='', wompi_reference='',
        )
        Pago.objects.create(
            suscripcion=self.suscripcion, monto=Decimal('150000'),
            estado='PENDIENTE', wompi_transaction_id='', wompi_reference='',
        )
        self.assertEqual(Pago.objects.filter(wompi_reference='').count(), 2)


class WebhookYaEstabaAprobadoTests(TestCase):
    """Gap #3: una redelivery de WOMPI sobre un pago YA aprobado no debe
    re-avanzar fecha_proximo_pago ni re-facturar."""

    def setUp(self):
        self.plan = PlanServicio.objects.create(nombre='Plan QA', precio=Decimal('150000'))
        self.suscripcion = Suscripcion.objects.create(
            plan=self.plan, estado='ACTIVA',
        )
        self.suscripcion.fecha_proximo_pago = None
        self.suscripcion.save(update_fields=['fecha_proximo_pago'])
        self.url = reverse('pagos:webhook')

    def _payload(self, tx_id='TX-WEBHOOK-1', status='APPROVED'):
        return {
            'event': 'transaction.updated',
            'data': {
                'transaction': {
                    'id': tx_id,
                    'reference': f'REF-{tx_id}',
                    'status': status,
                    'amount_in_cents': 15000000,
                }
            },
        }

    def test_redelivery_no_reavanza_fecha_proximo_pago(self):
        import json
        from unittest.mock import patch

        payload = self._payload()

        with patch('apps.pagos.views.wompi.verify_webhook_signature', return_value=True), \
                patch('apps.pagos.views.alegra.generar_factura_desde_pago', return_value=None):
            resp1 = self.client.post(
                self.url, data=json.dumps(payload), content_type='application/json'
            )
            self.assertEqual(resp1.status_code, 200)

            self.suscripcion.refresh_from_db()
            fecha_tras_primer_webhook = self.suscripcion.fecha_proximo_pago
            self.assertIsNotNone(fecha_tras_primer_webhook)

            # Redelivery del MISMO evento (mismo transaction_id, ya APROBADO)
            resp2 = self.client.post(
                self.url, data=json.dumps(payload), content_type='application/json'
            )
            self.assertEqual(resp2.status_code, 200)

        self.suscripcion.refresh_from_db()
        self.assertEqual(
            self.suscripcion.fecha_proximo_pago, fecha_tras_primer_webhook,
            'La redelivery del webhook re-avanzo fecha_proximo_pago sobre un '
            'pago que ya estaba APROBADO — falta el guard ya_estaba_aprobado.'
        )
        self.assertEqual(Pago.objects.filter(wompi_transaction_id='TX-WEBHOOK-1').count(), 1)


class PortalCargaEstilosBootstrapTests(TestCase):
    """Reproceso #195 (bounce): el hardening de backend quedó validado, pero
    los templates de /pagos/ usan clases Bootstrap 5 (card, badge, btn...)
    sin que Bootstrap CSS se cargara nunca -- base.html solo declaraba
    `extra_head`, no `extra_css` (el bloque de portal.html quedaba huérfano
    y Django lo descartaba en silencio). Ver PLAN F2 (RUN_2026-08-07_0220)."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='qa_pagos_195_css@test.com', password='x', rol='admin',
        )
        self.plan = PlanServicio.objects.create(nombre='Plan QA', precio=Decimal('150000'))
        Suscripcion.objects.create(plan=self.plan, estado='PENDIENTE')
        self.client.force_login(self.user)

    def _assert_bootstrap_cargado(self, url):
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('bootstrap@5.3.3/dist/css/bootstrap.min.css', html)
        self.assertIn('bootstrap-icons@1.11.3', html)

    def test_portal_carga_bootstrap(self):
        self._assert_bootstrap_cargado(reverse('pagos:portal'))

    def test_portal_carga_driver_js_css_bloque_ya_no_huerfano(self):
        resp = self.client.get(reverse('pagos:portal'))
        self.assertIn('driver.js@1.3.1/dist/driver.css', resp.content.decode())

    def test_historial_carga_bootstrap(self):
        self._assert_bootstrap_cargado(reverse('pagos:historial'))

    def test_facturacion_carga_bootstrap(self):
        self._assert_bootstrap_cargado(reverse('pagos:facturacion'))
