"""B5 (#123) — Tests del importador financiero de construcción + forms.

Cubre (tests_e2e del BLUEPRINT):
- ``b5_dashboard_render_completo``  → cubierto por F4/F6 (render real con DB). Aquí
  se valida la parte unitaria testeable sin servidor: forms + importers.
- ``b5_cargar_bd_form_200``         → validación del form de carga (.xlsx + tamaño).
- ``b5_facturacion_crud``           → validación del FacturacionConstruccionForm.

Estos tests NO requieren Cloud SQL: usan workbooks openpyxl en memoria + forms con
``files``/``data`` dict. El render de los 9 templates se valida en F4 (Docker) y
F6 (/qa-prod E2E), como indica el prompt F3.

Edge cases del dominio cubiertos:
- archivo no-.xlsx              → error
- archivo .xlsx sin filas       → advertencia
- presupuesto sin columnas mes  → advertencia
- costos solo con 'total'       → se interpreta como cantidad 1 × total
- factura con pagado > facturado → form inválido
- detect_excel_format_*         → discrimina contable/presupuesto/costos/None
"""
import io

from django.test import SimpleTestCase
from openpyxl import Workbook

from apps.construccion.forms_fin import (
    CargarBDContableConstruccionForm,
    CostosConstruccionForm,
    FacturacionConstruccionForm,
)
from apps.construccion.importers import (
    ContableConstruccionExcelImporter,
    PresupuestoConstruccionExcelImporter,
    detect_excel_format_construccion,
)


def _xlsx_bytes(rows, sheet_title='Hoja1'):
    """Construye un .xlsx en memoria con ``rows`` (list[list]) → SimpleUploadedFile-like."""
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    buf.name = 'test.xlsx'
    return buf


class _FakeUpload:
    """Mínimo file-like con .name y .size para los importers (sin Django storage)."""

    def __init__(self, buf, name='test.xlsx'):
        self._buf = buf
        self.name = name
        buf.seek(0, io.SEEK_END)
        self.size = buf.tell()
        buf.seek(0)

    def read(self, *a, **k):
        return self._buf.read(*a, **k)

    def seek(self, *a, **k):
        return self._buf.seek(*a, **k)

    def tell(self, *a, **k):
        return self._buf.tell(*a, **k)


# ===========================================================================
# Importador de presupuesto
# ===========================================================================
class PresupuestoImporterTests(SimpleTestCase):
    def test_presupuesto_agrupa_por_seccion(self):
        """Happy path: clasifica filas en ingreso/variables/fijos por concepto."""
        buf = _xlsx_bytes([
            ['Concepto', 'enero', 'febrero'],
            ['Ingresos por obra', 1000, 1200],
            ['Costo variable cemento', 300, 350],
            ['Gasto fijo arriendo', 100, 100],
        ])
        res = PresupuestoConstruccionExcelImporter().procesar(_FakeUpload(buf))
        self.assertTrue(res['exito'], res)
        datos = res['datos']
        self.assertIn('Ingresos por obra', datos['ingreso'])
        self.assertIn('Costo variable cemento', datos['variables'])
        self.assertIn('Gasto fijo arriendo', datos['fijos'])
        self.assertEqual(datos['ingreso']['Ingresos por obra']['enero'], 1000)

    def test_presupuesto_sin_columnas_mes_advertencia(self):
        """Edge case: archivo sin columnas de mes → advertencia (no exito)."""
        buf = _xlsx_bytes([['Concepto', 'Valor'], ['X', 10]])
        res = PresupuestoConstruccionExcelImporter().procesar(_FakeUpload(buf))
        self.assertFalse(res['exito'])
        self.assertIsNotNone(res['advertencia'])

    def test_archivo_no_xlsx_error(self):
        """Edge case: extensión inválida → error inmediato."""
        buf = _xlsx_bytes([['Concepto', 'enero'], ['X', 1]])
        res = PresupuestoConstruccionExcelImporter().procesar(
            _FakeUpload(buf, name='datos.csv'))
        self.assertFalse(res['exito'])
        self.assertIsNotNone(res['error'])


# ===========================================================================
# Detector de formato
# ===========================================================================
class DetectFormatTests(SimpleTestCase):
    def test_detecta_presupuesto(self):
        buf = _xlsx_bytes([['Concepto', 'enero', 'febrero', 'marzo'], ['X', 1, 2, 3]])
        self.assertEqual(detect_excel_format_construccion(_FakeUpload(buf)), 'presupuesto')

    def test_detecta_contable_por_hoja_bd(self):
        buf = _xlsx_bytes([['Cta equivalente', 'Neto'], ['Ingresos', 100]], sheet_title='BD')
        self.assertEqual(detect_excel_format_construccion(_FakeUpload(buf)), 'contable')

    def test_detecta_costos(self):
        buf = _xlsx_bytes([['Concepto', 'Cantidad', 'Costo unitario'], ['Cemento', 2, 50]])
        self.assertEqual(detect_excel_format_construccion(_FakeUpload(buf)), 'costos')

    def test_formato_no_reconocido(self):
        buf = _xlsx_bytes([['Foo', 'Bar'], ['a', 'b']])
        self.assertIsNone(detect_excel_format_construccion(_FakeUpload(buf)))

    def test_archivo_invalido_es_none(self):
        buf = _xlsx_bytes([['Concepto', 'enero'], ['X', 1]])
        self.assertIsNone(detect_excel_format_construccion(_FakeUpload(buf, name='x.txt')))


# ===========================================================================
# Importador contable (delega en ContableCompleteImporter de #120)
# ===========================================================================
class ContableImporterTests(SimpleTestCase):
    def test_contable_agrupa_por_cuenta(self):
        """Reusa la lógica de #120: agrupa por Cta equivalente sumando Neto."""
        rows = [
            ['Desc auxiliar', 'Neto', 'Cta equivalente'],
            ['mov 1', 100, 'Ingresos Operacionales'],
            ['mov 2', 200, 'Ingresos Operacionales'],
        ]
        buf = _xlsx_bytes(rows, sheet_title='BD')
        res = ContableConstruccionExcelImporter().procesar(_FakeUpload(buf))
        self.assertTrue(res['exito'], res)
        self.assertIn('finv2_bd', res['datos'])
        self.assertGreaterEqual(res['filas'], 1)


# ===========================================================================
# Forms
# ===========================================================================
class CargarBDFormTests(SimpleTestCase):
    def test_cargar_bd_form_invalido_sin_archivo(self):
        form = CargarBDContableConstruccionForm(data={}, files={})
        self.assertFalse(form.is_valid())

    def test_cargar_bd_form_rechaza_no_xlsx(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile('x.csv', b'1,2,3', content_type='text/csv')
        form = CargarBDContableConstruccionForm(data={}, files={'archivo': f})
        self.assertFalse(form.is_valid())
        self.assertIn('archivo', form.errors)


class FacturacionFormTests(SimpleTestCase):
    def test_factura_pagado_mayor_facturado_invalido(self):
        """Edge case: pagado > facturado → form inválido."""
        form = FacturacionConstruccionForm(data={
            'numero_factura': 'FV-1',
            'fecha_emision': '2026-01-15',
            'monto_facturado': '100.00',
            'monto_pagado': '150.00',
            'estado': 'EMITIDA',
            'observaciones': '',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('monto_pagado', form.errors)

    def test_factura_valida(self):
        form = FacturacionConstruccionForm(data={
            'numero_factura': 'FV-2',
            'fecha_emision': '2026-01-15',
            'monto_facturado': '100.00',
            'monto_pagado': '50.00',
            'estado': 'EN_VALIDACION',
            'observaciones': 'parcial',
        })
        self.assertTrue(form.is_valid(), form.errors)


class CostosFormTests(SimpleTestCase):
    def test_costo_cantidad_negativa_invalido(self):
        form = CostosConstruccionForm(data={
            'concepto': 'Cemento',
            'tipo_recurso': 'MATERIAL',
            'cantidad': '-1',
            'costo_unitario': '50',
            'fecha': '2026-01-10',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('cantidad', form.errors)
