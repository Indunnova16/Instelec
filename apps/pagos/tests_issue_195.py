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

from apps.pagos.models import PlanServicio, Suscripcion, Pago

User = get_user_model()


class WompiReferenceGranularidadTests(TestCase):
    """Gap #1: dos GETs del portal en el mismo mes deben generar referencias
    WOMPI distintas (antes usaban `%Y%m`, colisionaban)."""

    def setUp(self):
        self.user = User.objects.create_user(email='qa_pagos_195@test.com', password='x')
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
