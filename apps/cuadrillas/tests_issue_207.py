"""Tests #207 — Duplicar semana: elegir semana base (no solo la anterior).

Issue: Indunnova16/Instelec#207

Basados en los 2 escenarios del journey E2E (SPRINTS/RUN_2026-08-07_0220/
journeys/Instelec_207.yaml), traducidos a ``TestCase`` reales de Django:

  m1: desde una semana destino vacía, elegir una semana origen que NO es la
      N-1 (fixture año 2099 -- no toca datos reales) y duplicar directo, sin
      encadenar.
  m2: cuando el destino YA tiene programación (pide confirmación), la semana
      origen elegida debe viajar a través del redirect ``?confirmar_duplicado=1``
      y del hidden field del form de confirmar -- no perderse y caer de
      vuelta en el fallback N-1.

Ejecutar:
  DJANGO_SETTINGS_MODULE=config.settings.dev_lite \
    venv/bin/python -m pytest apps/cuadrillas/tests_issue_207.py -v \
    -o python_files="tests_*.py test_*.py"
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.cuadrillas.models import Cuadrilla, CuadrillaMiembro

Usuario = get_user_model()


def _crear_admin():
    return Usuario.objects.create_user(
        email="admin_207@test.com",
        password="testpass123!",
        first_name="Admin",
        last_name="207",
        rol="admin",
        is_staff=True,
    )


def _crear_usuario(documento, nombre):
    partes = nombre.split(maxsplit=1)
    return Usuario.objects.create(
        email=f"{documento}@test.local",
        documento=documento,
        first_name=partes[0],
        last_name=partes[1] if len(partes) > 1 else "",
        rol="liniero",
        is_active=True,
    )


def _crear_bloque(codigo, fecha, miembros, nombre="MANTENIMIENTO - 207"):
    c = Cuadrilla.objects.create(
        codigo=codigo,
        nombre=nombre,
        activa=True,
        observaciones="",
        fecha=fecha,
    )
    for usuario, cargo, rol_cuadrilla in miembros:
        CuadrillaMiembro.objects.create(
            cuadrilla=c,
            usuario=usuario,
            rol_cuadrilla_id=rol_cuadrilla,
            cargo=cargo,
            costo_dia=0,
            fecha_inicio=fecha,
            activo=True,
        )
    return c


class TestM1DuplicarSemanaOrigenElegidaSinEncadenar(TestCase):
    """Escenario m1 del journey: destino vacío (32/2099), origen elegido
    28/2099 (NO la N-1, que sería 31/2099 y está vacía)."""

    def setUp(self):
        self.admin = _crear_admin()
        self.client.force_login(self.admin)
        self.jefe = _crear_usuario("QA0207M1JEF", "QAE207M1 Jefe")

    def test_duplicar_desde_semana_no_anterior_sin_encadenar(self):
        _crear_bloque(
            "28-2099-0001-QAE",
            date(2099, 7, 8),
            [(self.jefe, "JT_CTA", "LINIERO_I")],
            nombre="QA_E2E_207_ORIGEN",
        )

        # Semana 31/2099 (la N-1 de 32) está vacía a propósito -- el fallback
        # viejo hubiera fallado acá.
        resp_destino_vacio = self.client.get(
            reverse("cuadrillas:semanal_grid", args=[2099, 32])
        )
        self.assertEqual(resp_destino_vacio.status_code, 200)
        self.assertIn("No hay programación cargada", resp_destino_vacio.content.decode())
        # El selector ofrece la semana 28 como opción de origen.
        self.assertIn('value="28-2099"', resp_destino_vacio.content.decode())

        resp = self.client.post(
            reverse("cuadrillas:semanal_duplicar", args=[2099, 32]),
            {"semana_origen_key": "28-2099"},
        )
        self.assertEqual(resp.status_code, 302)

        nueva = Cuadrilla.objects.get(codigo="32-2099-0001-QAE")
        self.assertEqual(nueva.nombre, "QA_E2E_207_ORIGEN")
        # Delta real: semana 28 -> semana 32 = 4 semanas ISO = 28 días.
        self.assertEqual(nueva.fecha, date(2099, 8, 5))
        self.assertEqual(nueva.miembros.first().fecha_inicio, date(2099, 8, 5))

        resp_final = self.client.get(resp.url)
        html = resp_final.content.decode()
        self.assertIn("desde la semana 28/2099", html)
        self.assertIn("QA_E2E_207_ORIGEN", html)

    def test_sin_semana_origen_key_cae_en_fallback_n_menos_1(self):
        """Compatibilidad: si el POST no manda `semana_origen_key` (callers
        viejos), el comportamiento es EXACTAMENTE el histórico (N-1)."""
        f = date(2026, 3, 16)
        _crear_bloque(
            "12-2026-0001-MAN",
            f,
            [(self.jefe, "JT_CTA", "LINIERO_I")],
        )
        resp = self.client.post(reverse("cuadrillas:semanal_duplicar", args=[2026, 13]))
        self.assertEqual(resp.status_code, 302)
        copia = Cuadrilla.objects.get(codigo="13-2026-0001-MAN")
        self.assertEqual(copia.fecha, date(2026, 3, 23))


class TestM2ConfirmarDuplicadoPreservaSemanaOrigenElegida(TestCase):
    """Escenario m2 del journey: destino (44/2099) YA tiene programación
    (fuerza confirmación); origen elegido 40/2099 (NO la N-1, 43/2099, que
    está vacía) debe sobrevivir el paso de confirmación."""

    def setUp(self):
        self.admin = _crear_admin()
        self.client.force_login(self.admin)
        self.jefe = _crear_usuario("QA0207M2JEF", "QAE207M2 Jefe")

    def test_confirmar_preserva_semana_origen_elegida(self):
        _crear_bloque(
            "40-2099-0001-QAX",
            date(2099, 9, 30),
            [(self.jefe, "JT_CTA", "LINIERO_I")],
            nombre="QA_E2E_207_M2_ORIGEN",
        )
        _crear_bloque(
            "44-2099-0002-QAX",
            date(2099, 10, 26),
            [],
            nombre="QA_E2E_207_M2_DESTINO_PREVIO",
        )

        # 1er POST (sin confirmar): destino ya tiene datos -> pide
        # confirmación, propagando la semana origen ELEGIDA en el redirect.
        resp1 = self.client.post(
            reverse("cuadrillas:semanal_duplicar", args=[2099, 44]),
            {"semana_origen_key": "40-2099"},
        )
        self.assertEqual(resp1.status_code, 302)
        self.assertIn("semana_origen_key=40-2099", resp1.url)
        self.assertFalse(Cuadrilla.objects.filter(codigo="44-2099-0001-QAX").exists())

        # La página de confirmación (GET siguiendo el redirect) trae el
        # hidden field con la semana origen elegida, NO la N-1 (43).
        resp_confirm_page = self.client.get(resp1.url)
        html_confirm = resp_confirm_page.content.decode()
        self.assertIn('name="semana_origen_key" value="40-2099"', html_confirm)

        # 2do POST (confirmar=1 + semana_origen_key=40-2099, como manda el
        # hidden field del form de confirmar) -> duplica desde 40, NO desde
        # 43 (vacía) ni pierde la selección.
        resp2 = self.client.post(
            reverse("cuadrillas:semanal_duplicar", args=[2099, 44]),
            {"confirmar": "1", "semana_origen_key": "40-2099"},
            follow=True,
        )
        self.assertEqual(resp2.status_code, 200)

        nueva = Cuadrilla.objects.get(codigo="44-2099-0001-QAX")
        self.assertEqual(nueva.nombre, "QA_E2E_207_M2_ORIGEN")
        # Delta real: semana 40 -> semana 44 = 4 semanas ISO = 28 días.
        self.assertEqual(nueva.fecha, date(2099, 10, 28))

        # El bloque YA existente en destino no se tocó.
        destino_previo = Cuadrilla.objects.get(codigo="44-2099-0002-QAX")
        self.assertEqual(destino_previo.nombre, "QA_E2E_207_M2_DESTINO_PREVIO")

        html2 = resp2.content.decode()
        self.assertIn("desde la semana 40/2099", html2)
        self.assertIn("QA_E2E_207_M2_ORIGEN", html2)
