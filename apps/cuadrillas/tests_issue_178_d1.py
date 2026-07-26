"""Tests #178 — Sprint (2026-07-25), sub-item D1: hora de inicio/fin
PLANEADA a nivel de bloque (pedido D).

Issue: Indunnova16/Instelec#178

D1 agrega ``Cuadrilla.hora_inicio_planeada`` / ``hora_fin_planeada`` (campos
nuevos de M1, nullable) al form de crear/editar bloque
(``_bloque_form.html``) y a la card de solo lectura (``_bloque_card.html``,
"Horario planeado: HH:MM–HH:MM"). Claramente separado de la asistencia REAL
(modelo ``Asistencia``, otra pantalla) — no hay colisión de datos ni de UI.

Ejecutar:
  DJANGO_SETTINGS_MODULE=config.settings.local \
    venv/bin/python -m pytest apps/cuadrillas/tests_issue_178_d1.py -v \
    -o python_files="tests_*.py test_*.py"
"""

from datetime import date, time

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.cuadrillas.models import Cuadrilla
from apps.cuadrillas.views_semanal import _parse_hora_planeada

Usuario = get_user_model()


def _crear_admin(sufijo="d1"):
    # Rol admin (NO superuser) para ejercitar el gate real de RoleRequiredMixin.
    return Usuario.objects.create_user(
        email=f"admin_178{sufijo}@test.com",
        password="testpass123!",
        first_name="Admin",
        last_name=sufijo.upper(),
        rol="admin",
        is_staff=True,
    )


class TestD1ParseHoraPlaneada:
    """Unit — helper de parseo, independiente del cliente HTTP."""

    def test_vacio_o_none_es_none(self):
        assert _parse_hora_planeada("") is None
        assert _parse_hora_planeada(None) is None
        assert _parse_hora_planeada("   ") is None

    def test_formato_hh_mm(self):
        assert _parse_hora_planeada("07:00") == time(7, 0)

    def test_formato_invalido_lanza_valueerror(self):
        import pytest

        with pytest.raises(ValueError):
            _parse_hora_planeada("25:99")
        with pytest.raises(ValueError):
            _parse_hora_planeada("no-es-una-hora")


class TestD1CrearBloqueConHoraPlaneada(TestCase):
    def setUp(self):
        self.admin = _crear_admin("d1crear")
        self.client.force_login(self.admin)

    def test_happy_crear_con_horas_persiste_y_se_muestra_en_card(self):
        resp = self.client.post(
            reverse("cuadrillas:semanal_bloque_crear", args=[2026, 44]),
            {
                "nombre": "QA_E2E_ Bloque horario",
                "hora_inicio_planeada": "07:00",
                "hora_fin_planeada": "15:00",
            },
        )
        self.assertEqual(resp.status_code, 200)
        cuadrilla = Cuadrilla.objects.get(nombre="QA_E2E_ Bloque horario")
        self.assertEqual(cuadrilla.hora_inicio_planeada, time(7, 0))
        self.assertEqual(cuadrilla.hora_fin_planeada, time(15, 0))
        self.assertIn("Horario planeado: 07:00–15:00", resp.content.decode())

    def test_edge_solo_una_hora_seteada_no_rompe(self):
        """edge 1: solo hora_inicio_planeada seteada -> se guarda igual, la
        otra queda en None (ambas nullable)."""
        resp = self.client.post(
            reverse("cuadrillas:semanal_bloque_crear", args=[2026, 44]),
            {
                "nombre": "QA_E2E_ Bloque solo inicio",
                "hora_inicio_planeada": "08:30",
                "hora_fin_planeada": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        cuadrilla = Cuadrilla.objects.get(nombre="QA_E2E_ Bloque solo inicio")
        self.assertEqual(cuadrilla.hora_inicio_planeada, time(8, 30))
        self.assertIsNone(cuadrilla.hora_fin_planeada)
        # Sin ambas horas, la card NO muestra el texto de horario planeado.
        self.assertNotIn("Horario planeado:", resp.content.decode())

    def test_edge_hora_fin_menor_a_inicio_rechazado_con_error_inline(self):
        """edge 2: hora_fin < hora_inicio -> 400 + mensaje inline, NO crea
        el bloque (reusa _form_con_error, mismo patrón que fecha inválida)."""
        resp = self.client.post(
            reverse("cuadrillas:semanal_bloque_crear", args=[2026, 44]),
            {
                "nombre": "QA_E2E_ Bloque horario invalido",
                "hora_inicio_planeada": "15:00",
                "hora_fin_planeada": "07:00",
            },
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn(
            "La hora de fin planeada no puede ser anterior a la hora de inicio planeada.",
            resp.content.decode(),
        )
        self.assertFalse(Cuadrilla.objects.filter(nombre="QA_E2E_ Bloque horario invalido").exists())
        # El valor ya tipeado por el usuario NO se pierde (se re-renderiza en el input).
        self.assertIn('value="15:00"', resp.content.decode())


class TestD1EditarBloqueConHoraPlaneada(TestCase):
    def setUp(self):
        self.admin = _crear_admin("d1editar")
        self.client.force_login(self.admin)
        self.cuadrilla = Cuadrilla.objects.create(
            codigo="44-2026-0001-EDT",
            nombre="QA_E2E_ Bloque a editar",
            activa=True,
            fecha=date(2026, 10, 26),
        )

    def test_happy_editar_agrega_horas_planeadas(self):
        resp = self.client.post(
            reverse("cuadrillas:semanal_bloque_editar", args=[self.cuadrilla.pk]),
            {
                "nombre": self.cuadrilla.nombre,
                "fecha": "2026-10-26",
                "hora_inicio_planeada": "06:30",
                "hora_fin_planeada": "14:30",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.cuadrilla.refresh_from_db()
        self.assertEqual(self.cuadrilla.hora_inicio_planeada, time(6, 30))
        self.assertEqual(self.cuadrilla.hora_fin_planeada, time(14, 30))
        self.assertIn("Horario planeado: 06:30–14:30", resp.content.decode())

    def test_edge_hora_invalida_no_modifica_bloque_existente(self):
        """edge: un valor no parseable (ni siquiera HH:MM) rechaza el submit
        sin tocar el registro existente."""
        resp = self.client.post(
            reverse("cuadrillas:semanal_bloque_editar", args=[self.cuadrilla.pk]),
            {
                "nombre": self.cuadrilla.nombre,
                "fecha": "2026-10-26",
                "hora_inicio_planeada": "no-es-hora",
                "hora_fin_planeada": "",
            },
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("La hora planeada ingresada no es válida.", resp.content.decode())
        self.cuadrilla.refresh_from_db()
        self.assertIsNone(self.cuadrilla.hora_inicio_planeada)
