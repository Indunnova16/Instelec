"""#100 — Endpoint torres-por-linea: etiqueta T-{n} + orden numérico.

El dropdown web de torres (actividades/crear, form_actividad, campo/reportar_dano)
consume `/actividades/api/torres-por-linea/<linea_id>/`. Antes devolvía el
`numero` crudo (E-1, E-10...) ordenado lexicográficamente. Ahora devuelve
`numero_display` (T-{n}) en orden numérico ascendente. El value del <option>
sigue siendo el `id`.
"""
import json

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from apps.lineas.models import Linea, Torre

User = get_user_model()


class TestTorresPorLineaEndpoint(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email='t100@test.com', password='x', rol='admin',
            is_superuser=True, is_staff=True,
        )
        cls.linea = Linea.objects.create(
            codigo='L-100', nombre='Test 100', cliente=Linea.Cliente.TRANSELCA,
        )
        # Numeros crudos desordenados y en formato 'E-' (caso real Sofi)
        from decimal import Decimal
        for n in ['E-2', 'E-10', 'E-1', 'E-3']:
            Torre.objects.create(
                linea=cls.linea, numero=n, tipo='SUSPENSION', estado='BUENO',
                latitud=Decimal('5.0'), longitud=Decimal('-75.0'),
            )

    def _get(self):
        self.client.force_login(self.user)
        return self.client.get(reverse(
            'actividades:torres_por_linea', kwargs={'linea_id': self.linea.id},
        ))

    def test_devuelve_numero_display_T(self):
        r = self._get()
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content)
        numeros = [t['numero'] for t in data]
        # Todos en formato T-{n}, ninguno con 'E-'
        self.assertTrue(all(x.startswith('T-') for x in numeros), numeros)
        self.assertFalse(any('E-' in x for x in numeros), numeros)

    def test_orden_numerico_ascendente(self):
        r = self._get()
        data = json.loads(r.content)
        numeros = [t['numero'] for t in data]
        # Numérico (1,2,3,10), NO lexicográfico (1,10,2,3)
        self.assertEqual(numeros, ['T-1', 'T-2', 'T-3', 'T-10'])

    def test_value_sigue_siendo_id(self):
        r = self._get()
        data = json.loads(r.content)
        for t in data:
            # cada item trae id (identificador) + numero (display)
            self.assertIn('id', t)
            self.assertIn('numero', t)
            # el id es un UUID parseable, no la etiqueta
            self.assertNotEqual(t['id'], t['numero'])
