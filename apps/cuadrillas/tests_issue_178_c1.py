"""Tests #178 — Sprint (2026-07-25), sub-item C1: botón "Reprogramar" — mover
un bloque desde una fecha específica sin romper el original (pedido C).

Issue: Indunnova16/Instelec#178

C1 agrega ``ProgramacionSemanalBloqueReprogramarView``
(POST /cuadrillas/semanal/bloque/<uuid:pk>/reprogramar/, name
``cuadrillas:semanal_bloque_reprogramar``): en una transacción, trunca
``fecha_fin`` del bloque origen a ``fecha_desde - 1 día``, crea un bloque
nuevo con la nueva actividad/línea + ``reprogramado_desde=origen``, y copia
el personal ACTIVO del origen al bloque nuevo — el origen NO se borra ni
pierde su personal histórico.

Ejecutar:
  DJANGO_SETTINGS_MODULE=config.settings.dev_lite \
    venv/bin/python -m pytest apps/cuadrillas/tests_issue_178_c1.py -v \
    -o python_files="tests_*.py test_*.py"
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.cuadrillas.models import Cuadrilla, CuadrillaMiembro

Usuario = get_user_model()


def _crear_admin():
    # Rol admin (NO superuser) para ejercitar el gate real de RoleRequiredMixin.
    return Usuario.objects.create_user(
        email="admin_178c1@test.com",
        password="testpass123!",
        first_name="Admin",
        last_name="C1",
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


def _crear_bloque(codigo, fecha, nombre="MANTENIMIENTO - 809"):
    return Cuadrilla.objects.create(codigo=codigo, nombre=nombre, activa=True, fecha=fecha)


def _agregar_miembro(
    cuadrilla,
    usuario,
    rol_cuadrilla_id="LINIERO_I",
    cargo=CuadrillaMiembro.CargoJerarquico.MIEMBRO,
):
    return CuadrillaMiembro.objects.create(
        cuadrilla=cuadrilla,
        usuario=usuario,
        rol_cuadrilla_id=rol_cuadrilla_id,
        cargo=cargo,
        costo_dia=0,
        fecha_inicio=cuadrilla.fecha or date.today(),
        activo=True,
    )


class TestC1Reprogramar(TestCase):
    def setUp(self):
        self.admin = _crear_admin()
        self.client.force_login(self.admin)

    def test_happy_reprograma_desde_dia3_origen_intacto_nuevo_con_miembros_copiados(self):
        """happy: reprogramar un bloque QA_E2E_ con 2 miembros desde el día 3
        de la semana -> bloque origen con fecha_fin truncada + 2
        CuadrillaMiembro SIN cambios, bloque nuevo con nueva actividad/línea
        + reprogramado_desde + 2 CuadrillaMiembro copiados."""
        # Semana 46/2026: lunes 2026-11-09 -- domingo 2026-11-15.
        # "Día 3" = miércoles 2026-11-11.
        origen = _crear_bloque("46-2026-0001-MAN", date(2026, 11, 9))
        u1 = _crear_usuario("178C1-001", "QA_E2E_ JHON JIMENEZ")
        u2 = _crear_usuario("178C1-002", "QA_E2E_ ANA TORRES")
        m1 = _agregar_miembro(origen, u1, "LINIERO_I", CuadrillaMiembro.CargoJerarquico.JT_CTA)
        m2 = _agregar_miembro(origen, u2, "AYUDANTE", CuadrillaMiembro.CargoJerarquico.MIEMBRO)

        resp = self.client.post(
            reverse("cuadrillas:semanal_bloque_reprogramar", args=[origen.pk]),
            {
                "nombre": "QA_E2E_ Emergencia sector sur",
                "fecha_desde": "2026-11-11",
                "motivo": "Emergencia reportada por el cliente",
            },
        )
        self.assertEqual(resp.status_code, 200)

        origen.refresh_from_db()
        self.assertEqual(origen.fecha_fin, date(2026, 11, 10))  # día 3 - 1 día
        # El origen NO pierde su personal histórico -- sigue activo, sin cambios.
        self.assertEqual(origen.miembros.filter(activo=True).count(), 2)
        m1.refresh_from_db()
        m2.refresh_from_db()
        self.assertTrue(m1.activo)
        self.assertTrue(m2.activo)
        self.assertEqual(m1.cargo, CuadrillaMiembro.CargoJerarquico.JT_CTA)

        nuevo = Cuadrilla.objects.exclude(pk=origen.pk).get(reprogramado_desde=origen)
        self.assertEqual(nuevo.nombre, "QA_E2E_ Emergencia sector sur")
        self.assertEqual(nuevo.fecha, date(2026, 11, 11))
        self.assertEqual(nuevo.observaciones, "Emergencia reportada por el cliente")
        self.assertEqual(nuevo.miembros.filter(activo=True).count(), 2)
        self.assertEqual(
            set(nuevo.miembros.values_list("usuario_id", flat=True)),
            {u1.id, u2.id},
        )

        # La respuesta trae la card nueva (OOB) + la card del origen actualizada.
        html = resp.content.decode()
        self.assertIn(nuevo.codigo, html)
        self.assertIn(origen.codigo, html)
        self.assertIn("Reprogramado desde", html)

    def test_edge_fecha_fuera_de_semana_del_origen_rechazado(self):
        """edge 1: fecha_desde fuera del rango lunes-domingo del bloque
        origen -> rechazado, NO crea bloque nuevo, origen sin cambios."""
        origen = _crear_bloque("46-2026-0002-MAN", date(2026, 11, 9))
        _agregar_miembro(origen, _crear_usuario("178C1-010", "QA_E2E_ LUIS PENA"))

        resp = self.client.post(
            reverse("cuadrillas:semanal_bloque_reprogramar", args=[origen.pk]),
            {
                "nombre": "QA_E2E_ Fuera de semana",
                "fecha_desde": "2026-11-20",  # semana ISO 47, no 46
            },
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("semana", resp.content.decode().lower())

        origen.refresh_from_db()
        self.assertIsNone(origen.fecha_fin)
        self.assertFalse(Cuadrilla.objects.filter(reprogramado_desde=origen).exists())
        self.assertEqual(Cuadrilla.objects.count(), 1)

    def test_edge_bloque_origen_sin_personal_reprograma_igual(self):
        """edge 2: bloque origen sin personal (0 miembros) -> reprograma
        igual, bloque nuevo con 0 miembros, no rompe."""
        origen = _crear_bloque("46-2026-0003-MAN", date(2026, 11, 9))
        self.assertEqual(origen.miembros.count(), 0)

        resp = self.client.post(
            reverse("cuadrillas:semanal_bloque_reprogramar", args=[origen.pk]),
            {
                "nombre": "QA_E2E_ Sin personal",
                "fecha_desde": "2026-11-11",
            },
        )
        self.assertEqual(resp.status_code, 200)

        origen.refresh_from_db()
        self.assertEqual(origen.fecha_fin, date(2026, 11, 10))
        nuevo = Cuadrilla.objects.exclude(pk=origen.pk).get(reprogramado_desde=origen)
        self.assertEqual(nuevo.miembros.filter(activo=True).count(), 0)

    def test_edge_nombre_vacio_rechazado(self):
        """Robustez: nombre obligatorio -- vacío -> 400, no crea nada."""
        origen = _crear_bloque("46-2026-0004-MAN", date(2026, 11, 9))

        resp = self.client.post(
            reverse("cuadrillas:semanal_bloque_reprogramar", args=[origen.pk]),
            {"nombre": "", "fecha_desde": "2026-11-11"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Cuadrilla.objects.count(), 1)

    def test_edge_fecha_anterior_al_inicio_del_origen_rechazada(self):
        """Robustez: fecha_desde <= fecha de inicio del origen -> rechazado
        (dejaría al origen sin ningún día vigente, contradice "sin romper el
        original")."""
        origen = _crear_bloque("46-2026-0005-MAN", date(2026, 11, 9))

        resp = self.client.post(
            reverse("cuadrillas:semanal_bloque_reprogramar", args=[origen.pk]),
            {"nombre": "QA_E2E_ Mismo dia", "fecha_desde": "2026-11-09"},
        )
        self.assertEqual(resp.status_code, 400)

        origen.refresh_from_db()
        self.assertIsNone(origen.fecha_fin)
        self.assertEqual(Cuadrilla.objects.count(), 1)
