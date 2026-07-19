"""
Tests issue #176 (bounce 3) — Salario enlazado a Cargo + Import/Export masivo.

Archivo NUEVO (A8 del plan `SPRINTS/PLAN_2026-07-19_176_salario_cargo_import_export.md`),
consolidado por sub-item conforme se fue implementando el sprint completo
(A1-A7) en el mismo worktree/branch. Convención de nombres de clase:
`Test<subitem><Tema>`.

HALLAZGO CRÍTICO documentado en el plan (y que este archivo verifica
explícitamente en `TestA4RegresionFinanciero*`): `financiero/reports.py` y
`apps/cuadrillas/views_semanal.py` **NO leen** `Cargo.salario_base` ni
`PersonalCuadrilla.salario_base` hoy — usan fuentes de datos completamente
distintas (un dict hardcoded con bug de casing preexistente, y el campo
persistido `CuadrillaMiembro.costo_dia`, respectivamente). El pedido
original del cliente ("el salario permite calcular costo/día en reportes")
NO queda resuelto por el alcance de este issue — es una decisión de scope
explícita, documentada acá y en el comentario de cierre (A10, F6).

Issue: Indunnova16/Instelec#176

Ejecutar con:
    DJANGO_SETTINGS_MODULE=config.settings.dev_lite \
        venv/bin/python -m pytest apps/cuadrillas/tests_issue_176_salario.py -v
"""

from datetime import date
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.cuadrillas.models import Cargo, Cuadrilla, CuadrillaMiembro, PersonalCuadrilla
from tests.factories import (
    ActividadCompletadaFactory,
    CuadrillaFactory,
    CuadrillaMiembroFactory,
)

Usuario = get_user_model()


def _crear_admin(sufijo="176sal"):
    return Usuario.objects.create_user(
        email=f"admin_{sufijo}@test.com",
        password="testpass123!",
        first_name="Admin",
        last_name="Salario176",
        rol="admin",
        is_staff=True,
        is_superuser=True,
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


# ---------------------------------------------------------------------------
# A4 — Test de regresión financiero (premisa corregida vs. supuesto original)
# ---------------------------------------------------------------------------
class TestA4RegresionFinancieroReportsPy(TestCase):
    """`financiero.reports.CuadroCostosGenerator._calcular_costos_personal`
    sigue usando su propio dict interno `valores_dia` (con el bug de casing
    preexistente ya documentado, fuera de scope) -- NO lee `Cargo.salario_base`
    ni `PersonalCuadrilla.salario_base`, aunque A1-A3 ya existan."""

    def test_calcular_costos_personal_ignora_cargo_salario_base(self):
        cargo = Cargo.objects.filter(codigo="LINIERO_I").first()
        if cargo is None:
            cargo = Cargo.objects.create(codigo="LINIERO_I", nombre="Liniero I")
        # Valor absurdo/inconfundible: si el código llegara a leer esto, el
        # test lo detecta inmediatamente (no matchea el 80000 del fallback).
        cargo.salario_base = Decimal("999999999")
        cargo.save(update_fields=["salario_base"])

        actividad = ActividadCompletadaFactory()
        CuadrillaMiembroFactory(
            cuadrilla=actividad.cuadrilla,
            rol_cuadrilla_id="LINIERO_I",
            fecha_inicio=actividad.fecha_programada,
        )

        from apps.actividades.models import Actividad
        from apps.financiero.reports import CuadroCostosGenerator

        generator = CuadroCostosGenerator(
            anio=actividad.fecha_programada.year, mes=actividad.fecha_programada.month
        )
        actividades_qs = Actividad.objects.filter(pk=actividad.pk)
        resultado = generator._calcular_costos_personal(actividades_qs)

        self.assertEqual(len(resultado["detalle"]), 1)
        valor_dia = resultado["detalle"][0]["valor_dia"]
        # Bug preexistente (fuera de scope): 'LINIERO_I' (mayúscula, código
        # real) nunca matchea las keys lowercase de valores_dia -> cae al
        # default 80000. Lo que este test PROTEGE es que A1-A3 no lo cambien
        # a leer Cargo.salario_base (999999999) por accidente.
        self.assertEqual(valor_dia, Decimal("80000"))
        self.assertNotEqual(valor_dia, cargo.salario_base)

    def test_calcular_costos_personal_ignora_personal_cuadrilla_salario_base(self):
        """Aunque el PersonalCuadrilla del miembro tenga salario_base editado
        vía el CRUD de Colaboradores (A1 bounce 1), _calcular_costos_personal
        no lo consulta -- trabaja sobre CuadrillaMiembro, no PersonalCuadrilla."""
        usuario = _crear_usuario("176sal-fin-001", "Regresion Financiera")
        PersonalCuadrilla.objects.filter(documento="176sal-fin-001").delete()
        PersonalCuadrilla.objects.create(
            nombre="Regresion Financiera",
            documento="176sal-fin-001",
            rol_cuadrilla_id="AYUDANTE",
            salario_base=Decimal("777777777"),
        )
        actividad = ActividadCompletadaFactory()
        CuadrillaMiembro.objects.create(
            cuadrilla=actividad.cuadrilla,
            usuario=usuario,
            rol_cuadrilla_id="AYUDANTE",
            fecha_inicio=actividad.fecha_programada,
            activo=True,
        )

        from apps.actividades.models import Actividad
        from apps.financiero.reports import CuadroCostosGenerator

        generator = CuadroCostosGenerator(
            anio=actividad.fecha_programada.year, mes=actividad.fecha_programada.month
        )
        resultado = generator._calcular_costos_personal(
            Actividad.objects.filter(pk=actividad.pk)
        )
        valor_dia = resultado["detalle"][0]["valor_dia"]
        self.assertNotEqual(valor_dia, Decimal("777777777"))


class TestA4RegresionFinancieroViewsSemanal(TestCase):
    """`views_semanal.ProgramacionSemanalDuplicarView` sigue copiando el
    campo PERSISTIDO `CuadrillaMiembro.costo_dia` (fijado una vez al crear
    el miembro) -- no recalcula desde `Cargo.salario_base` en cada
    duplicado, aunque el Cargo tenga un salario distinto asignado después."""

    def setUp(self):
        self.admin = _crear_admin("176sal-sem")
        self.client = Client()
        self.client.force_login(self.admin)

    def test_duplicar_semana_copia_costo_dia_persistido_no_salario_base_actual(self):
        cargo = Cargo.objects.filter(codigo="AYUDANTE").first()
        if cargo is None:
            cargo = Cargo.objects.create(codigo="AYUDANTE", nombre="Ayudante")
        usuario = _crear_usuario("176sal-sem-001", "Duplicado Semanal")

        origen = Cuadrilla.objects.create(
            codigo="20-2026-9001-MAN",
            nombre="MANTENIMIENTO - 176SAL",
            activa=True,
            fecha=date(2026, 5, 11),
        )
        CuadrillaMiembro.objects.create(
            cuadrilla=origen,
            usuario=usuario,
            rol_cuadrilla_id="AYUDANTE",
            cargo=CuadrillaMiembro.CargoJerarquico.MIEMBRO,
            costo_dia=Decimal("1750905"),
            fecha_inicio=date(2026, 5, 11),
            activo=True,
        )

        # Después de crear el miembro (costo_dia ya fijado), el Cargo cambia
        # de salario -- si el duplicado leyera Cargo.salario_base en vez del
        # costo_dia persistido, el valor copiado sería distinto.
        cargo.salario_base = Decimal("555555555")
        cargo.save(update_fields=["salario_base"])

        resp = self.client.post(reverse("cuadrillas:semanal_duplicar", args=[2026, 21]))
        self.assertEqual(resp.status_code, 302)

        copia = Cuadrilla.objects.get(codigo="21-2026-9001-MAN")
        miembro_copia = copia.miembros.get(usuario=usuario)
        self.assertEqual(miembro_copia.costo_dia, Decimal("1750905"))
        self.assertNotEqual(miembro_copia.costo_dia, cargo.salario_base)


class TestA4SmokeNominaRenderOnly(TestCase):
    """Smoke E2E render-only: /financiero/nomina/ sigue respondiendo 200
    después de A1-A3 (no regresión de import/carga de módulos)."""

    def setUp(self):
        self.admin = _crear_admin("176sal-nomina")
        self.client = Client()
        self.client.force_login(self.admin)

    def test_nomina_renderiza_sin_error(self):
        resp = self.client.get(reverse("financiero:nomina"))
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# A5 — Import/export masivo de Cargo (upsert por código)
# ---------------------------------------------------------------------------
class TestA5ImportExportCargo(TestCase):
    """CargoUploadView (upsert por código) + CargoExportView (xlsx)."""

    def setUp(self):
        self.admin = _crear_admin("176sal-a5")
        self.client = Client()
        self.client.force_login(self.admin)

    @staticmethod
    def _build_workbook(rows):
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Código", "Nombre", "Salario Base"])
        for row in rows:
            ws.append(row)
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        buf.name = "cargos.xlsx"
        return buf

    def test_import_crea_codigo_nuevo(self):
        archivo = self._build_workbook([["QA_A5_NUEVO", "Cargo A5 Nuevo", 2500000]])
        url = reverse("cuadrillas:cargos_upload")
        resp = self.client.post(url, {"archivo": archivo})
        self.assertIn(resp.status_code, (200, 302))
        cargo = Cargo.objects.get(codigo="QA_A5_NUEVO")
        self.assertEqual(cargo.nombre, "Cargo A5 Nuevo")
        self.assertEqual(cargo.salario_base, Decimal("2500000"))
        self.assertTrue(cargo.activo)

    def test_import_actualiza_nombre_y_salario_de_codigo_existente(self):
        Cargo.objects.create(codigo="QA_A5_EXISTE", nombre="Nombre Viejo", salario_base=Decimal("1"))
        archivo = self._build_workbook([["QA_A5_EXISTE", "Nombre Actualizado", 3300000]])
        url = reverse("cuadrillas:cargos_upload")
        resp = self.client.post(url, {"archivo": archivo})
        self.assertIn(resp.status_code, (200, 302))
        cargo = Cargo.objects.get(codigo="QA_A5_EXISTE")
        self.assertEqual(cargo.nombre, "Nombre Actualizado")
        self.assertEqual(cargo.salario_base, Decimal("3300000"))
        # Sigue siendo UN solo registro (upsert, no duplicado).
        self.assertEqual(Cargo.objects.filter(codigo="QA_A5_EXISTE").count(), 1)

    def test_import_dos_filas_una_nueva_una_existente_ambas_persisten(self):
        """Test contra dato legacy real: LINIERO_I (sembrado por el conftest
        autouse) se actualiza junto con un código nuevo en la MISMA carga --
        no se aborta el lote por mezclar creación + actualización."""
        cargo_legacy = Cargo.objects.get(codigo="LINIERO_I")
        salario_original = cargo_legacy.salario_base
        archivo = self._build_workbook(
            [
                ["LINIERO_I", "Liniero I", 3176095],
                ["QA_A5_LOTE_NUEVO", "Cargo Lote Nuevo", 1900000],
            ]
        )
        url = reverse("cuadrillas:cargos_upload")
        resp = self.client.post(url, {"archivo": archivo})
        self.assertIn(resp.status_code, (200, 302))
        cargo_legacy.refresh_from_db()
        self.assertEqual(cargo_legacy.salario_base, Decimal("3176095"))
        self.assertNotEqual(cargo_legacy.salario_base, salario_original)
        self.assertTrue(Cargo.objects.filter(codigo="QA_A5_LOTE_NUEVO").exists())

    def test_import_fila_con_salario_invalido_no_aborta_lote_completo(self):
        """Edge case: una fila con salario no numérico cae a 0 (no revienta
        el proceso) y la fila siguiente válida igual se procesa."""
        archivo = self._build_workbook(
            [
                ["QA_A5_SALARIO_MALO", "Cargo Salario Malo", "no-es-un-numero"],
                ["QA_A5_SALARIO_OK", "Cargo Salario OK", 1000000],
            ]
        )
        url = reverse("cuadrillas:cargos_upload")
        resp = self.client.post(url, {"archivo": archivo})
        self.assertIn(resp.status_code, (200, 302))
        malo = Cargo.objects.get(codigo="QA_A5_SALARIO_MALO")
        self.assertEqual(malo.salario_base, Decimal("0"))
        ok = Cargo.objects.get(codigo="QA_A5_SALARIO_OK")
        self.assertEqual(ok.salario_base, Decimal("1000000"))

    def test_export_descarga_xlsx_con_tres_columnas_correctas(self):
        Cargo.objects.create(codigo="QA_A5_EXPORT", nombre="Cargo Exportable", salario_base=Decimal("4200000"))
        url = reverse("cuadrillas:cargos_export")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        import openpyxl

        wb = openpyxl.load_workbook(BytesIO(resp.content))
        ws = wb.active
        header = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
        self.assertEqual(header, ["Código", "Nombre", "Salario Base"])
        codigos = [row[0] for row in ws.iter_rows(min_row=2, values_only=True)]
        self.assertIn("QA_A5_EXPORT", codigos)

    def test_import_sin_archivo_muestra_error_no_500(self):
        url = reverse("cuadrillas:cargos_upload")
        resp = self.client.post(url, {})
        self.assertIn(resp.status_code, (200, 302))


# ---------------------------------------------------------------------------
# A6 — Exponer import de Colaboradores en su pantalla natural + export
# ---------------------------------------------------------------------------
class TestA6ImportColaboradoresExpuestoYExport(TestCase):
    """El import (PersonalCuadrillaUploadView) YA FUNCIONA -- A6 solo agrega
    una segunda entrada visual en /cuadrillas/colaboradores/ apuntando al
    MISMO endpoint (sin tocar su lógica) + el export nuevo."""

    def setUp(self):
        self.admin = _crear_admin("176sal-a6")
        self.client = Client()
        self.client.force_login(self.admin)

    def test_modal_importar_visible_en_colaboradores_lista(self):
        resp = self.client.get(reverse("cuadrillas:colaboradores_lista"))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("modal-importar-colaboradores", content)
        self.assertIn(reverse("cuadrillas:personal_upload"), content)

    def test_modal_nuevo_postea_al_mismo_endpoint_ya_validado(self):
        """El modal nuevo de colaboradores_lista.html debe postear al MISMO
        personal_upload que ya funciona (validado en vivo por el cliente
        2026-07-17) -- no se duplica ni se reimplementa la lógica."""
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Nombre", "Documento", "Cargo", "Salario Base", "Fecha Ingreso", "Fecha Salida"])
        ws.append(["Via Modal Nuevo", "176sal-a6-001", "AYUDANTE", 1750905, "2025-02-01", ""])
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        buf.name = "colaboradores.xlsx"

        url = reverse("cuadrillas:personal_upload")
        resp = self.client.post(url, {"archivo": buf})
        self.assertIn(resp.status_code, (200, 302))
        persona = PersonalCuadrilla.objects.get(documento="176sal-a6-001")
        self.assertEqual(persona.nombre, "Via Modal Nuevo")
        self.assertEqual(persona.salario_base, Decimal("1750905"))

    def test_export_descarga_xlsx_con_seis_columnas_incluye_registro_legacy(self):
        """Test contra dato legacy real: Andrea (documento 43482087,
        LINIERO_I, salario_base=15000.00) debe aparecer en el export."""
        cargo = Cargo.objects.filter(codigo="LINIERO_I").first()
        if cargo is None:
            cargo = Cargo.objects.create(codigo="LINIERO_I", nombre="Liniero I")
        PersonalCuadrilla.objects.filter(documento="43482087").delete()
        PersonalCuadrilla.objects.create(
            nombre="Andrea",
            documento="43482087",
            rol_cuadrilla_id="LINIERO_I",
            salario_base=Decimal("15000.00"),
            fecha_ingreso=date(2025, 1, 1),
        )

        url = reverse("cuadrillas:colaboradores_export")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        import openpyxl

        wb = openpyxl.load_workbook(BytesIO(resp.content))
        ws = wb.active
        header = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
        self.assertEqual(
            header,
            ["Documento", "Nombre", "Cargo", "Salario Base", "Fecha Ingreso", "Fecha Salida"],
        )
        filas = {row[0]: row for row in ws.iter_rows(min_row=2, values_only=True)}
        self.assertIn("43482087", filas)
        fila_andrea = filas["43482087"]
        self.assertEqual(fila_andrea[1], "Andrea")
        self.assertEqual(fila_andrea[2], "Liniero I")
        self.assertEqual(fila_andrea[3], 15000.0)

    def test_export_colaborador_sin_fecha_salida_exporta_celda_vacia(self):
        """Edge case: colaborador activo (sin fecha_salida) no debe romper
        el export -- la celda queda en blanco (openpyxl round-tripea '' como
        None al releer, comportamiento normal de Excel para celda vacía),
        no lanza excepción ni escribe un string 'None' literal."""
        PersonalCuadrilla.objects.filter(documento="176sal-a6-002").delete()
        PersonalCuadrilla.objects.create(
            nombre="Sin Fecha Salida",
            documento="176sal-a6-002",
            rol_cuadrilla_id="AYUDANTE",
            activo=True,
        )
        url = reverse("cuadrillas:colaboradores_export")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        import openpyxl

        wb = openpyxl.load_workbook(BytesIO(resp.content))
        ws = wb.active
        filas = {row[0]: row for row in ws.iter_rows(min_row=2, values_only=True)}
        self.assertIn("176sal-a6-002", filas)
        self.assertIn(filas["176sal-a6-002"][5], (None, ""))


# ---------------------------------------------------------------------------
# A7 — Copy de orden de dependencia Cargo -> Colaboradores
# ---------------------------------------------------------------------------
class TestA7CopyDependenciaCargoColaboradores(TestCase):
    """Texto de orden de dependencia visible en el modal de import de
    Colaboradores (mismo archivo que A6)."""

    def setUp(self):
        self.admin = _crear_admin("176sal-a7")
        self.client = Client()
        self.client.force_login(self.admin)

    def test_copy_orden_dependencia_visible_en_modal(self):
        resp = self.client.get(reverse("cuadrillas:colaboradores_lista"))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("deben existir primero", content)
        self.assertIn(reverse("cuadrillas:cargos_lista"), content)

    def test_copy_queda_dentro_del_modal_importar_no_en_otro_lugar(self):
        """Edge case: el copy debe estar asociado al modal de import, no
        aparecer suelto en cualquier parte de la página (regresión de
        ubicación, similar al bounce=1 de #176 donde un boton quedo mezclado
        con el card equivocado)."""
        resp = self.client.get(reverse("cuadrillas:colaboradores_lista"))
        content = resp.content.decode()
        idx_modal = content.index('id="modal-importar-colaboradores"')
        idx_copy = content.index("deben existir primero")
        idx_cierre_modal = content.index("</form>", idx_modal)
        self.assertLess(idx_modal, idx_copy)
        self.assertLess(idx_copy, idx_cierre_modal)
