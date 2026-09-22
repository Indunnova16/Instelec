"""Issue #271 Sprint A — A2: form + templates del Maestro de Colaboradores
con los 2 campos nuevos (fecha_firma_contrato / fecha_ingreso_proyecto)
separados, en vez de la antigua `fecha_ingreso` (deprecada en A1).

Cubre:
- `PersonalCuadrillaForm.Meta.fields` expone los 2 campos nuevos (ya NO
  `fecha_ingreso`).
- `clean()` reformulado: compara `fecha_salida` contra
  `fecha_ingreso_proyecto` (el dato operativo), NO contra el legacy
  `fecha_ingreso`.
- Los templates `colaboradores_form.html` / `colaboradores_lista.html`
  renderizan los 2 campos/columnas nuevos con sus propios ids/labels.

`fecha_ingreso` sigue existiendo en el MODEL STATE (A1, deprecado a
propósito) pero A2 la retira del form/templates -- este archivo verifica
justamente ese retiro explícito.
"""
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.cuadrillas.forms_personal import PersonalCuadrillaForm
from apps.cuadrillas.models import Cargo, PersonalCuadrilla

pytestmark = pytest.mark.django_db

Usuario = get_user_model()


@pytest.fixture(autouse=True)
def _seed_cargo_liniero():
    """Este módulo vive en tests/cuadrillas/ (NO apps/cuadrillas/), fuera
    del alcance del conftest autouse que siembra el catálogo completo de
    Cargo (apps/cuadrillas/conftest.py). `rol_cuadrilla` es FK requerida
    (sin blank=True) -- sin un Cargo real, el form nunca es válido."""
    Cargo.objects.get_or_create(
        codigo="LINIERO_I", defaults={"nombre": "Liniero I", "activo": True}
    )


def _crear_admin():
    return Usuario.objects.create_user(
        email="admin_271_a2@test.com",
        password="testpass123!",
        first_name="Admin",
        last_name="Test271A2",
        rol="admin",
        is_staff=True,
        is_superuser=True,
    )


def _form_data(**overrides):
    data = {
        "nombre": "Colaborador QA 271",
        "documento": "271-A2-0001",
        "rol_cuadrilla": "LINIERO_I",
        "salario_base": "1750905",
        "fecha_firma_contrato": "2026-01-10",
        "fecha_ingreso_proyecto": "2026-01-20",
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Form: Meta.fields / widgets / clean()
# ---------------------------------------------------------------------------
def test_form_expone_los_2_campos_nuevos_y_ya_no_fecha_ingreso():
    form = PersonalCuadrillaForm()
    assert "fecha_firma_contrato" in form.fields
    assert "fecha_ingreso_proyecto" in form.fields
    assert "fecha_ingreso" not in form.fields


def test_form_valido_con_ambas_fechas_nuevas_persiste_los_campos_correctos():
    form = PersonalCuadrillaForm(data=_form_data())
    assert form.is_valid(), form.errors

    colaborador = form.save()
    colaborador.refresh_from_db()

    assert colaborador.fecha_firma_contrato == date(2026, 1, 10)
    assert colaborador.fecha_ingreso_proyecto == date(2026, 1, 20)
    # El legacy no se toca por este form (A1 lo dejó deprecado pero presente).
    assert colaborador.fecha_ingreso is None


def test_form_valido_sin_fechas_por_ser_ambas_opcionales():
    """Ambas fechas son null=True/blank=True (A1) -- el form debe permitir
    guardarlas vacías, igual que antes con `fecha_ingreso`."""
    data = _form_data(documento="271-A2-0002")
    data.pop("fecha_firma_contrato")
    data.pop("fecha_ingreso_proyecto")
    form = PersonalCuadrillaForm(data=data)
    assert form.is_valid(), form.errors


def test_edge_fecha_salida_anterior_a_fecha_ingreso_proyecto_es_invalida():
    """Edge case reformulado (F2): la comparación es contra
    `fecha_ingreso_proyecto` (fecha operativa), no contra el legacy
    `fecha_ingreso`."""
    data = _form_data(
        documento="271-A2-0003",
        fecha_ingreso_proyecto="2026-03-01",
        fecha_salida="2026-02-15",
    )
    form = PersonalCuadrillaForm(data=data)
    assert not form.is_valid()
    assert "La fecha de salida no puede ser anterior a la fecha de ingreso a proyecto." in str(
        form.errors
    )


def test_edge_fecha_salida_posterior_o_igual_a_fecha_ingreso_proyecto_es_valida():
    data = _form_data(
        documento="271-A2-0004",
        fecha_ingreso_proyecto="2026-03-01",
        fecha_salida="2026-03-01",
    )
    form = PersonalCuadrillaForm(data=data)
    assert form.is_valid(), form.errors


def test_edge_fecha_ingreso_proyecto_vacia_no_dispara_comparacion():
    """Sin `fecha_ingreso_proyecto`, no hay contra qué comparar
    `fecha_salida` -- no debe reventar ni bloquear el guardado."""
    data = _form_data(documento="271-A2-0005", fecha_salida="2026-01-01")
    data.pop("fecha_ingreso_proyecto")
    form = PersonalCuadrillaForm(data=data)
    assert form.is_valid(), form.errors


# ---------------------------------------------------------------------------
# Dato legacy (issue #271, A1 ya corrió backfill sobre filas existentes) --
# el form de A2 debe seguir funcionando para EDITAR un colaborador que ya
# tenía `fecha_ingreso` legacy backfillada a `fecha_firma_contrato`.
# ---------------------------------------------------------------------------
def test_editar_colaborador_con_dato_legacy_backfillado_no_lo_pisa_sin_querer():
    legado = PersonalCuadrilla.objects.create(
        nombre="Legacy Backfill 271",
        documento="271-A2-LEGACY",
        rol_cuadrilla_id="LINIERO_I",
        fecha_ingreso=date(2020, 5, 1),
        fecha_firma_contrato=date(2020, 5, 1),  # ya backfillado por A1
    )
    form = PersonalCuadrillaForm(
        data=_form_data(
            documento="271-A2-LEGACY",
            fecha_firma_contrato="2020-05-01",
            fecha_ingreso_proyecto="2020-06-01",
        ),
        instance=legado,
    )
    assert form.is_valid(), form.errors
    actualizado = form.save()
    actualizado.refresh_from_db()

    assert actualizado.fecha_firma_contrato == date(2020, 5, 1)
    assert actualizado.fecha_ingreso_proyecto == date(2020, 6, 1)
    # El legacy físico sigue intacto -- A2 no lo toca.
    assert actualizado.fecha_ingreso == date(2020, 5, 1)


# ---------------------------------------------------------------------------
# Templates: ids/labels/columnas nuevas
# ---------------------------------------------------------------------------
class TestTemplatesRenderizanCamposNuevos:
    def setup_method(self):
        self.client = Client()
        self.admin = _crear_admin()
        self.client.force_login(self.admin)

    def test_form_nuevo_renderiza_ids_de_los_2_campos_nuevos(self):
        resp = self.client.get(reverse("cuadrillas:colaboradores_crear"))
        assert resp.status_code == 200
        content = resp.content.decode()
        assert 'id="id_fecha_firma_contrato"' in content
        assert 'id="id_fecha_ingreso_proyecto"' in content
        # El id legacy ya no debe estar en el form (issue #271, A2).
        assert 'id="id_fecha_ingreso"' not in content
        assert "Fecha de firma de contrato" in content
        assert "Fecha de ingreso a proyecto" in content

    def test_form_editar_precarga_valores_de_los_2_campos_nuevos(self):
        colaborador = PersonalCuadrilla.objects.create(
            nombre="Editar Fechas 271",
            documento="271-A2-EDIT",
            rol_cuadrilla_id="LINIERO_I",
            fecha_firma_contrato=date(2025, 4, 1),
            fecha_ingreso_proyecto=date(2025, 4, 15),
        )
        resp = self.client.get(
            reverse("cuadrillas:colaboradores_editar", args=[colaborador.pk])
        )
        assert resp.status_code == 200
        content = resp.content.decode()
        # Nota (#271 A2): el widget DateInput no fija `format`, así que
        # DjangoDate se serializa en el formato local (dd/mm/aaaa) -- mismo
        # patrón pre-existente que `fecha_salida` (widget idéntico, sin
        # tocar en este sub-item). Se documenta como observación, no se
        # amplía el scope de A2 a un formateo distinto para TODOS los
        # DateField del form.
        assert 'value="01/04/2025"' in content
        assert 'value="15/04/2025"' in content

    def test_lista_renderiza_2_columnas_nuevas_con_dato_legacy(self):
        """Registro `pre-existente` (ya backfillado por A1) -- verifica
        contra dato legacy, no solo fixtures propias del sub-item."""
        PersonalCuadrilla.objects.create(
            nombre="Listado Legacy 271",
            documento="271-A2-LISTA",
            rol_cuadrilla_id="LINIERO_I",
            fecha_ingreso=date(2019, 8, 20),
            fecha_firma_contrato=date(2019, 8, 20),
        )
        resp = self.client.get(reverse("cuadrillas:colaboradores_lista"))
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Fecha Firma Contrato" in content
        assert "Fecha Ingreso Proyecto" in content
        assert "20/08/2019" in content

    def test_lista_vacia_usa_colspan_9(self):
        PersonalCuadrilla.objects.all().delete()
        resp = self.client.get(reverse("cuadrillas:colaboradores_lista"))
        assert resp.status_code == 200
        content = resp.content.decode()
        assert 'colspan="9"' in content
        assert 'colspan="8"' not in content
