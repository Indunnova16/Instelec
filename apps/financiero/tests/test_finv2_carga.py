import io
from datetime import datetime

import pytest
from openpyxl import Workbook

from apps.contratos.models import Contrato
from apps.financiero.importers_finv2_carga import procesar_carga_financiera
from apps.financiero.models_finv2_carga import CargaFinanciera, LineaCargaFinanciera


def _libro(*, incluir_homologacion=True, neto=100):
    libro = Workbook()
    real = libro.active
    real.title = 'BD Real'
    real.append(['Auxiliar', 'Desc. auxiliar', 'Neto', 'Fecha', 'Docto.', 'Periodo', 'x', 'x', 'x', 'x', 'x', 'x', 'x', 'x', 'Cuenta Equiv', 'CdeC equiv'])
    real.append([1, 'Compra cable', neto, datetime(2026, 1, 31), 'DOC-1', 202601, None, None, None, None, None, None, None, None, 'Materiales', 'TRANSELCA'])
    real.append([2, 'Otro periodo', 999, datetime(2026, 2, 1), 'DOC-2', 202602, None, None, None, None, None, None, None, None, 'Materiales', 'TRANSELCA'])
    ppto = libro.create_sheet('BD Ppto')
    ppto.append(['Tipo', 'Proyecto', 'Rubro', 'Clasificacion', 'Valor', 'mes', 'año', 'ciudad'])
    ppto.append(['Presupuesto', 'Transelca', 'Materiales', 'Costos', 120, 1, 2026, 'Barranquilla'])
    if incluir_homologacion:
        homologacion = libro.create_sheet('Homologacion')
        homologacion.append(['tipo', 'Grupo', 'Concepto', 'Rubro'])
        homologacion.append(['REAL', 'Materiales', 'Compra cable', 'TRANSELCA'])
    salida = io.BytesIO()
    libro.save(salida)
    salida.seek(0)
    salida.name = 'TRANSELCA.xlsx'
    return salida


@pytest.fixture
def proyecto(db):
    return Contrato.objects.create(codigo='TRAN-246', nombre='Transelca', unidad_negocio='MANTENIMIENTO')


@pytest.mark.django_db
def test_carga_transelca_reemplaza_periodo(proyecto):
    primero = procesar_carga_financiera(_libro(neto=100), proyecto=proyecto, anio=2026, mes=1, usuario=None)
    assert primero.exito
    assert LineaCargaFinanciera.objects.filter(carga=primero.carga).count() == 2

    segundo = procesar_carga_financiera(_libro(neto=250), proyecto=proyecto, anio=2026, mes=1, usuario=None)
    assert segundo.exito
    assert CargaFinanciera.objects.filter(proyecto=proyecto, anio=2026, mes=1).count() == 1
    lineas = LineaCargaFinanciera.objects.filter(carga=segundo.carga)
    assert lineas.count() == 2
    assert lineas.get(tipo='REAL').valor == 250
    assert segundo.resumen['lineas_homologacion_origen'] == 1


@pytest.mark.django_db
def test_carga_rechaza_hoja_faltante(proyecto):
    resultado = procesar_carga_financiera(_libro(incluir_homologacion=False), proyecto=proyecto, anio=2026, mes=1, usuario=None)
    assert not resultado.exito
    assert resultado.carga is None
    assert 'Homologacion' in resultado.error
    assert CargaFinanciera.objects.count() == 0


@pytest.mark.django_db
def test_carga_rechaza_periodo_sin_lineas(proyecto):
    resultado = procesar_carga_financiera(_libro(), proyecto=proyecto, anio=2026, mes=3, usuario=None)
    assert not resultado.exito
    assert 'no contiene líneas' in resultado.error
