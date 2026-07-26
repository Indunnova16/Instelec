"""Tests #178 — Sprint (2026-07-25), sub-item B1: listado de personal SIN
programar en la semana del grid semanal de cuadrillas.

Issue: Indunnova16/Instelec#178

B1 agrega ``_personal_sin_asignar(anio, semana)`` (apps/cuadrillas/views_semanal.py)
-- ``PersonalCuadrilla`` activo del maestro Colaboradores que NO tiene ningún
``CuadrillaMiembro`` activo en los bloques (``Cuadrilla``) de la semana
consultada (Gabriel: manejan hasta 120 personas, "se le queda a uno por ahí
volando") -- y una nueva sección "Personal sin programar" en
``_tab_semanas.html`` (después de NOVEDADES), visible tanto en
``/cuadrillas/semanal/<anio>/<semana>/`` como en la pantalla fusionada
``/cuadrillas/`` (``CuadrillaListView``, ambas reusan ``_contexto_semana``).

Ejecutar:
  DJANGO_SETTINGS_MODULE=config.settings.dev_lite \
    venv/bin/python -m pytest apps/cuadrillas/tests_issue_178_b1.py -v \
    -o python_files="tests_*.py test_*.py"
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.cuadrillas.models import Cuadrilla, CuadrillaMiembro, PersonalCuadrilla
from apps.cuadrillas.views_semanal import _personal_sin_asignar

Usuario = get_user_model()


def _crear_admin():
    # Rol admin (NO superuser) para ejercitar el gate real de RoleRequiredMixin
    # (allowed_roles), no un bypass de superusuario.
    return Usuario.objects.create_user(
        email="admin_178b1@test.com",
        password="testpass123!",
        first_name="Admin",
        last_name="B1",
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


def _crear_personal(documento, nombre, activo=True):
    return PersonalCuadrilla.objects.create(documento=documento, nombre=nombre, activo=activo)


def _crear_bloque(codigo, fecha, miembros, nombre="MANTENIMIENTO - 809"):
    c = Cuadrilla.objects.create(codigo=codigo, nombre=nombre, activa=True, fecha=fecha)
    for usuario in miembros:
        CuadrillaMiembro.objects.create(
            cuadrilla=c,
            usuario=usuario,
            rol_cuadrilla_id="LINIERO_I",
            cargo="MIEMBRO",
            costo_dia=0,
            fecha_inicio=fecha,
            activo=True,
        )
    return c


class TestB1PersonalSinAsignar(TestCase):
    def setUp(self):
        self.admin = _crear_admin()
        self.client.force_login(self.admin)

    def test_happy_colaboradores_sin_bloque_aparecen_listados(self):
        """happy: 2 colaboradores QA_E2E_ activos SIN bloque esta semana →
        ambos aparecen listados; un tercero YA asignado en un bloque de esa
        misma semana NO aparece."""
        _crear_usuario("178B1-001", "QA_E2E_ ANA TORRES")
        _crear_personal("178B1-001", "QA_E2E_ ANA TORRES")
        _crear_usuario("178B1-002", "QA_E2E_ LUIS PENA")
        _crear_personal("178B1-002", "QA_E2E_ LUIS PENA")
        usuario_asignado = _crear_usuario("178B1-003", "QA_E2E_ CARLOS RUIZ")
        _crear_personal("178B1-003", "QA_E2E_ CARLOS RUIZ")
        _crear_bloque("40-2026-0001-MAN", date(2026, 9, 28), [usuario_asignado])

        resp = self.client.get(reverse("cuadrillas:semanal_grid", args=[2026, 40]))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("Personal sin programar", html)
        # CARLOS RUIZ SÍ aparece en la página (está asignado — se ve en la
        # card del bloque), pero NO debe aparecer DENTRO de la sección
        # "Personal sin programar" específicamente. Acotamos el assert a esa
        # sección (no a la página completa) para no confundir "aparece en
        # otro lado legítimamente" con "el filtro de exclusión falló".
        seccion_idx = html.index("Personal sin programar")
        fin_idx = html.find("Datalist global", seccion_idx)
        seccion_html = html[seccion_idx:fin_idx] if fin_idx != -1 else html[seccion_idx:]
        self.assertIn("QA_E2E_ ANA TORRES", seccion_html)
        self.assertIn("QA_E2E_ LUIS PENA", seccion_html)
        self.assertNotIn("QA_E2E_ CARLOS RUIZ", seccion_html)

        # Nivel unitario: el helper devuelve exactamente los documentos esperados.
        docs = list(_personal_sin_asignar(2026, 40).values_list("documento", flat=True))
        self.assertIn("178B1-001", docs)
        self.assertIn("178B1-002", docs)
        self.assertNotIn("178B1-003", docs)

    def test_edge_asignado_en_otra_semana_si_aparece_en_semana_actual(self):
        """edge 1: colaborador asignado a un bloque de OTRA semana → SÍ
        aparece en la semana consultada (no es un falso negativo — "sin
        asignar" está scoped a la semana, no es un estado global)."""
        usuario = _crear_usuario("178B1-010", "QA_E2E_ MARIA LOPEZ")
        _crear_personal("178B1-010", "QA_E2E_ MARIA LOPEZ")
        _crear_bloque("41-2026-0001-MAN", date(2026, 10, 5), [usuario])  # semana 41

        resp = self.client.get(reverse("cuadrillas:semanal_grid", args=[2026, 40]))  # semana 40
        self.assertIn("QA_E2E_ MARIA LOPEZ", resp.content.decode())
        self.assertIn(
            "178B1-010", list(_personal_sin_asignar(2026, 40).values_list("documento", flat=True))
        )

    def test_edge_colaborador_inactivo_no_aparece(self):
        """edge 2: colaborador inactivo (activo=False) → NO aparece aunque
        no esté asignado a ningún bloque."""
        _crear_personal("178B1-020", "QA_E2E_ INACTIVO GOMEZ", activo=False)

        resp = self.client.get(reverse("cuadrillas:semanal_grid", args=[2026, 40]))
        self.assertNotIn("QA_E2E_ INACTIVO GOMEZ", resp.content.decode())
        self.assertNotIn(
            "178B1-020", list(_personal_sin_asignar(2026, 40).values_list("documento", flat=True))
        )

    def test_seccion_no_aparece_si_todos_estan_asignados(self):
        """Sin huecos visibles: si NO hay ningún colaborador sin asignar, la
        sección completa se omite (no un encabezado vacío confuso).

        Neutraliza cualquier ``PersonalCuadrilla`` preexistente ajeno a este
        test (la BD de test se reusa entre corridas, ``--reuse-db`` — no está
        garantizado que empiece vacía) para que el escenario "todos
        asignados" sea determinístico dentro de la transacción de este test."""
        PersonalCuadrilla.objects.update(activo=False)
        usuario = _crear_usuario("178B1-030", "QA_E2E_ UNICO ASIGNADO")
        _crear_personal("178B1-030", "QA_E2E_ UNICO ASIGNADO")
        _crear_bloque("42-2026-0001-MAN", date(2026, 10, 12), [usuario])

        resp = self.client.get(reverse("cuadrillas:semanal_grid", args=[2026, 42]))
        self.assertNotIn("Personal sin programar", resp.content.decode())
        self.assertEqual(list(_personal_sin_asignar(2026, 42)), [])
