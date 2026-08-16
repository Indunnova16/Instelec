"""Regression tests for the weekly-crew range and free-route changes in #223."""

from datetime import date

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import Client, TestCase
from django.urls import reverse

from apps.cuadrillas.models import Cuadrilla
from apps.cuadrillas.views_semanal import _bloque_a_dict
from apps.lineas.models import Linea, Torre, Tramo


Usuario = get_user_model()


class TestProgramacionSemanalTramoLibreYRango(TestCase):
    """A1: free route text and both date boundaries survive all weekly views."""

    def setUp(self):
        self.admin = Usuario.objects.create_user(
            email="admin_223@test.local",
            password="testpass123!",
            first_name="Admin",
            last_name="223",
            rol="admin",
            is_staff=True,
            is_superuser=True,
        )
        self.client = Client()
        self.client.force_login(self.admin)
        self.crear_url = reverse("cuadrillas:semanal_bloque_crear", args=[2099, 1])

    def test_crear_y_editar_persisten_tramo_libre_y_rango_completo(self):
        response = self.client.post(
            self.crear_url,
            {
                "nombre": "Cuadrilla QA 223",
                "tramo_libre": "K12+345 a K13+000",
                "fecha_inicio": "2099-01-05",
                "fecha_fin": "2099-01-09",
            },
        )

        self.assertEqual(response.status_code, 200)
        cuadrilla = Cuadrilla.objects.get(nombre="Cuadrilla QA 223")
        self.assertEqual(cuadrilla.tramo_libre, "K12+345 a K13+000")
        self.assertEqual(cuadrilla.fecha, date(2099, 1, 5))
        self.assertEqual(cuadrilla.fecha_fin, date(2099, 1, 9))
        self.assertContains(response, "Fecha Inicio")
        self.assertContains(response, "Fecha Fin")
        self.assertContains(response, "K12+345 a K13+000")

        response = self.client.post(
            reverse("cuadrillas:semanal_bloque_editar", args=[cuadrilla.id]),
            {
                "nombre": "Cuadrilla QA 223 editada",
                "tramo_libre": "K13+000 a K13+500",
                "fecha_inicio": "2099-01-06",
                "fecha_fin": "2099-01-10",
            },
        )

        self.assertEqual(response.status_code, 200)
        cuadrilla.refresh_from_db()
        self.assertEqual(cuadrilla.tramo_libre, "K13+000 a K13+500")
        self.assertEqual(cuadrilla.fecha, date(2099, 1, 6))
        self.assertEqual(cuadrilla.fecha_fin, date(2099, 1, 10))

    def test_fecha_fin_anterior_no_guarda_y_mantiene_error_visible(self):
        response = self.client.post(
            self.crear_url,
            {
                "nombre": "Cuadrilla rango inválido",
                "tramo_libre": "Vano 25-50",
                "fecha_inicio": "2099-01-10",
                "fecha_fin": "2099-01-09",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "La fecha de fin no puede ser anterior", status_code=400)
        self.assertContains(response, 'value="Vano 25-50"', status_code=400)
        self.assertEqual(Cuadrilla.objects.filter(nombre="Cuadrilla rango inválido").count(), 0)

    def test_fecha_fin_malformada_no_guarda(self):
        response = self.client.post(
            self.crear_url,
            {
                "nombre": "Cuadrilla fecha inválida",
                "fecha_inicio": "2099-01-05",
                "fecha_fin": "09-01-2099",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "La fecha de fin ingresada no es válida", status_code=400)
        self.assertFalse(Cuadrilla.objects.filter(nombre="Cuadrilla fecha inválida").exists())

    def test_cuadrilla_legacy_con_tramo_fk_aun_renderiza_en_card_y_pdf(self):
        linea = Linea.objects.create(codigo="223-L", nombre="Línea legacy", cliente="TRANSELCA")
        inicio = Torre.objects.create(linea=linea, numero="1", latitud="7.0", longitud="-75.5")
        fin = Torre.objects.create(linea=linea, numero="2", latitud="7.1", longitud="-75.6")
        tramo = Tramo.objects.create(
            linea=linea,
            codigo="223-LEG",
            nombre="Tramo legado",
            torre_inicio=inicio,
            torre_fin=fin,
        )
        legacy = Cuadrilla.objects.create(
            codigo="01-2099-0002-LEG",
            nombre="Cuadrilla legacy 223",
            tramo=tramo,
            fecha=date(2099, 1, 5),
            fecha_fin=date(2099, 1, 9),
        )

        bloque = _bloque_a_dict(legacy)
        self.assertEqual(bloque["tramo_libre"], "")
        card = render_to_string("cuadrillas/partials/_bloque_card.html", {"b": bloque, "anio": 2099, "semana": 1})
        pdf = render_to_string(
            "cuadrillas/programacion_semanal_pdf.html",
            {
                "bloques": [bloque], "semana": 1, "anio": 2099, "tiene_datos": True,
                "lunes": None, "domingo": None, "total_bloques": 1, "total_miembros": 0,
                "total_novedades": 0, "novedades": [], "generado": None,
            },
        )
        self.assertIn("Tramo 223-LEG - Tramo legado", card)
        self.assertIn("Tramo 223-LEG", pdf)
