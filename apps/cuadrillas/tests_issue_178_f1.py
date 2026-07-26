"""Tests #178 — Sprint (2026-07-25), sub-item F1: filtro por semana en el
Mapa de cuadrillas.

Issue: Indunnova16/Instelec#178

F1 extrae ``_prefijo`` de ``views_semanal.py`` a ``apps/cuadrillas/utils_semana.py``
(solo mover) y hace que ``MapaCuadrillasPartialView.get_context_data``
(``apps/cuadrillas/views.py``) acepte ``?anio=&semana=`` opcional, filtrando
``Cuadrilla.objects.filter(activa=True, codigo__startswith=_prefijo(anio, semana))``
— MISMO criterio ``codigo`` ``WW-YYYY-`` que usa todo el resto del módulo
(``_bloques_qs``). El wiring de JS (selector + ``loadCrewLocations()``
leyendo ``window.location.search``) vive en ``mapa.html`` y se valida por
E2E real (F5) — el test client de Django no ejecuta JS; acá se cubre el
comportamiento server-side de la vista, que es lo que el fetch del browser
termina consultando.

Ejecutar:
  DJANGO_SETTINGS_MODULE=config.settings.dev_lite \
    venv/bin/python -m pytest apps/cuadrillas/tests_issue_178_f1.py -v \
    -o python_files="tests_*.py test_*.py"
"""

import json
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.cuadrillas.models import Cuadrilla, TrackingUbicacion
from apps.cuadrillas.utils_semana import _prefijo

Usuario = get_user_model()


def _crear_admin():
    return Usuario.objects.create_user(
        email="admin_178f1@test.com",
        password="testpass123!",
        first_name="Admin",
        last_name="F1",
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


def _crear_cuadrilla_con_ubicacion(codigo, nombre, usuario, lat, lng):
    c = Cuadrilla.objects.create(codigo=codigo, nombre=nombre, activa=True, fecha=date(2026, 9, 28))
    TrackingUbicacion.objects.create(cuadrilla=c, usuario=usuario, latitud=lat, longitud=lng)
    return c


class TestUtilsSemanaPrefijoExtraido(TestCase):
    """F1: `_prefijo` ahora vive en utils_semana.py y views_semanal.py sigue
    exponiéndolo con el mismo nombre (import, no redefinición) — no debe
    haber quedado una copia duplicada desincronizada."""

    def test_prefijo_mismo_resultado_desde_ambos_modulos(self):
        from apps.cuadrillas import views_semanal

        self.assertEqual(_prefijo(2026, 5), "05-2026-")
        self.assertEqual(views_semanal._prefijo(2026, 5), _prefijo(2026, 5))
        self.assertIs(views_semanal._prefijo, _prefijo)


class TestF1FiltroSemanaMapa(TestCase):
    def setUp(self):
        self.admin = _crear_admin()
        self.client.force_login(self.admin)

    def _get_json(self, **params):
        resp = self.client.get(
            reverse("cuadrillas:mapa_partial"),
            params,
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        return json.loads(resp.content)

    def test_happy_filtra_solo_la_semana_pedida(self):
        """happy: 2 bloques QA_E2E_ en semanas DISTINTAS, cada uno con su
        TrackingUbicacion → filtrar por una semana muestra SOLO esa."""
        u1 = _crear_usuario("178F1-001", "QA_E2E_ TRACKER UNO")
        u2 = _crear_usuario("178F1-002", "QA_E2E_ TRACKER DOS")
        _crear_cuadrilla_con_ubicacion(
            "40-2026-0001-MAN", "QA_E2E_ BLOQUE SEMANA 40", u1, "4.60000000", "-74.08000000"
        )
        _crear_cuadrilla_con_ubicacion(
            "41-2026-0001-MAN", "QA_E2E_ BLOQUE SEMANA 41", u2, "4.61000000", "-74.09000000"
        )

        data = self._get_json(anio=2026, semana=40)
        codigos = {u["cuadrilla_codigo"] for u in data["ubicaciones"]}
        self.assertIn("40-2026-0001-MAN", codigos)
        self.assertNotIn("41-2026-0001-MAN", codigos)

        # Confirma el criterio: el mismo prefijo que usa el resto del módulo.
        self.assertTrue(Cuadrilla.objects.filter(codigo__startswith=_prefijo(2026, 40)).exists())

    def test_sin_filtro_muestra_todas(self):
        """Comportamiento actual preservado: sin `anio`/`semana` en la
        querystring, se listan TODAS las cuadrillas activas con ubicación."""
        u1 = _crear_usuario("178F1-003", "QA_E2E_ TRACKER TRES")
        u2 = _crear_usuario("178F1-004", "QA_E2E_ TRACKER CUATRO")
        _crear_cuadrilla_con_ubicacion(
            "40-2026-0002-MAN", "QA_E2E_ BLOQUE A", u1, "4.60000000", "-74.08000000"
        )
        _crear_cuadrilla_con_ubicacion(
            "41-2026-0002-MAN", "QA_E2E_ BLOQUE B", u2, "4.61000000", "-74.09000000"
        )

        data = self._get_json()
        codigos = {u["cuadrilla_codigo"] for u in data["ubicaciones"]}
        self.assertIn("40-2026-0002-MAN", codigos)
        self.assertIn("41-2026-0002-MAN", codigos)

    def test_edge_semana_sin_ninguna_cuadrilla_no_rompe(self):
        """edge: semana sin ninguna cuadrilla → lista vacía, 200 (el overlay
        informativo del mapa ya existente, #175 A3, lo maneja client-side)."""
        u1 = _crear_usuario("178F1-005", "QA_E2E_ TRACKER CINCO")
        _crear_cuadrilla_con_ubicacion(
            "40-2026-0003-MAN", "QA_E2E_ BLOQUE C", u1, "4.60000000", "-74.08000000"
        )

        data = self._get_json(anio=2099, semana=1)
        self.assertEqual(data["ubicaciones"], [])

    def test_edge_parametros_no_numericos_ignora_filtro_no_500(self):
        """Parámetros de querystring corruptos/no numéricos no deben romper
        la vista con un 500 — se ignora el filtro (comportamiento actual:
        todas las cuadrillas activas)."""
        u1 = _crear_usuario("178F1-006", "QA_E2E_ TRACKER SEIS")
        _crear_cuadrilla_con_ubicacion(
            "40-2026-0004-MAN", "QA_E2E_ BLOQUE D", u1, "4.60000000", "-74.08000000"
        )

        data = self._get_json(anio="abc", semana="xyz")
        codigos = {u["cuadrilla_codigo"] for u in data["ubicaciones"]}
        self.assertIn("40-2026-0004-MAN", codigos)

    def test_mapa_view_get_html_acepta_querystring_sin_error(self):
        """La página completa /cuadrillas/mapa/?anio=&semana= (URL directa,
        testable — el JS la lee en DOMContentLoaded) sigue devolviendo 200."""
        resp = self.client.get(reverse("cuadrillas:mapa") + "?anio=2026&semana=40")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('id="filtro-anio"', html)
        self.assertIn('id="filtro-semana"', html)
