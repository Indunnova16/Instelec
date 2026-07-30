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

from django.test import TestCase

from apps.pagos.models import calcular_n_meses


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
