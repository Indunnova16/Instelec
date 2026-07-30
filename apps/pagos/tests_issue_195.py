"""Tests #195 — hardening pagos WOMPI (paridad con ObrajeCRM#11):
1) wompi_reference con granularidad de microsegundos (no colisiona en el mismo mes)
2) UniqueConstraint parcial en wompi_reference/wompi_transaction_id
3) Guard ya_estaba_aprobado en el webhook (idempotencia real ante redelivery)
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.pagos.models import PlanServicio, Suscripcion

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
