"""
Importers for activity programming from Excel files.
"""
import logging
from datetime import date
from decimal import Decimal

from django.db import transaction
from openpyxl import load_workbook

logger = logging.getLogger(__name__)


class ProgramaTranselcaImporter:
    """
    Importa Excel de Transelca con columnas:
    - Aviso SAP
    - Línea
    - Tipo Actividad
    - Mes programado
    - Ejecutor (OUTSOURCING)
    - Tramo (opcional)
    - Torre inicio / Torre fin (opcional)
    - Valor facturación (opcional)

    El formato puede variar, por lo que se intenta detectar las columnas
    por sus nombres en la primera fila.
    """

    # Mapeo de nombres de columnas posibles a campos internos
    COLUMN_MAPPINGS = {
        'aviso_sap': ['aviso sap', 'aviso', 'nro aviso', 'numero aviso', 'sap', 'no. aviso'],
        'linea': ['línea', 'linea', 'line', 'codigo linea', 'código línea'],
        'tipo_actividad': ['tipo actividad', 'actividad', 'tipo', 'tipo de actividad', 'descripcion actividad'],
        'mes': ['mes', 'mes programado', 'fecha programada', 'mes ejecucion'],
        'anio': ['año', 'ano', 'year'],
        'ejecutor': ['ejecutor', 'contratista', 'outsourcing', 'empresa'],
        'tramo': ['tramo', 'sector', 'seccion'],
        'torre_inicio': ['torre inicio', 'torre ini', 'desde torre', 'torre desde'],
        'torre_fin': ['torre fin', 'torre final', 'hasta torre', 'torre hasta'],
        'valor_facturacion': ['valor', 'valor facturacion', 'facturacion', 'precio', 'monto'],
        'observaciones': ['observaciones', 'notas', 'comentarios', 'obs'],
    }

    def __init__(self):
        self.errores = []
        self.advertencias = []
        self.actividades_creadas = []
        self.actividades_actualizadas = []
        self.filas_omitidas = []
        self.column_indices = {}

    def importar(self, archivo_excel, programacion_mensual, opciones=None):
        """
        Importa actividades desde un archivo Excel de Transelca.

        Args:
            archivo_excel: File object or path to Excel file
            programacion_mensual: ProgramacionMensual instance to associate activities
            opciones: Dict with import options (actualizar_existentes, etc.)

        Returns:
            Dict with import summary
        """

        from .models import Actividad

        opciones = opciones or {}
        actualizar_existentes = opciones.get('actualizar_existentes', False)

        try:
            workbook = load_workbook(archivo_excel, read_only=True, data_only=True)
            sheet = workbook.active
        except Exception as e:
            logger.error(f"Error loading Excel file: {e}")
            return {
                'exito': False,
                'error': f'Error al cargar archivo Excel: {str(e)}',
                'actividades_creadas': 0,
                'actividades_actualizadas': 0,
            }

        # Detectar columnas en la primera fila
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return {
                'exito': False,
                'error': 'El archivo está vacío',
                'actividades_creadas': 0,
                'actividades_actualizadas': 0,
            }

        header_row = rows[0]
        self._detectar_columnas(header_row)

        if 'linea' not in self.column_indices:
            return {
                'exito': False,
                'error': 'No se encontró la columna de Línea en el archivo',
                'actividades_creadas': 0,
                'actividades_actualizadas': 0,
            }

        if 'tipo_actividad' not in self.column_indices:
            return {
                'exito': False,
                'error': 'No se encontró la columna de Tipo de Actividad en el archivo',
                'actividades_creadas': 0,
                'actividades_actualizadas': 0,
            }

        # Procesar filas de datos
        linea_asociada = programacion_mensual.linea

        with transaction.atomic():
            for row_num, row in enumerate(rows[1:], start=2):
                try:
                    resultado = self._procesar_fila(
                        row, row_num, programacion_mensual, linea_asociada, actualizar_existentes
                    )
                    if resultado == 'creada':
                        self.actividades_creadas.append(row_num)
                    elif resultado == 'actualizada':
                        self.actividades_actualizadas.append(row_num)
                    elif resultado == 'omitida':
                        self.filas_omitidas.append(row_num)
                except Exception as e:
                    logger.warning(f"Error processing row {row_num}: {e}")
                    self.errores.append({
                        'fila': row_num,
                        'error': str(e)
                    })

        # Actualizar programación mensual
        programacion_mensual.total_actividades = Actividad.objects.filter(
            programacion=programacion_mensual
        ).count()
        programacion_mensual.save(update_fields=['total_actividades', 'updated_at'])

        return {
            'exito': True,
            'actividades_creadas': len(self.actividades_creadas),
            'actividades_actualizadas': len(self.actividades_actualizadas),
            'filas_omitidas': len(self.filas_omitidas),
            'errores': self.errores,
            'advertencias': self.advertencias,
            'columnas_detectadas': list(self.column_indices.keys()),
        }

    def _detectar_columnas(self, header_row):
        """Detecta las columnas en la fila de encabezado."""
        for col_idx, cell_value in enumerate(header_row):
            if cell_value is None:
                continue
            cell_lower = str(cell_value).lower().strip()

            for field_name, posibles in self.COLUMN_MAPPINGS.items():
                if cell_lower in posibles:
                    self.column_indices[field_name] = col_idx
                    break

        logger.info(f"Detected columns: {self.column_indices}")

    def _get_cell_value(self, row, field_name):
        """Obtiene el valor de una celda por nombre de campo."""
        if field_name not in self.column_indices:
            return None
        idx = self.column_indices[field_name]
        if idx < len(row):
            return row[idx]
        return None

    def _detectar_fecha_excel(self, data_rows):
        """Detecta año y mes del Excel inspeccionando datos."""
        anio = None
        mes = None

        for row in data_rows[:5]:
            if 'anio' in self.column_indices:
                val = self._get_cell_value(row, 'anio')
                if val:
                    try:
                        anio = int(val)
                        if 2000 < anio < 2100:
                            break
                    except (ValueError, TypeError):
                        pass

            if 'mes' in self.column_indices:
                val = self._get_cell_value(row, 'mes')
                if val:
                    try:
                        mes = int(val)
                        if 1 <= mes <= 12:
                            break
                    except (ValueError, TypeError):
                        pass

        return anio, mes

    def _procesar_fila(self, row, row_num, programacion_mensual, linea_asociada, actualizar_existentes):
        """Procesa una fila del Excel y crea/actualiza la actividad."""
        from apps.lineas.models import Linea, Torre, Tramo

        from .models import Actividad, TipoActividad

        # Obtener valores de la fila
        aviso_sap = self._get_cell_value(row, 'aviso_sap')
        linea_codigo = self._get_cell_value(row, 'linea')
        tipo_actividad_nombre = self._get_cell_value(row, 'tipo_actividad')
        tramo_codigo = self._get_cell_value(row, 'tramo')
        torre_inicio_num = self._get_cell_value(row, 'torre_inicio')
        _torre_fin_num = self._get_cell_value(row, 'torre_fin')  # noqa: F841
        valor_facturacion = self._get_cell_value(row, 'valor_facturacion')
        observaciones = self._get_cell_value(row, 'observaciones')

        # Validaciones básicas
        if not linea_codigo and not linea_asociada:
            self.advertencias.append({
                'fila': row_num,
                'mensaje': 'No se especificó línea y no hay línea asociada a la programación'
            })
            return 'omitida'

        if not tipo_actividad_nombre:
            self.advertencias.append({
                'fila': row_num,
                'mensaje': 'No se especificó tipo de actividad'
            })
            return 'omitida'

        # Buscar línea
        linea = linea_asociada
        if linea_codigo:
            try:
                linea = Linea.objects.get(codigo__iexact=str(linea_codigo).strip())
            except Linea.DoesNotExist:
                self.advertencias.append({
                    'fila': row_num,
                    'mensaje': f'Línea no encontrada: {linea_codigo}'
                })
                if not linea_asociada:
                    return 'omitida'

        # Buscar tipo de actividad
        try:
            tipo_actividad = TipoActividad.objects.get(
                nombre__iexact=str(tipo_actividad_nombre).strip()
            )
        except TipoActividad.DoesNotExist:
            # Intentar búsqueda parcial
            tipos = TipoActividad.objects.filter(
                nombre__icontains=str(tipo_actividad_nombre).strip()
            )
            if tipos.exists():
                tipo_actividad = tipos.first()
                self.advertencias.append({
                    'fila': row_num,
                    'mensaje': f'Tipo de actividad "{tipo_actividad_nombre}" mapeado a "{tipo_actividad.nombre}"'
                })
            else:
                self.advertencias.append({
                    'fila': row_num,
                    'mensaje': f'Tipo de actividad no encontrado: {tipo_actividad_nombre}'
                })
                return 'omitida'

        # Buscar tramo (opcional)
        tramo = None
        if tramo_codigo:
            try:
                tramo = Tramo.objects.get(codigo__iexact=str(tramo_codigo).strip())
            except Tramo.DoesNotExist:
                self.advertencias.append({
                    'fila': row_num,
                    'mensaje': f'Tramo no encontrado: {tramo_codigo}'
                })

        # Buscar torre (opcional, usa la torre de inicio del tramo si hay tramo)
        torre = None
        if tramo:
            torre = tramo.torre_inicio
        elif torre_inicio_num:
            try:
                torre = Torre.objects.get(
                    linea=linea,
                    numero=str(torre_inicio_num).strip()
                )
            except Torre.DoesNotExist:
                self.advertencias.append({
                    'fila': row_num,
                    'mensaje': f'Torre no encontrada: {torre_inicio_num}'
                })

        # Preparar valor de facturación
        valor_fact = Decimal('0')
        if valor_facturacion:
            try:
                valor_fact = Decimal(str(valor_facturacion).replace(',', '.').replace('$', '').strip())
            except (ValueError, TypeError):
                self.advertencias.append({
                    'fila': row_num,
                    'mensaje': f'Valor de facturación inválido: {valor_facturacion}'
                })

        # Verificar si ya existe (por aviso SAP)
        actividad_existente = None
        if aviso_sap:
            aviso_sap_str = str(aviso_sap).strip()
            try:
                actividad_existente = Actividad.objects.get(aviso_sap=aviso_sap_str)
            except Actividad.DoesNotExist:
                pass

        if actividad_existente:
            if actualizar_existentes:
                # Actualizar actividad existente
                actividad_existente.linea = linea
                actividad_existente.tipo_actividad = tipo_actividad
                actividad_existente.torre = torre
                actividad_existente.tramo = tramo
                actividad_existente.programacion = programacion_mensual
                if valor_fact > 0:
                    actividad_existente.valor_facturacion = valor_fact
                if observaciones:
                    actividad_existente.observaciones_programacion = str(observaciones)
                actividad_existente.save()
                return 'actualizada'
            else:
                self.advertencias.append({
                    'fila': row_num,
                    'mensaje': f'Actividad con Aviso SAP {aviso_sap} ya existe, omitiendo'
                })
                return 'omitida'

        # Crear nueva actividad
        Actividad.objects.create(
            linea=linea,
            torre=torre,
            tipo_actividad=tipo_actividad,
            programacion=programacion_mensual,
            tramo=tramo,
            aviso_sap=str(aviso_sap).strip() if aviso_sap else '',
            fecha_programada=date(programacion_mensual.anio, programacion_mensual.mes, 1),
            estado=Actividad.Estado.PENDIENTE,
            prioridad=Actividad.Prioridad.NORMAL,
            valor_facturacion=valor_fact,
            observaciones_programacion=str(observaciones) if observaciones else '',
        )

        return 'creada'


class AvisosTranselcaImporter:
    """
    Importador especializado para el archivo de Avisos Abiertos de Transelca.

    Formato esperado del Excel:
    - LINEA: Código de línea (L-838, L-5156, etc.)
    - CIRCUITO: Número de circuito
    - TIPO: Categoría de actividad
    - AVISO: Número de aviso SAP
    - PT SAP: Puesto de trabajo SAP
    - CENTRO EMPL.: Centro de emplazamiento
    - Columnas de equipos: cantidad de elementos por tipo de actividad
    """

    # Mapeo de categorías del Excel a TipoActividad
    CATEGORIA_MAPPING = {
        'poda': 'PODA',
        'lavado tradicional': 'LAVADO',
        'lavado': 'LAVADO',
        'servidumbre': 'SERVIDUMBRE',
        'corredor eléctrico': 'CORREDOR',
        'corredor electrico': 'CORREDOR',
        'gestionar permiso': 'PERMISO',
        'permiso': 'PERMISO',
        'inspección pedestre': 'INSPECCION_PED',
        'inspeccion pedestre': 'INSPECCION_PED',
        'termografía': 'TERMOGRAFIA',
        'termografia': 'TERMOGRAFIA',
        'descargas parciales': 'DESCARGAS',
        'mtto electromecánico': 'ELECTROMEC',
        'mtto electromecanico': 'ELECTROMEC',
        'medida puesta tierra': 'MEDICION_PT',
        'medición': 'MEDICION',
        'medicion': 'MEDICION',
        'limpieza': 'LIMPIEZA',
        'cambio herrajes': 'HERRAJES',
        'herrajes': 'HERRAJES',
        'cambio aisladores': 'AISLADORES',
        'aisladores': 'AISLADORES',
        'señalización': 'SEÑALIZACION',
        'señalizacion': 'SEÑALIZACION',
    }

    # Columnas esperadas
    COLUMN_MAPPINGS = {
        'linea': ['linea', 'línea', 'line', 'codigo_linea'],
        'circuito': ['circuito', 'cto', 'circuit'],
        'tipo': ['tipo', 'tipo actividad', 'actividad', 'categoria'],
        'aviso': ['aviso', 'aviso sap', 'nro aviso', 'no. aviso'],
        'pt_sap': ['pt sap', 'pt', 'puesto trabajo', 'puesto de trabajo'],
        'centro_empl': ['centro empl', 'centro empl.', 'centro emplazamiento', 'ce'],
        'contratista': ['contratista', 'ejecutor', 'outsourcing', 'empresa'],
        'torre_inicio': ['torre inicio', 'desde', 'torre desde'],
        'torre_fin': ['torre fin', 'hasta', 'torre hasta'],
        'descripcion': ['descripcion', 'descripción', 'descripcion actividad'],
        'anio': ['año', 'año fin prioridad', 'ano', 'year'],
        'mes': ['mes', 'mes ejecucion', 'mes\nejecu', 'month'],
    }

    def __init__(self):
        self.errores = []
        self.advertencias = []
        self.actividades_creadas = []
        self.actividades_actualizadas = []
        self.actividades_omitidas = []
        self.column_indices = {}

    def importar(self, archivo_excel, anio: int = None, mes: int = None, opciones=None):
        """
        Importa avisos desde el archivo Excel de Transelca.

        Args:
            archivo_excel: File object or path to Excel file
            anio: Año de la programación (opcional, se detecta del Excel si no se proporciona)
            mes: Mes de la programación (opcional, se detecta del Excel si no se proporciona)
            opciones: Dict with import options

        Returns:
            Dict with import summary
        """
        from apps.lineas.models import Linea
        from datetime import date

        from .models import TipoActividad

        opciones = opciones or {}
        actualizar_existentes = opciones.get('actualizar_existentes', False)
        crear_lineas = opciones.get('crear_lineas', False)

        try:
            workbook = load_workbook(archivo_excel, read_only=True, data_only=True)
            sheet = workbook.active
        except Exception as e:
            logger.error(f"Error loading Excel file: {e}")
            return {
                'exito': False,
                'error': f'Error al cargar archivo Excel: {str(e)}',
                'actividades_creadas': 0,
            }

        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return {'exito': False, 'error': 'El archivo está vacío'}

        # Detectar columnas
        header_row = rows[0]
        self._detectar_columnas(header_row)

        if 'aviso' not in self.column_indices:
            return {
                'exito': False,
                'error': 'No se encontró la columna de Aviso SAP',
            }

        # Detectar año y mes del Excel si no se proporcionan
        if not anio or not mes:
            anio_excel, mes_excel = self._detectar_fecha_excel(rows[1:])
            if anio_excel and mes_excel:
                anio = anio or anio_excel
                mes = mes or mes_excel

        # Usar valores por defecto si no se encuentran
        if not anio or not mes:
            hoy = date.today()
            anio = anio or hoy.year
            mes = mes or hoy.month

        # Cache de líneas y tipos de actividad
        lineas_cache = {linea_obj.codigo: linea_obj for linea_obj in Linea.objects.all()}
        tipos_cache = {t.categoria: t for t in TipoActividad.objects.filter(activo=True)}

        # También crear cache por nombre
        tipos_nombre_cache = {t.nombre.lower(): t for t in TipoActividad.objects.filter(activo=True)}

        with transaction.atomic():
            for row_num, row in enumerate(rows[1:], start=2):
                try:
                    resultado = self._procesar_fila(
                        row, row_num, anio, mes,
                        lineas_cache, tipos_cache, tipos_nombre_cache,
                        actualizar_existentes, crear_lineas
                    )
                    if resultado == 'creada':
                        self.actividades_creadas.append(row_num)
                    elif resultado == 'actualizada':
                        self.actividades_actualizadas.append(row_num)
                    elif resultado == 'omitida':
                        self.actividades_omitidas.append(row_num)
                except Exception as e:
                    logger.warning(f"Error processing row {row_num}: {e}")
                    self.errores.append({'fila': row_num, 'error': str(e)})

        return {
            'exito': True,
            'actividades_creadas': len(self.actividades_creadas),
            'actividades_actualizadas': len(self.actividades_actualizadas),
            'actividades_omitidas': len(self.actividades_omitidas),
            'errores': self.errores,
            'advertencias': self.advertencias,
            'columnas_detectadas': list(self.column_indices.keys()),
        }

    def _detectar_columnas(self, header_row):
        """Detecta las columnas en la fila de encabezado."""
        for col_idx, cell_value in enumerate(header_row):
            if cell_value is None:
                continue
            cell_lower = str(cell_value).lower().strip()

            for field_name, posibles in self.COLUMN_MAPPINGS.items():
                if cell_lower in posibles:
                    self.column_indices[field_name] = col_idx
                    break

        logger.info(f"Avisos importer detected columns: {self.column_indices}")

    def _detectar_fecha_excel(self, data_rows):
        """Detecta año y mes del Excel inspeccionando datos."""
        anio = None
        mes = None

        for row in data_rows[:5]:  # Revisar primeras 5 filas
            if 'anio' in self.column_indices:
                val = self._get_cell(row, 'anio')
                if val:
                    try:
                        anio = int(val)
                        if 2000 < anio < 2100:
                            break
                    except (ValueError, TypeError):
                        pass

            if 'mes' in self.column_indices:
                val = self._get_cell(row, 'mes')
                if val:
                    try:
                        mes = int(val)
                        if 1 <= mes <= 12:
                            break
                    except (ValueError, TypeError):
                        pass

        return anio, mes

    def _get_cell(self, row, field_name):
        """Obtiene el valor de una celda."""
        if field_name not in self.column_indices:
            return None
        idx = self.column_indices[field_name]
        if idx < len(row):
            return row[idx]
        return None

    def _mapear_categoria(self, tipo_str):
        """Mapea el tipo del Excel a la categoría del modelo."""
        if not tipo_str:
            return None
        tipo_lower = str(tipo_str).lower().strip()
        return self.CATEGORIA_MAPPING.get(tipo_lower)

    def _procesar_fila(self, row, row_num, anio, mes, lineas_cache, tipos_cache,
                       tipos_nombre_cache, actualizar_existentes, crear_lineas):
        """Procesa una fila del Excel."""

        from .models import Actividad, ProgramacionMensual

        aviso_sap = self._get_cell(row, 'aviso')
        if not aviso_sap:
            return 'omitida'

        aviso_sap = str(aviso_sap).strip()

        linea_codigo = self._get_cell(row, 'linea')
        tipo_str = self._get_cell(row, 'tipo')
        pt_sap = self._get_cell(row, 'pt_sap')
        # centro_empl and circuito read for future use
        _centro_empl = self._get_cell(row, 'centro_empl')  # noqa: F841
        _circuito = self._get_cell(row, 'circuito')  # noqa: F841
        descripcion = self._get_cell(row, 'descripcion')

        # Buscar línea
        linea = None
        if linea_codigo:
            linea_codigo_str = str(linea_codigo).strip()
            linea = lineas_cache.get(linea_codigo_str)
            if not linea:
                # Intentar búsqueda flexible
                for codigo, linea_obj in lineas_cache.items():
                    if linea_codigo_str in codigo or codigo in linea_codigo_str:
                        linea = linea_obj
                        break

            if not linea:
                self.advertencias.append({
                    'fila': row_num,
                    'mensaje': f'Línea no encontrada: {linea_codigo_str}'
                })
                return 'omitida'

        # Buscar tipo de actividad
        tipo_actividad = None
        if tipo_str:
            categoria = self._mapear_categoria(tipo_str)
            if categoria and categoria in tipos_cache:
                tipo_actividad = tipos_cache[categoria]
            else:
                # Buscar por nombre
                tipo_lower = str(tipo_str).lower().strip()
                for nombre, t in tipos_nombre_cache.items():
                    if tipo_lower in nombre or nombre in tipo_lower:
                        tipo_actividad = t
                        break

        if not tipo_actividad:
            # Usar tipo genérico
            tipo_actividad = tipos_cache.get('OTRO')
            if tipo_actividad:
                self.advertencias.append({
                    'fila': row_num,
                    'mensaje': f'Tipo "{tipo_str}" mapeado a "Otro"'
                })

        if not linea or not tipo_actividad:
            self.advertencias.append({
                'fila': row_num,
                'mensaje': 'Faltan datos requeridos (línea o tipo)'
            })
            return 'omitida'

        # Buscar o crear programación mensual
        programacion, _ = ProgramacionMensual.objects.get_or_create(
            anio=anio,
            mes=mes,
            linea=linea,
            defaults={'total_actividades': 0}
        )

        # Buscar torre por defecto (primera de la línea)
        torre = linea.torres.first()

        # Verificar si existe
        try:
            actividad = Actividad.objects.get(aviso_sap=aviso_sap)
            if actualizar_existentes:
                actividad.linea = linea
                actividad.tipo_actividad = tipo_actividad
                actividad.pt_sap = str(pt_sap).strip() if pt_sap else ''
                actividad.programacion = programacion
                if descripcion:
                    actividad.observaciones_programacion = str(descripcion)
                actividad.save()
                return 'actualizada'
            return 'omitida'
        except Actividad.DoesNotExist:
            pass

        # Crear actividad
        Actividad.objects.create(
            linea=linea,
            torre=torre,
            tipo_actividad=tipo_actividad,
            programacion=programacion,
            aviso_sap=aviso_sap,
            pt_sap=str(pt_sap).strip() if pt_sap else '',
            fecha_programada=date(anio, mes, 1),
            estado=Actividad.Estado.PENDIENTE,
            prioridad=Actividad.Prioridad.NORMAL,
            observaciones_programacion=str(descripcion) if descripcion else '',
        )

        return 'creada'


class ImportadorExcelGenerico:
    """
    Importador genérico para diferentes formatos de Excel.
    Útil para importar datos de otras fuentes.
    """

    def __init__(self, mapping_columnas=None):
        self.mapping_columnas = mapping_columnas or {}
        self.errores = []
        self.registros_procesados = 0

    def leer_excel(self, archivo_excel, hoja=None):
        """
        Lee un archivo Excel y retorna los datos como lista de diccionarios.

        Args:
            archivo_excel: File object or path
            hoja: Nombre de la hoja (None = hoja activa)

        Returns:
            List of dicts with row data
        """
        try:
            workbook = load_workbook(archivo_excel, read_only=True, data_only=True)
            if hoja:
                sheet = workbook[hoja]
            else:
                sheet = workbook.active
        except Exception as e:
            logger.error(f"Error loading Excel: {e}")
            return []

        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return []

        headers = [str(h).strip() if h else f'col_{i}' for i, h in enumerate(rows[0])]
        data = []

        for row in rows[1:]:
            row_dict = {}
            for i, value in enumerate(row):
                if i < len(headers):
                    col_name = headers[i]
                    # Aplicar mapping si existe
                    if col_name.lower() in self.mapping_columnas:
                        col_name = self.mapping_columnas[col_name.lower()]
                    row_dict[col_name] = value
            data.append(row_dict)

        return data


class AvancesImporter:
    """
    Importa avances de actividades desde Excel con detección flexible de columnas.
    Busca actividades por aviso_sap y actualiza porcentaje_avance, estado, observaciones.
    """

    COLUMN_MAPPINGS = {
        'aviso_sap': ['aviso sap', 'aviso', 'nro aviso', 'numero aviso', 'sap', 'no. aviso', 'aviso_sap', 'id aviso'],
        'porcentaje_avance': ['avance', 'porcentaje avance', '% avance', 'avance %', 'porcentaje', 'progreso', '% progreso', 'porcentaje_avance'],
        'estado': ['estado', 'estado actividad', 'status'],
        'observaciones': ['observaciones', 'notas', 'comentarios', 'obs', 'nota'],
    }

    ESTADO_MAPPING = {
        'pendiente': 'PENDIENTE',
        'programada': 'PROGRAMADA',
        'en curso': 'EN_CURSO',
        'en_curso': 'EN_CURSO',
        'completada': 'COMPLETADA',
        'cancelada': 'CANCELADA',
        'reprogramada': 'REPROGRAMADA',
    }

    def __init__(self):
        self.errores = []
        self.advertencias = []
        self.actividades_actualizadas = []
        self.filas_omitidas = []
        self.column_indices = {}

    def importar(self, archivo_excel):
        """Importa avances desde un archivo Excel."""
        try:
            workbook = load_workbook(archivo_excel, read_only=True, data_only=True)
            sheet = workbook.active
        except Exception as e:
            logger.error(f"Error loading Excel file: {e}")
            return {'exito': False, 'error': f'Error al cargar archivo Excel: {str(e)}'}

        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return {'exito': False, 'error': 'El archivo está vacío'}

        self._detectar_columnas(rows[0])

        if 'aviso_sap' not in self.column_indices:
            columnas_recibidas = [str(h) for h in rows[0] if h]
            return {
                'exito': False,
                'error': f'No se encontró columna de Aviso SAP. Columnas detectadas: {", ".join(columnas_recibidas)}',
                'columnas_recibidas': columnas_recibidas,
            }

        with transaction.atomic():
            for row_num, row in enumerate(rows[1:], start=2):
                try:
                    self._procesar_fila(row, row_num)
                except Exception as e:
                    logger.warning(f"Error processing row {row_num}: {e}")
                    self.errores.append({'fila': row_num, 'error': str(e)})

        return {
            'exito': True,
            'actividades_actualizadas': len(self.actividades_actualizadas),
            'filas_omitidas': len(self.filas_omitidas),
            'errores': self.errores,
            'advertencias': self.advertencias,
            'columnas_detectadas': list(self.column_indices.keys()),
        }

    def _detectar_columnas(self, header_row):
        """Detecta las columnas en la fila de encabezado."""
        for col_idx, cell_value in enumerate(header_row):
            if cell_value is None:
                continue
            cell_lower = str(cell_value).lower().strip()
            for field_name, posibles in self.COLUMN_MAPPINGS.items():
                if cell_lower in posibles and field_name not in self.column_indices:
                    self.column_indices[field_name] = col_idx
                    break

        logger.info(f"Avances importer detected columns: {self.column_indices}")

    def _get_cell(self, row, field_name):
        """Obtiene el valor de una celda por nombre de campo."""
        if field_name not in self.column_indices:
            return None
        idx = self.column_indices[field_name]
        return row[idx] if idx < len(row) else None

    def _procesar_fila(self, row, row_num):
        """Procesa una fila del Excel y actualiza la actividad."""
        from .models import Actividad

        aviso_sap = self._get_cell(row, 'aviso_sap')
        if not aviso_sap:
            self.filas_omitidas.append(row_num)
            return

        aviso_sap = str(aviso_sap).strip()
        try:
            actividad = Actividad.objects.get(aviso_sap=aviso_sap)
        except Actividad.DoesNotExist:
            self.advertencias.append({
                'fila': row_num,
                'mensaje': f'Aviso SAP no encontrado: {aviso_sap}'
            })
            self.filas_omitidas.append(row_num)
            return

        actualizado = False

        porcentaje = self._get_cell(row, 'porcentaje_avance')
        if porcentaje is not None:
            try:
                pct = Decimal(str(porcentaje).replace('%', '').replace(',', '.').strip())
                actividad.actualizar_avance(pct)
                actualizado = True
            except (ValueError, TypeError):
                self.advertencias.append({
                    'fila': row_num,
                    'mensaje': f'Porcentaje inválido para SAP {aviso_sap}: {porcentaje}'
                })

        estado_raw = self._get_cell(row, 'estado')
        if estado_raw:
            estado_mapped = self.ESTADO_MAPPING.get(str(estado_raw).lower().strip())
            if estado_mapped and estado_mapped in dict(Actividad.Estado.choices):
                actividad.estado = estado_mapped
                actividad.save(update_fields=['estado', 'updated_at'])
                actualizado = True

        obs = self._get_cell(row, 'observaciones')
        if obs:
            actividad.observaciones_programacion = str(obs)
            actividad.save(update_fields=['observaciones_programacion', 'updated_at'])
            actualizado = True

        if actualizado:
            self.actividades_actualizadas.append(aviso_sap)
