"""
Tests issue #176 — Maestros editables: Tipos de Actividad y Colaboradores.

Cubre (dentro de apps/cuadrillas):
- A2: migración PersonalCuadrilla (salario_base, fecha_ingreso, fecha_salida)
  + save()/signal que fija activo=False cuando se registra fecha_salida.
- A3: CRUD Colaboradores en /cuadrillas/colaboradores/.
- A5: Importer de colaboradores (extiende PersonalCuadrillaUploadView).
- A4: Refactor de asignación a cuadrilla (picklist activo=True, cargo
  bloqueado, autocompletado AJAX, resolución/creación de Usuario).

Issue: Indunnova16/Instelec#176

Ejecutar con:
    python3 manage.py test apps.cuadrillas.tests_issue_176 -v 2
"""

from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from apps.cuadrillas.models import Cuadrilla, CuadrillaMiembro, PersonalCuadrilla

Usuario = get_user_model()


def _crear_admin():
    return Usuario.objects.create_user(
        email="admin_176@test.com",
        password="testpass123!",
        first_name="Admin",
        last_name="Test176",
        rol="admin",
        is_staff=True,
        is_superuser=True,
    )


# ---------------------------------------------------------------------------
# A2 — Migración PersonalCuadrilla: campos nuevos + save()/signal fecha_salida
# ---------------------------------------------------------------------------
class TestA2PersonalCuadrillaCamposNuevos(TestCase):
    """A2: salario_base/fecha_ingreso/fecha_salida + activo=False automático."""

    def test_migracion_aplica_sobre_datos_legacy_defaults_sensatos(self):
        """Un PersonalCuadrilla creado SIN los campos nuevos usa defaults sensatos
        (salario_base=0, fecha_ingreso/fecha_salida=None) — simula un registro
        legacy pre-existente antes de esta migración."""
        legacy = PersonalCuadrilla.objects.create(
            nombre="Colaborador Legacy",
            documento="LEG-0001",
            rol_cuadrilla=PersonalCuadrilla.RolCuadrilla.LINIERO_I,
        )
        legacy.refresh_from_db()
        self.assertEqual(legacy.salario_base, Decimal("0"))
        self.assertIsNone(legacy.fecha_ingreso)
        self.assertIsNone(legacy.fecha_salida)
        self.assertTrue(legacy.activo)

    def test_registrar_fecha_salida_inactiva_automaticamente(self):
        """Al registrar fecha_salida, activo pasa a False vía save()."""
        persona = PersonalCuadrilla.objects.create(
            nombre="Juan Perez",
            documento="176-0001",
            rol_cuadrilla=PersonalCuadrilla.RolCuadrilla.AYUDANTE,
            salario_base=Decimal("1750905"),
            fecha_ingreso=date(2025, 1, 15),
            activo=True,
        )
        self.assertTrue(persona.activo)

        persona.fecha_salida = date.today()
        persona.save()
        persona.refresh_from_db()

        self.assertFalse(persona.activo)
        self.assertIsNotNone(persona.fecha_salida)

    def test_sin_fecha_salida_permanece_activo(self):
        """Sin fecha_salida, el colaborador permanece activo=True (no se toca)."""
        persona = PersonalCuadrilla.objects.create(
            nombre="Maria Gomez",
            documento="176-0002",
            rol_cuadrilla=PersonalCuadrilla.RolCuadrilla.LINIERO_II,
            salario_base=Decimal("2804856"),
            fecha_ingreso=date(2025, 3, 1),
        )
        persona.refresh_from_db()
        self.assertTrue(persona.activo)
        self.assertIsNone(persona.fecha_salida)

        # Editar otro campo sin tocar fecha_salida no debe desactivar.
        persona.salario_base = Decimal("2900000")
        persona.save()
        persona.refresh_from_db()
        self.assertTrue(persona.activo)


# ---------------------------------------------------------------------------
# A3 — CRUD Colaboradores en /cuadrillas/colaboradores/
# ---------------------------------------------------------------------------
class TestA3CRUDColaboradores(TestCase):
    """A3: crear/editar/inactivar sobre PersonalCuadrilla extendido."""

    def setUp(self):
        self.admin = _crear_admin()
        self.client = Client()
        self.client.force_login(self.admin)

    def test_crear_colaborador_persiste(self):
        url = reverse("cuadrillas:colaboradores_crear")
        resp = self.client.post(
            url,
            {
                "nombre": "Carlos Ruiz",
                "documento": "176-1001",
                "rol_cuadrilla": PersonalCuadrilla.RolCuadrilla.CONDUCTOR,
                "salario_base": "1800000",
                "fecha_ingreso": "2026-01-10",
            },
        )
        self.assertIn(resp.status_code, (200, 302))
        self.assertTrue(PersonalCuadrilla.objects.filter(documento="176-1001").exists())
        creado = PersonalCuadrilla.objects.get(documento="176-1001")
        self.assertEqual(creado.nombre, "Carlos Ruiz")
        self.assertEqual(creado.salario_base, Decimal("1800000"))
        self.assertTrue(creado.activo)

    def test_editar_colaborador_existente_actualiza_campos(self):
        persona = PersonalCuadrilla.objects.create(
            nombre="Ana Torres",
            documento="176-1002",
            rol_cuadrilla=PersonalCuadrilla.RolCuadrilla.AYUDANTE,
            salario_base=Decimal("1750905"),
        )
        url = reverse("cuadrillas:colaboradores_editar", args=[persona.pk])
        resp = self.client.post(
            url,
            {
                "nombre": "Ana Torres Actualizada",
                "documento": "176-1002",
                "rol_cuadrilla": PersonalCuadrilla.RolCuadrilla.LINIERO_I,
                "salario_base": "3176095",
                "fecha_ingreso": "2025-05-01",
            },
        )
        self.assertIn(resp.status_code, (200, 302))
        persona.refresh_from_db()
        self.assertEqual(persona.nombre, "Ana Torres Actualizada")
        self.assertEqual(persona.rol_cuadrilla, PersonalCuadrilla.RolCuadrilla.LINIERO_I)
        self.assertEqual(persona.salario_base, Decimal("3176095"))

    def test_documento_duplicado_rechazado_con_mensaje_dominio(self):
        PersonalCuadrilla.objects.create(
            nombre="Pedro Existing",
            documento="176-1003",
            rol_cuadrilla=PersonalCuadrilla.RolCuadrilla.LINIERO_I,
        )
        url = reverse("cuadrillas:colaboradores_crear")
        resp = self.client.post(
            url,
            {
                "nombre": "Otro Pedro",
                "documento": "176-1003",
                "rol_cuadrilla": PersonalCuadrilla.RolCuadrilla.AYUDANTE,
                "salario_base": "1000000",
            },
        )
        # No debe lanzar IntegrityError (500); debe re-renderizar el form con error.
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PersonalCuadrilla.objects.filter(documento="176-1003").count(), 1)
        form = resp.context["form"]
        self.assertFalse(form.is_valid())
        self.assertIn("documento", form.errors)

    def test_inactivar_via_fecha_salida_reusa_signal_a2(self):
        persona = PersonalCuadrilla.objects.create(
            nombre="Luis Mora",
            documento="176-1004",
            rol_cuadrilla=PersonalCuadrilla.RolCuadrilla.LINIERO_I,
            activo=True,
        )
        url = reverse("cuadrillas:colaboradores_editar", args=[persona.pk])
        resp = self.client.post(
            url,
            {
                "nombre": persona.nombre,
                "documento": persona.documento,
                "rol_cuadrilla": persona.rol_cuadrilla,
                "salario_base": "0",
                "fecha_salida": date.today().isoformat(),
            },
        )
        self.assertIn(resp.status_code, (200, 302))
        persona.refresh_from_db()
        self.assertFalse(persona.activo)

    def test_colaborador_inactivo_no_aparece_en_lista_activa(self):
        activo = PersonalCuadrilla.objects.create(
            nombre="Activo Uno",
            documento="176-1005",
            rol_cuadrilla=PersonalCuadrilla.RolCuadrilla.LINIERO_I,
            activo=True,
        )
        PersonalCuadrilla.objects.create(
            nombre="Inactivo Uno",
            documento="176-1006",
            rol_cuadrilla=PersonalCuadrilla.RolCuadrilla.LINIERO_I,
            fecha_salida=date.today(),
        )
        # El listado por defecto muestra todos (activos + inactivos) para que
        # el admin pueda reactivar; el filtro estado=activos es el que
        # excluye inactivos — es el usado por el picklist real (A4).
        url = reverse("cuadrillas:colaboradores_lista")
        resp = self.client.get(url, {"estado": "activos"})
        self.assertEqual(resp.status_code, 200)
        nombres = [p.nombre for p in resp.context["colaboradores"]]
        self.assertIn("Activo Uno", nombres)
        self.assertNotIn("Inactivo Uno", nombres)


# ---------------------------------------------------------------------------
# A5 — Importer de colaboradores (extiende PersonalCuadrillaUploadView)
# ---------------------------------------------------------------------------
class TestA5ImporterColaboradores(TestCase):
    """A5: PersonalCuadrillaUploadView soporta columnas nuevas."""

    def setUp(self):
        self.admin = _crear_admin()
        self.client = Client()
        self.client.force_login(self.admin)

    @staticmethod
    def _build_workbook(rows):
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Nombre", "Documento", "Cargo", "Salario Base", "Fecha Ingreso", "Fecha Salida"])
        for row in rows:
            ws.append(row)
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        buf.name = "colaboradores.xlsx"
        return buf

    def test_importa_fila_con_campos_nuevos(self):
        archivo = self._build_workbook(
            [
                ["Jose Herrera", "176-2001", "AYUDANTE", 1750905, "2025-02-01", ""],
            ]
        )
        url = reverse("cuadrillas:personal_upload")
        resp = self.client.post(url, {"archivo": archivo})
        self.assertIn(resp.status_code, (200, 302))
        persona = PersonalCuadrilla.objects.get(documento="176-2001")
        self.assertEqual(persona.nombre, "Jose Herrera")
        self.assertEqual(persona.salario_base, Decimal("1750905"))
        self.assertEqual(persona.fecha_ingreso, date(2025, 2, 1))
        self.assertIsNone(persona.fecha_salida)
        self.assertTrue(persona.activo)

    def test_fila_sin_fecha_salida_queda_activo(self):
        archivo = self._build_workbook(
            [
                ["Sin Salida", "176-2002", "LINIERO_I", 3176095, "2026-01-01", ""],
            ]
        )
        url = reverse("cuadrillas:personal_upload")
        self.client.post(url, {"archivo": archivo})
        persona = PersonalCuadrilla.objects.get(documento="176-2002")
        self.assertTrue(persona.activo)

    def test_fila_con_fecha_salida_queda_inactivo(self):
        archivo = self._build_workbook(
            [
                ["Con Salida", "176-2003", "LINIERO_I", 3176095, "2024-01-01", "2026-01-01"],
            ]
        )
        url = reverse("cuadrillas:personal_upload")
        self.client.post(url, {"archivo": archivo})
        persona = PersonalCuadrilla.objects.get(documento="176-2003")
        self.assertFalse(persona.activo)

    def test_documento_duplicado_en_archivo_se_reporta_sin_abortar(self):
        # Pre-existente en BD para forzar duplicado ya conocido + duplicado intra-archivo
        PersonalCuadrilla.objects.create(
            nombre="Ya Existe",
            documento="176-2004",
            rol_cuadrilla=PersonalCuadrilla.RolCuadrilla.LINIERO_I,
        )
        archivo = self._build_workbook(
            [
                ["Ya Existe Actualizado", "176-2004", "AYUDANTE", 1800000, "2025-06-01", ""],
                ["Fila Valida", "176-2005", "CONDUCTOR", 480000, "2025-06-01", ""],
            ]
        )
        url = reverse("cuadrillas:personal_upload")
        resp = self.client.post(url, {"archivo": archivo})
        self.assertIn(resp.status_code, (200, 302))
        # El "duplicado" en este importer es update_or_create (no error) — pero
        # la fila válida siguiente SIEMPRE debe procesarse (no abortar el resto).
        self.assertTrue(PersonalCuadrilla.objects.filter(documento="176-2005").exists())
        actualizado = PersonalCuadrilla.objects.get(documento="176-2004")
        self.assertEqual(actualizado.nombre, "Ya Existe Actualizado")


# ---------------------------------------------------------------------------
# A4 — Refactor asignación a cuadrilla
# ---------------------------------------------------------------------------
class TestA4RefactorAsignacionCuadrilla(TestCase):
    """A4: picklist activo=True, cargo bloqueado, AJAX, resolución de Usuario."""

    def setUp(self):
        self.admin = _crear_admin()
        self.client = Client()
        self.client.force_login(self.admin)
        self.cuadrilla = Cuadrilla.objects.create(
            codigo="01-2026-TST",
            nombre="Cuadrilla Test 176",
            activa=True,
        )
        self.personal_activo = PersonalCuadrilla.objects.create(
            nombre="Roberto Activo",
            documento="176-3001",
            rol_cuadrilla=PersonalCuadrilla.RolCuadrilla.LINIERO_I,
            salario_base=Decimal("3176095"),
            activo=True,
        )
        self.personal_inactivo = PersonalCuadrilla.objects.create(
            nombre="Sergio Inactivo",
            documento="176-3002",
            rol_cuadrilla=PersonalCuadrilla.RolCuadrilla.AYUDANTE,
            fecha_salida=date.today(),
        )

    def test_colaborador_inactivo_no_aparece_en_picklist(self):
        url = reverse("cuadrillas:detalle", args=[self.cuadrilla.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        disponibles = resp.context["personal_disponible"]
        ids = [str(p.id) for p in disponibles]
        self.assertIn(str(self.personal_activo.id), ids)
        self.assertNotIn(str(self.personal_inactivo.id), ids)

    def test_autocompletado_ajax_responde_nombre_y_cargo_por_documento(self):
        url = reverse("cuadrillas:personal_detalle_api")
        resp = self.client.get(url, {"documento": "176-3001"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["nombre"], "Roberto Activo")
        self.assertEqual(data["rol_cuadrilla"], PersonalCuadrilla.RolCuadrilla.LINIERO_I)

    def test_cargo_bloqueado_post_con_rol_distinto_usa_el_del_maestro(self):
        url = reverse("cuadrillas:miembro_agregar", args=[self.cuadrilla.pk])
        resp = self.client.post(
            url,
            {
                "documento": "176-3001",
                "rol_cuadrilla": "SUPERVISOR",  # intento de forzar un rol distinto
                "cargo": "MIEMBRO",
            },
        )
        self.assertIn(resp.status_code, (200, 302))
        miembro = CuadrillaMiembro.objects.filter(
            cuadrilla=self.cuadrilla,
            usuario__documento="176-3001",
        ).first()
        self.assertIsNotNone(miembro)
        # Se ignora el rol del POST; se usa el del maestro PersonalCuadrilla.
        self.assertEqual(miembro.rol_cuadrilla, PersonalCuadrilla.RolCuadrilla.LINIERO_I)

    def test_usuario_se_crea_o_reusa_al_asignar_primera_vez(self):
        self.assertFalse(Usuario.objects.filter(documento="176-3001").exists())
        url = reverse("cuadrillas:miembro_agregar", args=[self.cuadrilla.pk])
        self.client.post(
            url,
            {
                "documento": "176-3001",
                "rol_cuadrilla": PersonalCuadrilla.RolCuadrilla.LINIERO_I,
                "cargo": "MIEMBRO",
            },
        )
        usuario = Usuario.objects.get(documento="176-3001")
        self.assertEqual(usuario.get_full_name(), "Roberto Activo")
        self.assertFalse(usuario.is_active)
        self.assertFalse(usuario.has_usable_password())

        miembro = CuadrillaMiembro.objects.get(cuadrilla=self.cuadrilla, usuario=usuario)
        self.assertEqual(miembro.usuario_id, usuario.id)

    def test_colaborador_inactivo_no_puede_ser_asignado(self):
        url = reverse("cuadrillas:miembro_agregar", args=[self.cuadrilla.pk])
        resp = self.client.post(
            url,
            {
                "documento": "176-3002",
                "rol_cuadrilla": PersonalCuadrilla.RolCuadrilla.AYUDANTE,
                "cargo": "MIEMBRO",
            },
        )
        self.assertIn(resp.status_code, (200, 302))
        self.assertFalse(
            CuadrillaMiembro.objects.filter(
                cuadrilla=self.cuadrilla, usuario__documento="176-3002"
            ).exists()
        )

    def test_cuadrillamiembro_legacy_sigue_renderizando_sin_error(self):
        """Miembro legado (Usuario sin PersonalCuadrilla correspondiente)
        sigue apareciendo en la tabla de miembros sin romper la vista."""
        legacy_usuario = Usuario.objects.create_user(
            email="legacy176@test.com",
            password="testpass123!",
            first_name="Legacy",
            last_name="Miembro",
            rol="liniero",
        )
        CuadrillaMiembro.objects.create(
            cuadrilla=self.cuadrilla,
            usuario=legacy_usuario,
            rol_cuadrilla="LINIERO_I",
            fecha_inicio=date.today() - timedelta(days=30),
            activo=True,
        )
        url = reverse("cuadrillas:detalle", args=[self.cuadrilla.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        nombres = [m.usuario.get_full_name() for m in resp.context["miembros"]]
        self.assertIn("Legacy Miembro", nombres)
