"""A1 (#120) — Bucketing mensual del importer contable + matriz rubro × 12 meses.

Cubre el sub-item A1 del Sprint A (Presupuesto bi-modal matriz + filtro mes):

- happy: BD con fechas en ≥3 meses fiscales → ``meses`` por rubro poblado en las
  columnas correctas (julio..junio) y matriz armada por ``build_rubro_matrix_rows``.
- edge1: fila sin fecha (col D y col F vacías) NO rompe; cae en ``sin_mes`` y NO
  aparece en ninguna columna mensual, pero SÍ suma al total anual.
- edge2: datos legacy SIN la sub-llave ``meses`` (estructura previa a A1) →
  ``build_rubro_matrix_rows`` tolera y devuelve matriz de ceros sin reventar.
- paridad: para cada rubro, ``sum(meses_matriz) + sin_mes == total`` anual.
- fallback Periodo: fila sin Fecha pero con col F ``Periodo`` YYYYMM se bucketea.

Estos tests son PUROS (no tocan BD): ``ContableCompleteImporter._build_mapeo``
captura la excepción de acceso a ``MapeoCtaRubro`` y cae al dict semilla, así que
corren sin Postgres (gotcha del repo: venv local no corre tests con psycopg).
"""
import datetime
import io

from openpyxl import Workbook

from apps.financiero.importers_finv2 import (
    MESES_FISCALES,
    MESES_FISCALES_KEYS,
    SIN_MES_KEY,
    ContableCompleteImporter,
    build_mes_filter_rows,
    build_rubro_matrix_rows,
)


# --------------------------------------------------------------------------- #
# Helpers de fixtures Excel en memoria (espejo de test_b1.py)
# --------------------------------------------------------------------------- #
_HEADERS = [
    'Auxiliar', 'Desc. auxiliar', 'Neto', 'Fecha', 'Docto.', 'Periodo',
    'Tercero movto.', 'Razón social', 'Desc. C.O.', 'Usuario',
    'C.O. movto.', 'Notas', 'C.Costo', 'Desc. C.Costo', 'Cta equivalente',
]


def _excel_bytes(rows, sheet_name='BD', headers=None, name='bd.xlsx'):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append(headers or _HEADERS)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    buf.name = name
    buf.size = len(buf.getvalue())
    return buf


def _row(neto, cta_equiv, fecha=None, periodo=None, desc='', auxiliar='X'):
    """Fila BD: C=Neto(3), D=Fecha(4), F=Periodo(6), O=cta_equiv(15)."""
    r = [auxiliar, desc, neto, fecha, None, periodo, None, None, None, None,
         None, None, None, None, cta_equiv]
    return r


def _idx(mes_key):
    """Índice de columna de un mes fiscal en la matriz (0..11)."""
    return MESES_FISCALES_KEYS.index(mes_key)


# --------------------------------------------------------------------------- #
# happy path
# --------------------------------------------------------------------------- #
def test_a1_happy_bucketea_por_mes_fiscal():
    """Movimientos en julio/agosto/enero → buckets mensuales por rubro correctos."""
    rows = [
        _row(-100, 'Ingresos Operacionales', fecha=datetime.datetime(2024, 7, 15)),
        _row(-50, 'Ingresos Operacionales', fecha=datetime.datetime(2024, 8, 3)),
        _row(-25, 'Ingresos Operacionales', fecha=datetime.datetime(2025, 1, 9)),
    ]
    res = ContableCompleteImporter().procesar_bd_completa(_excel_bytes(rows))
    assert res['exito'] is True

    bloque = res['datos']['finv2_bd']
    meses = bloque['rubros']['Ingresos Operacionales']['meses']
    assert meses['julio'] == -100
    assert meses['agosto'] == -50
    assert meses['enero'] == -25
    # Total anual = suma de los 3 buckets.
    assert bloque['rubros']['Ingresos Operacionales']['total'] == -175

    rows_m, totales_col, meses_fiscales, total_general = \
        build_rubro_matrix_rows(res['datos'])
    assert meses_fiscales == MESES_FISCALES
    assert len(rows_m) == 1
    fila = rows_m[0]
    assert len(fila['meses']) == 12
    assert fila['meses'][_idx('julio')] == -100
    assert fila['meses'][_idx('agosto')] == -50
    assert fila['meses'][_idx('enero')] == -25
    # Columnas sin movimiento = 0.
    assert fila['meses'][_idx('diciembre')] == 0.0
    # Totales por columna coherentes.
    assert totales_col[_idx('julio')] == -100
    assert total_general == -175


def test_a1_orden_columnas_es_julio_a_junio():
    """El primer mes de la matriz es julio y el último junio (año fiscal)."""
    assert MESES_FISCALES_KEYS[0] == 'julio'
    assert MESES_FISCALES_KEYS[-1] == 'junio'
    assert len(MESES_FISCALES_KEYS) == 12


# --------------------------------------------------------------------------- #
# edge1 — fila sin fecha
# --------------------------------------------------------------------------- #
def test_a1_edge1_fila_sin_fecha_va_a_sin_mes_no_a_columna():
    """Fila sin Fecha ni Periodo → bucket sin_mes; suma al anual, no a la matriz."""
    rows = [
        _row(-200, 'salarios', fecha=datetime.datetime(2024, 9, 1)),
        _row(-80, 'salarios'),  # sin fecha ni periodo
    ]
    res = ContableCompleteImporter().procesar_bd_completa(_excel_bytes(rows))
    assert res['exito'] is True

    bloque = res['datos']['finv2_bd']
    meses = bloque['rubros']['Personal']['meses']
    assert meses['septiembre'] == -200
    assert meses[SIN_MES_KEY] == -80
    assert bloque['rubros']['Personal']['total'] == -280
    assert bloque['filas_sin_mes'] == 1

    rows_m, totales_col, _mf, total_general = build_rubro_matrix_rows(res['datos'])
    fila = rows_m[0]
    # La matriz mensual NO incluye el sin_mes en ninguna columna.
    assert sum(fila['meses']) == -200
    # Pero el total anual de la fila SÍ lo incluye.
    assert fila['total'] == -280
    assert total_general == -280
    # sin_mes no aparece como columna.
    assert len(fila['meses']) == 12


# --------------------------------------------------------------------------- #
# edge2 — datos legacy sin 'meses'
# --------------------------------------------------------------------------- #
def test_a1_edge2_datos_legacy_sin_meses_da_matriz_de_ceros():
    """Estructura previa a A1 (rubros sin 'meses') → matriz de ceros, sin crash."""
    datos_legacy = {
        'finv2_bd': {
            'rubros': {
                'Personal': {'total': 5000.0, 'cuentas': []},  # sin 'meses'
                'Ingresos Operacionales': {'total': -9000.0, 'cuentas': []},
            },
            'total': -4000.0,
            'cuentas_count': 2,
            'cuentas_no_mapeadas': [],
        }
    }
    rows_m, totales_col, meses_fiscales, total_general = \
        build_rubro_matrix_rows(datos_legacy)
    assert len(rows_m) == 2
    for fila in rows_m:
        assert fila['meses'] == [0.0] * 12
    assert totales_col == [0.0] * 12
    # El total anual del rubro y general se respetan aunque no haya meses.
    assert total_general == -4000.0
    totales_anuales = {f['rubro']: f['total'] for f in rows_m}
    assert totales_anuales['Personal'] == 5000.0


def test_a1_edge2b_datos_vacios_no_rompen():
    """datos None / sin finv2_bd → matriz vacía sin excepción."""
    for datos in (None, {}, {'otra_llave': 1}):
        rows_m, totales_col, meses_fiscales, total_general = \
            build_rubro_matrix_rows(datos)
        assert rows_m == []
        assert totales_col == [0.0] * 12
        assert total_general == 0.0


# --------------------------------------------------------------------------- #
# paridad sum(meses) + sin_mes == total
# --------------------------------------------------------------------------- #
def test_a1_paridad_suma_meses_mas_sin_mes_igual_total():
    """Para cada rubro: Σ(buckets mensuales) + sin_mes == total anual."""
    rows = [
        _row(-100, 'Ingresos Operacionales', fecha=datetime.datetime(2024, 7, 1)),
        _row(-60, 'Ingresos Operacionales', fecha=datetime.datetime(2024, 12, 1)),
        _row(-40, 'Ingresos Operacionales'),  # sin_mes
        _row(300, 'salarios', fecha=datetime.datetime(2025, 2, 1)),
        _row(150, 'salarios', fecha=datetime.datetime(2025, 6, 1)),
    ]
    res = ContableCompleteImporter().procesar_bd_completa(_excel_bytes(rows))
    bloque = res['datos']['finv2_bd']

    for rubro, info in bloque['rubros'].items():
        suma_buckets = round(sum(info['meses'].values()), 2)
        assert suma_buckets == info['total'], f'paridad rota en {rubro}'

    # Paridad también a nivel matriz: Σ columnas + Σ(sin_mes) == total general.
    rows_m, totales_col, _mf, total_general = build_rubro_matrix_rows(res['datos'])
    suma_columnas = round(sum(totales_col), 2)
    suma_sin_mes = round(
        sum((info['meses'].get(SIN_MES_KEY, 0.0)
             for info in bloque['rubros'].values())), 2)
    assert round(suma_columnas + suma_sin_mes, 2) == total_general


# --------------------------------------------------------------------------- #
# fallback col F (Periodo YYYYMM)
# --------------------------------------------------------------------------- #
def test_a1_fallback_periodo_yyyymm_cuando_no_hay_fecha():
    """Sin Fecha (col D) pero con Periodo '202410' (col F) → octubre."""
    rows = [
        _row(-70, 'salarios', periodo='202410'),
        _row(-30, 'salarios', periodo=202503),  # int, marzo
    ]
    res = ContableCompleteImporter().procesar_bd_completa(_excel_bytes(rows))
    meses = res['datos']['finv2_bd']['rubros']['Personal']['meses']
    assert meses['octubre'] == -70
    assert meses['marzo'] == -30
    assert SIN_MES_KEY not in meses  # ninguna fila cayó a sin_mes


def test_a1_fecha_como_string_se_parsea():
    """Fecha en texto 'YYYY-MM-DD' (algunos export) se bucketea igual."""
    rows = [_row(-90, 'salarios', fecha='2024-11-20')]
    res = ContableCompleteImporter().procesar_bd_completa(_excel_bytes(rows))
    meses = res['datos']['finv2_bd']['rubros']['Personal']['meses']
    assert meses['noviembre'] == -90


# --------------------------------------------------------------------------- #
# build_mes_filter_rows (vista 'Filtro Mes')
# --------------------------------------------------------------------------- #
def test_a1_filtro_mes_devuelve_solo_rubros_con_valor():
    """build_mes_filter_rows: solo rubros con movimiento en el mes pedido."""
    rows = [
        _row(-100, 'Ingresos Operacionales', fecha=datetime.datetime(2024, 7, 1)),
        _row(-50, 'salarios', fecha=datetime.datetime(2024, 8, 1)),
    ]
    res = ContableCompleteImporter().procesar_bd_completa(_excel_bytes(rows))

    filas_jul, total_jul, label = build_mes_filter_rows(res['datos'], 'julio')
    assert label == 'Julio'
    assert total_jul == -100
    rubros_jul = {f['rubro'] for f in filas_jul}
    assert rubros_jul == {'Ingresos Operacionales'}  # Personal no tuvo julio


def test_a1_filtro_mes_invalido_devuelve_vacio():
    """Mes no fiscal → ([], 0.0, '') sin excepción."""
    filas, total, label = build_mes_filter_rows({'finv2_bd': {'rubros': {}}}, 'nofiscal')
    assert filas == []
    assert total == 0.0
    assert label == ''
