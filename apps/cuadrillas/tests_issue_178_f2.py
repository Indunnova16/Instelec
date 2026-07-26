"""Tests #178 — Sprint (2026-07-25), sub-item F2: entrada manual de
coordenadas (pedido F, parte 2 — sitios sin señal).

Issue: Indunnova16/Instelec#178

F2 agrega ``apps/cuadrillas/views_mapa.py`` (nuevo módulo, patrón
optional-import) con ``TrackingUbicacionManualCreateView`` — crea un
``TrackingUbicacion(origen='manual')`` puntual para una cuadrilla, distinto
del ping GPS automático. El botón + mini-form viven en ``mapa.html``; el
marcador Leaflet correspondiente usa un ícono distinto (``crew-marker-manual``).

Ejecutar:
  DJANGO_SETTINGS_MODULE=config.settings.local \
    venv/bin/python -m pytest apps/cuadrillas/tests_issue_178_f2.py -v \
    -o python_files="tests_*.py test_*.py"
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.cuadrillas.models import Cuadrilla, TrackingUbicacion

Usuario = get_user_model()


def _crear_admin(sufijo="f2"):
    return Usuario.objects.create_user(
        email=f"admin_178{sufijo}@test.com",
        password="testpass123!",
        first_name="Admin",
        last_name=sufijo.upper(),
        rol="admin",
        is_staff=True,
    )


def _crear_cuadrilla(codigo, activa=True):
    return Cuadrilla.objects.create(codigo=codigo, nombre=f"QA_E2E_ {codigo}", activa=activa)


class TestF2UbicacionManual(TestCase):
    def setUp(self):
        self.admin = _crear_admin("f2")
        self.client.force_login(self.admin)
        self.cuadrilla = _crear_cuadrilla("178F2-0001")

    def test_happy_coordenada_manual_crea_tracking_con_origen_manual(self):
        resp = self.client.post(
            reverse("cuadrillas:ubicacion_manual_crear", args=[self.cuadrilla.pk]),
            {"lat": "4.5709", "lng": "-74.2973"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["ubicacion"]["origen"], "manual")
        self.assertEqual(data["ubicacion"]["cuadrilla_codigo"], "178F2-0001")

        ubicacion = TrackingUbicacion.objects.get(cuadrilla=self.cuadrilla)
        self.assertEqual(ubicacion.origen, TrackingUbicacion.OrigenUbicacion.MANUAL)
        self.assertEqual(ubicacion.usuario, self.admin)
        self.assertAlmostEqual(float(ubicacion.latitud), 4.5709, places=4)
        self.assertAlmostEqual(float(ubicacion.longitud), -74.2973, places=4)

        # Aparece en la respuesta del mapa (MapaCuadrillasPartialView) con
        # origen='manual', distinguible del GPS automático.
        resp_mapa = self.client.get(
            reverse("cuadrillas:mapa_partial"), HTTP_ACCEPT="application/json"
        )
        ubicaciones = resp_mapa.json()["ubicaciones"]
        entrada = next(u for u in ubicaciones if u["cuadrilla_id"] == str(self.cuadrilla.id))
        self.assertEqual(entrada["origen"], "manual")

    def test_edge_lat_fuera_de_rango_rechazado_no_crea_registro(self):
        """edge 1: lat > 90 (fuera de rango válido) -> rechazado, no crea
        el TrackingUbicacion."""
        resp = self.client.post(
            reverse("cuadrillas:ubicacion_manual_crear", args=[self.cuadrilla.pk]),
            {"lat": "95.0", "lng": "-74.2973"},
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data["ok"])
        self.assertIn("rango", data["error"].lower())
        self.assertFalse(TrackingUbicacion.objects.filter(cuadrilla=self.cuadrilla).exists())

    def test_edge_lng_fuera_de_rango_rechazado_no_crea_registro(self):
        resp = self.client.post(
            reverse("cuadrillas:ubicacion_manual_crear", args=[self.cuadrilla.pk]),
            {"lat": "4.5709", "lng": "-200.0"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(TrackingUbicacion.objects.filter(cuadrilla=self.cuadrilla).exists())

    def test_edge_cuadrilla_inactiva_no_permite_reportar_ubicacion(self):
        """edge 2: cuadrilla dada de baja (activa=False) -> no permite
        reportar ubicación manual para ella."""
        cuadrilla_inactiva = _crear_cuadrilla("178F2-0002", activa=False)
        resp = self.client.post(
            reverse("cuadrillas:ubicacion_manual_crear", args=[cuadrilla_inactiva.pk]),
            {"lat": "4.5709", "lng": "-74.2973"},
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data["ok"])
        self.assertIn("inactiva", data["error"].lower())
        self.assertFalse(TrackingUbicacion.objects.filter(cuadrilla=cuadrilla_inactiva).exists())

    def test_edge_valores_no_numericos_rechazados(self):
        """Robustez extra: lat/lng con texto no numérico -> 400 explícito, no
        un 500 crudo de Decimal()."""
        resp = self.client.post(
            reverse("cuadrillas:ubicacion_manual_crear", args=[self.cuadrilla.pk]),
            {"lat": "no-es-numero", "lng": "-74.2973"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(TrackingUbicacion.objects.filter(cuadrilla=self.cuadrilla).exists())

    def test_cuadrilla_inexistente_404(self):
        import uuid

        resp = self.client.post(
            reverse("cuadrillas:ubicacion_manual_crear", args=[uuid.uuid4()]),
            {"lat": "4.5709", "lng": "-74.2973"},
        )
        self.assertEqual(resp.status_code, 404)

    def test_mapa_view_expone_cuadrillas_activas_para_el_selector(self):
        """El selector del mini-form debe listar cuadrillas activas
        (incluso sin tracking previo) — no solo las que ya aparecen en
        MapaCuadrillasPartialView."""
        resp = self.client.get(reverse("cuadrillas:mapa"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("178F2-0001", resp.content.decode())
        self.assertIn("Coordenada manual", resp.content.decode())
