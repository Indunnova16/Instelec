"""Sub-item A1 del Sprint A de Instelec#268.

Migración aditiva: FK `proveedor` nullable en `LineaCargaFinanciera`, para
filtrar/mostrar/enlazar sin parsear `datos_origen` (ver #262). No crea modelo
nuevo — reusa `LineaCargaFinanciera.Tipo.REAL` + `CargaFinanciera` ya
existentes.
"""

import pytest
from django.db import IntegrityError

from apps.contratos.models import Contrato
from apps.financiero.models_finv2_carga import CargaFinanciera, LineaCargaFinanciera
from apps.financiero.models_finv2_facturas import Proveedor


@pytest.fixture
def proyecto(db):
    return Contrato.objects.create(codigo='INST-268', nombre='Instelec 268', unidad_negocio='MANTENIMIENTO')


@pytest.fixture
def carga(proyecto):
    return CargaFinanciera.objects.create(proyecto=proyecto, anio=2026, mes=1)


@pytest.mark.django_db
def test_linea_carga_admite_proveedor_asociado(carga):
    """Happy path: se puede asociar un Proveedor existente a una línea nueva."""
    proveedor = Proveedor.objects.create(nombre='Proveedor 268', nit='900268001')
    linea = LineaCargaFinanciera.objects.create(
        carga=carga, tipo=LineaCargaFinanciera.Tipo.REAL,
        concepto='Compra cable', valor=100, proveedor=proveedor,
    )
    linea.refresh_from_db()
    assert linea.proveedor_id == proveedor.pk
    assert proveedor.lineas_carga_financiera.count() == 1


@pytest.mark.django_db
def test_linea_carga_sin_proveedor_queda_nula(carga):
    """Edge case 1: el campo es nullable/blank — no rompe líneas sin proveedor
    identificado (la mayoría del histórico, importado antes de #268)."""
    linea = LineaCargaFinanciera.objects.create(
        carga=carga, tipo=LineaCargaFinanciera.Tipo.REAL,
        concepto='Concepto sin proveedor', valor=50,
    )
    linea.refresh_from_db()
    assert linea.proveedor_id is None


@pytest.mark.django_db
def test_no_se_puede_borrar_proveedor_con_lineas_asociadas(carga):
    """Edge case 2: on_delete=PROTECT — igual que el resto de FKs de este
    módulo (ver `carga.proyecto`, `homologacion`), borrar el proveedor no
    puede dejar líneas huérfanas silenciosamente."""
    proveedor = Proveedor.objects.create(nombre='Proveedor protegido', nit='900268002')
    LineaCargaFinanciera.objects.create(
        carga=carga, tipo=LineaCargaFinanciera.Tipo.REAL,
        concepto='Compra protegida', valor=75, proveedor=proveedor,
    )
    with pytest.raises(IntegrityError):
        proveedor.delete()


@pytest.mark.django_db
def test_linea_carga_legacy_preexistente_no_requiere_proveedor(carga):
    """Dato legacy: una línea creada como lo hacía el importador ANTES de
    #268 (sin pasar `proveedor`) sigue siendo válida y consultable — la
    migración es aditiva, no exige backfill."""
    legacy = LineaCargaFinanciera.objects.create(
        carga=carga, tipo=LineaCargaFinanciera.Tipo.PRESUPUESTO,
        concepto='Línea legacy pre-268', valor=200,
        datos_origen={'Rubro': 'Materiales'},
    )
    recargada = LineaCargaFinanciera.objects.get(pk=legacy.pk)
    assert recargada.proveedor is None
    assert recargada.concepto == 'Línea legacy pre-268'
