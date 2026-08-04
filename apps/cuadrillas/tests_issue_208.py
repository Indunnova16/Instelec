"""
Tests issue #208 — Regresión: botón "Importar Excel" oculto en Programación
Semanal.

Contexto: el botón de carga masiva de cuadrillas (S18 vertical, #124,
endpoint ``cuadrillas:masiva_upload`` -> ``/cuadrillas/masiva/upload/``)
existía y era usado por el cliente ("yo lo vi, yo lo subí" -- Alcides). La
fusión de pantallas de #188 (commit 97854fa, sub-item A11) lo retiró de
``templates/cuadrillas/lista.html`` asumiendo por error que era "carga
masiva de personal" -- en realidad ``CuadrillaMasivaUploadView`` crea/
actualiza bloques ``Cuadrilla`` (la programación semanal misma), no
``PersonalCuadrilla``. Quedó reubicado solo en
``/cuadrillas/colaboradores/``, su pantalla equivocada, y el cliente cerró
#188 sin notar la pérdida.

Este archivo fija la regresión: el botón debe estar visible en la pestaña
"Semanas" de ``/cuadrillas/`` (y en la página standalone
``/cuadrillas/semanal/<anio>/<semana>/``, que comparte el mismo partial
``partials/_tab_semanas.html``), apuntando exactamente al endpoint que
Alcides usaba.

Ejecutar con:
    pytest apps/cuadrillas/tests_issue_208.py -v
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

Usuario = get_user_model()


def _crear_admin():
    return Usuario.objects.create_user(
        email="admin_208@test.com",
        password="testpass123!",
        first_name="Admin",
        last_name="Test208",
        rol="admin",
        is_staff=True,
        is_superuser=True,
    )


class TestIssue208BotonImportarExcelRestaurado(TestCase):
    """El botón "Importar Excel" (carga masiva S18 de Cuadrilla) debe volver
    a ser visible en la pestaña Semanas -- no una funcionalidad nueva, sino
    la restauración de un flujo de import que ya funciona."""

    def setUp(self):
        self.admin = _crear_admin()
        self.client = Client()
        self.client.force_login(self.admin)

    def test_happy_boton_visible_en_cuadrillas_lista(self):
        resp = self.client.get(reverse("cuadrillas:lista"))
        self.assertEqual(resp.status_code, 200)
        contenido = resp.content.decode()

        # El botón debe estar presente...
        self.assertIn("Importar Excel", contenido)
        # ...con el aria-label histórico (mismo que usaba el botón original
        # antes de #188, para que cualquier test/QA que dependa de ese
        # aria-label lo siga encontrando)...
        self.assertIn('aria-label="Carga masiva de cuadrillas desde Excel"', contenido)
        # ...y apuntando al MISMO endpoint que Alcides usaba (verificado en
        # código: CuadrillaMasivaUploadView, no PersonalCuadrillaUploadView).
        self.assertIn(reverse("cuadrillas:masiva_upload"), contenido)

    def test_happy_boton_visible_en_semanal_grid_standalone(self):
        hoy = date.today()
        anio, semana, _ = hoy.isocalendar()
        resp = self.client.get(
            reverse("cuadrillas:semanal_grid", kwargs={"anio": anio, "semana": semana})
        )
        self.assertEqual(resp.status_code, 200)
        contenido = resp.content.decode()
        self.assertIn("Importar Excel", contenido)
        self.assertIn(reverse("cuadrillas:masiva_upload"), contenido)

    def test_regresion_endpoint_import_sigue_vivo(self):
        # El endpoint nunca se perdió -- solo la puerta (el botón). Este
        # test cierra el loop: si algún día el endpoint también se rompe,
        # que falle acá y no solo en producción.
        resp = self.client.get(reverse("cuadrillas:masiva_upload"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Carga Masiva de Cuadrillas", resp.content.decode())
