"""Tests #178 — Programación semanal de cuadrillas (Sprint A).

Issue: Indunnova16/Instelec#178

Un solo archivo cubre los 6 sub-items del Sprint A (backend puro, sin UI):

- A1: parser de bloques por celda combinada col A/D (ambos importers).
- A2: fix NOVEDADES — reset del bloque activo, registro independiente.
- A3: soporte hojas vc/C12/C16/'12 (2)'.
- A4: columna PT SAP mapeada en ProgramacionS18CuadrillaImporter.
- A5: choices MALACATERO/COORDINADOR_HSQ + warning explícito CARGO desconocido.
- A6: enlace CEDULA→PersonalCuadrilla (patrón resolver-o-crear #176 + opt-in
  crear_usuarios_faltantes #124).

Verificado dato-por-dato con openpyxl contra el Excel real del cliente
("Programación - S27.xlsx", 34 hojas, adjunto del comentario del issue):
merges de columna A/D 100% consistentes en 106 bloques de muestra; 3
excepciones reales (semanas 03/05/27) donde el heurístico sugerido por el
cliente (CARGO=CONDUCTOR cierra bloque) NO habría funcionado (bloques sin
fila CONDUCTOR, p.ej. "Apoyo IG" en semana 05) — de ahí que A1 use el RANGO
de la celda combinada como fuente de verdad, no el valor de CARGO.

Ejecutar:
  DJANGO_SETTINGS_MODULE=config.settings.dev_lite \
    venv/bin/python -m pytest apps/cuadrillas/tests_issue_178.py -v \
    -o python_files="tests_*.py test_*.py"
"""
from datetime import date
from io import BytesIO

import pytest
from openpyxl import Workbook

from apps.actividades.importers import ProgramacionSemanalImporter
from apps.actividades.models import Actividad
from apps.cuadrillas.importers import ProgramacionS18CuadrillaImporter
from apps.cuadrillas.models import (
    Cuadrilla,
    CuadrillaMiembro,
    NovedadPersonalSemana,
    PersonalCuadrilla,
)
from apps.cuadrillas.tests_s18 import S18_HEADERS, _act, _crear_linea, _crear_usuario, _miembro

# ---------------------------------------------------------------------------
# Helpers compartidos
# ---------------------------------------------------------------------------

def _build_merged_excel(bloques, sheet_name='27', banner=True):
    """Construye un Excel con celdas REALMENTE combinadas en columna A
    (numero) para cada bloque — igual al formato real de Instelec.

    `bloques`: lista de listas de filas (cada fila = 16 valores en el orden
    de `S18_HEADERS`, que es el MISMO layout de columnas que usan ambos
    importers reales: ProgramacionS18CuadrillaImporter y
    ProgramacionSemanalImporter). La primera fila de cada bloque trae
    `numero`; las siguientes deben traer `numero=None` (tal como las deja
    el merge real de Excel).
    """
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    if banner:
        ws.append(['INSTELEC SAS - NIT 890911324'])
    ws.append(S18_HEADERS)
    fila_actual = 3 if banner else 2
    for bloque in bloques:
        inicio = fila_actual
        for fila in bloque:
            ws.append(fila)
            fila_actual += 1
        fin = fila_actual - 1
        # La sección NOVEDADES real NUNCA trae columna A combinada (verificado
        # contra el Excel del cliente: el marcador 'NOVEDADES' y sus filas de
        # personal quedan sueltos, sin merge) — no generar merge para ella.
        primera_celda_a = str(bloque[0][0] or '').strip().upper() if bloque else ''
        if fin > inicio and primera_celda_a != 'NOVEDADES':
            ws.merge_cells(start_row=inicio, start_column=1, end_row=fin, end_column=1)
    out = BytesIO()
    wb.save(out)
    out.seek(0)
    return out


def _novedades_marker():
    """Fila encabezado de la sección NOVEDADES ('#'='NOVEDADES', resto None)."""
    return ['NOVEDADES'] + [None] * (len(S18_HEADERS) - 1)


def _novedad_fila(nombre, cedula, cargo='', nota=''):
    """Fila de personal dentro de NOVEDADES — la nota va en AVISOS (col M),
    igual que en el Excel real del cliente."""
    return [None, None, None, None, None, None, nombre, cedula, '', cargo, None, None, nota, '', '', '']


def _crear_cuadrilla_con_miembro(usuario, codigo_cuadrilla):
    cuadrilla, _ = Cuadrilla.objects.get_or_create(
        codigo=codigo_cuadrilla, defaults={'nombre': codigo_cuadrilla, 'activa': True}
    )
    CuadrillaMiembro.objects.create(
        cuadrilla=cuadrilla,
        usuario=usuario,
        rol_cuadrilla='LINIERO_I',
        cargo='MIEMBRO',
        costo_dia=0,
        fecha_inicio=date.today(),
        activo=True,
    )
    return cuadrilla


# ---------------------------------------------------------------------------
# A1 — Parser de bloques por celda combinada (ProgramacionS18CuadrillaImporter)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestA1BloquePorMergeCuadrillas:
    """Sub-item A1 (cuadrillas/importers.py::ProgramacionS18CuadrillaImporter)."""

    def test_happy_bloque_cierra_en_merge_exacto(self):
        _crear_linea('LN817')
        _crear_linea('LN805')
        _crear_usuario('1143246675', 'JHON JAIRO JIMENEZ')
        _crear_usuario('1004487321', 'KEINER SERRANO')
        _crear_usuario('1093293706', 'SNEYDER JEREZ')

        bloque1 = [
            _act(1, 'Servidumbre Completa', '817', date(2026, 4, 27), date(2026, 5, 3),
                 'JHON JAIRO JIMENEZ', '1143246675', 'LINIERO I', 'JT/CTA'),
            _miembro('KEINER SERRANO', '1004487321', 'LINIERO II'),
        ]
        bloque2 = [
            _act(2, 'Avisos SC', '805', date(2026, 4, 27), date(2026, 5, 3),
                 'SNEYDER JEREZ', '1093293706', 'LINIERO II', 'JT/CTA'),
        ]
        excel = _build_merged_excel([bloque1, bloque2])
        res = ProgramacionS18CuadrillaImporter().importar(excel)

        assert res['exito'] is True, res.get('error')
        assert res['cuadrillas_creadas'] == 2
        assert res['miembros_agregados'] == 3
        c1 = Cuadrilla.objects.get(codigo__endswith='SER')
        c2 = Cuadrilla.objects.get(codigo__endswith='AVI')
        assert c1.miembros.count() == 2
        assert c2.miembros.count() == 1
        # No se mezclaron: el miembro de bloque2 NO quedó en bloque1.
        assert not c1.miembros.filter(usuario__documento='1093293706').exists()

    def test_edge_bloque_sin_conductor_no_se_corta_prematuro(self):
        """Reproduce el caso real (semana 05, bloque 'Apoyo IG'): un bloque
        cuyo ÚLTIMO miembro NO tiene CARGO=CONDUCTOR. El heurístico sugerido
        por el cliente (CARGO=CONDUCTOR cierra el bloque) fallaría acá — el
        merge de columna A debe seguir siendo 100% confiable."""
        _crear_linea('LN817')
        _crear_usuario('1042438483', 'ALFONSO LOPEZ')
        _crear_usuario('1037472307', 'MANUEL ZARZA')
        _crear_usuario('1123405494', 'YEISON CRUZ')
        _crear_usuario('85202378', 'MARTIN FLOREZ')

        bloque_sin_conductor = [
            _act(11, 'Apoyo IG', '817', date(2025, 1, 26), date(2025, 1, 31),
                 'ALFONSO LOPEZ', '1042438483', 'AYUDANTE', None),
            _miembro('MANUEL ZARZA', '1037472307', 'AYUDANTE'),
            _miembro('YEISON CRUZ', '1123405494', 'AYUDANTE'),
            _miembro('MARTIN FLOREZ', '85202378', 'LINIERO II'),  # última fila, NO conductor
        ]
        excel = _build_merged_excel([bloque_sin_conductor])
        res = ProgramacionS18CuadrillaImporter().importar(excel)

        assert res['exito'] is True, res.get('error')
        assert res['cuadrillas_creadas'] == 1
        # Los 4 miembros quedan en EL MISMO bloque (no se cortó al no
        # encontrar CONDUCTOR).
        assert res['miembros_agregados'] == 4
        cuad = Cuadrilla.objects.get()
        assert cuad.miembros.count() == 4

    def test_edge_bloque_de_una_sola_fila(self):
        """Bloque de 1 sola fila no genera merge (Excel no combina un único
        cell) — debe caer al heurístico de respaldo ('#' en blanco) sin
        romper, con advertencia explícita del fallback."""
        _crear_linea('LN817')
        _crear_usuario('1143246675', 'JHON JAIRO')

        bloque_1_fila = [
            _act(1, 'Hurto', '817', date(2026, 3, 26), date(2026, 3, 29),
                 'JHON JAIRO', '1143246675', 'LINIERO I', 'JT/CTA'),
        ]
        excel = _build_merged_excel([bloque_1_fila])
        res = ProgramacionS18CuadrillaImporter().importar(excel)

        assert res['exito'] is True, res.get('error')
        assert res['cuadrillas_creadas'] == 1
        assert res['miembros_agregados'] == 1
        assert any(
            'celdas combinadas' in a or 'heurístico de respaldo' in a
            for a in res['advertencias']
        )


# ---------------------------------------------------------------------------
# A1 — Parser de bloques por celda combinada (ProgramacionSemanalImporter)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestA1BloquePorMergeActividades:
    """Sub-item A1 (actividades/importers.py::ProgramacionSemanalImporter)."""

    def test_happy_bloque_cierra_en_merge_exacto(self):
        # NOTA: ProgramacionSemanalImporter._asignar_cuadrillas SOLO lee las
        # cédulas de las filas de PERSONAL adicionales (continuación), no la
        # del encabezado de actividad (comportamiento preexistente de
        # #48/B5, ajeno a A1) — por eso cada bloque trae una fila `_miembro`
        # explícita con la cédula que sí tiene CuadrillaMiembro asociado.
        linea1 = _crear_linea_con_torre('LN817')
        linea2 = _crear_linea_con_torre('LN805')
        u1 = _crear_usuario('1143246675', 'JHON JAIRO JIMENEZ')
        u2 = _crear_usuario('1093293706', 'SNEYDER JEREZ')
        _crear_cuadrilla_con_miembro(u1, 'CUA-BLOQUE-1')
        _crear_cuadrilla_con_miembro(u2, 'CUA-BLOQUE-2')

        bloque1 = [
            _act(1, 'Servidumbre Completa', '817', date(2026, 4, 27), date(2026, 5, 3),
                 'JHON JAIRO JIMENEZ', '1143246675', 'LINIERO I', 'JT/CTA',
                 avisos='5720001'),
            _miembro('JHON JAIRO JIMENEZ', '1143246675', 'LINIERO I'),
        ]
        bloque2 = [
            _act(2, 'Avisos SC', '805', date(2026, 4, 27), date(2026, 5, 3),
                 'SNEYDER JEREZ', '1093293706', 'LINIERO II', 'JT/CTA',
                 avisos='5720002'),
            _miembro('SNEYDER JEREZ', '1093293706', 'LINIERO II'),
        ]
        excel = _build_merged_excel([bloque1, bloque2])
        res = ProgramacionSemanalImporter().importar(excel)

        assert res['exito'] is True
        assert res['actividades_creadas'] == 2
        act1 = Actividad.objects.get(aviso_sap='5720001')
        act2 = Actividad.objects.get(aviso_sap='5720002')
        assert act1.linea_id == linea1.id
        assert act2.linea_id == linea2.id
        # La cuadrilla asignada a cada actividad es la de SU PROPIO bloque.
        assert act1.cuadrillas.filter(codigo='CUA-BLOQUE-1').exists()
        assert not act1.cuadrillas.filter(codigo='CUA-BLOQUE-2').exists()
        assert act2.cuadrillas.filter(codigo='CUA-BLOQUE-2').exists()
        assert not act2.cuadrillas.filter(codigo='CUA-BLOQUE-1').exists()

    def test_edge_bloque_sin_conductor_no_mezcla_cedulas_con_el_siguiente(self):
        """Caso real (semana 05, 'Apoyo IG'): bloque sin fila CARGO=CONDUCTOR
        seguido de OTRO bloque — las cédulas del primero no deben "fugarse"
        al segundo ni viceversa."""
        _crear_linea_con_torre('LN817')
        u1 = _crear_usuario('1042438483', 'ALFONSO LOPEZ')
        u2 = _crear_usuario('85202378', 'MARTIN FLOREZ')  # último miembro, NO conductor
        u3 = _crear_usuario('9999999998', 'OTRO TRABAJADOR')  # miembro del 2do bloque
        _crear_cuadrilla_con_miembro(u1, 'CUA-APOYO-IG')
        _crear_cuadrilla_con_miembro(u2, 'CUA-APOYO-IG')
        _crear_cuadrilla_con_miembro(u3, 'CUA-SIGUIENTE')

        bloque_sin_conductor = [
            _act(11, 'Apoyo IG', '817', date(2025, 1, 26), date(2025, 1, 31),
                 'ALFONSO LOPEZ', '1042438483', 'AYUDANTE', None, avisos='5720011'),
            _miembro('MARTIN FLOREZ', '85202378', 'LINIERO II'),
        ]
        bloque_siguiente = [
            _act(12, 'Revisión', '817', date(2025, 2, 1), date(2025, 2, 3),
                 'OTRO TRABAJADOR', '9999999998', 'LINIERO I', 'JT/CTA', avisos='5720012'),
            _miembro('OTRO TRABAJADOR', '9999999998', 'LINIERO I'),
        ]
        excel = _build_merged_excel([bloque_sin_conductor, bloque_siguiente])
        res = ProgramacionSemanalImporter().importar(excel)

        assert res['exito'] is True
        act_apoyo = Actividad.objects.get(aviso_sap='5720011')
        act_siguiente = Actividad.objects.get(aviso_sap='5720012')
        assert act_apoyo.cuadrillas.filter(codigo='CUA-APOYO-IG').exists()
        assert not act_apoyo.cuadrillas.filter(codigo='CUA-SIGUIENTE').exists()
        assert act_siguiente.cuadrillas.filter(codigo='CUA-SIGUIENTE').exists()
        assert not act_siguiente.cuadrillas.filter(codigo='CUA-APOYO-IG').exists()

    def test_edge_bloque_de_una_sola_fila(self):
        _crear_linea_con_torre('LN817')
        _crear_usuario('1143246675', 'JHON JAIRO')
        bloque_1_fila = [
            _act(1, 'Hurto', '817', date(2026, 3, 26), date(2026, 3, 29),
                 'JHON JAIRO', '1143246675', 'LINIERO I', 'JT/CTA', avisos='5730001'),
        ]
        excel = _build_merged_excel([bloque_1_fila])
        res = ProgramacionSemanalImporter().importar(excel)

        assert res['exito'] is True
        assert res['actividades_creadas'] == 1
        assert Actividad.objects.filter(aviso_sap='5730001').exists()


# ---------------------------------------------------------------------------
# A2 — Fix NOVEDADES (ProgramacionS18CuadrillaImporter)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestA2NovedadesCuadrillas:
    """Sub-item A2 (cuadrillas/importers.py::ProgramacionS18CuadrillaImporter).

    Bug real confirmado por F1: al detectar NOVEDADES el importer NO
    reseteaba el bloque activo, así que el personal en vacaciones/incapacidad
    quedaba mezclado como miembro de la ÚLTIMA actividad real de la hoja.
    """

    def test_happy_novedades_no_se_atribuye_a_ultima_actividad(self):
        _crear_linea('LN817')
        _crear_usuario('1143246675', 'JHON JAIRO')

        bloque = [
            _act(1, 'Servidumbre', '817', date(2026, 4, 27), date(2026, 5, 3),
                 'JHON JAIRO', '1143246675', 'LINIERO I', 'JT/CTA'),
        ]
        novedades = [
            _novedades_marker(),
            _novedad_fila('IVAN CRUZATE', '73266972', 'LINIERO I', 'Vacaciones'),
            _novedad_fila('YESID BARRIOS', '72135975', 'LINIERO II', 'Vacaciones'),
        ]
        excel = _build_merged_excel([bloque, novedades])
        res = ProgramacionS18CuadrillaImporter().importar(excel)

        assert res['exito'] is True, res.get('error')
        assert res['cuadrillas_creadas'] == 1
        # Las 2 personas de NOVEDADES NO quedaron como miembro de la cuadrilla.
        assert res['miembros_agregados'] == 1
        assert res['novedades_creadas'] == 2
        cuad = Cuadrilla.objects.get()
        assert cuad.miembros.count() == 1
        assert not cuad.miembros.filter(usuario__documento__in=['73266972', '72135975']).exists()
        # Las novedades quedan persistidas como registro independiente.
        n1 = NovedadPersonalSemana.objects.get(cedula='73266972')
        assert n1.nombre == 'IVAN CRUZATE'
        assert n1.nota == 'Vacaciones'
        assert n1.semana == 27

    def test_edge_hoja_sin_novedades_no_rompe_import(self):
        _crear_linea('LN817')
        _crear_usuario('1143246675', 'JHON JAIRO')
        bloque = [
            _act(1, 'Servidumbre', '817', date(2026, 4, 27), date(2026, 5, 3),
                 'JHON JAIRO', '1143246675', 'LINIERO I', 'JT/CTA'),
        ]
        excel = _build_merged_excel([bloque])
        res = ProgramacionS18CuadrillaImporter().importar(excel)

        assert res['exito'] is True, res.get('error')
        assert res['cuadrillas_creadas'] == 1
        assert res['novedades_creadas'] == 0
        assert NovedadPersonalSemana.objects.count() == 0

    def test_edge_misma_cedula_en_actividad_y_novedades_ambos_persisten(self):
        """Reincorporación a mitad de semana: la misma cédula puede aparecer
        como miembro de una actividad Y en NOVEDADES — no debe haber
        deduplicación indebida entre ambos registros."""
        _crear_linea('LN817')
        _crear_usuario('1143246675', 'JHON JAIRO')
        _crear_usuario('1004487321', 'KEINER SERRANO')

        bloque = [
            _act(1, 'Servidumbre', '817', date(2026, 4, 27), date(2026, 5, 3),
                 'JHON JAIRO', '1143246675', 'LINIERO I', 'JT/CTA'),
            _miembro('KEINER SERRANO', '1004487321', 'LINIERO II'),
        ]
        novedades = [
            _novedades_marker(),
            _novedad_fila('KEINER SERRANO', '1004487321', 'LINIERO II', 'Incapacidad parcial'),
        ]
        excel = _build_merged_excel([bloque, novedades])
        res = ProgramacionS18CuadrillaImporter().importar(excel)

        assert res['exito'] is True, res.get('error')
        assert res['miembros_agregados'] == 2
        assert res['novedades_creadas'] == 1
        cuad = Cuadrilla.objects.get()
        assert cuad.miembros.filter(usuario__documento='1004487321').exists()
        assert NovedadPersonalSemana.objects.filter(cedula='1004487321').exists()


# ---------------------------------------------------------------------------
# A2 — Fix NOVEDADES (ProgramacionSemanalImporter)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestA2NovedadesActividades:
    """Sub-item A2 (actividades/importers.py::ProgramacionSemanalImporter)."""

    def test_happy_novedades_no_se_atribuye_a_ultima_actividad(self):
        _crear_linea_con_torre('LN817')
        bloque = [
            _act(1, 'Servidumbre', '817', date(2026, 4, 27), date(2026, 5, 3),
                 'JHON JAIRO', '1143246675', 'LINIERO I', 'JT/CTA', avisos='5740001'),
        ]
        novedades = [
            _novedades_marker(),
            _novedad_fila('IVAN CRUZATE', '73266972', 'LINIERO I', 'Vacaciones'),
        ]
        excel = _build_merged_excel([bloque, novedades])
        res = ProgramacionSemanalImporter().importar(excel)

        assert res['exito'] is True
        assert res['actividades_creadas'] == 1
        assert res['novedades_creadas'] == 1
        n1 = NovedadPersonalSemana.objects.get(cedula='73266972')
        assert n1.nota == 'Vacaciones'
        assert n1.semana == 27

    def test_edge_hoja_sin_novedades_no_rompe_import(self):
        _crear_linea_con_torre('LN817')
        bloque = [
            _act(1, 'Servidumbre', '817', date(2026, 4, 27), date(2026, 5, 3),
                 'JHON JAIRO', '1143246675', 'LINIERO I', 'JT/CTA', avisos='5740002'),
        ]
        excel = _build_merged_excel([bloque])
        res = ProgramacionSemanalImporter().importar(excel)

        assert res['exito'] is True
        assert res['actividades_creadas'] == 1
        assert res['novedades_creadas'] == 0

    def test_edge_misma_cedula_en_actividad_y_novedades_ambos_persisten(self):
        _crear_linea_con_torre('LN817')
        u1 = _crear_usuario('1004487321', 'KEINER SERRANO')
        _crear_cuadrilla_con_miembro(u1, 'CUA-REINCORPORA')

        bloque = [
            _act(1, 'Servidumbre', '817', date(2026, 4, 27), date(2026, 5, 3),
                 'JHON JAIRO', '1143246675', 'LINIERO I', 'JT/CTA', avisos='5740003'),
            _miembro('KEINER SERRANO', '1004487321', 'LINIERO II'),
        ]
        novedades = [
            _novedades_marker(),
            _novedad_fila('KEINER SERRANO', '1004487321', 'LINIERO II', 'Incapacidad parcial'),
        ]
        excel = _build_merged_excel([bloque, novedades])
        res = ProgramacionSemanalImporter().importar(excel)

        assert res['exito'] is True
        act = Actividad.objects.get(aviso_sap='5740003')
        assert act.cuadrillas.filter(codigo='CUA-REINCORPORA').exists()
        assert NovedadPersonalSemana.objects.filter(cedula='1004487321').exists()


# ---------------------------------------------------------------------------
# A3 — Soporte hojas vc/C12/C16/'12 (2)' (ambos importers comparten la misma
# lógica _es_hoja_semanal/SHEETS_EXCLUIR — un solo test cubre ambas clases).
# ---------------------------------------------------------------------------

class TestA3SoporteHojasVcC12C16:
    """Sub-item A3. `_es_hoja_semanal`/`SHEETS_EXCLUIR` de
    `ProgramacionS18CuadrillaImporter` (cuadrillas) y
    `ProgramacionSemanalImporter` (actividades)."""

    @pytest.mark.parametrize('importer_cls', [ProgramacionS18CuadrillaImporter, ProgramacionSemanalImporter])
    def test_happy_vc_c12_c16_parentesis_matchean(self, importer_cls):
        assert importer_cls._es_hoja_semanal('vc') is True
        assert importer_cls._es_hoja_semanal('C12') is True
        assert importer_cls._es_hoja_semanal('C16') is True
        assert importer_cls._es_hoja_semanal('12 (2)') is True
        # Casos ya soportados antes de A3, no deben regresionar.
        assert importer_cls._es_hoja_semanal('18') is True
        assert importer_cls._es_hoja_semanal('Semana 5') is True

    @pytest.mark.parametrize('importer_cls', [ProgramacionS18CuadrillaImporter, ProgramacionSemanalImporter])
    def test_edge_catalogos_siguen_excluidos(self, importer_cls):
        for nombre in ['pt-corredores', 'Hoja1', 'Hoja2', 'Hoja5', 'Sheet1', 'Resumen', 'Instrucciones']:
            assert importer_cls._es_hoja_semanal(nombre) is False, nombre


# ---------------------------------------------------------------------------
# A4 — Mapear columna PT SAP (ProgramacionS18CuadrillaImporter)
# ---------------------------------------------------------------------------

def _act_con_pt_sap(numero, actividad, linea, inicio, fin, personal, cedula, cargo,
                     rol=None, placa=None, pt_sap=''):
    """Fila S18 con PT SAP (columna O) explícito — `_act` de tests_s18 no
    expone ese campo porque no existía mapeo antes de A4."""
    return [numero, actividad, linea, '', inicio, fin, personal, cedula,
            '', cargo, rol, placa, '', '', pt_sap, '']


@pytest.mark.django_db
class TestA4PTSAPCuadrillas:
    """Sub-item A4 (cuadrillas/importers.py::ProgramacionS18CuadrillaImporter).

    Hoy PT SAP no está mapeado en absoluto — se agrega al COLUMN_MAPPINGS
    reusando el patrón _split_multi/_join_multi ya usado por AVISOS/ORDEN.
    """

    def test_happy_pt_sap_multivalor_persiste_y_reserializa_igual(self):
        _crear_linea('LN817')
        _crear_usuario('1143246675', 'JHON JAIRO')
        bloque = [
            _act_con_pt_sap(1, 'Servidumbre', '817', date(2026, 4, 27), date(2026, 5, 3),
                             'JHON JAIRO', '1143246675', 'LINIERO I', 'JT/CTA',
                             pt_sap='30001234\n30005678'),
        ]
        excel = _build_merged_excel([bloque])
        res = ProgramacionS18CuadrillaImporter().importar(excel)

        assert res['exito'] is True, res.get('error')
        cuad = Cuadrilla.objects.get()
        assert 'PT SAP: 30001234, 30005678' in cuad.observaciones

    def test_edge_pt_sap_vacio_no_rompe_import(self):
        _crear_linea('LN817')
        _crear_usuario('1143246675', 'JHON JAIRO')
        bloque = [
            _act_con_pt_sap(1, 'Servidumbre', '817', date(2026, 4, 27), date(2026, 5, 3),
                             'JHON JAIRO', '1143246675', 'LINIERO I', 'JT/CTA', pt_sap=''),
        ]
        excel = _build_merged_excel([bloque])
        res = ProgramacionS18CuadrillaImporter().importar(excel)

        assert res['exito'] is True, res.get('error')
        cuad = Cuadrilla.objects.get()
        assert 'PT SAP:' not in cuad.observaciones


# ---------------------------------------------------------------------------
# A5 — Choices MALACATERO/COORDINADOR HSQ (ProgramacionS18CuadrillaImporter)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestA5RolesNuevosCuadrillas:
    """Sub-item A5. Hoy MALACATERO/COORDINADOR HSQ caían en fallback
    silencioso a LINIERO_I; ahora clasifican correcto y un CARGO
    desconocido nuevo genera advertencia explícita (no más fallback mudo)."""

    def test_happy_malacatero_y_coordinador_hsq_clasifican_correcto(self):
        _crear_linea('LN817')
        _crear_usuario('1143246675', 'JHON JAIRO')
        _crear_usuario('72015917', 'CASIMIRO PALOMINO')
        _crear_usuario('99988877', 'PEDRO COORDINADOR')

        bloque = [
            _act(1, 'Servidumbre', '817', date(2026, 4, 27), date(2026, 5, 3),
                 'JHON JAIRO', '1143246675', 'LINIERO I', 'JT/CTA'),
            _miembro('CASIMIRO PALOMINO', '72015917', 'MALACATERO'),
            _miembro('PEDRO COORDINADOR', '99988877', 'COORDINADOR HSQ'),
        ]
        excel = _build_merged_excel([bloque])
        res = ProgramacionS18CuadrillaImporter().importar(excel)

        assert res['exito'] is True, res.get('error')
        m1 = CuadrillaMiembro.objects.get(usuario__documento='72015917')
        m2 = CuadrillaMiembro.objects.get(usuario__documento='99988877')
        assert m1.rol_cuadrilla == 'MALACATERO'
        assert m2.rol_cuadrilla == 'COORDINADOR_HSQ'
        # No cayeron al fallback silencioso.
        assert not any('no reconocido' in a for a in res['advertencias'])

    def test_edge_cargo_desconocido_genera_advertencia_explicita(self):
        _crear_linea('LN817')
        _crear_usuario('1143246675', 'JHON JAIRO')
        _crear_usuario('55544433', 'NUEVO CARGO PERSONA')

        bloque = [
            _act(1, 'Servidumbre', '817', date(2026, 4, 27), date(2026, 5, 3),
                 'JHON JAIRO', '1143246675', 'LINIERO I', 'JT/CTA'),
            _miembro('NUEVO CARGO PERSONA', '55544433', 'TOPOGRAFO JEFE'),
        ]
        excel = _build_merged_excel([bloque])
        res = ProgramacionS18CuadrillaImporter().importar(excel)

        assert res['exito'] is True, res.get('error')
        miembro = CuadrillaMiembro.objects.get(usuario__documento='55544433')
        # No falla silenciosamente: clasifica a LINIERO_I por defecto...
        assert miembro.rol_cuadrilla == 'LINIERO_I'
        # ...pero deja advertencia explícita (no más fallback mudo).
        assert any(
            'TOPOGRAFO JEFE' in a and 'no reconocido' in a
            for a in res['advertencias']
        )


# ---------------------------------------------------------------------------
# A6 — Enlace CEDULA→PersonalCuadrilla (ProgramacionS18CuadrillaImporter)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestA6EnlacePersonalCuadrilla:
    """Sub-item A6. La cédula del Excel enlaza al maestro de Colaboradores
    (PersonalCuadrilla, #176) — el rol_cuadrilla viene del maestro, no se
    re-parsea el CARGO. Cédulas legacy (Usuario sin PersonalCuadrilla, de
    antes de #176) preservan el comportamiento histórico de #124 para no
    romper cuadrillas ya en producción."""

    def test_happy_cedula_existente_en_personal_cuadrilla_enlaza(self):
        _crear_linea('LN817')
        _crear_usuario('1143246675', 'JHON JAIRO')
        PersonalCuadrilla.objects.create(
            nombre='CASIMIRO PALOMINO ARMESTO', documento='72015917',
            rol_cuadrilla='SUPERVISOR', activo=True,
        )
        bloque = [
            _act(1, 'Servidumbre', '817', date(2026, 4, 27), date(2026, 5, 3),
                 'JHON JAIRO', '1143246675', 'LINIERO I', 'JT/CTA'),
            # CARGO del Excel dice 'AYUDANTE', pero el maestro dice SUPERVISOR
            # — debe ganar el maestro (fuente de verdad, patrón #176 A4).
            _miembro('CASIMIRO PALOMINO ARMESTO', '72015917', 'AYUDANTE'),
        ]
        excel = _build_merged_excel([bloque])
        res = ProgramacionS18CuadrillaImporter().importar(excel)

        assert res['exito'] is True, res.get('error')
        miembro = CuadrillaMiembro.objects.get(usuario__documento='72015917')
        assert miembro.rol_cuadrilla == 'SUPERVISOR'
        assert res['personal_creados'] == 0

    def test_edge_cedula_no_encontrada_flag_off_advertencia_y_omite(self):
        _crear_linea('LN817')
        _crear_usuario('1143246675', 'JHON JAIRO')
        bloque = [
            _act(1, 'Servidumbre', '817', date(2026, 4, 27), date(2026, 5, 3),
                 'JHON JAIRO', '1143246675', 'LINIERO I', 'JT/CTA'),
            _miembro('DESCONOCIDO TOTAL', '11122233', 'LINIERO I'),
        ]
        excel = _build_merged_excel([bloque])
        res = ProgramacionS18CuadrillaImporter().importar(excel)

        assert res['exito'] is True, res.get('error')
        assert not PersonalCuadrilla.objects.filter(documento='11122233').exists()
        assert not CuadrillaMiembro.objects.filter(usuario__documento='11122233').exists()
        assert any(
            '11122233' in a and 'omitido' in a
            for a in res['advertencias']
        )
        assert res['personal_creados'] == 0

    def test_edge_cedula_no_encontrada_flag_on_crea_personal_cuadrilla(self):
        _crear_linea('LN817')
        _crear_usuario('1143246675', 'JHON JAIRO')
        bloque = [
            _act(1, 'Servidumbre', '817', date(2026, 4, 27), date(2026, 5, 3),
                 'JHON JAIRO', '1143246675', 'LINIERO I', 'JT/CTA'),
            _miembro('NUEVO INGRESO', '11122234', 'MALACATERO'),
        ]
        excel = _build_merged_excel([bloque])
        res = ProgramacionS18CuadrillaImporter().importar(
            excel, {'crear_usuarios_faltantes': True}
        )

        assert res['exito'] is True, res.get('error')
        assert res['personal_creados'] == 1
        personal = PersonalCuadrilla.objects.get(documento='11122234')
        assert personal.rol_cuadrilla == 'MALACATERO'
        assert personal.activo is True
        miembro = CuadrillaMiembro.objects.get(usuario__documento='11122234')
        assert miembro.rol_cuadrilla == 'MALACATERO'

    def test_legacy_usuario_sin_personal_cuadrilla_preserva_comportamiento_124(self):
        """No-regresión CRÍTICA: una cédula que YA existe como Usuario (creada
        antes de que #176 introdujera PersonalCuadrilla) pero que NUNCA se
        migró al maestro debe seguir vinculándose y clasificándose por CARGO,
        exactamente como funcionaba en #124 — A6 NO debe romper cuadrillas ya
        en producción."""
        _crear_linea('LN817')
        _crear_usuario('1143246675', 'JHON JAIRO')
        _crear_usuario('8646508', 'OMAR ZAMBRANO')  # legacy: Usuario SIN PersonalCuadrilla

        bloque = [
            _act(1, 'Servidumbre', '817', date(2026, 4, 27), date(2026, 5, 3),
                 'JHON JAIRO', '1143246675', 'LINIERO I', 'JT/CTA'),
            _miembro('OMAR ZAMBRANO', '8646508', 'CONDUCTOR'),
        ]
        excel = _build_merged_excel([bloque])
        res = ProgramacionS18CuadrillaImporter().importar(excel)

        assert res['exito'] is True, res.get('error')
        miembro = CuadrillaMiembro.objects.get(usuario__documento='8646508')
        assert miembro.rol_cuadrilla == 'CONDUCTOR'
        assert res['personal_creados'] == 0
        assert not PersonalCuadrilla.objects.filter(documento='8646508').exists()


def _crear_linea_con_torre(codigo):
    """Linea + Torre real (con lat/lon) para el importer de actividades, que
    necesita `linea.torres` para no crear un placeholder T-AUTO."""
    from decimal import Decimal

    from apps.lineas.models import Linea, Torre

    linea = Linea.objects.create(
        codigo=codigo,
        nombre=f'Línea {codigo}',
        longitud_km=Decimal('10.00'),
        tension_kv=110,
        activa=True,
    )
    Torre.objects.create(
        linea=linea,
        numero='T-001',
        tipo=Torre.TipoTorre.SUSPENSION,
        latitud=Decimal('10.0'),
        longitud=Decimal('-75.0'),
    )
    return linea
