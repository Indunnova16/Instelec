from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from openpyxl import load_workbook

from apps.construccion.excel_psc import (
    HEADERS,
    HISTORICAL_HEADERS,
    VERTICAL_HEADERS,
    exportar_programacion_semanal,
    importar_programacion_semanal,
    mapear_tarea,
)
from apps.construccion.models import (
    AsignacionPersonalProyectoConstruccion,
    ProgramacionSemanalConstruccion,
    ProgramacionSemanalConstruccionPersonal,
    ProgramacionSemanalConstruccionVehiculo,
    ProyectoConstruccion,
)
from apps.contratos.models import Contrato
from apps.cuadrillas.models import Cargo, PersonalCuadrilla, Vehiculo


@pytest.fixture
def excel_data(db):
    contrato = Contrato.objects.create(codigo='PSC-XLSX', nombre='Contrato XLSX', unidad_negocio='CONSTRUCCION')
    proyecto = ProyectoConstruccion.objects.create(contrato=contrato, nombre='Proyecto XLSX')
    cargo, _ = Cargo.objects.get_or_create(codigo='PSC-XLSX', defaults={'nombre': 'Operario XLSX'})
    persona = PersonalCuadrilla.objects.create(
        nombre='Ana XLSX', documento='PSC-XLSX-1', rol_cuadrilla=cargo, area='CONSTRUCCION',
        salario_base=Decimal('9000.00'),
    )
    AsignacionPersonalProyectoConstruccion.objects.create(proyecto=proyecto, personal=persona, fecha_inicio=date(2024, 1, 1))
    vehiculo = Vehiculo.objects.create(placa='XLSX225')
    return proyecto, persona, vehiculo


def _file(rows):
    from openpyxl import Workbook
    book = Workbook()
    sheet = book.active
    sheet.append(HEADERS)
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    book.save(output)
    output.seek(0)
    output.name = 'programacion.xlsx'
    return output


def _row(proyecto, persona='', vehiculo='', **overrides):
    values = [proyecto.nombre, 'Obra Civil', 'Excavación', '', persona, vehiculo,
              '2026-08-17', '2026-08-21', '07:00', '16:00', 'Importación test']
    mapping = dict(zip(HEADERS, values))
    mapping.update(overrides)
    return [mapping[key] for key in HEADERS]


def _historical_file(rows):
    from openpyxl import Workbook
    book = Workbook()
    sheet = book.active
    sheet.append(HISTORICAL_HEADERS)
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    book.save(output)
    output.seek(0)
    output.name = 'programacion_historica.xlsx'
    return output


def _segunda_persona(proyecto):
    cargo, _ = Cargo.objects.get_or_create(codigo='PSC-XLSX-2', defaults={'nombre': 'Ayudante XLSX'})
    persona = PersonalCuadrilla.objects.create(
        nombre='Beto XLSX', documento='PSC-XLSX-2', rol_cuadrilla=cargo, area='CONSTRUCCION',
        salario_base=Decimal('6000.00'),
    )
    AsignacionPersonalProyectoConstruccion.objects.create(
        proyecto=proyecto, personal=persona, fecha_inicio=date(2024, 1, 1),
    )
    return persona


@pytest.mark.django_db
def test_http_get_xlsx(admin_user, client):
    client.force_login(admin_user)
    response = client.get(reverse('construccion:psc_plantilla_excel'))
    assert response.status_code == 200
    assert response['Content-Type'].startswith('application/vnd.openxmlformats-officedocument')
    assert tuple(next(load_workbook(BytesIO(b''.join(response.streaming_content))).active.values)) == HEADERS


@pytest.mark.django_db
def test_importador_historico_renderiza_selector_de_proyecto(admin_user, client, excel_data):
    proyecto, _, _ = excel_data
    client.force_login(admin_user)
    response = client.get(reverse('construccion:psc_importar_excel'))
    content = response.content.decode()
    assert response.status_code == 200
    assert 'id="psc-proyecto-historico"' in content
    assert proyecto.nombre in content
    assert 'El archivo no identifica el proyecto de forma confiable' in content


@pytest.mark.django_db
def test_exportar_xlsx_incluye_trece_columnas_verticales(admin_user, client, excel_data):
    client.force_login(admin_user)
    response = client.get(reverse('construccion:psc_exportar_excel'))
    assert response.status_code == 200
    assert tuple(next(load_workbook(BytesIO(b''.join(response.streaming_content))).active.values)) == VERTICAL_HEADERS


@pytest.mark.django_db
def test_exportacion_vertical_agrupa_personal_y_deja_opcionales_vacios(excel_data):
    proyecto, persona, vehiculo = excel_data
    segunda = _segunda_persona(proyecto)
    programacion = ProgramacionSemanalConstruccion.objects.create(
        proyecto=proyecto,
        cuadrilla='Obra Civil 1',
        tipo_actividad='OBRA_CIVIL',
        subactividad='Excavación',
        fecha_inicio=date(2025, 12, 1),
        fecha_fin=date(2025, 12, 1),
    )
    # Se crean directo (no vía `construir_asignacion_presupuestada`), por lo
    # que quedan sin snapshot de tarifa -- Tarifa/Día vacía es el
    # comportamiento correcto para este caso legacy/manual.
    ProgramacionSemanalConstruccionPersonal.objects.create(programacion=programacion, personal=segunda)
    ProgramacionSemanalConstruccionPersonal.objects.create(programacion=programacion, personal=persona)
    ProgramacionSemanalConstruccionVehiculo.objects.create(programacion=programacion, vehiculo=vehiculo)

    sheet = load_workbook(exportar_programacion_semanal()).active
    assert tuple(sheet.iter_rows(min_row=1, max_row=1, values_only=True).__next__()) == VERTICAL_HEADERS
    rows = list(sheet.iter_rows(min_row=2, values_only=True))
    assert rows == [
        (date(2025, 12, 1), 'Excavación', 'Obra Civil 1', 'Ana XLSX', 'Operario XLSX',
         'PSC-XLSX-1', '', '', 'XLSX225', '', 'Colaborador presupuestario', '', '$0'),
        ('', '', '', 'Beto XLSX', 'Ayudante XLSX', 'PSC-XLSX-2', '', '', '', '',
         'Colaborador presupuestario', '', ''),
    ]


@pytest.mark.django_db
def test_exportacion_vertical_conserva_registro_legacy_sin_cuadrilla(excel_data):
    proyecto, persona, _ = excel_data
    legado = ProgramacionSemanalConstruccion.objects.create(
        proyecto=proyecto,
        tipo_actividad='OBRA_CIVIL',
        subactividad='Excavación',
        fecha_inicio=date(2024, 12, 1),
        fecha_fin=date(2024, 12, 1),
    )
    ProgramacionSemanalConstruccionPersonal.objects.create(programacion=legado, personal=persona)

    rows = list(load_workbook(exportar_programacion_semanal()).active.iter_rows(min_row=2, values_only=True))
    assert rows == [
        (date(2024, 12, 1), 'Excavación', '', 'Ana XLSX', 'Operario XLSX',
         'PSC-XLSX-1', '', '', '', '', 'Colaborador presupuestario', '', '$0'),
    ]


@pytest.mark.django_db
def test_exportacion_vertical_incluye_rol_tarifa_y_presupuesto_total(excel_data):
    """Cobertura #225 Sprint C: las 3 columnas nuevas con valores correctos,
    calculadas vía el snapshot de tarifa y `obtener_plan_presupuesto_para_real`
    (Sprint A/B), no recalculadas a mano en el exportador."""
    from apps.construccion.services_psc_presupuesto import construir_asignacion_presupuestada

    proyecto, persona, _ = excel_data  # salario_base=9000 -> tarifa/día=300
    segunda = _segunda_persona(proyecto)  # salario_base=6000 -> tarifa/día=200
    programacion = ProgramacionSemanalConstruccion.objects.create(
        proyecto=proyecto,
        cuadrilla='Obra Civil 2',
        tipo_actividad='OBRA_CIVIL',
        subactividad='Excavación',
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 1, 1),
    )
    ProgramacionSemanalConstruccionPersonal.objects.bulk_create([
        construir_asignacion_presupuestada(
            programacion, persona,
            rol_presupuesto=ProgramacionSemanalConstruccionPersonal.RolPresupuesto.SUPERVISOR,
        ),
        construir_asignacion_presupuestada(
            programacion, segunda,
            rol_presupuesto=ProgramacionSemanalConstruccionPersonal.RolPresupuesto.COLABORADOR,
        ),
    ])

    rows = list(load_workbook(exportar_programacion_semanal()).active.iter_rows(min_row=2, values_only=True))
    # Presupuesto total = (300 + 200) * 1 día = $500, solo en la fila de encabezado (index 0).
    assert rows == [
        (date(2026, 1, 1), 'Excavación', 'Obra Civil 2', 'Ana XLSX', 'Operario XLSX',
         'PSC-XLSX-1', '', '', '', '', 'Supervisor presupuestario', '$300', '$500'),
        ('', '', '', 'Beto XLSX', 'Ayudante XLSX', 'PSC-XLSX-2', '', '', '', '',
         'Colaborador presupuestario', '$200', ''),
    ]


@pytest.mark.django_db
def test_upload_y_reporte(admin_user, client, excel_data):
    proyecto, persona, vehiculo = excel_data
    client.force_login(admin_user)
    response = client.post(reverse('construccion:psc_importar_excel'), {
        'archivo': _file([_row(proyecto, persona.documento, vehiculo.placa)]),
        'proyecto_historico': str(proyecto.pk),
    })
    assert response.status_code == 200
    assert ProgramacionSemanalConstruccion.objects.count() == 1
    contenido = response.content.decode()
    assert 'Se importaron 1 programaciones' in contenido
    # #225 Sprint C: el reporte renderizado (no solo el resultado en memoria)
    # debe mostrar el presupuesto calculado -- 9000/30=$300/día x 5 días=$1.500,
    # única persona = supervisor presupuestario por defecto.
    assert 'Presupuesto total' in contenido
    assert '$1.500' in contenido


@pytest.mark.django_db
def test_upload_exige_proyecto_destino_explicito(admin_user, client, excel_data):
    proyecto, persona, vehiculo = excel_data
    client.force_login(admin_user)
    response = client.post(
        reverse('construccion:psc_importar_excel'),
        {'archivo': _file([_row(proyecto, persona.documento, vehiculo.placa)])},
    )
    assert response.status_code == 400
    assert 'Seleccione explícitamente el proyecto destino' in response.content.decode()
    assert ProgramacionSemanalConstruccion.objects.count() == 0


@pytest.mark.django_db
def test_upload_con_proyecto_historico_vacio_no_revienta(admin_user, client, excel_data):
    """El <select> real siempre manda el campo, vacío ('') si no se elige --
    a diferencia de omitirlo del todo (caso del test anterior). Un UUIDField
    rechaza el filtro por '' con ValidationError; sin capturarla, la vista
    devolvía 500 en vez del 400 que el usuario debe ver."""
    proyecto, persona, vehiculo = excel_data
    client.force_login(admin_user)
    response = client.post(reverse('construccion:psc_importar_excel'), {
        'archivo': _file([_row(proyecto, persona.documento, vehiculo.placa)]),
        'proyecto_historico': '',
    })
    assert response.status_code == 400
    assert 'Seleccione explícitamente el proyecto destino' in response.content.decode()
    assert ProgramacionSemanalConstruccion.objects.count() == 0


@pytest.mark.django_db
def test_importacion_atomica_si_una_fila_es_invalida(excel_data):
    proyecto, persona, vehiculo = excel_data
    result = importar_programacion_semanal(_file([
        _row(proyecto, persona.documento, vehiculo.placa),
        _row(proyecto, 'NO-EXISTE', vehiculo.placa),
    ]))
    assert not result.ok
    assert result.errors[0]['row'] == 3
    assert ProgramacionSemanalConstruccion.objects.count() == 0


@pytest.mark.django_db
def test_importar_asigna_primer_documento_como_supervisor_presupuestario(excel_data):
    """Cobertura #225 Sprint C: primer documento de 'Personal' -> SUPERVISOR,
    el resto -> COLABORADOR. Decisión de diseño confirmada con Miguel: el
    orden textual en la columna 'Personal' es el contrato, sin columnas
    nuevas en la plantilla de 11 columnas ya en uso."""
    proyecto, persona, vehiculo = excel_data
    segunda = _segunda_persona(proyecto)
    personal_csv = f'{persona.documento}, {segunda.documento}'
    result = importar_programacion_semanal(_file([
        _row(proyecto, personal_csv, vehiculo.placa),
    ]))
    assert result.ok, result.errors
    programacion = ProgramacionSemanalConstruccion.objects.get()
    asignaciones = {
        asignacion.personal_id: asignacion.rol_presupuesto
        for asignacion in programacion.asignaciones_personal.all()
    }
    assert asignaciones[persona.pk] == ProgramacionSemanalConstruccionPersonal.RolPresupuesto.SUPERVISOR
    assert asignaciones[segunda.pk] == ProgramacionSemanalConstruccionPersonal.RolPresupuesto.COLABORADOR
    # El reporte post-import (sin paso de preview separado, ver `views_psc_excel.py`)
    # expone el presupuesto total calculado para que el usuario lo vea sin
    # tener que abrir el detalle de la programación.
    assert result.presupuestos == [{
        'programacion_id': str(programacion.pk),
        'cuadrilla': programacion.subactividad,
        'fecha_inicio': programacion.fecha_inicio.isoformat(),
        'presupuesto_total': result.presupuestos[0]['presupuesto_total'],
    }]
    assert result.presupuestos[0]['presupuesto_total'].startswith('$')


@pytest.mark.django_db
def test_importar_un_solo_documento_lo_asigna_como_supervisor(excel_data):
    """Con un único documento en 'Personal', ese documento es el supervisor
    presupuestario (no queda sin supervisor)."""
    proyecto, persona, vehiculo = excel_data
    result = importar_programacion_semanal(_file([
        _row(proyecto, persona.documento, vehiculo.placa),
    ]))
    assert result.ok, result.errors
    asignacion = ProgramacionSemanalConstruccionPersonal.objects.get(personal=persona)
    assert asignacion.rol_presupuesto == ProgramacionSemanalConstruccionPersonal.RolPresupuesto.SUPERVISOR


@pytest.mark.django_db
def test_importar_sin_personal_es_error_de_validacion(excel_data):
    """Decisión #225 Sprint C: 'Personal' vacío es un error explícito, no una
    programación sin supervisor presupuestario -- consistente con la regla ya
    validada en Sprint B (exactamente 1 supervisor obligatorio)."""
    proyecto, _, vehiculo = excel_data
    result = importar_programacion_semanal(_file([
        _row(proyecto, '', vehiculo.placa),
    ]))
    assert not result.ok
    assert 'Personal es obligatorio' in result.errors[0]['error']
    assert ProgramacionSemanalConstruccion.objects.count() == 0


@pytest.mark.django_db
def test_importar_historico_asigna_primera_fila_del_bloque_como_supervisor(excel_data):
    """Mismo contrato aplicado al importador histórico (7 columnas): también
    termina en `construir_asignacion_presupuestada`, así que la primera fila
    de cada bloque Fecha+Cuadrilla es el supervisor presupuestario."""
    proyecto, persona, _ = excel_data
    segunda = _segunda_persona(proyecto)
    result = importar_programacion_semanal(_historical_file([
        [datetime(2024, 12, 3), 'Excavación', 'Axiatech / Instelec', 'Obra Civil 1', persona.nombre, 'Operario', persona.documento],
        [None, None, None, None, segunda.nombre, 'Ayudante', segunda.documento],
    ]), proyecto_historico=proyecto)
    assert result.ok, result.errors
    programacion = ProgramacionSemanalConstruccion.objects.get()
    asignaciones = {
        asignacion.personal_id: asignacion.rol_presupuesto
        for asignacion in programacion.asignaciones_personal.all()
    }
    assert asignaciones[persona.pk] == ProgramacionSemanalConstruccionPersonal.RolPresupuesto.SUPERVISOR
    assert asignaciones[segunda.pk] == ProgramacionSemanalConstruccionPersonal.RolPresupuesto.COLABORADOR
    assert result.presupuestos and result.presupuestos[0]['presupuesto_total'].startswith('$')


@pytest.mark.django_db
def test_importa_plano_historico_en_dos_grupos_y_hereda_celdas_combinadas(excel_data):
    proyecto, persona, _ = excel_data
    segunda = _segunda_persona(proyecto)
    result = importar_programacion_semanal(_historical_file([
        [datetime(2024, 12, 3), 'Excavación', 'Axiatech / Instelec', 'Obra Civil 1', persona.nombre, 'Operario', persona.documento],
        [None, None, None, None, segunda.nombre, 'Ayudante', segunda.documento],
        [datetime(2024, 12, 4), 'Replanteo topográfico', None, 'Topografía', persona.nombre, 'Operario', persona.documento],
    ]), proyecto_historico=proyecto)
    assert result.ok
    assert result.created == 2
    grupos = ProgramacionSemanalConstruccion.objects.order_by('fecha_inicio')
    assert [(grupo.fecha_inicio, grupo.cuadrilla, grupo.subactividad) for grupo in grupos] == [
        (date(2024, 12, 3), 'Obra Civil 1', 'Excavación'),
        (date(2024, 12, 4), 'Topografía', 'Replanteo'),
    ]
    assert grupos[0].asignaciones_personal.count() == 2
    assert grupos[0].observaciones == 'Empresa informada: Axiatech / Instelec'


@pytest.mark.django_db
def test_plano_historico_reporta_la_fila_y_no_persiste_parcialmente(excel_data):
    proyecto, persona, _ = excel_data
    result = importar_programacion_semanal(_historical_file([
        [datetime(2024, 12, 3), 'Excavación', None, 'Obra Civil 1', persona.nombre, 'Operario', persona.documento],
        [None, None, None, None, 'Persona inexistente', 'Ayudante', 'NO-EXISTE'],
    ]), proyecto_historico=proyecto)
    assert not result.ok
    assert result.errors == [{'row': 3, 'error': 'Personal "NO-EXISTE" no existe.'}]
    assert ProgramacionSemanalConstruccion.objects.count() == 0


@pytest.mark.django_db
def test_plano_historico_exige_proyecto_para_no_inventar_el_destino(excel_data):
    _, persona, _ = excel_data
    result = importar_programacion_semanal(_historical_file([
        [datetime(2024, 12, 3), 'Excavación', None, 'Obra Civil 1', persona.nombre, 'Operario', persona.documento],
    ]))
    assert not result.ok
    assert result.errors == [{
        'row': 0,
        'error': 'Seleccione el proyecto al que corresponde el plano histórico.',
    }]


@pytest.mark.django_db
def test_rechaza_cruce_de_personal_en_archivo(excel_data):
    proyecto, persona, vehiculo = excel_data
    result = importar_programacion_semanal(_file([
        _row(proyecto, persona.documento, vehiculo.placa),
        _row(proyecto, persona.documento, vehiculo.placa, **{'Fecha Inicio': '2026-08-20'}),
    ]))
    assert not result.ok
    assert 'se cruza con la fila 2' in result.errors[0]['error']


def test_contrato_vertical_conserva_layout_historico_y_exportacion():
    assert HISTORICAL_HEADERS == (
        'Fecha', 'Tarea', 'Empresa', 'Cuadrilla', 'Apellidos y Nombres',
        'CARGO PRINCIPAL', 'Identificación',
    )
    assert VERTICAL_HEADERS == (
        'Fecha', 'Tarea', 'Cuadrilla', 'Personal', 'Cargo', 'Cédula',
        'Supervisor', 'Horario', 'Vehículo', 'Observaciones',
        'Rol Presupuesto', 'Tarifa/Día', 'Presupuesto Total',
    )


def test_mapea_tarea_historica_con_contexto_a_catalogo_psc():
    mapeo = mapear_tarea('REPLANTEO TOPOGRÁFICO, CONTROL EXCAVACIONES T42')
    assert (mapeo.tipo_actividad, mapeo.subactividad, mapeo.actividad_complementaria) == (
        'PRELIMINARES', 'Replanteo', '',
    )


def test_tarea_no_catalogada_se_conserva_como_complementaria():
    mapeo = mapear_tarea('Tareas de oficina')
    assert mapeo.tipo_actividad == 'COMPLEMENTARIAS'
    assert mapeo.subactividad == 'Tareas de oficina'
    assert mapeo.actividad_complementaria == 'Tareas de oficina'


def test_tarea_vacia_es_error_explicito():
    with pytest.raises(ValidationError, match='Tarea es obligatoria'):
        mapear_tarea('')


@pytest.mark.django_db
def test_registro_legacy_sin_cuadrilla_permanece_compatible(excel_data):
    proyecto, _, _ = excel_data
    legado = ProgramacionSemanalConstruccion.objects.create(
        proyecto=proyecto,
        tipo_actividad='OBRA_CIVIL',
        subactividad='Excavación',
        fecha_inicio=date(2025, 12, 1),
        fecha_fin=date(2025, 12, 1),
    )
    assert legado.cuadrilla == ''
