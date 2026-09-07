"""Archivo Excel para Programación Semanal de Construcción (#225, B4)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from io import BytesIO
import re
import unicodedata
from zipfile import ZIP_DEFLATED, ZipFile

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

from apps.cuadrillas.models import PersonalCuadrilla, Vehiculo
from apps.usuarios.models import Usuario

from .models import (
    ProgramacionSemanalConstruccion,
    ProgramacionSemanalConstruccionPersonal,
    ProgramacionSemanalConstruccionVehiculo,
    ProyectoConstruccion,
    AsignacionPersonalProyectoConstruccion,
)
from .services_psc_disponibilidad import personal_elegible, validar_personal_elegible


HEADERS = (
    'Proyecto', 'Tipo Actividad', 'Sub-Actividad', 'Supervisor', 'Personal',
    'Vehículos', 'Fecha Inicio', 'Fecha Fin', 'Hora Inicio', 'Hora Fin', 'Observaciones',
)

# Contrato confirmado para la importación histórica de #225.  El archivo
# recibido trae las siete primeras columnas; las cuatro restantes solo existen
# en la exportación para conservar los datos opcionales de una programación.
HISTORICAL_HEADERS = (
    'Fecha', 'Tarea', 'Empresa', 'Cuadrilla', 'Apellidos y Nombres',
    'CARGO PRINCIPAL', 'Identificación',
)
VERTICAL_HEADERS = (
    'Fecha', 'Tarea', 'Cuadrilla', 'Personal', 'Cargo', 'Cédula',
    'Supervisor', 'Horario', 'Vehículo', 'Observaciones',
)
MAX_IMPORT_ROWS = 500


@dataclass
class ImportResult:
    created: int = 0
    errors: list[dict] = field(default_factory=list)

    @property
    def ok(self):
        return not self.errors


@dataclass(frozen=True)
class TareaMapeo:
    """Destino de una tarea histórica dentro del contrato vertical PSC."""

    tipo_actividad: str
    subactividad: str
    actividad_complementaria: str = ''


def _normalizar_tarea(value):
    """Normaliza variantes de mayúsculas, tildes y puntuación del plano legado."""
    value = unicodedata.normalize('NFKD', str(value or ''))
    value = ''.join(char for char in value if not unicodedata.combining(char))
    return re.sub(r'\s+', ' ', value.upper()).strip()


# Las tareas del plano pueden llevar contexto (torre, frente o actividad
# secundaria). El primer alias específico conserva el catálogo cerrado de PSC.
TAREA_ALIASES = (
    ('AHUYENTAMIENTO', 'PRELIMINARES', 'Ahuyentamiento'),
    ('FAUNA', 'PRELIMINARES', 'Fauna y Flora'),
    ('FLORA', 'PRELIMINARES', 'Fauna y Flora'),
    ('ARQUEOLOG', 'PRELIMINARES', 'Arqueología'),
    ('REPLANTEO', 'PRELIMINARES', 'Replanteo'),
    ('LIBERACION', 'PRELIMINARES', 'Liberación Predial'),
    ('SEMÁFORO', 'PRELIMINARES', 'Semáforos'),
    ('SEMAFORO', 'PRELIMINARES', 'Semáforos'),
    ('ACCESO', 'PRELIMINARES', 'Accesos'),
    ('CERRAMIENTO', 'OBRA_CIVIL', 'Cerramiento'),
    ('EXCAVACION', 'OBRA_CIVIL', 'Excavación'),
    ('SOLADO', 'OBRA_CIVIL', 'Solado'),
    ('ACERO', 'OBRA_CIVIL', 'Acero'),
    ('VACIADO', 'OBRA_CIVIL', 'Vaciado'),
    ('COMPACTACION', 'OBRA_CIVIL', 'Compactación'),
    ('CUNETA', 'OBRA_CIVIL', 'Obras de Protección (Cunetas, Trinchos)'),
    ('TRINCHO', 'OBRA_CIVIL', 'Obras de Protección (Cunetas, Trinchos)'),
    ('PRE-ARMAD', 'MONTAJE', 'Pre-armada'),
    ('PREARMAD', 'MONTAJE', 'Pre-armada'),
    ('ESTRUCTURA EN SITIO', 'MONTAJE', 'Estructura en Sitio'),
    ('TORRE MONTADA', 'MONTAJE', 'Torre Montada'),
    ('PUESTA A TIERRA', 'MONTAJE', 'Sistemas de Puesta a Tierra'),
    ('PINTURA', 'MONTAJE', 'Pintura'),
    ('RIEGA MANILA', 'TENDIDO', 'Riega Manila'),
    ('RIEGA GUAYA', 'TENDIDO', 'Riega Guayas'),
    ('TENDIDO CONDUCTOR', 'TENDIDO', 'Tendido Conductor'),
    ('TENDIDO FIBRA', 'TENDIDO', 'Tendido Fibra OPGW'),
    ('EMPALME', 'TENDIDO', 'Empalmes'),
)


def mapear_tarea(tarea):
    """Resuelve una ``Tarea`` del plano a tipo/subactividad PSC.

    Una tarea no catalogada no se pierde: se conserva como actividad
    complementaria para que el histórico pueda importarse sin inventar un
    catálogo cerrado que el cliente no confirmó.
    """
    descripcion = str(tarea or '').strip()
    if not descripcion:
        raise ValidationError('Tarea es obligatoria.')
    normalizada = _normalizar_tarea(descripcion)
    for alias, tipo_actividad, subactividad in TAREA_ALIASES:
        if _normalizar_tarea(alias) in normalizada:
            return TareaMapeo(tipo_actividad, subactividad)
    return TareaMapeo(
        ProgramacionSemanalConstruccion.TipoActividad.COMPLEMENTARIAS,
        descripcion,
        descripcion,
    )


def _workbook_response(rows=()):
    book = Workbook()
    sheet = book.active
    sheet.title = 'Programación semanal'
    sheet.append(HEADERS)
    for cell in sheet[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='1D4ED8')
    sheet.freeze_panes = 'A2'
    sheet.auto_filter.ref = f'A1:K{max(2, len(rows) + 1)}'
    for row in rows:
        sheet.append(row)
    for column, width in {'A': 28, 'B': 24, 'C': 30, 'D': 28, 'E': 35, 'F': 25,
                          'G': 14, 'H': 14, 'I': 12, 'J': 12, 'K': 40}.items():
        sheet.column_dimensions[column].width = width
    output = BytesIO()
    book.save(output)
    output.seek(0)
    return output


def _vertical_workbook_response(rows=()):
    """Construye el XLSX vertical contratado para la programación histórica."""
    book = Workbook()
    # El contrato distingue una fecha de un datetime al reabrir el archivo.
    book.iso_dates = True
    sheet = book.active
    sheet.title = 'Programación semanal'
    sheet.append(VERTICAL_HEADERS)
    for cell in sheet[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='1D4ED8')
    sheet.freeze_panes = 'A2'
    sheet.auto_filter.ref = f'A1:J{max(2, len(rows) + 1)}'
    for row in rows:
        sheet.append(row)
    for column, width in {'A': 14, 'B': 30, 'C': 24, 'D': 35, 'E': 24,
                          'F': 18, 'G': 30, 'H': 18, 'I': 16, 'J': 40}.items():
        sheet.column_dimensions[column].width = width
    output = BytesIO()
    book.save(output)
    return _preservar_celdas_texto_vacias(output)


def _preservar_celdas_texto_vacias(output):
    """Conserva ``''`` como texto al reabrir el XLSX, no como ``None``.

    openpyxl escribe una cadena vacía como ``<c t="inlineStr"></c>`` y al
    cargarla la interpreta como ``None``. El formato vertical distingue los
    opcionales explícitamente vacíos, por lo que se completa el nodo inline
    string vacío que XLSX admite de forma nativa.
    """
    output.seek(0)
    normalized = BytesIO()
    with ZipFile(output) as source, ZipFile(normalized, 'w', ZIP_DEFLATED) as target:
        for info in source.infolist():
            content = source.read(info.filename)
            if info.filename.startswith('xl/worksheets/'):
                content = re.sub(
                    rb'(<c\b[^>]*\bt="inlineStr")></c>',
                    rb'\1><is><t></t></is></c>',
                    content,
                )
            target.writestr(info, content)
    normalized.seek(0)
    return normalized


def plantilla_programacion_semanal():
    """Devuelve la plantilla XLSX con las once columnas contratadas."""
    return _workbook_response()


def exportar_programacion_semanal():
    """Exporta las programaciones en filas verticales agrupadas por cuadrilla."""
    programaciones = ProgramacionSemanalConstruccion.objects.select_related(
        'proyecto', 'supervisor',
    ).prefetch_related(
        'asignaciones_personal__personal__rol_cuadrilla',
        'asignaciones_vehiculo__vehiculo',
    ).order_by('fecha_inicio', 'cuadrilla', 'pk')
    rows = []
    for item in programaciones:
        # openpyxl serializa los ``datetime`` con formato de fecha/hora y luego
        # los vuelve a entregar como datetime. El contrato de la exportación
        # vertical es una fecha pura, incluso para registros legacy.
        fecha = item.fecha_inicio.date() if isinstance(item.fecha_inicio, datetime) else item.fecha_inicio
        asignaciones = sorted(
            item.asignaciones_personal.all(), key=lambda asignacion: (
                asignacion.personal.nombre.casefold(), asignacion.personal.documento,
            ),
        )
        vehiculos = ', '.join(sorted(
            asignacion.vehiculo.placa for asignacion in item.asignaciones_vehiculo.all()
        ))
        supervisor = item.supervisor.get_full_name() if item.supervisor else ''
        if item.hora_inicio and item.hora_fin:
            horario = f'{item.hora_inicio:%H:%M} - {item.hora_fin:%H:%M}'
        else:
            horario = ''
        tarea = item.actividad_complementaria or item.subactividad or ''
        encabezado = (
            fecha, tarea, item.cuadrilla or '', supervisor or '', horario or '',
            vehiculos or '', item.observaciones or '',
        )
        if not asignaciones:
            rows.append((*encabezado[:3], '', '', '', *encabezado[3:]))
            continue
        for index, asignacion in enumerate(asignaciones):
            personal = asignacion.personal
            cargo = personal.get_rol_cuadrilla_display()
            if index == 0:
                rows.append((
                    encabezado[0], encabezado[1], encabezado[2], personal.nombre,
                    cargo, personal.documento, encabezado[3], encabezado[4],
                    encabezado[5], encabezado[6],
                ))
            else:
                rows.append((
                    '', '', '', personal.nombre, cargo, personal.documento,
                    '', '', '', '',
                ))
    return _vertical_workbook_response(rows)


def _as_date(value, field_name):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        for pattern in ('%Y-%m-%d', '%d/%m/%Y'):
            try:
                return datetime.strptime(value.strip(), pattern).date()
            except ValueError:
                continue
    raise ValidationError(f'{field_name} debe ser una fecha válida (AAAA-MM-DD).')


def _as_time(value, field_name):
    if value in (None, ''):
        return None
    if isinstance(value, datetime):
        return value.time().replace(second=0, microsecond=0)
    if isinstance(value, time):
        return value.replace(second=0, microsecond=0)
    if isinstance(value, str):
        try:
            return time.fromisoformat(value.strip())
        except ValueError:
            pass
    raise ValidationError(f'{field_name} debe ser una hora válida (HH:MM).')


def _tokens(value):
    return [part.strip() for part in str(value or '').split(',') if part.strip()]


def _one(queryset, value, description):
    matches = list(queryset)
    if not matches:
        raise ValidationError(f'{description} "{value}" no existe.')
    if len(matches) > 1:
        raise ValidationError(f'{description} "{value}" es ambiguo; use un identificador único.')
    return matches[0]


def _tipo(value):
    normalized = str(value or '').strip().casefold()
    for code, label in ProgramacionSemanalConstruccion.TipoActividad.choices:
        if normalized in (code.casefold(), label.casefold()):
            return code
    raise ValidationError('Tipo Actividad no es válido.')


def _parse_row(row):
    proyecto_nombre, tipo, subactividad, supervisor, personal, vehiculos, inicio, fin, hora_inicio, hora_fin, observaciones = row
    proyecto = _one(ProyectoConstruccion.objects.filter(nombre__iexact=str(proyecto_nombre or '').strip()), proyecto_nombre, 'Proyecto')
    fecha_inicio, fecha_fin = _as_date(inicio, 'Fecha Inicio'), _as_date(fin, 'Fecha Fin')
    if fecha_fin < fecha_inicio:
        raise ValidationError('Fecha Fin no puede ser anterior a Fecha Inicio.')
    inicio_hora, fin_hora = _as_time(hora_inicio, 'Hora Inicio'), _as_time(hora_fin, 'Hora Fin')
    if fecha_inicio == fecha_fin and inicio_hora and fin_hora and fin_hora <= inicio_hora:
        raise ValidationError('Hora Fin debe ser posterior a Hora Inicio.')
    tipo_actividad = _tipo(tipo)
    subactividad = str(subactividad or '').strip()
    if tipo_actividad == ProgramacionSemanalConstruccion.TipoActividad.COMPLEMENTARIAS:
        if not subactividad:
            raise ValidationError('Sub-Actividad es obligatoria para actividades complementarias.')
        actividad_complementaria = subactividad
    elif not subactividad:
        raise ValidationError('Sub-Actividad es obligatoria.')
    else:
        actividad_complementaria = ''
    supervisor = str(supervisor or '').strip()
    supervisor_obj = _one(Usuario.objects.filter(email__iexact=supervisor), supervisor, 'Supervisor') if supervisor else None
    people = []
    for token in _tokens(personal):
        people.append(_one(PersonalCuadrilla.objects.filter(documento__iexact=token), token, 'Personal'))
    if len({str(person.pk) for person in people}) != len(people):
        raise ValidationError('Personal contiene una persona repetida.')
    vehicle_objects = [_one(Vehiculo.objects.filter(placa__iexact=token), token, 'Vehículo') for token in _tokens(vehiculos)]
    if len({str(vehicle.pk) for vehicle in vehicle_objects}) != len(vehicle_objects):
        raise ValidationError('Vehículos contiene una placa repetida.')
    return {
        'proyecto': proyecto, 'tipo_actividad': tipo_actividad, 'subactividad': subactividad,
        'actividad_complementaria': actividad_complementaria, 'supervisor': supervisor_obj,
        'personal': people, 'vehiculos': vehicle_objects, 'fecha_inicio': fecha_inicio,
        'fecha_fin': fecha_fin, 'hora_inicio': inicio_hora, 'hora_fin': fin_hora,
        'observaciones': str(observaciones or '').strip(),
    }


def _historical_headers_match(header):
    """Acepta las siete columnas del plano, aunque Excel conserve vacías A:K."""
    return (
        tuple(header[:len(HISTORICAL_HEADERS)]) == HISTORICAL_HEADERS
        and all(value in (None, '') for value in header[len(HISTORICAL_HEADERS):])
    )


def _historical_person(documento, nombre, numero):
    documento = str(documento or '').strip()
    if not documento:
        raise ValidationError('Identificación es obligatoria.')
    person = _one(
        PersonalCuadrilla.objects.filter(documento__iexact=documento), documento, 'Personal',
    )
    # El documento es la identidad contractual. El nombre queda en el XLSX como
    # referencia humana y puede haber variado (segundo apellido, tildes) desde
    # que se cargó la programación histórica.
    return person


def _parse_historical_rows(data_rows, proyecto):
    """Convierte el plano con celdas combinadas en cabeceras PSC por cuadrilla.

    El plano real repite sólo el integrante: Fecha, Tarea y Cuadrilla quedan
    vacías en las filas siguientes del mismo bloque. Por eso se propagan hacia
    abajo y cada combinación Fecha+Cuadrilla se persiste como una programación.
    """
    result = ImportResult()
    if proyecto is None:
        result.errors.append({
            'row': 0,
            'error': 'Seleccione el proyecto al que corresponde el plano histórico.',
        })
        return [], result

    context = {'fecha': None, 'tarea': '', 'empresa': '', 'cuadrilla': ''}
    groups = {}
    for numero, row in data_rows:
        if len(row) < len(HISTORICAL_HEADERS):
            result.errors.append({'row': numero, 'error': 'La fila no contiene las 7 columnas históricas requeridas.'})
            continue
        fecha, tarea, empresa, cuadrilla, nombre, cargo, documento = row[:len(HISTORICAL_HEADERS)]
        if fecha not in (None, ''):
            try:
                context['fecha'] = _as_date(fecha, 'Fecha')
            except ValidationError as exc:
                result.errors.append({'row': numero, 'error': '; '.join(exc.messages)})
                context['fecha'] = None
        if tarea not in (None, ''):
            context['tarea'] = str(tarea).strip()
        if empresa not in (None, ''):
            context['empresa'] = str(empresa).strip()
        if cuadrilla not in (None, ''):
            context['cuadrilla'] = str(cuadrilla).strip()
        if not any(value not in (None, '') for value in (nombre, cargo, documento)):
            continue
        if not context['fecha'] or not context['tarea'] or not context['cuadrilla']:
            result.errors.append({
                'row': numero,
                'error': 'La fila necesita Fecha, Tarea y Cuadrilla propias o heredadas del bloque anterior.',
            })
            continue
        try:
            person = _historical_person(documento, nombre, numero)
            mapeo = mapear_tarea(context['tarea'])
        except ValidationError as exc:
            result.errors.append({'row': numero, 'error': '; '.join(exc.messages)})
            continue
        key = (context['fecha'], context['cuadrilla'])
        group = groups.get(key)
        if group is None:
            group = {
                'row': numero,
                'proyecto': proyecto,
                'cuadrilla': context['cuadrilla'],
                'tipo_actividad': mapeo.tipo_actividad,
                'subactividad': mapeo.subactividad,
                'actividad_complementaria': mapeo.actividad_complementaria,
                'fecha_inicio': context['fecha'],
                'fecha_fin': context['fecha'],
                'hora_inicio': None,
                'hora_fin': None,
                'supervisor': None,
                'observaciones': f"Empresa informada: {context['empresa']}" if context['empresa'] else '',
                'personal': [],
            }
            groups[key] = group
        elif (
            group['tipo_actividad'], group['subactividad'], group['actividad_complementaria'],
        ) != (mapeo.tipo_actividad, mapeo.subactividad, mapeo.actividad_complementaria):
            result.errors.append({
                'row': numero,
                'error': 'Fecha y Cuadrilla ya están asociadas a otra Tarea; sepárelas en cuadrillas distintas.',
            })
            continue
        if any(existing.pk == person.pk for _, existing in group['personal']):
            result.errors.append({'row': numero, 'error': f'Personal {person.documento} está repetido en la cuadrilla.'})
            continue
        group['personal'].append((numero, person))
    return list(groups.values()), result


def _validar_personal_historico(group):
    """Valida vigencia histórica, sin exigir que el excolaborador siga activo hoy."""
    fecha = group['fecha_inicio']
    for numero, person in group['personal']:
        aprobado = AsignacionPersonalProyectoConstruccion.objects.filter(
            proyecto=group['proyecto'], personal=person, fecha_inicio__lte=fecha,
        ).filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha)).exists()
        vigente = (
            (person.activo or person.fecha_salida is not None)
            and (person.fecha_ingreso is None or person.fecha_ingreso <= fecha)
            and (person.fecha_salida is None or person.fecha_salida >= fecha)
        )
        ocupado = ProgramacionSemanalConstruccionPersonal.objects.filter(
            personal=person,
            programacion__fecha_inicio__lte=fecha,
            programacion__fecha_fin__gte=fecha,
        ).exists()
        if not aprobado or not vigente or ocupado:
            detail = 'sin aprobación vigente en el proyecto' if not aprobado else (
                'fuera de vigencia laboral para la fecha' if not vigente else 'ya programado para la fecha'
            )
            raise ValidationError(f'Fila {numero}: Personal {person.documento} {detail}.')


def _importar_historico(data_rows, proyecto):
    groups, result = _parse_historical_rows(data_rows, proyecto)
    if result.errors:
        return result
    if not groups:
        result.errors.append({'row': 0, 'error': 'El archivo no contiene programaciones para importar.'})
        return result
    occupied = {}
    for group in groups:
        for numero, person in group['personal']:
            for other_date, other_row in occupied.get(person.pk, []):
                if group['fecha_inicio'] == other_date:
                    result.errors.append({'row': numero, 'error': f'Personal {person.documento} se cruza con la fila {other_row}.'})
            occupied.setdefault(person.pk, []).append((group['fecha_inicio'], numero))
    if result.errors:
        return result
    try:
        with transaction.atomic():
            for group in groups:
                _validar_personal_historico(group)
                people = [person for _, person in group['personal']]
                fields = {key: value for key, value in group.items() if key not in ('row', 'personal')}
                programacion = ProgramacionSemanalConstruccion.objects.create(**fields)
                ProgramacionSemanalConstruccionPersonal.objects.bulk_create([
                    ProgramacionSemanalConstruccionPersonal(programacion=programacion, personal=person)
                    for person in people
                ])
    except ValidationError as exc:
        result.errors.append({'row': 0, 'error': '; '.join(exc.messages)})
        return result
    result.created = len(groups)
    return result


def importar_programacion_semanal(uploaded_file, proyecto_historico=None):
    """Valida todo el XLSX y persiste sus filas en una única transacción."""
    result = ImportResult()
    # El cap de filas se aplica AL LEER, no después: materializar el archivo
    # entero con `list(...)` anula el streaming de `read_only=True` y un XLSX
    # de pocos MB con millones de filas (zip-bomb) tumbaba el contenedor por
    # OOM antes de llegar a la validación de `MAX_IMPORT_ROWS`.
    try:
        workbook = load_workbook(uploaded_file, read_only=True, data_only=True)
        sheet = workbook.active
        rows = []
        for row in sheet.iter_rows(values_only=True):
            rows.append(row)
            if len(rows) > MAX_IMPORT_ROWS + 1:  # +1 por la fila de encabezado
                result.errors.append({
                    'row': 0,
                    'error': f'El archivo supera el máximo de {MAX_IMPORT_ROWS} filas.',
                })
                return result
    except Exception as exc:
        result.errors.append({'row': 0, 'error': f'No se pudo leer el archivo XLSX: {exc}'})
        return result
    if not rows:
        result.errors.append({'row': 1, 'error': 'El archivo no contiene encabezados.'})
        return result
    data_rows = [(number, row) for number, row in enumerate(rows[1:], start=2) if any(value not in (None, '') for value in row)]
    if not data_rows:
        result.errors.append({'row': 0, 'error': 'El archivo no contiene programaciones para importar.'})
        return result
    if len(data_rows) > MAX_IMPORT_ROWS:
        result.errors.append({'row': 0, 'error': f'El archivo supera el máximo de {MAX_IMPORT_ROWS} filas.'})
        return result
    if _historical_headers_match(rows[0]):
        return _importar_historico(data_rows, proyecto_historico)
    if tuple(rows[0]) != HEADERS:
        result.errors.append({
            'row': 1,
            'error': 'Las columnas deben coincidir con la plantilla descargada o con el plano histórico de 7 columnas.',
        })
        return result
    parsed = []
    for number, row in data_rows:
        if len(row) != len(HEADERS):
            result.errors.append({'row': number, 'error': 'La fila no contiene las 11 columnas requeridas.'})
            continue
        try:
            parsed.append((number, _parse_row(row)))
        except ValidationError as exc:
            result.errors.append({'row': number, 'error': '; '.join(exc.messages)})
    occupied = {}
    for number, item in parsed:
        for person in item['personal']:
            for other_start, other_end, other_row in occupied.get(person.pk, []):
                if item['fecha_inicio'] <= other_end and item['fecha_fin'] >= other_start:
                    result.errors.append({'row': number, 'error': f'Personal {person.documento} se cruza con la fila {other_row}.'})
            occupied.setdefault(person.pk, []).append((item['fecha_inicio'], item['fecha_fin'], number))

    # Los cruces dentro del mismo archivo son deterministas y deben informarse
    # antes de consultar disponibilidad persistida: de otro modo una regla de
    # elegibilidad externa oculta la fila conflictiva que el usuario debe editar.
    if result.errors:
        return result

    for number, item in parsed:
        eligible_ids = set(personal_elegible(item['proyecto'].pk, item['fecha_inicio'], item['fecha_fin']).values_list('pk', flat=True))
        ineligible = [person.documento for person in item['personal'] if person.pk not in eligible_ids]
        if ineligible:
            result.errors.append({'row': number, 'error': 'Personal no elegible o ya ocupado: ' + ', '.join(ineligible)})
    if result.errors:
        return result
    # La elegibilidad ya se validó arriba, pero se revalida dentro de la
    # transacción por si otra sesión asignó a esa persona entremedio (TOCTOU).
    # Si eso pasa, la excepción debe volverse un error de fila reportable —
    # dejarla escapar daba un 500 en vez del reporte que la pantalla espera.
    try:
        with transaction.atomic():
            for numero, item in parsed:
                people, vehicles = item.pop('personal'), item.pop('vehiculos')
                programacion = ProgramacionSemanalConstruccion.objects.create(**item)
                validar_personal_elegible(programacion, [person.pk for person in people])
                ProgramacionSemanalConstruccionPersonal.objects.bulk_create([
                    ProgramacionSemanalConstruccionPersonal(programacion=programacion, personal=person)
                    for person in people
                ])
                ProgramacionSemanalConstruccionVehiculo.objects.bulk_create([
                    ProgramacionSemanalConstruccionVehiculo(programacion=programacion, vehiculo=vehicle)
                    for vehicle in vehicles
                ])
    except ValidationError as exc:
        result.errors.append({
            'row': numero,
            'error': 'La disponibilidad cambió mientras se importaba: '
                     + '; '.join(exc.messages),
        })
        return result
    result.created = len(parsed)
    return result
