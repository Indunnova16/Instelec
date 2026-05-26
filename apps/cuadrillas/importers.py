"""
Importers para Cuadrillas desde Excel.

`CuadrillaImporter` lee un archivo con el formato de Avisos SAP donde:

- Fila con columna ``#`` no vacía = encabezado de cuadrilla.
- Filas siguientes con ``#`` vacío = miembros de la cuadrilla previa.

Sigue el patrón de ``ProgramacionSemanalImporter`` en
``apps/actividades/importers.py``: ``COLUMN_MAPPINGS`` para detección flexible
de encabezados + transacción atómica + resumen detallado de creación/error.
"""
import logging
from datetime import date

from django.db import transaction
from openpyxl import load_workbook

logger = logging.getLogger(__name__)


# Costo diario por defecto por rol — alineado con CuadrillaMasivaUploadView
# pre-block. Si el rol no se mapea, queda en 0 y el coordinador lo corrige.
COSTOS_POR_ROL = {
    'SUPERVISOR': 0,
    'LINIERO_I': 3176095,
    'LINIERO_II': 2804856,
    'AYUDANTE': 1750905,
    'CONDUCTOR': 480000,
    'ADMINISTRADOR_OBRA': 2522400,
    'PROFESIONAL_SST': 4204000,
    'ING_RESIDENTE': 7357000,
    'SERVICIO_GENERAL': 1750905,
    'ALMACENISTA': 1800000,
    'SUPERVISOR_FOREST': 2969427,
    'ASISTENTE_FOREST': 4204000,
}


# Mapeo de texto libre del Excel ("Liniero", "Ayudante", etc.) a los choices
# del modelo CuadrillaMiembro.RolCuadrilla.
ROL_TEXTO_A_CHOICE = {
    'supervisor': 'SUPERVISOR',
    'liniero': 'LINIERO_I',
    'liniero i': 'LINIERO_I',
    'liniero 1': 'LINIERO_I',
    'liniero ii': 'LINIERO_II',
    'liniero 2': 'LINIERO_II',
    'ayudante': 'AYUDANTE',
    'conductor': 'CONDUCTOR',
    'administrador obra': 'ADMINISTRADOR_OBRA',
    'administrador de obra': 'ADMINISTRADOR_OBRA',
    'profesional sst': 'PROFESIONAL_SST',
    'sst': 'PROFESIONAL_SST',
    'ingeniero residente': 'ING_RESIDENTE',
    'ing residente': 'ING_RESIDENTE',
    'ing. residente': 'ING_RESIDENTE',
    'servicio general': 'SERVICIO_GENERAL',
    'almacenista': 'ALMACENISTA',
    'supervisor forestal': 'SUPERVISOR_FOREST',
    'asistente forestal': 'ASISTENTE_FOREST',
}


class CuadrillaImporter:
    """
    Importa cuadrillas desde un Excel con formato Aviso SAP.

    Estructura:
        - Fila con ``#`` no vacío → encabezado de cuadrilla (crea/actualiza).
        - Filas siguientes con ``#`` vacío → miembros de la cuadrilla previa.

    Detecta columnas automáticamente por nombre (acepta variaciones).
    Operación atómica: si falla la importación de una cuadrilla por error
    fatal (línea inexistente), revierte TODO. Cédulas/vehículos no
    encontrados solo generan advertencias (la cuadrilla se crea sin ellos).
    """

    COLUMN_MAPPINGS = {
        'numero': ['#', 'no', 'no.', 'item', 'num', 'numero'],
        'cuadrilla': ['cuadrilla', 'codigo', 'codigo cuadrilla', 'codigo_cuadrilla', 'código cuadrilla'],
        'linea': ['linea', 'línea', 'lineas', 'codigo linea', 'código línea'],
        'supervisor': ['supervisor', 'super', 'super.', 'supervisor nombre', 'jefe cuadrilla'],
        'personal': ['personal', 'nombre', 'nombres', 'nombre miembro'],
        'cedula': ['cedula', 'cédula', 'documento', 'doc', 'identificacion', 'identificación'],
        'cargo': ['cargo', 'rol', 'rol cuadrilla', 'puesto'],
        'celular': ['celular', 'telefono', 'teléfono', 'cel', 'celular personal'],
        'placa': ['placa', 'vehiculo', 'vehículo', 'veh', 'vehiculo asignado'],
        'estado': ['estado', 'activa', 'activo'],
        'observaciones': ['observaciones', 'notas', 'comentarios', 'obs'],
    }

    def __init__(self):
        self.errores = []
        self.advertencias = []
        self.cuadrillas_creadas = 0
        self.cuadrillas_actualizadas = 0
        self.miembros_agregados = 0
        self.column_indices = {}

    # ---------- API pública ----------

    def importar(self, archivo_excel, opciones=None):
        """
        Importa cuadrillas desde archivo Excel.

        Args:
            archivo_excel: file-like object o ruta al Excel.
            opciones: dict con flags:
                - actualizar_existentes (bool): si True, actualiza cuadrillas
                  que ya existen por código. Si False, las deja intactas.

        Returns:
            dict con resumen:
                - exito (bool)
                - error (str, solo si no éxito)
                - cuadrillas_creadas (int)
                - cuadrillas_actualizadas (int)
                - miembros_agregados (int)
                - advertencias (list[str])
                - errores (list[str])
                - columnas_detectadas (list[str])
        """
        opciones = opciones or {}
        actualizar_existentes = opciones.get('actualizar_existentes', False)

        try:
            workbook = load_workbook(archivo_excel, read_only=True, data_only=True)
            sheet = workbook.active
        except Exception as e:
            logger.error(f"Error cargando Excel: {e}")
            return self._resultado_error(f'Error al cargar archivo Excel: {e}')

        rows = list(sheet.iter_rows(values_only=True))
        try:
            workbook.close()
        except Exception:
            pass

        if not rows:
            return self._resultado_error('El archivo está vacío')

        self._detectar_columnas(rows[0])

        if 'cuadrilla' not in self.column_indices:
            return self._resultado_error('No se encontró columna "CUADRILLA" en el archivo')
        if 'linea' not in self.column_indices:
            return self._resultado_error('No se encontró columna "LÍNEA" en el archivo')

        # Procesar — agrupamos por cuadrilla (encabezado + miembros).
        cuadrilla_actual = None
        miembros_actuales = []
        cuadrillas_bloque = []  # list of (cuadrilla_dict, miembros_list, row_num)

        for row_num, row in enumerate(rows[1:], start=2):
            if not row or all(c is None or str(c).strip() == '' for c in row):
                continue

            numero = self._get_cell_value(row, 'numero')

            if numero is not None and str(numero).strip() != '':
                # Encabezado de nueva cuadrilla.
                if cuadrilla_actual is not None:
                    cuadrillas_bloque.append((cuadrilla_actual, miembros_actuales, cuadrilla_actual['_row_num']))
                cuadrilla_actual = self._parsear_cuadrilla(row)
                cuadrilla_actual['_row_num'] = row_num
                miembros_actuales = []
                # La fila de encabezado puede TAMBIÉN contener el primer
                # miembro (formato Aviso SAP del issue #105).
                personal = self._get_cell_value(row, 'personal')
                cedula = self._get_cell_value(row, 'cedula')
                if personal or cedula:
                    miembros_actuales.append({
                        'nombre': self._str_or_empty(personal),
                        'cedula': self._str_or_empty(cedula),
                        'cargo': self._str_or_empty(self._get_cell_value(row, 'cargo')),
                        'celular': self._str_or_empty(self._get_cell_value(row, 'celular')),
                        '_row_num': row_num,
                    })
            else:
                if cuadrilla_actual is None:
                    self.advertencias.append(
                        f'Fila {row_num}: miembro sin cuadrilla previa, omitido'
                    )
                    continue
                personal = self._get_cell_value(row, 'personal')
                cedula = self._get_cell_value(row, 'cedula')
                if personal or cedula:
                    miembros_actuales.append({
                        'nombre': self._str_or_empty(personal),
                        'cedula': self._str_or_empty(cedula),
                        'cargo': self._str_or_empty(self._get_cell_value(row, 'cargo')),
                        'celular': self._str_or_empty(self._get_cell_value(row, 'celular')),
                        '_row_num': row_num,
                    })

        # Última cuadrilla pendiente.
        if cuadrilla_actual is not None:
            cuadrillas_bloque.append((cuadrilla_actual, miembros_actuales, cuadrilla_actual['_row_num']))

        if not cuadrillas_bloque:
            return self._resultado_error('No se encontraron cuadrillas en el archivo')

        # Transacción atómica — un error fatal revierte todo.
        try:
            with transaction.atomic():
                for cuadrilla_data, miembros, row_num in cuadrillas_bloque:
                    self._guardar_cuadrilla(cuadrilla_data, miembros, actualizar_existentes, row_num)
                if self.errores:
                    # Errores fatales: rollback explícito.
                    raise _RollbackImport(f'{len(self.errores)} errores fatales')
        except _RollbackImport:
            logger.warning('CuadrillaImporter: rollback por errores fatales')
            return {
                'exito': False,
                'error': 'Importación revertida por errores fatales (ver lista)',
                'cuadrillas_creadas': 0,
                'cuadrillas_actualizadas': 0,
                'miembros_agregados': 0,
                'advertencias': self.advertencias,
                'errores': self.errores,
                'columnas_detectadas': list(self.column_indices.keys()),
            }
        except Exception as e:
            logger.exception('CuadrillaImporter: error inesperado')
            return self._resultado_error(f'Error inesperado: {e}')

        return {
            'exito': True,
            'cuadrillas_creadas': self.cuadrillas_creadas,
            'cuadrillas_actualizadas': self.cuadrillas_actualizadas,
            'miembros_agregados': self.miembros_agregados,
            'advertencias': self.advertencias,
            'errores': self.errores,
            'columnas_detectadas': list(self.column_indices.keys()),
        }

    # ---------- internos ----------

    def _detectar_columnas(self, header_row):
        for col_idx, cell_value in enumerate(header_row):
            if cell_value is None:
                continue
            cell_lower = str(cell_value).lower().strip()
            for field_name, posibles in self.COLUMN_MAPPINGS.items():
                if cell_lower in posibles:
                    self.column_indices[field_name] = col_idx
                    break
        logger.info(f'CuadrillaImporter columnas detectadas: {self.column_indices}')

    def _get_cell_value(self, row, field_name):
        if field_name not in self.column_indices:
            return None
        idx = self.column_indices[field_name]
        if idx < len(row):
            return row[idx]
        return None

    def _str_or_empty(self, value, default=''):
        if value is None:
            return default
        text = str(value).strip()
        return text if text else default

    def _parsear_cuadrilla(self, row):
        return {
            'codigo': self._str_or_empty(self._get_cell_value(row, 'cuadrilla')),
            'linea_nombre': self._str_or_empty(self._get_cell_value(row, 'linea')),
            'supervisor_nombre': self._str_or_empty(self._get_cell_value(row, 'supervisor')),
            'placa': self._str_or_empty(self._get_cell_value(row, 'placa')),
            'estado': self._str_or_empty(self._get_cell_value(row, 'estado'), 'Activa'),
            'observaciones': self._str_or_empty(self._get_cell_value(row, 'observaciones')),
        }

    def _guardar_cuadrilla(self, cuadrilla_data, miembros, actualizar, row_num):
        from apps.cuadrillas.models import Cuadrilla, CuadrillaMiembro, Vehiculo
        from apps.lineas.models import Linea
        from apps.usuarios.models import Usuario

        codigo = cuadrilla_data['codigo']
        if not codigo:
            self.errores.append(f'Fila {row_num}: código de cuadrilla vacío')
            return

        linea_nombre = cuadrilla_data['linea_nombre']
        if not linea_nombre:
            self.errores.append(f'Fila {row_num}: línea vacía para cuadrilla {codigo}')
            return

        # Resolver línea (error fatal si no existe).
        try:
            linea = Linea.objects.get(nombre__iexact=linea_nombre)
        except Linea.DoesNotExist:
            try:
                linea = Linea.objects.get(codigo__iexact=linea_nombre)
            except Linea.DoesNotExist:
                self.errores.append(
                    f'Fila {row_num}: línea "{linea_nombre}" no existe para cuadrilla {codigo}'
                )
                return

        # Resolver supervisor (warning si no existe; deja null).
        supervisor = None
        if cuadrilla_data['supervisor_nombre']:
            sup_nombre = cuadrilla_data['supervisor_nombre']
            partes = sup_nombre.split()
            supervisor = Usuario.objects.filter(
                first_name__icontains=partes[0] if partes else sup_nombre,
                is_active=True,
            ).first()
            if not supervisor:
                self.advertencias.append(
                    f'Fila {row_num}: supervisor "{sup_nombre}" no encontrado, queda sin asignar'
                )

        # Resolver vehículo (warning si no existe; deja null).
        vehiculo = None
        if cuadrilla_data['placa']:
            placa = cuadrilla_data['placa']
            vehiculo = Vehiculo.objects.filter(placa__iexact=placa, activo=True).first()
            if not vehiculo:
                self.advertencias.append(
                    f'Fila {row_num}: vehículo placa "{placa}" no encontrado, queda sin asignar'
                )

        activa = cuadrilla_data['estado'].lower() in ['activa', 'active', 'activo', 'true', '1', 'si', 'sí']

        # Crear o actualizar.
        existente = Cuadrilla.objects.filter(codigo=codigo).first()

        if existente is None:
            # B3: campos auditoría (motivo_desactivacion, fecha_desactivacion,
            # desactivado_por) quedan vacíos al crear cuadrilla nueva activa.
            # Si el schema tiene los campos NOT NULL pero el modelo aún no
            # los expone (escenario worktree B4 pre-merge), seteamos via
            # kwargs defensivos detectados a runtime.
            create_kwargs = {
                'codigo': codigo,
                'nombre': f'Cuadrilla {codigo}',
                'linea_asignada': linea,
                'supervisor': supervisor,
                'vehiculo': vehiculo,
                'activa': activa,
                'observaciones': cuadrilla_data['observaciones'],
            }
            # Detectar y completar campos auditoría B3 si existen en el modelo.
            modelo_fields = {f.name for f in Cuadrilla._meta.get_fields()}
            if 'motivo_desactivacion' in modelo_fields:
                create_kwargs['motivo_desactivacion'] = ''
            cuadrilla = self._crear_cuadrilla_b3_safe(Cuadrilla, create_kwargs)
            self.cuadrillas_creadas += 1
        else:
            if actualizar:
                # B3: preservar histórico — si la cuadrilla está inactiva con
                # campos auditoría poblados (motivo_desactivacion, etc.), no
                # los tocamos. Solo actualizamos relaciones operativas.
                existente.linea_asignada = linea
                existente.supervisor = supervisor
                existente.vehiculo = vehiculo
                # Si la cuadrilla viene Activa en el Excel y estaba inactiva,
                # solo la reactivamos; el campo motivo_desactivacion se
                # conserva como histórico (decisión: NO limpiarlo aquí, eso
                # lo hace explícitamente la vista de reactivar de B3).
                existente.activa = activa
                if cuadrilla_data['observaciones']:
                    existente.observaciones = cuadrilla_data['observaciones']
                existente.save()
                self.cuadrillas_actualizadas += 1
            cuadrilla = existente

        # Miembros.
        for miembro_data in miembros:
            self._agregar_miembro(cuadrilla, miembro_data)

    def _crear_cuadrilla_b3_safe(self, modelo, kwargs):
        """Crea Cuadrilla manejando el caso pre-merge B3.

        Si el schema de BD tiene columnas auditoría B3 (motivo_desactivacion,
        fecha_desactivacion, desactivado_por_id) como NOT NULL pero el modelo
        Python aún no las expone (worktree B4 corre antes que F4 merge B3),
        usamos raw SQL desde el inicio para evitar IntegrityError dentro de
        la transacción atómica externa.
        """
        from django.db import connection

        schema_cols = self._cuadrilla_schema_cols()
        if 'motivo_desactivacion' not in schema_cols:
            # Schema "limpio": ORM funciona normalmente.
            return modelo.objects.create(**kwargs)

        # Schema con B3: insertar via raw SQL completando audit fields vacíos.
        import uuid
        from django.utils import timezone

        new_id = uuid.uuid4()
        now = timezone.now()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO cuadrillas
                    (id, created_at, updated_at, codigo, nombre, activa,
                     observaciones, linea_asignada_id, supervisor_id,
                     vehiculo_id, fecha, motivo_desactivacion,
                     fecha_desactivacion, desactivado_por_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    str(new_id), now, now,
                    kwargs['codigo'], kwargs['nombre'], kwargs['activa'],
                    kwargs.get('observaciones', ''),
                    kwargs['linea_asignada'].id if kwargs.get('linea_asignada') else None,
                    kwargs['supervisor'].id if kwargs.get('supervisor') else None,
                    kwargs['vehiculo'].id if kwargs.get('vehiculo') else None,
                    None, '', None, None,
                ],
            )
        return modelo.objects.get(id=new_id)

    @classmethod
    def _cuadrilla_schema_cols(cls):
        """Cachea las columnas reales de la tabla cuadrillas en la BD."""
        if hasattr(cls, '_schema_cols_cache'):
            return cls._schema_cols_cache
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'cuadrillas'"
            )
            cols = {row[0] for row in cursor.fetchall()}
        cls._schema_cols_cache = cols
        return cols

    def _agregar_miembro(self, cuadrilla, miembro_data):
        from apps.cuadrillas.models import CuadrillaMiembro
        from apps.usuarios.models import Usuario

        cedula = miembro_data['cedula']
        row_num = miembro_data.get('_row_num', '?')

        if not cedula:
            self.advertencias.append(f'Fila {row_num}: miembro sin cédula, omitido')
            return

        try:
            usuario = Usuario.objects.get(documento=cedula)
        except Usuario.DoesNotExist:
            self.advertencias.append(
                f'Fila {row_num}: usuario con cédula "{cedula}" no existe, miembro omitido'
            )
            return

        rol_choice = ROL_TEXTO_A_CHOICE.get(miembro_data['cargo'].lower(), 'LINIERO_I')

        _, creado = CuadrillaMiembro.objects.get_or_create(
            cuadrilla=cuadrilla,
            usuario=usuario,
            activo=True,
            defaults={
                'rol_cuadrilla': rol_choice,
                'cargo': 'MIEMBRO',
                'costo_dia': COSTOS_POR_ROL.get(rol_choice, 0),
                'fecha_inicio': date.today(),
            },
        )
        if creado:
            self.miembros_agregados += 1

    def _resultado_error(self, msg):
        return {
            'exito': False,
            'error': msg,
            'cuadrillas_creadas': 0,
            'cuadrillas_actualizadas': 0,
            'miembros_agregados': 0,
            'advertencias': self.advertencias,
            'errores': self.errores,
            'columnas_detectadas': list(self.column_indices.keys()),
        }


class _RollbackImport(Exception):
    """Señal interna para forzar rollback de la transacción."""
    pass
