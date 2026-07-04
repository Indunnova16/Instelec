"""Tests #178 — Sprint C (parte NO bloqueada): C2 duplicar semana + C3 export PDF.

Issue: Indunnova16/Instelec#178

Cubre la programación semanal (grid mínimo C1 que aloja las acciones, duplicar
semana anterior C2 y export PDF C3). La "semana" se materializa como el conjunto
de ``Cuadrilla`` con prefijo de código ``WW-YYYY-`` — no hay modelo propio.

Ejecutar:
  DJANGO_SETTINGS_MODULE=config.settings.dev_lite \
    venv/bin/python -m pytest apps/cuadrillas/tests_issue_178_bc.py -v \
    -o python_files="tests_*.py test_*.py"
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.cuadrillas.models import Cuadrilla, CuadrillaMiembro, NovedadPersonalSemana

try:
    import weasyprint  # noqa: F401

    WEASYPRINT_OK = True
except Exception:  # pragma: no cover
    WEASYPRINT_OK = False

Usuario = get_user_model()


def _crear_admin():
    # Rol admin (NO superuser) para ejercitar el gate real de RoleRequiredMixin
    # (allowed_roles), no un bypass de superusuario.
    return Usuario.objects.create_user(
        email="admin_178bc@test.com",
        password="testpass123!",
        first_name="Admin",
        last_name="BC",
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


def _crear_bloque(
    codigo, fecha, miembros, nombre="MANTENIMIENTO - 809", obs="Avisos: 5720754 | Orden: 1"
):
    c = Cuadrilla.objects.create(
        codigo=codigo,
        nombre=nombre,
        activa=True,
        observaciones=obs,
        fecha=fecha,
    )
    for usuario, cargo, rol_cuadrilla in miembros:
        CuadrillaMiembro.objects.create(
            cuadrilla=c,
            usuario=usuario,
            rol_cuadrilla=rol_cuadrilla,
            cargo=cargo,
            costo_dia=0,
            fecha_inicio=fecha,
            activo=True,
        )
    return c


# ---------------------------------------------------------------------------
# C2 — Duplicar semana anterior
# ---------------------------------------------------------------------------
class TestC2DuplicarSemana(TestCase):
    def setUp(self):
        self.admin = _crear_admin()
        self.client.force_login(self.admin)
        self.jt = _crear_usuario("111", "PEDRO PEREZ")
        self.ayu = _crear_usuario("222", "JUAN GOMEZ")

    def test_duplicar_semana_con_datos_crea_copia_editable(self):
        """Happy: duplicar semana 12→13 copia bloques + miembros (fechas +7d),
        de forma no destructiva (la semana origen queda intacta)."""
        f = date(2026, 3, 16)
        _crear_bloque(
            "12-2026-0001-MAN",
            f,
            [
                (self.jt, "JT_CTA", "LINIERO_I"),
                (self.ayu, "MIEMBRO", "AYUDANTE"),
            ],
        )
        _crear_bloque(
            "12-2026-0002-PODA", f, [(self.ayu, "MIEMBRO", "AYUDANTE")], nombre="PODA - 810"
        )

        resp = self.client.post(reverse("cuadrillas:semanal_duplicar", args=[2026, 13]))
        self.assertEqual(resp.status_code, 302)

        destino = Cuadrilla.objects.filter(codigo__startswith="13-2026-").order_by("codigo")
        self.assertEqual(destino.count(), 2)
        copia = destino.get(codigo="13-2026-0001-MAN")
        # Miembros copiados
        self.assertEqual(copia.miembros.filter(activo=True).count(), 2)
        # Fecha corrida +7 días
        self.assertEqual(copia.fecha, date(2026, 3, 23))
        self.assertEqual(copia.miembros.first().fecha_inicio, date(2026, 3, 23))
        # No destructivo: la semana origen sigue con sus 2 bloques
        self.assertEqual(Cuadrilla.objects.filter(codigo__startswith="12-2026-").count(), 2)

    def test_duplicar_origen_sin_datos_muestra_error_y_no_crea(self):
        """Edge: la semana anterior no tiene datos → error claro, no crea vacío."""
        resp = self.client.post(
            reverse("cuadrillas:semanal_duplicar", args=[2026, 30]), follow=True
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Cuadrilla.objects.filter(codigo__startswith="30-2026-").exists())
        msgs = [m.message for m in resp.context["messages"]]
        self.assertTrue(any("no tiene programación" in m for m in msgs))

    def test_duplicar_destino_con_datos_pide_confirmacion(self):
        """Edge: destino ya tiene datos → pide confirmación (no crea todavía),
        y al confirmar agrega SOLO lo que falta sin sobrescribir lo existente."""
        f = date(2026, 3, 16)
        _crear_bloque("12-2026-0001-MAN", f, [(self.jt, "JT_CTA", "LINIERO_I")])
        _crear_bloque(
            "12-2026-0002-PODA", f, [(self.ayu, "MIEMBRO", "AYUDANTE")], nombre="PODA - 810"
        )
        # Destino ya tiene el bloque 0002 (con nombre distinto — no debe pisarse)
        _crear_bloque(
            "13-2026-0002-PODA",
            date(2026, 3, 23),
            [(self.jt, "JT_CTA", "LINIERO_I")],
            nombre="ORIGINAL DESTINO",
        )

        # Sin confirmar → no crea el faltante, redirige pidiendo confirmación
        resp = self.client.post(reverse("cuadrillas:semanal_duplicar", args=[2026, 13]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("confirmar_duplicado=1", resp.url)
        self.assertFalse(Cuadrilla.objects.filter(codigo="13-2026-0001-MAN").exists())

        # Con confirmar → crea el faltante (0001) y omite el existente (0002)
        resp2 = self.client.post(
            reverse("cuadrillas:semanal_duplicar", args=[2026, 13]),
            {"confirmar": "1"},
            follow=True,
        )
        self.assertEqual(resp2.status_code, 200)
        self.assertTrue(Cuadrilla.objects.filter(codigo="13-2026-0001-MAN").exists())
        # El bloque destino pre-existente NO se sobrescribió
        self.assertEqual(
            Cuadrilla.objects.get(codigo="13-2026-0002-PODA").nombre, "ORIGINAL DESTINO"
        )

    def test_duplicar_no_copia_novedades(self):
        """Las NOVEDADES no se duplican (son por naturaleza de la semana origen)."""
        f = date(2026, 3, 16)
        _crear_bloque("12-2026-0001-MAN", f, [(self.jt, "JT_CTA", "LINIERO_I")])
        NovedadPersonalSemana.objects.create(
            cedula="999",
            nombre="ANA VACACIONES",
            cargo="AYUDANTE",
            semana=12,
            anio=2026,
            nota="Vacaciones",
        )
        self.client.post(reverse("cuadrillas:semanal_duplicar", args=[2026, 13]))
        self.assertEqual(NovedadPersonalSemana.objects.filter(semana=13, anio=2026).count(), 0)

    def test_duplicar_cruza_anio(self):
        """Edge: semana 1 duplica desde la última semana ISO del año anterior."""
        ultima = date(2025, 12, 28).isocalendar()[1]  # 52 o 53
        f = date(2025, 12, 22)
        _crear_bloque(f"{ultima:02d}-2025-0001-MAN", f, [(self.jt, "JT_CTA", "LINIERO_I")])
        self.client.post(reverse("cuadrillas:semanal_duplicar", args=[2026, 1]))
        self.assertTrue(Cuadrilla.objects.filter(codigo="01-2026-0001-MAN").exists())


# ---------------------------------------------------------------------------
# C3 — Export PDF
# ---------------------------------------------------------------------------
class TestC3ExportPDF(TestCase):
    def setUp(self):
        self.admin = _crear_admin()
        self.client.force_login(self.admin)

    def test_pdf_semana_con_datos(self):
        """Happy: PDF de una semana con datos → 200, content-type PDF, bytes>0."""
        if not WEASYPRINT_OK:
            self.skipTest("weasyprint no disponible en el entorno de test")
        jt = _crear_usuario("111", "PEDRO PEREZ")
        _crear_bloque("12-2026-0001-MAN", date(2026, 3, 16), [(jt, "JT_CTA", "LINIERO_I")])
        resp = self.client.get(reverse("cuadrillas:semanal_pdf", args=[2026, 12]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        content = b"".join(resp.streaming_content) if resp.streaming else resp.content
        self.assertGreater(len(content), 0)
        self.assertTrue(content.startswith(b"%PDF"))

    def test_pdf_semana_vacia_no_500(self):
        """Edge: semana vacía → PDF con 'sin datos', no 500."""
        if not WEASYPRINT_OK:
            self.skipTest("weasyprint no disponible en el entorno de test")
        resp = self.client.get(reverse("cuadrillas:semanal_pdf", args=[2026, 30]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))


# ---------------------------------------------------------------------------
# C1 — Grid semanal (aloja las acciones)
# ---------------------------------------------------------------------------
class TestC1GridSemanal(TestCase):
    def setUp(self):
        self.admin = _crear_admin()
        self.client.force_login(self.admin)

    def test_grid_con_datos_muestra_bloques_y_acciones(self):
        jt = _crear_usuario("111", "PEDRO PEREZ")
        _crear_bloque("12-2026-0001-MAN", date(2026, 3, 16), [(jt, "JT_CTA", "LINIERO_I")])
        resp = self.client.get(reverse("cuadrillas:semanal_grid", args=[2026, 12]))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("PEDRO PEREZ", html)
        self.assertIn("Duplicar semana anterior", html)
        self.assertIn("Exportar PDF", html)

    def test_grid_semana_vacia_no_500(self):
        resp = self.client.get(reverse("cuadrillas:semanal_grid", args=[2026, 30]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("No hay programación", resp.content.decode())

    def test_grid_requiere_login(self):
        self.client.logout()
        resp = self.client.get(reverse("cuadrillas:semanal_grid", args=[2026, 12]))
        self.assertIn(resp.status_code, (302, 301))

    def test_bloque_inactivo_excluido_del_grid_y_del_duplicado(self):
        """Un bloque dado de baja (activa=False) no aparece en el grid ni se
        duplica — consistente con CuadrillaListView (activa=True)."""
        jt = _crear_usuario("111", "PEDRO PEREZ")
        activo = _crear_bloque("12-2026-0001-MAN", date(2026, 3, 16), [(jt, "JT_CTA", "LINIERO_I")])
        inactivo = _crear_bloque(
            "12-2026-0009-OLD",
            date(2026, 3, 16),
            [(jt, "MIEMBRO", "AYUDANTE")],
            nombre="BLOQUE BAJA",
        )
        inactivo.activa = False
        inactivo.save(update_fields=["activa"])

        # Grid: solo el bloque activo
        resp = self.client.get(reverse("cuadrillas:semanal_grid", args=[2026, 12]))
        html = resp.content.decode()
        self.assertIn(activo.codigo, html)
        self.assertNotIn("BLOQUE BAJA", html)

        # Duplicar 12→13: solo copia el activo
        self.client.post(reverse("cuadrillas:semanal_duplicar", args=[2026, 13]))
        self.assertTrue(Cuadrilla.objects.filter(codigo="13-2026-0001-MAN").exists())
        self.assertFalse(Cuadrilla.objects.filter(codigo="13-2026-0009-OLD").exists())
