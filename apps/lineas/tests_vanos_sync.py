"""#101 — Tests para la materialización de Vanos desde ``cantidad_vanos``.

Causa raíz del re-reporte (Sofi 2026-06-06): ``cantidad_vanos`` era un contador
metadato; editarlo NO creaba filas ``Vano``, así que la grilla de Registrar
Avances salía vacía pese a "tener 100 vanos". Fix: ``Linea.sincronizar_vanos``
+ llamada en el handler AJAX ``actualizar_vanos``.

Cubre:
- crea vanos 1..N
- idempotencia (no duplica al re-sincronizar)
- NO destructivo (preserva vanos con estado/datos)
- tope MAX_VANOS_AUTOGENERADOS
- entradas inválidas / <=0 → 0
- integración POST actualizar_vanos (crea vanos + JSON) y rol admin_general permitido
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from apps.lineas.models import Linea, Vano

User = get_user_model()


def _linea(codigo='L-101', cantidad_vanos=None):
    return Linea.objects.create(
        codigo=codigo,
        nombre='Test 101',
        cliente=Linea.Cliente.TRANSELCA,
        cantidad_vanos=cantidad_vanos,
    )


class TestSincronizarVanos(TestCase):
    def test_crea_1_a_n(self):
        linea = _linea()
        creados = linea.sincronizar_vanos(100)
        self.assertEqual(creados, 100)
        self.assertEqual(linea.vanos.count(), 100)
        numeros = set(linea.vanos.values_list('numero', flat=True))
        self.assertIn('1', numeros)
        self.assertIn('100', numeros)
        self.assertNotIn('101', numeros)

    def test_idempotente(self):
        linea = _linea()
        self.assertEqual(linea.sincronizar_vanos(50), 50)
        # Segunda corrida: nada nuevo, sin duplicados (unique_together linea,numero)
        self.assertEqual(linea.sincronizar_vanos(50), 0)
        self.assertEqual(linea.vanos.count(), 50)

    def test_ampliar_solo_crea_faltantes(self):
        linea = _linea()
        linea.sincronizar_vanos(10)
        creados = linea.sincronizar_vanos(15)
        self.assertEqual(creados, 5)
        self.assertEqual(linea.vanos.count(), 15)

    def test_no_destructivo_preserva_estado(self):
        linea = _linea()
        linea.sincronizar_vanos(10)
        v = linea.vanos.get(numero='3')
        v.estado = Vano.Estado.EJECUTADO
        v.save(update_fields=['estado'])
        # Reducir el contador no debe borrar nada (no destructivo)
        creados = linea.sincronizar_vanos(5)
        self.assertEqual(creados, 0)
        self.assertEqual(linea.vanos.count(), 10)
        self.assertEqual(linea.vanos.get(numero='3').estado, Vano.Estado.EJECUTADO)

    def test_cap_max(self):
        linea = _linea()
        creados = linea.sincronizar_vanos(Linea.MAX_VANOS_AUTOGENERADOS + 500)
        self.assertEqual(creados, Linea.MAX_VANOS_AUTOGENERADOS)
        self.assertEqual(linea.vanos.count(), Linea.MAX_VANOS_AUTOGENERADOS)

    def test_invalidos_devuelven_cero(self):
        linea = _linea()
        for v in (0, -5, None, 'abc'):
            self.assertEqual(linea.sincronizar_vanos(v), 0)
        self.assertEqual(linea.vanos.count(), 0)


class TestActualizarVanosEndpoint(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            email='admin@101.test', password='x', rol='admin',
            is_superuser=True, is_staff=True,
        )
        cls.admin_general = User.objects.create_user(
            email='ag@101.test', password='x', rol='admin_general',
        )
        cls.liniero = User.objects.create_user(
            email='lin@101.test', password='x', rol='liniero',
        )

    def _post(self, linea, cantidad):
        return self.client.post(
            reverse('lineas:detalle', kwargs={'pk': linea.pk}),
            {'action': 'actualizar_vanos', 'cantidad_vanos': str(cantidad)},
        )

    def test_admin_materializa_vanos(self):
        linea = _linea()
        self.client.force_login(self.admin)
        r = self._post(linea, 100)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['vanos_creados'], 100)
        self.assertEqual(data['vanos_total'], 100)
        self.assertEqual(linea.vanos.count(), 100)

    def test_admin_general_permitido(self):
        """admin_general (RBAC v2) NO debe recibir 403 al actualizar vanos."""
        linea = _linea()
        self.client.force_login(self.admin_general)
        r = self._post(linea, 5)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(linea.vanos.count(), 5)

    def test_liniero_403(self):
        linea = _linea()
        self.client.force_login(self.liniero)
        r = self._post(linea, 5)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(linea.vanos.count(), 0)
