"""
Excel importers for PresupuestoDetallado.
"""
import logging
import unicodedata

from openpyxl import load_workbook

logger = logging.getLogger(__name__)

MESES = [
    'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
    'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
]

# Items where multiple Excel rows map to one ESTRUCTURA item (values are SUMMED)
MERGE_ITEMS = {
    'Auxilio alimentación/alojamiento operación',
    'Auxilio alimentación/alojamiento administración',
    'Servicios públicos',
}

# Explicit mapping: normalized Excel name -> exact ESTRUCTURA_COSTOS item name.
# Keys are the output of _normalize_name() applied to the raw Excel cell.
EXCEL_TO_ESTRUCTURA = {
    # ── Costos Variables / MO ──
    'nomina operacion': 'Nómina operación',
    'tiempo extra operacion': 'Tiempo extra operación',
    'tiempo festivo operacion': 'Tiempo festivo operación',
    'beneficios operacion': 'Beneficios operación',
    'aportes parafiscales operacion': 'Aportes y parafiscales operación',
    'prestaciones sociales operacion': 'Prestaciones sociales operación',
    'fic operacion': 'FIC operación',
    'seguro de vida operacion': 'Seguro de vida operación',
    'viaticos reembolsables operacion': 'Viáticos reembolsables operación',
    'viaticos no reembolsables operacion': 'Viáticos NO reembolsables operación',
    'viaticos descanso operacion': 'Viáticos descanso operación',
    'auxilio de alimentacion operacion': 'Auxilio alimentación/alojamiento operación',
    'auxilio de alojamiento operacion': 'Auxilio alimentación/alojamiento operación',
    'hidratacion operacion': 'Hidratación operación',
    'campamento operacion': 'Campamento operación',
    'alimentacion operacion': 'Alimentación operación',
    'celaduria campo': 'Celaduría campo',
    # ── Costos Variables / SST ──
    'epp consumibles': 'EPP consumibles',
    'epp alturas': 'EPP alturas',
    'epp servidumbre': 'EPP servidumbre',
    'seguridad grupal': 'Seguridad grupal',
    'bioseguridad': 'Bioseguridad',
    'dotacion operacion': 'Dotación operación',
    'examenmedico operacion': 'Examen médico operación',
    'examen medico operacion': 'Examen médico operación',
    'certificacion operacion': 'Certificación operación',
    'capacitaciones': 'Capacitaciones',
    'ambiental': 'Ambiental',
    # ── Costos Variables / TA ──
    'transporte operacion': 'Transporte operación',
    'transporte de materiales y herramientas': 'Transporte de materiales y herramientas',
    'transporte reembolsable': 'Transporte reembolsable',
    # ── Costos Variables / MH ──
    'material obra': 'Material obra',
    'material fungible': 'Material fungible',
    'insumos maquinaria y equipos': 'Insumos maquinaria y equipos',
    'activos fijos': 'Activos fijos',
    'httas menores': 'Herramientas menores',
    'herramientas menores': 'Herramientas menores',
    'gastos reembolsables': 'Gastos reembolsables',
    # ── Costos Variables / SC ──
    'subcontratistas': 'Subcontratistas',
    # ── Costos Fijos / MO ──
    'nomina admi': 'Nómina administración',
    'nomina administracion': 'Nómina administración',
    'tiempo extra admi': 'Tiempo extra administración',
    'tiempo extra administracion': 'Tiempo extra administración',
    'tiempo festivo admi': 'Tiempo festivo administración',
    'tiempo festivo administracion': 'Tiempo festivo administración',
    'beneficios admi': 'Beneficios administración',
    'beneficios administracion': 'Beneficios administración',
    'aportes parafiscales admi': 'Aportes y parafiscales administración',
    'aportes parafiscales administracion': 'Aportes y parafiscales administración',
    'prestaciones sociales admi': 'Prestaciones sociales administración',
    'prestaciones sociales administracion': 'Prestaciones sociales administración',
    'fic administracion': 'FIC administración',
    'fic admi': 'FIC administración',
    'seguro de vida admi': 'Seguro de vida administración',
    'seguro de vida administracion': 'Seguro de vida administración',
    'viaticos reembolsables administracion': 'Viáticos reembolsables administración',
    'viaticos no reembolsables administracion': 'Viáticos NO reembolsables administración',
    'viaticos descanso administracion': 'Viáticos descanso administración',
    'auxilio de alimentacion administracion': 'Auxilio alimentación/alojamiento administración',
    'auxilio de alojamiento administracion': 'Auxilio alimentación/alojamiento administración',
    'hidratacion administracion': 'Hidratación administración',
    'campamento administracion': 'Campamento administración',
    'alimentacion administracion': 'Alimentación administración',
    # ── Costos Fijos / SST ──
    'dotacion administracion': 'Dotación administración',
    'examenmedico admi': 'Examen médico administración',
    'examen medico admi': 'Examen médico administración',
    'examen medico administracion': 'Examen médico administración',
    'certificacion admi': 'Certificación administración',
    'certificacion administracion': 'Certificación administración',
    # ── Costos Fijos / TA ──
    'transporte admi': 'Transporte administración',
    'transporte administracion': 'Transporte administración',
    'transporte ocasional': 'Transporte ocasional',
    'arrendamiento oficina bodega': 'Arrendamiento oficina',
    'arrendamiento oficina': 'Arrendamiento oficina',
    'arrendamiento patio': 'Arrendamiento patio',
    'servicos publicos oficina bodega': 'Servicios públicos',
    'servicios publicos oficina bodega': 'Servicios públicos',
    'servicios publicos patio': 'Servicios públicos',
    'servicios publicos': 'Servicios públicos',
    'celular internet': 'Celular / internet',
    'seguridad privada': 'Seguridad privada',
    'gastos menores': 'Gastos menores',
    'insumos y elementos de oficina': 'Insumos oficina',
    'insumos oficina': 'Insumos oficina',
    'ingreso a sitio de torre': 'Ingreso sitio torre',
    'ingreso sitio torre': 'Ingreso sitio torre',
    'actividades por garantia y o imprevistos': 'Actividades por garantía / imprevistos',
    'actividades por garantia imprevistos': 'Actividades por garantía / imprevistos',
    # ── Costos Fijos / PFS ──
    'garantias fianzas seguros': 'Garantías, fianzas y seguros',
    'garantias fianzas y seguros': 'Garantías, fianzas y seguros',
}


def _normalize_name(name: str) -> str:
    """Normalize an Excel item name for dictionary lookup."""
    s = name.strip().lower()
    s = s.replace('_', ' ').replace('-', ' ')
    # Strip accents
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    # Remove punctuation
    s = s.replace('/', ' ').replace('(', '').replace(')', '').replace(',', '')
    s = ' '.join(s.split())
    return s


def _parse_value(val):
    """Convert a cell value to integer."""
    if val is None:
        return 0
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0


class PresupuestoExcelImporter:
    """Parses a presupuesto Excel and returns a datos dict."""

    def __init__(self):
        self.matched = 0
        self.unmatched_items = []
        self.warnings = []

    def importar(self, archivo, estructura_costos):
        """
        Parse the Excel file and return a datos dict compatible with
        PresupuestoDetallado.datos.
        """
        try:
            wb = load_workbook(archivo, read_only=True, data_only=True)
        except Exception as e:
            return {'exito': False, 'error': f'Error al cargar archivo: {e}'}

        # Find PRESUPUESTO sheet
        sheet = None
        for name in wb.sheetnames:
            if 'presupuesto' in name.lower():
                sheet = wb[name]
                break
        if sheet is None:
            sheet = wb.active
            self.warnings.append('No se encontró hoja PRESUPUESTO, usando hoja activa.')

        # Detect month columns by scanning header rows
        month_cols = {}
        for scan_row in [3, 12, 1, 2, 4]:
            for col in range(1, 30):
                val = sheet.cell(row=scan_row, column=col).value
                if val and str(val).strip().lower() in MESES:
                    month_cols[str(val).strip().lower()] = col
            if len(month_cols) == 12:
                break

        if len(month_cols) < 12:
            wb.close()
            return {
                'exito': False,
                'error': f'Solo se detectaron {len(month_cols)} de 12 meses en las cabeceras.',
            }

        # Build reverse lookup: item name -> (seccion_key, codigo)
        item_lookup = {}
        for seccion_key, seccion in estructura_costos.items():
            for cat in seccion['categorias']:
                for item_name in cat['items']:
                    item_lookup[item_name] = (seccion_key, cat['codigo'])

        # Initialize datos with zeros
        from apps.financiero.views import _build_empty_datos
        datos = _build_empty_datos()

        # Parse all rows
        max_row = min(sheet.max_row or 200, 200)
        for row_num in range(1, max_row + 1):
            col_b = sheet.cell(row=row_num, column=2).value
            if not col_b:
                continue
            col_b_str = str(col_b).strip()

            # Check if this is the INGRESO PROYECTADO row
            if 'ingreso proyectado' in col_b_str.lower():
                # Only use the first occurrence (row ~5, not the summary at row ~91)
                if any(datos['ingreso_proyectado'][m] != 0 for m in MESES):
                    continue
                for mes, col in month_cols.items():
                    datos['ingreso_proyectado'][mes] = _parse_value(
                        sheet.cell(row=row_num, column=col).value
                    )
                continue

            # For cost items, column A must have a category code
            col_a = sheet.cell(row=row_num, column=1).value
            if not col_a:
                continue
            col_a_str = str(col_a).strip()
            if col_a_str not in ('MO', 'SST', 'TA', 'MH', 'SC', 'PFS'):
                continue

            # Normalize and lookup
            normalized = _normalize_name(col_b_str)
            estructura_name = EXCEL_TO_ESTRUCTURA.get(normalized)

            if not estructura_name:
                self.unmatched_items.append(f'Fila {row_num}: [{col_a_str}] {col_b_str}')
                continue

            if estructura_name not in item_lookup:
                self.warnings.append(
                    f'Fila {row_num}: "{estructura_name}" no está en ESTRUCTURA_COSTOS'
                )
                continue

            seccion_key, codigo = item_lookup[estructura_name]
            self.matched += 1

            # Extract monthly values
            for mes, col in month_cols.items():
                val = _parse_value(sheet.cell(row=row_num, column=col).value)
                if estructura_name in MERGE_ITEMS:
                    datos[seccion_key][codigo][estructura_name][mes] += val
                else:
                    datos[seccion_key][codigo][estructura_name][mes] = val

        wb.close()

        return {
            'exito': True,
            'datos': datos,
            'matched': self.matched,
            'unmatched': len(self.unmatched_items),
            'unmatched_items': self.unmatched_items,
            'warnings': self.warnings,
        }
