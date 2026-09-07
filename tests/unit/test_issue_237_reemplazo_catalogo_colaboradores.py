"""#237 — migración de datos 0031: reemplazo total del catálogo de Colaboradores.

Corre la función real de la migración (`reemplazar_catalogo`) contra un
PersonalCuadrilla legacy simulado (equivalente al dato real de prod: fila
corrupta + registros con Nombre/Documento cruzados) y valida el resultado.
"""

import importlib

import pytest
from django.apps import apps as django_apps

from apps.cuadrillas.models import Cargo, PersonalCuadrilla

MIGRATION = importlib.import_module(
    "apps.cuadrillas.migrations.0031_issue_237_reemplazo_catalogo_colaboradores"
)


@pytest.fixture
def seed_cargos(db):
    codigos = {fila["cargo"] for fila in MIGRATION.COLABORADORES}
    for codigo in codigos:
        Cargo.objects.get_or_create(codigo=codigo, defaults={"nombre": codigo, "activo": True})
    return codigos


@pytest.mark.django_db
class TestReemplazoCatalogoColaboradores:
    def test_datos_migracion_tienen_221_filas_unicas(self):
        assert len(MIGRATION.COLABORADORES) == 221
        documentos = [fila["documento"] for fila in MIGRATION.COLABORADORES]
        assert len(set(documentos)) == 221

    def test_datos_migracion_excluyen_fila_corrupta_y_duplicados(self):
        documentos = {fila["documento"] for fila in MIGRATION.COLABORADORES}
        for doc_excluido in ("2026", "71674541", "71002534", "1063295634"):
            assert doc_excluido not in documentos

    def test_reemplaza_catalogo_legacy_con_dato_cruzado(self, seed_cargos):
        # Simula el dato legacy real: fila corrupta + Nombre/Documento cruzados.
        Cargo.objects.get_or_create(
            codigo="LINIERO_I", defaults={"nombre": "Liniero I", "activo": True}
        )
        PersonalCuadrilla.objects.create(nombre="1", documento="2026", rol_cuadrilla_id="LINIERO_I")
        PersonalCuadrilla.objects.create(
            nombre="GUILLERMO LOSADA ISAZA", documento="71674541", rol_cuadrilla_id="LINIERO_I"
        )

        MIGRATION.reemplazar_catalogo(django_apps, None)

        assert PersonalCuadrilla.objects.count() == 221
        assert not PersonalCuadrilla.objects.filter(documento="2026").exists()
        assert not PersonalCuadrilla.objects.filter(documento="71674541").exists()

    def test_activo_deriva_de_fecha_salida(self, seed_cargos):
        MIGRATION.reemplazar_catalogo(django_apps, None)

        esperados_activos = sum(1 for f in MIGRATION.COLABORADORES if f["fecha_salida"] is None)
        assert PersonalCuadrilla.objects.filter(activo=True).count() == esperados_activos
        assert PersonalCuadrilla.objects.filter(activo=False).count() == 221 - esperados_activos

    def test_cargos_truncados_se_resuelven_contra_catalogo_real(self, seed_cargos):
        MIGRATION.reemplazar_catalogo(django_apps, None)

        gabriel = PersonalCuadrilla.objects.get(documento="91109552")
        assert gabriel.rol_cuadrilla_id == "COORDINADOR_INGENIE"
        oscar = PersonalCuadrilla.objects.get(documento="91074638")
        assert oscar.rol_cuadrilla_id == "COORDINADOR_TOPOGRAF"

    def test_reversa_lanza_error_explicito(self):
        with pytest.raises(RuntimeError, match="no reversible"):
            MIGRATION.restaurar_no_reversible(django_apps, None)
