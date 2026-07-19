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
