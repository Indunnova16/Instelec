"""Issue #200 — Carga masiva de Programación Mensual: actividades creadas
pero no aparecen bajo el filtro de mes + errores de la carga ocultos.

Confirmado en vivo por Alcides subiendo su archivo real: "importación
exitosa, 43 actividades, 139 advertencias" pero al buscar una actividad
concreta no aparecía en Seguimiento/Programación Mensual.

Causa raíz 1 (fecha del filtro): `ProgramacionListView` filtra
estrictamente por mes/año, por defecto el de HOY
(`apps/actividades/views.py::ProgramacionListView.get_queryset`, L230-243).
`ProgramacionSemanalImporter` programa cada actividad con la fecha real de
la columna INICIO del Excel (`apps/actividades/importers.py`, L1337/1348) —
casi siempre un mes distinto al actual. El bug real es que
`ImportarProgramacionView.post()` redirigía SIEMPRE a
`actividades:programacion` SIN el mes/año real de lo importado
(`apps/actividades/views.py`, L440 antes del fix) — el usuario caía en el
filtro por defecto (mes de hoy) y las actividades "desaparecían".

Causa raíz 2 (errores ocultos): el resultado del importador trae detalle
real por fila en `advertencias` (hoja/fila/mensaje) y `errores` (hoja/
excepción), pero la vista sólo mostraba `len(advertencias)` — nunca el
contenido — y JAMÁS mostraba `errores` (ni el conteo). Con 139 advertencias
era imposible saber qué había fallado.

Fix:
1. `ProgramacionSemanalImporter.importar()` ahora expone `meses_tocados`
   (lista ordenada de tuplas (anio, mes) realmente tocadas).
2. La vista arma el mensaje de éxito incluyendo esos meses/años explícitos
   y, si TODO el import cayó en un único mes/año, redirige directo a
   `actividades:programacion?mes=X&anio=Y` (root cause 1).
3. La vista muestra el detalle real de `advertencias` (vía
   `_resumen_advertencias`, no sólo el conteo) y cada entrada de `errores`
   como un mensaje de error propio (root cause 2).
"""
from datetime import date
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

import pytest
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import Workbook

from apps.actividades.importers import AvisosTranselcaImporter, ProgramacionSemanalImporter
from apps.actividades.models import Actividad, TipoActividad
from apps.actividades.views import ImportarProgramacionView
from apps.lineas.models import Linea, Torre

XLSX_CONTENT_TYPE = (
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
)

HEADER_ROW = [
    '#', 'ACTIVIDAD', 'LINEA', 'TRAMO', 'INICIO', 'FIN', 'PERSONAL',
    'CEDULA', 'CELULAR', 'CARGO', 'ROL', 'PLACA', 'AVISOS', 'ORDEN',
    'PT SAP', 'Comentarios',
]


def _crear_linea(codigo, con_torres=True):
    linea = Linea.objects.create(
        codigo=codigo,
        nombre=f'Línea {codigo}',
        longitud_km=Decimal('10.00'),
        tension_kv=110,
        activa=True,
    )
    if con_torres:
        Torre.objects.create(
            linea=linea,
            numero='T-001',
            tipo=Torre.TipoTorre.SUSPENSION,
            latitud=Decimal('10.0'),
            longitud=Decimal('-75.0'),
        )
    return linea


def _fila_actividad(numero, actividad, linea, inicio, avisos, fin=None):
    return [
        numero, actividad, linea, 'Tramo A', inicio, fin, None, None, None,
        None, None, None, avisos, f'OT-{numero}', f'PT-{numero}', 'Test',
    ]


def _build_xlsx(sheet_name, filas, hoja_banner='Fecha de envio: hoy'):
    """Construye un .xlsx sintético con el formato semanal real de Instelec
    (banner en fila 1, header en fila 2, datos desde fila 3) — mismo layout
    que documenta `ProgramacionSemanalImporter`."""
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append([hoja_banner])
    ws.append(HEADER_ROW)
    for fila in filas:
        ws.append(fila)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


def _uploaded_file(nombre, contenido):
    return SimpleUploadedFile(nombre, contenido, content_type=XLSX_CONTENT_TYPE)


def _build_xlsx_mensual(filas):
    """Layout de la plantilla mensual real: hoja no numérica y fecha por fila."""
    wb = Workbook()
    ws = wb.active
    ws.title = 'Programación'
    ws.append(['Aviso SAP', 'Línea', 'Torre', 'TipoActividad', 'Fecha'])
    for fila in filas:
        ws.append(fila)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


def _crear_tipo_termografia():
    return TipoActividad.objects.create(
        codigo='TERM-200', nombre='Termografía', categoria='TERMOGRAFIA', activo=True,
    )


# ============================================================================
# 1. Unit: `_resumen_advertencias` — el detalle real reemplaza el conteo.
# ============================================================================

class TestResumenAdvertencias:
    """Antes la vista sólo mostraba `len(advertencias)`; ahora arma el
    detalle real hoja/fila/mensaje que el importador ya calculaba pero se
    descartaba por completo."""

    def test_vacio_retorna_string_vacio(self):
        assert ImportarProgramacionView._resumen_advertencias([]) == ''

    def test_incluye_hoja_fila_y_mensaje(self):
        adv = [{'hoja': '05', 'fila': 4, 'mensaje': 'línea no encontrada'}]
        resumen = ImportarProgramacionView._resumen_advertencias(adv)
        assert 'Hoja 05, fila 4: línea no encontrada' in resumen

    def test_sin_fila_usa_solo_hoja_y_mensaje(self):
        adv = [{'hoja': '05', 'mensaje': 'columnas faltantes'}]
        resumen = ImportarProgramacionView._resumen_advertencias(adv)
        assert resumen == "Hoja 05: columnas faltantes"

    def test_sin_hoja_usa_mensaje_crudo(self):
        # ej. advertencias de cédula-no-vinculada, que no traen hoja/fila
        adv = [{'mensaje': 'cédula 123 no vinculada a ninguna cuadrilla'}]
        resumen = ImportarProgramacionView._resumen_advertencias(adv)
        assert resumen == 'cédula 123 no vinculada a ninguna cuadrilla'

    def test_trunca_con_conteo_de_restantes(self):
        adv = [
            {'hoja': '05', 'fila': i, 'mensaje': f'msg {i}'}
            for i in range(20)
        ]
        resumen = ImportarProgramacionView._resumen_advertencias(adv, limite=5)
        assert resumen.count('Hoja 05, fila') == 5
        assert '... y 15 advertencia(s) más' in resumen


# ============================================================================
# 2. Importer expone `meses_tocados`.
# ============================================================================

@pytest.mark.django_db
class TestImporterExponeMesesTocados:

    def test_un_solo_mes_tocado(self):
        _crear_linea('Q1')
        contenido = _build_xlsx('05', [
            _fila_actividad(1, 'Termografia', 'Q1', date(2026, 9, 15), '9990001'),
        ])
        resultado = ProgramacionSemanalImporter().importar(
            _uploaded_file('prog.xlsx', contenido), opciones={}
        )
        assert resultado['exito'] is True
        assert resultado['actividades_creadas'] == 1
        assert resultado['meses_tocados'] == [(2026, 9)]
        actividad = Actividad.objects.get(aviso_sap='9990001')
        assert actividad.fecha_programada == date(2026, 9, 15)

    def test_dos_meses_distintos_tocados(self):
        _crear_linea('Q1')
        contenido = _build_xlsx('05', [
            _fila_actividad(1, 'Termografia', 'Q1', date(2026, 9, 15), '9990001'),
            _fila_actividad(2, 'Termografia', 'Q1', date(2026, 10, 5), '9990002'),
        ])
        resultado = ProgramacionSemanalImporter().importar(
            _uploaded_file('prog.xlsx', contenido), opciones={}
        )
        assert resultado['meses_tocados'] == [(2026, 9), (2026, 10)]


@pytest.mark.django_db
class TestPlantillaMensualIssue200:
    """Regresión del reproceso: esta plantilla cae en AvisosTranselcaImporter,
    no en la rama semanal que ya había sido corregida."""

    def test_preserva_tipo_torre_fecha_y_mes_real_por_fila(self):
        linea = _crear_linea('LN839', con_torres=False)
        Torre.objects.create(
            linea=linea, numero='T-025', tipo=Torre.TipoTorre.SUSPENSION,
            latitud=Decimal('10.0'), longitud=Decimal('-75.0'),
        )
        Torre.objects.create(
            linea=linea, numero='T-026', tipo=Torre.TipoTorre.SUSPENSION,
            latitud=Decimal('10.1'), longitud=Decimal('-75.1'),
        )
        _crear_tipo_termografia()
        contenido = _build_xlsx_mensual([
            ['QA_E2E_200_A', 'LN839', 'T025', 'Termografía', date(2030, 11, 15)],
            ['QA_E2E_200_B', 'LN839', 'T026', 'Termografía', date(2030, 11, 16)],
        ])

        resultado = AvisosTranselcaImporter().importar(_uploaded_file('mensual.xlsx', contenido))

        assert resultado['exito'] is True
        assert resultado['actividades_creadas'] == 2
        assert resultado['meses_tocados'] == [(2030, 11)]
        actividad = Actividad.objects.get(aviso_sap='QA_E2E_200_A')
        assert actividad.torre.numero == 'T-025'
        assert actividad.tipo_actividad.categoria == 'TERMOGRAFIA'
        assert actividad.fecha_programada == date(2030, 11, 15)

    def test_post_mensual_redirige_y_muestra_advertencia_con_fila(self, authenticated_client):
        linea = _crear_linea('LN839')
        _crear_tipo_termografia()
        contenido = _build_xlsx_mensual([
            ['QA_E2E_200_C', linea.codigo, 'T-001', 'Termografía', date(2030, 11, 15)],
            ['QA_E2E_200_D', linea.codigo, 'INEXISTENTE', 'Termografía', date(2030, 11, 16)],
        ])

        response = authenticated_client.post(
            reverse('actividades:importar'),
            {'archivo': _uploaded_file('mensual.xlsx', contenido)},
        )

        assert response.url == f"{reverse('actividades:programacion')}?mes=11&anio=2030"
        mensajes = ' '.join(m.message for m in get_messages(response.wsgi_request))
        assert 'Torre no encontrada' in mensajes
        assert 'fila 3' in mensajes.lower()


# ============================================================================
# 3. Vista: mensaje + redirect con mes/año + detalle de advertencias/errores.
# ============================================================================

@pytest.mark.django_db
class TestImportarProgramacionViewIssue200:

    def test_redirige_al_mes_real_cuando_es_uno_solo(self, authenticated_client):
        """Root cause 1: antes el redirect siempre caía en
        `actividades:programacion` sin filtro → mostraba el mes de HOY, no
        el mes real de las actividades importadas."""
        _crear_linea('Q1')
        contenido = _build_xlsx('05', [
            _fila_actividad(1, 'Termografia', 'Q1', date(2026, 9, 15), '9990001'),
        ])
        url = reverse('actividades:importar')
        response = authenticated_client.post(
            url, {'archivo': _uploaded_file('prog.xlsx', contenido)}
        )
        assert response.status_code == 302
        assert response.url == f"{reverse('actividades:programacion')}?mes=9&anio=2026"

        # Y la actividad realmente aparece bajo ese filtro (round-trip).
        list_response = authenticated_client.get(response.url)
        assert list_response.status_code == 200
        avisos = [a.aviso_sap for a in list_response.context['actividades']]
        assert '9990001' in avisos

    def test_no_redirige_con_mes_fijo_si_hay_varios_meses(self, authenticated_client):
        """Si el Excel programa actividades en >1 mes no hay un único mes al
        que redirigir con certeza — se mantiene el comportamiento por
        defecto, pero el mensaje (probado abajo) sigue listando todos."""
        _crear_linea('Q1')
        contenido = _build_xlsx('05', [
            _fila_actividad(1, 'Termografia', 'Q1', date(2026, 9, 15), '9990001'),
            _fila_actividad(2, 'Termografia', 'Q1', date(2026, 10, 5), '9990002'),
        ])
        url = reverse('actividades:importar')
        response = authenticated_client.post(
            url, {'archivo': _uploaded_file('prog.xlsx', contenido)}
        )
        assert response.status_code == 302
        assert response.url == reverse('actividades:programacion')

    def test_mensaje_exito_indica_mes_y_anio_explicitos(self, authenticated_client):
        """Requerimiento #1 del issue: el mensaje debe decir explícitamente
        para qué mes/año quedaron programadas las actividades."""
        _crear_linea('Q1')
        contenido = _build_xlsx('05', [
            _fila_actividad(1, 'Termografia', 'Q1', date(2026, 9, 15), '9990001'),
        ])
        url = reverse('actividades:importar')
        response = authenticated_client.post(
            url, {'archivo': _uploaded_file('prog.xlsx', contenido)}
        )
        mensajes = [m.message for m in get_messages(response.wsgi_request)]
        assert any('Septiembre 2026' in m for m in mensajes), mensajes

    def test_advertencias_muestran_detalle_real_no_solo_conteo(self, authenticated_client):
        """Root cause 2: una línea inexistente en el Excel debe generar una
        advertencia CON DETALLE visible (hoja/fila/mensaje), no sólo sumar
        al conteo genérico."""
        # Ninguna línea creada en BD → la fila con linea='NOEXISTE' dispara
        # la advertencia 'línea no encontrada'.
        contenido = _build_xlsx('05', [
            _fila_actividad(1, 'Termografia', 'NOEXISTE', date(2026, 9, 15), '9990001'),
        ])
        url = reverse('actividades:importar')
        response = authenticated_client.post(
            url, {'archivo': _uploaded_file('prog.xlsx', contenido)}
        )
        mensajes = [m.message for m in get_messages(response.wsgi_request)]
        detalle = ' '.join(mensajes)
        assert 'línea no encontrada' in detalle
        assert 'fila 3' in detalle  # header en fila 2 → primera fila de datos = 3

    def test_errores_de_hoja_ya_no_quedan_completamente_ocultos(self, authenticated_client):
        """Root cause 2: `resultado['errores']` (excepciones por hoja) antes
        NUNCA se mostraba — ni siquiera el conteo. Ahora cada error se
        muestra explícitamente."""
        _crear_linea('Q1')
        contenido = _build_xlsx('05', [
            _fila_actividad(1, 'Termografia', 'Q1', date(2026, 9, 15), '9990001'),
        ])
        resultado_canned = {
            'exito': True,
            'sheets_procesadas': ['05'],
            'actividades_creadas': 1,
            'actividades_actualizadas': 0,
            'novedades_creadas': 0,
            'errores': [{'hoja': '06', 'error': 'KeyError inesperado en fila 9'}],
            'advertencias': [],
            'resumen_por_hoja': {},
            'meses_tocados': [(2026, 9)],
        }
        with patch.object(ProgramacionSemanalImporter, 'importar', return_value=resultado_canned):
            url = reverse('actividades:importar')
            response = authenticated_client.post(
                url, {'archivo': _uploaded_file('prog.xlsx', contenido)}
            )
        mensajes = [m.message for m in get_messages(response.wsgi_request)]
        detalle = ' '.join(mensajes)
        assert 'KeyError inesperado en fila 9' in detalle
        assert "hoja '06'" in detalle
