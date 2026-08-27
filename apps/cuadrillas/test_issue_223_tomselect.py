"""Regression coverage for the omitted personnel TomSelect controls in #223."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.cuadrillas.models import Cuadrilla, PersonalCuadrilla


Usuario = get_user_model()


class TestIssue223PersonalTomSelect(TestCase):
    """Both personnel pickers retain the legacy documento contract."""

    def setUp(self):
        self.admin = Usuario.objects.create_user(
            email="admin_tomselect_223@test.local",
            password="testpass123!",
            first_name="Admin",
            last_name="TomSelect 223",
            rol="admin",
            is_staff=True,
            is_superuser=True,
        )
        self.client = Client()
        self.client.force_login(self.admin)
        self.personal_legacy = PersonalCuadrilla.objects.create(
            nombre="Colaborador Legacy 223",
            documento="LEG-223-001",
            rol_cuadrilla_id="LINIERO_I",
            activo=True,
            area="MANTENIMIENTO",
        )
        self.cuadrilla = Cuadrilla.objects.create(
            codigo="01-2099-TOM-223",
            nombre="Cuadrilla TomSelect 223",
            activa=True,
        )

    def test_detalle_migra_picker_legacy_a_tomselect_sin_cambiar_documento(self):
        response = self.client.get(reverse("cuadrillas:detalle", args=[self.cuadrilla.pk]))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        inicio = html.rfind("<select", 0, html.index('id="documento_input"'))
        picker = html[inicio : inicio + 600]
        self.assertIn('<select name="documento"', picker)
        self.assertIn("js-tomselect", picker)
        self.assertIn('value="LEG-223-001"', picker)
        self.assertIn("Colaborador Legacy 223 — LEG-223-001", picker)
        self.assertIn('onchange="autoCargarDatosPorDocumento()"', picker)
        self.assertNotIn("personal_disponible_list", html)

    def test_card_semanal_inicializa_tomselect_al_montarse_con_alpine(self):
        response = self.client.post(
            reverse("cuadrillas:semanal_bloque_crear", args=[2099, 1]),
            {"nombre": "Bloque TomSelect 223"},
        )

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('data-action="agregar-personal"', html)
        self.assertIn("$nextTick(() => window.initTomSelect", html)
        self.assertIn('id="id_documento"', html)
        self.assertIn("js-tomselect", html)

    def test_card_semanal_permite_dropdown_fuera_de_la_card_abierta(self):
        response = self.client.post(
            reverse("cuadrillas:semanal_bloque_crear", args=[2099, 1]),
            {"nombre": "Bloque overflow TomSelect 223"},
        )

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(":class=\"agregando ? 'relative z-10 overflow-visible'", html)
        self.assertIn(": 'overflow-hidden'\"", html)
