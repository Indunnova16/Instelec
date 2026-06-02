"""
Importador contable completo v2 — B1 (#120).

Lee la hoja 'BD' del archivo 'BASE DE DATOS.xlsx' (≈23k filas), agrupa por la
columna O ("Cta equivalente") sumando la columna C ("Neto"), y mapea cada
cuenta equivalente a un rubro presupuestal via ``MapeoCtaRubro`` (o el dict
semilla ``MAPEO_CTA_RUBRO_DEFAULT``). Las cuentas no mapeadas caen en
"Otros / No Clasificado".

Devuelve una estructura ``datos`` que se guarda en
``PresupuestoDetallado.datos`` bajo la llave ``finv2_bd`` (no colisiona con la
estructura legacy de ``_build_display_rows`` / ``_build_empty_datos``, que vive
en las otras llaves del mismo JSONField).

Reusa el patrón de detección de columnas y lectura openpyxl de
``apps.financiero.importers`` (``_normalize_name`` / ``load_workbook
read_only``).
"""
import unicodedata

from openpyxl import load_workbook

from .models_finv2_mapeo import (
    MAPEO_CTA_RUBRO_DEFAULT,
    RUBRO_NO_CLASIFICADO,
)


# Tamaño máximo de archivo aceptado (20 MB, por requerimiento #120).
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

# Nombres de hoja candidatos para la base de datos contable.
_BD_SHEET_NAMES = ('bd', 'base de datos', 'base datos')

# Encabezados (normalizados) esperados en la fila 1.
_HEADER_CTA = 'cta equivalente'   # columna O
_HEADER_NETO = 'neto'             # columna C
_HEADER_DESC = 'desc auxiliar'    # columna B


def _norm(value) -> str:
    """Normaliza un texto para comparación: minúsculas, sin acentos/puntuación."""
    if value is None:
        return ''
    s = str(value).strip().lower()
    s = s.replace('_', ' ').replace('-', ' ').replace('.', ' ')
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = s.replace('/', ' ').replace('(', '').replace(')', '').replace(',', '')
    return ' '.join(s.split())


def _to_number(value):
    """Convierte un valor de celda a float; None/no-numérico → 0.0."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


class ContableCompleteImporter:
    """Procesa la BD contable completa y la agrupa en rubros presupuestales."""

    def __init__(self):
        self.warnings = []

    # ------------------------------------------------------------------ #
    # Mapeo cuenta → rubro
    # ------------------------------------------------------------------ #
    def _build_mapeo(self, mapeo=None):
        """Construye el dict {cta_equivalente_normalizada: rubro}.

        Prioridad: ``mapeo`` explícito > registros activos de ``MapeoCtaRubro``
        en BD > ``MAPEO_CTA_RUBRO_DEFAULT`` semilla.
        """
        if mapeo:
            return {_norm(k): v for k, v in mapeo.items()}

        tabla = dict(MAPEO_CTA_RUBRO_DEFAULT)
        try:
            from .models_finv2_mapeo import MapeoCtaRubro
            qs = MapeoCtaRubro.objects.filter(activo=True)
            for m in qs:
                tabla[_norm(m.cta_equivalente)] = m.rubro_presupuestal
        except Exception:
            # En contextos sin BD (p.ej. validación de sintaxis) seguimos con
            # el dict semilla. El importador real corre dentro de la vista.
            pass
        return {_norm(k): v for k, v in tabla.items()}

    def _rubro_para(self, cta_equivalente, mapeo):
        """Devuelve el rubro para una cuenta equivalente (o NO_CLASIFICADO)."""
        return mapeo.get(_norm(cta_equivalente), RUBRO_NO_CLASIFICADO)

    # ------------------------------------------------------------------ #
    # Detección de columnas
    # ------------------------------------------------------------------ #
    def _locate_sheet(self, wb):
        for name in wb.sheetnames:
            if _norm(name) in _BD_SHEET_NAMES:
                return wb[name]
        return None

    def _locate_columns(self, sheet):
        """Detecta los índices (1-based) de las columnas O, C y B por encabezado.

        Si no encuentra por nombre, cae a los índices fijos del layout #120
        (C=3, B=2, O=15).
        """
        headers = {}
        for col in range(1, 30):
            val = sheet.cell(row=1, column=col).value
            if val:
                headers[_norm(val)] = col

        cta_col = headers.get(_HEADER_CTA)
        neto_col = headers.get(_HEADER_NETO)
        desc_col = headers.get(_HEADER_DESC) or headers.get('descripcion')

        # Fallback a índices fijos del layout documentado en #120.
        if not cta_col:
            cta_col = 15  # O
        if not neto_col:
            neto_col = 3   # C
        if not desc_col:
            desc_col = 2   # B

        return cta_col, neto_col, desc_col

    # ------------------------------------------------------------------ #
    # Entry point
    # ------------------------------------------------------------------ #
    def procesar_bd_completa(self, archivo, mapeo=None):
        """Procesa el archivo y devuelve un dict de resultado.

        Estructura de retorno::

            {
              'exito': bool,
              'error': str | None,        # mensaje ❌ del issue
              'advertencia': str | None,  # mensaje ⚠️ del issue
              'mensaje': str | None,      # mensaje ✅ del issue
              'datos': {...} | None,      # estructura finv2_bd para .datos
              'cuentas': int,
              'total': float,
              'no_mapeadas': [str, ...],
            }
        """
        # --- Validación de archivo (tamaño + extensión) ---
        nombre = getattr(archivo, 'name', '') or ''
        if not nombre.lower().endswith('.xlsx'):
            return self._error(
                'Archivo inválido. Verifique que sea .xlsx con estructura correcta'
            )

        tamano = getattr(archivo, 'size', None)
        if tamano is not None and tamano > MAX_UPLOAD_BYTES:
            return self._error(
                'Archivo inválido. El archivo excede el tamaño máximo (20 MB).'
            )

        try:
            wb = load_workbook(archivo, read_only=True, data_only=True)
        except Exception as exc:  # noqa: BLE001
            return self._error(
                'Archivo inválido. Verifique que sea .xlsx con estructura '
                f'correcta ({exc}).'
            )

        # --- Edge case 1: hoja BD ausente ---
        sheet = self._locate_sheet(wb)
        if sheet is None:
            sheet = wb.active
            self.warnings.append(
                f"No se encontró hoja 'BD'; usando hoja activa '{sheet.title}'."
            )

        cta_col, neto_col, desc_col = self._locate_columns(sheet)

        # --- Edge case 2: columna O (Cta equivalente) ausente / vacía ---
        # Validamos leyendo el encabezado real de la columna detectada.
        header_cta = _norm(sheet.cell(row=1, column=cta_col).value)
        if header_cta and header_cta != _HEADER_CTA and 'cta' not in header_cta:
            wb.close()
            return self._advertencia(
                'Archivo sin datos válidos en columnas O (Cta equivalente) o '
                'C (Neto)'
            )

        mapeo_tabla = self._build_mapeo(mapeo)

        # --- Agrupación por cuenta equivalente (col O) sumando Neto (col C) ---
        # grupos[cta] = {'descripcion': str, 'total': float}
        grupos = {}
        filas_validas = 0
        max_col = max(cta_col, neto_col, desc_col)

        for row in sheet.iter_rows(min_row=2, max_col=max_col, values_only=True):
            cta_val = row[cta_col - 1] if len(row) >= cta_col else None
            neto_val = row[neto_col - 1] if len(row) >= neto_col else None
            desc_val = row[desc_col - 1] if len(row) >= desc_col else None

            # Validar que la fila tenga O, C, B (requerimiento #120 paso 1).
            if cta_val is None or neto_val is None:
                continue
            cta_str = str(cta_val).strip()
            if not cta_str:
                continue

            neto = _to_number(neto_val)
            filas_validas += 1

            grupo = grupos.setdefault(
                cta_str, {'descripcion': '', 'total': 0.0}
            )
            grupo['total'] += neto
            if not grupo['descripcion'] and desc_val:
                grupo['descripcion'] = str(desc_val).strip()

        wb.close()

        # --- Edge case 3: archivo sin filas válidas ---
        if filas_validas == 0 or not grupos:
            return self._advertencia(
                'Archivo sin datos válidos en columnas O (Cta equivalente) o '
                'C (Neto)'
            )

        # --- Mapeo cuenta → rubro y construcción de la estructura datos ---
        rubros = {}  # rubro -> {'total': float, 'cuentas': [ {...} ]}
        no_mapeadas = []

        for cta, info in sorted(grupos.items()):
            rubro = self._rubro_para(cta, mapeo_tabla)
            if rubro == RUBRO_NO_CLASIFICADO:
                no_mapeadas.append(cta)
            destino = rubros.setdefault(rubro, {'total': 0.0, 'cuentas': []})
            destino['total'] += info['total']
            destino['cuentas'].append({
                'cta_equivalente': cta,
                'descripcion': info['descripcion'],
                'total': round(info['total'], 2),
            })

        total_general = round(sum(r['total'] for r in rubros.values()), 2)
        for r in rubros.values():
            r['total'] = round(r['total'], 2)

        datos = {
            'finv2_bd': {
                'rubros': rubros,
                'total': total_general,
                'cuentas_count': len(grupos),
                'cuentas_no_mapeadas': no_mapeadas,
            }
        }

        mensaje = (
            f'Importación completada. {len(grupos)} cuentas procesadas. '
            f'Total importado: ${total_general:,.0f}'
        )
        if no_mapeadas:
            self.warnings.append(
                f'{len(no_mapeadas)} cuentas sin mapeo se agruparon en '
                f'"{RUBRO_NO_CLASIFICADO}".'
            )

        return {
            'exito': True,
            'error': None,
            'advertencia': None,
            'mensaje': mensaje,
            'datos': datos,
            'cuentas': len(grupos),
            'total': total_general,
            'no_mapeadas': no_mapeadas,
            'warnings': self.warnings,
        }

    # ------------------------------------------------------------------ #
    # Helpers de resultado
    # ------------------------------------------------------------------ #
    def _error(self, msg):
        return {
            'exito': False, 'error': msg, 'advertencia': None, 'mensaje': None,
            'datos': None, 'cuentas': 0, 'total': 0.0, 'no_mapeadas': [],
            'warnings': self.warnings,
        }

    def _advertencia(self, msg):
        return {
            'exito': False, 'error': None, 'advertencia': msg, 'mensaje': None,
            'datos': None, 'cuentas': 0, 'total': 0.0, 'no_mapeadas': [],
            'warnings': self.warnings,
        }


def build_rubro_display_rows(datos):
    """Construye filas para el template a partir de ``datos['finv2_bd']``.

    Cada fila: {'rubro': str, 'total': float, 'pct': float, 'cuentas': [...]}.
    Devuelve (rows, total_general). Tolerante a datos vacíos / legacy sin
    la llave finv2_bd (devuelve ([], 0)).
    """
    bloque = (datos or {}).get('finv2_bd') or {}
    rubros = bloque.get('rubros') or {}
    total_general = bloque.get('total') or 0.0

    rows = []
    for rubro, info in sorted(
        rubros.items(), key=lambda kv: kv[1].get('total', 0), reverse=True
    ):
        rubro_total = info.get('total', 0.0)
        pct = (rubro_total / total_general * 100) if total_general else 0.0
        rows.append({
            'rubro': rubro,
            'total': rubro_total,
            'pct': round(pct, 1),
            'cuentas': info.get('cuentas', []),
        })
    return rows, total_general
