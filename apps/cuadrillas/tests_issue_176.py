"""
Tests issue #176 — Maestros editables: Tipos de Actividad, Colaboradores y
Cargos.

Cubre (dentro de apps/cuadrillas):
- A2 (bounce 1): migración PersonalCuadrilla (salario_base, fecha_ingreso,
  fecha_salida) + save()/signal que fija activo=False cuando se registra
  fecha_salida.
- A3 (bounce 1): CRUD Colaboradores en /cuadrillas/colaboradores/.
- A5 (bounce 1): Importer de colaboradores (extiende PersonalCuadrillaUploadView).
- A4 (bounce 1): Refactor de asignación a cuadrilla (picklist activo=True,
  cargo bloqueado, autocompletado AJAX, resolución/creación de Usuario).
- TestMaestro3A1CargoModeloYSeed (bounce 2, Maestro 3): modelo Cargo +
  migración de seed 0019_seed_cargos (14 códigos de la unión de ambos
  RolCuadrilla). Las clases `TestMaestro3A*` cubren los sub-items A1-A6 del
  plan SPRINTS/PLAN_2026-07-10_maestro_cargos.md — usan el prefijo
  "Maestro3" para no colisionar con los nombres TestA2/A3/A4/A5 del
  bounce 1 de arriba (letras reusadas en el plan nuevo).

Issue: Indunnova16/Instelec#176

Ejecutar con:
    pytest apps/cuadrillas/tests_issue_176.py -v
"""

import importlib
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.cuadrillas.models import Cargo, Cuadrilla, CuadrillaMiembro, PersonalCuadrilla

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
        PersonalCuadrilla.objects.create(
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


# ---------------------------------------------------------------------------
# Reproceso bounce=1 (FIX_INCOMPLETO) — navbar Parametrizacion sin los 2
# maestros nuevos, formato de moneda sin intcomma y boton "Subir Excel de
# Cargos" mezclado con el card "Agregar Miembro".
# ---------------------------------------------------------------------------
class TestReprocesoNavbarFormatoBoton(TestCase):
    """QA #176 bounce=1: reporto que los maestros de A1/A3 no eran
    descubribles por navegacion normal (solo por URL directa), que los
    montos monetarios de Colaboradores no tenian separador de miles, y que
    el boton de carga masiva de Excel quedo dentro del card de alta
    individual de miembro."""

    def setUp(self):
        self.admin = _crear_admin()
        self.client = Client()
        self.client.force_login(self.admin)

    def test_sidebar_incluye_links_a_tipos_actividad_y_colaboradores(self):
        url = reverse("cuadrillas:colaboradores_lista")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, reverse("actividades:tipos_lista"))
        self.assertContains(resp, reverse("cuadrillas:colaboradores_lista"))

    def test_salario_base_se_muestra_con_separador_de_miles(self):
        PersonalCuadrilla.objects.create(
            nombre="Colaborador Moneda",
            documento="176-4001",
            rol_cuadrilla=PersonalCuadrilla.RolCuadrilla.LINIERO_I,
            salario_base=Decimal("3176095"),
            activo=True,
        )
        url = reverse("cuadrillas:colaboradores_lista")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "3.176.095")

    def test_costo_dia_miembro_se_muestra_con_separador_de_miles(self):
        cuadrilla = Cuadrilla.objects.create(
            codigo="02-2026-TST",
            nombre="Cuadrilla Moneda 176",
            activa=True,
        )
        usuario = Usuario.objects.create_user(
            email="miembro176moneda@test.com",
            password="testpass123!",
            first_name="Roberto",
            last_name="Moneda",
            rol="liniero",
            documento="176-4002",
        )
        CuadrillaMiembro.objects.create(
            cuadrilla=cuadrilla,
            usuario=usuario,
            rol_cuadrilla=PersonalCuadrilla.RolCuadrilla.LINIERO_I,
            costo_dia=Decimal("3176095"),
            fecha_inicio=date.today(),
            activo=True,
        )
        url = reverse("cuadrillas:detalle", args=[cuadrilla.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "3.176.095")

    def test_boton_subir_excel_cargos_queda_en_card_propio(self):
        """El boton + form colapsable de carga masiva debe quedar en su
        propio card, cerrado ANTES de que abra el card 'Agregar Miembro'
        (antes de este fix compartian el mismo div)."""
        cuadrilla = Cuadrilla.objects.create(
            codigo="03-2026-TST",
            nombre="Cuadrilla Reubicacion 176",
            activa=True,
        )
        url = reverse("cuadrillas:detalle", args=[cuadrilla.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        idx_subir = content.index("Subir Excel de Cargos")
        idx_agregar = content.index("Agregar Miembro")
        idx_cierre_form_upload = content.index("</form>", idx_subir)
        self.assertLess(idx_subir, idx_agregar)
        # El form de upload (dentro de su propio card) debe cerrarse antes
        # de que empiece el texto "Agregar Miembro" del card siguiente.
        self.assertLess(idx_cierre_form_upload, idx_agregar)


# ---------------------------------------------------------------------------
# Maestro 3: Cargos (issue #176, bounce 2) — A1: modelo Cargo + seed
# ---------------------------------------------------------------------------
# Los 14 códigos esperados: union de PersonalCuadrilla.RolCuadrilla y
# CuadrillaMiembro.RolCuadrilla (idénticos, confirmado en F2). Se corre la
# función de la migración 0019_seed_cargos directamente (importlib, el
# nombre del módulo empieza con dígitos y no es importable con `import`
# normal) contra el registro de apps real — el schema de Cargo no ha
# cambiado de forma desde 0018, así que apps.get_model('cuadrillas','Cargo')
# resuelve igual con el apps registry real que con el histórico.
_SEED_MODULE = importlib.import_module("apps.cuadrillas.migrations.0019_seed_cargos")


class TestMaestro3A1CargoModeloYSeed(TestCase):
    """A1: modelo Cargo (codigo/nombre/activo) + data migration de seed."""

    def test_modelo_cargo_tiene_los_campos_esperados(self):
        cargo = Cargo.objects.create(codigo="SOLDADOR", nombre="Soldador")
        self.assertTrue(cargo.activo)
        self.assertEqual(str(cargo), "SOLDADOR - Soldador")

    def test_codigo_es_unico(self):
        from django.db import transaction
        from django.db.utils import IntegrityError

        Cargo.objects.create(codigo="SUPERVISOR", nombre="Supervisor")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Cargo.objects.create(codigo="SUPERVISOR", nombre="Otro Nombre")

    def test_seed_crea_los_14_codigos_de_la_union_de_ambos_enums(self):
        _SEED_MODULE.seed_cargos(django_apps, None)
        self.assertEqual(Cargo.objects.count(), 14)
        codigos_sembrados = set(Cargo.objects.values_list("codigo", flat=True))
        codigos_personal = {c for c, _ in PersonalCuadrilla.RolCuadrilla.choices}
        codigos_miembro = {c for c, _ in CuadrillaMiembro.RolCuadrilla.choices}
        self.assertEqual(codigos_personal, codigos_miembro)  # union == cada uno (idénticos)
        self.assertEqual(codigos_sembrados, codigos_personal)

    def test_seed_labels_coinciden_con_rolcuadrilla_choices(self):
        _SEED_MODULE.seed_cargos(django_apps, None)
        labels_esperados = dict(PersonalCuadrilla.RolCuadrilla.choices)
        for cargo in Cargo.objects.all():
            self.assertEqual(cargo.nombre, labels_esperados[cargo.codigo])

    def test_seed_es_idempotente_correrlo_dos_veces_no_duplica(self):
        _SEED_MODULE.seed_cargos(django_apps, None)
        _SEED_MODULE.seed_cargos(django_apps, None)
        self.assertEqual(Cargo.objects.count(), 14)

    def test_seed_no_pisa_activo_false_si_ya_fue_inactivado_por_el_usuario(self):
        """get_or_create solo aplica defaults en creación — si el
        coordinador ya inactivó un cargo sembrado, re-correr la migración
        (idempotencia) no debe reactivarlo."""
        _SEED_MODULE.seed_cargos(django_apps, None)
        cargo = Cargo.objects.get(codigo="ASISTENTE_FOREST")
        cargo.activo = False
        cargo.save(update_fields=["activo"])
        _SEED_MODULE.seed_cargos(django_apps, None)
        cargo.refresh_from_db()
        self.assertFalse(cargo.activo)
        self.assertEqual(Cargo.objects.count(), 14)
