"""B5 — ProgramacionSemanalImporter fix para Programación S18 real (issue #48).

Sofi (anasofiamc1-cpu) reportó 25-may-2026: "Permite subir el excel pero no
procesa la información correcta, no crea los avisos correspondientes" tras
adjuntar el archivo real `Programación - S18.xlsx`.

Causa raíz multifactor (ver commit del fix):
1. `_es_hoja_semanal` rechazaba nombres con `(2)` ej. `'12 (2)'` (copias
   intencionales de hoja semana en planta).
2. Filas con `#='-'` o `#='NOVEDADES'` se trataban como actividades y
   consumían el slot de `current_actividad_idx`, generando ruido en
   advertencias y dañando la lógica de personnel-grouping en algunos
   escenarios.
3. Si la línea no tiene `Torre`s aún, la actividad se perdía en silencio
   (omitida). En BD prod de Instelec algunas líneas todavía no traen sus
   torres importadas → todas las actividades de esas líneas se perdían.
4. Header esperado en `rows[1]` (fila 2) hardcoded — frágil si la planta
   inserta una fila extra de banner.

Tests:
- happy: S18 real produce ≥1 actividad por línea conocida.
- happy variante: S18 con `Torre` autocreada cuando línea no tiene torres.
- variante de nombre: hoja `'12 (2)'` ahora se procesa.
- ruido: filas con `#='-'` y `#='NOVEDADES'` se ignoran sin contarse.
- legacy preservado: archivo `Programación S06.xlsx` sigue creando
  actividades (no rompimos el path original).
"""
import pytest
from pathlib import Path

from apps.actividades.importers import ProgramacionSemanalImporter
from apps.lineas.models import Linea, Torre


FIXTURES = Path(__file__).resolve().parent.parent.parent / 'tests' / 'fixtures'
DOCUMENTACION = Path(__file__).resolve().parent.parent.parent / 'Documentacion'

S18_PATH = FIXTURES / 'Programacion_S18_real.xlsx'
S06_PATH = DOCUMENTACION / 'Programación S06.xlsx'


# Líneas que aparecen en S18 real (columna LINEA, valores separados por '/')
LINEAS_S18 = ['817', '818', '801', '802', '806', '816',
              '821', '826', '838', '805', '807', '839',
              '809', '834', '815']

# Líneas que aparecen en S06 legacy (inspeccionadas del Excel real)
LINEAS_S06 = ['5156', '5157', '733', '734', '801', '802', '803', '804',
              '805', '811', '812', '813', '815', '829', '830', '834',
              '839', '840']


def _crear_linea(codigo, con_torres=True):
    """Helper: crea Linea + Torre opcional."""
    from decimal import Decimal
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


# ============================================================================
# Tests del helper _es_hoja_semanal (puros, sin DB)
# ============================================================================

class TestEsHojaSemanal:
    """Test del clasificador estático _es_hoja_semanal."""

    def test_acepta_numero_simple(self):
        assert ProgramacionSemanalImporter._es_hoja_semanal('18') is True
        assert ProgramacionSemanalImporter._es_hoja_semanal('02') is True

    def test_acepta_con_prefijo_s(self):
        assert ProgramacionSemanalImporter._es_hoja_semanal('S18') is True
        assert ProgramacionSemanalImporter._es_hoja_semanal('s5') is True

    def test_acepta_semana_completa(self):
        assert ProgramacionSemanalImporter._es_hoja_semanal('Semana 5') is True
        assert ProgramacionSemanalImporter._es_hoja_semanal('semana_05') is True

    def test_acepta_copia_excel_con_paréntesis(self):
        """B5 fix: '12 (2)' es una hoja válida (copia que hace Excel al
        duplicar hoja semana). Antes el regex la rechazaba."""
        assert ProgramacionSemanalImporter._es_hoja_semanal('12 (2)') is True
        assert ProgramacionSemanalImporter._es_hoja_semanal('18 (1)') is True
        assert ProgramacionSemanalImporter._es_hoja_semanal('S18 (3)') is True

    def test_rechaza_excluidas(self):
        for nombre in ['vc', 'Hoja1', 'Sheet1', 'Resumen', 'Instrucciones']:
            assert ProgramacionSemanalImporter._es_hoja_semanal(nombre) is False

    def test_rechaza_texto_libre(self):
        assert ProgramacionSemanalImporter._es_hoja_semanal('Backup') is False
        assert ProgramacionSemanalImporter._es_hoja_semanal('Notas') is False


class TestEsNumeroActividad:
    """Test del filtro de filas-actividad real vs ruido."""

    def test_acepta_enteros_positivos(self):
        assert ProgramacionSemanalImporter._es_numero_actividad('1') is True
        assert ProgramacionSemanalImporter._es_numero_actividad('11') is True

    def test_rechaza_dash(self):
        """B5: el archivo S18 tiene `#='-'` en R54 (separador visual)."""
        assert ProgramacionSemanalImporter._es_numero_actividad('-') is False

    def test_rechaza_texto(self):
        """B5: R55 trae `#='NOVEDADES'` como cabecera de sección final."""
        assert ProgramacionSemanalImporter._es_numero_actividad('NOVEDADES') is False
        assert ProgramacionSemanalImporter._es_numero_actividad('Nota') is False

    def test_rechaza_vacio_y_cero(self):
        assert ProgramacionSemanalImporter._es_numero_actividad('') is False
        assert ProgramacionSemanalImporter._es_numero_actividad('0') is False


# ============================================================================
# Tests integrales contra el archivo real S18
# ============================================================================

@pytest.mark.django_db
class TestB5UploadProgramacionS18CreaActividades:
    """B5 — happy path E2E del importer con el archivo S18 real."""

    def test_b5_upload_programacion_s18_crea_actividades(self):
        """Caso principal del issue #48: el archivo real S18 debe producir
        actividades para las líneas conocidas."""
        from apps.actividades.models import Actividad

        # Setup: crear las líneas que aparecen en S18 real
        for c in LINEAS_S18:
            _crear_linea(c, con_torres=True)

        # Run
        importer = ProgramacionSemanalImporter()
        with open(S18_PATH, 'rb') as f:
            resultado = importer.importar(f, opciones={})

        # Asserts
        assert resultado['exito'] is True, (
            f"Importer falló: {resultado.get('error')}"
        )
        assert resultado['actividades_creadas'] >= 1, (
            "El archivo S18 real debería producir ≥1 actividad creada. "
            f"Resumen: {resultado}"
        )
        # Cuántas avisos esperamos: el archivo S18 tiene 11 filas-actividad
        # reales (#1..#11) con un total de ≥10 avisos expandidos.
        assert resultado['actividades_creadas'] >= 10, (
            f"S18 real tiene ≥10 avisos esperados; obtuvimos "
            f"{resultado['actividades_creadas']}. "
            f"Resumen por hoja: {resultado.get('resumen_por_hoja')}"
        )

        # Sanity check: actividades creadas en BD
        assert Actividad.objects.count() == resultado['actividades_creadas']

        # Avisos SAP esperados del archivo (subset)
        avisos_esperados = ['5720794', '5720796', '5764874']
        for aviso in avisos_esperados:
            assert Actividad.objects.filter(aviso_sap=aviso).exists(), (
                f"Aviso {aviso} debería estar creado tras importar S18"
            )

    def test_b5_filas_ruido_no_generan_advertencias_falsas(self):
        """B5 fix verifica: las filas con `#='-'` y `#='NOVEDADES'` del
        archivo S18 no producen advertencias del tipo 'sin avisos' /
        'sin línea'; se ignoran silenciosamente."""
        for c in LINEAS_S18:
            _crear_linea(c, con_torres=True)

        importer = ProgramacionSemanalImporter()
        with open(S18_PATH, 'rb') as f:
            resultado = importer.importar(f, opciones={})

        # Buscar advertencias provenientes de filas-ruido EN LA HOJA '18'
        # (la hoja '12 (2)' del mismo archivo es un mes anterior con
        # filas legítimas vacías; no es objetivo de este test).
        adv_sin_avisos_18 = [
            a for a in resultado.get('advertencias', [])
            if a.get('hoja') == '18'
            and ('sin avisos' in a.get('mensaje', '').lower()
                 or 'sin línea' in a.get('mensaje', '').lower())
        ]
        # No debería haber advertencia por las filas R54 (`-`) y R55
        # (`NOVEDADES`) de la hoja '18'; ahora se ignoran sin pasar por
        # la validación de avisos/línea.
        assert len(adv_sin_avisos_18) == 0, (
            f"Filas-ruido de hoja '18' están generando advertencias "
            f"falsas: {adv_sin_avisos_18[:3]}"
        )

    def test_b5_linea_sin_torres_crea_placeholder(self):
        """B5 fix: cuando una línea no tiene torres registradas todavía,
        el importer crea una torre placeholder T-AUTO y no pierde la
        actividad. Caso real Instelec: BD prod tiene líneas sin torres."""
        # Sólo crear la primera línea S18 SIN torre — el resto sin línea
        # (forzamos uno de los avisos a usar línea sin torres).
        linea_sin_torres = _crear_linea('817', con_torres=False)
        _crear_linea('818', con_torres=False)
        # Resto con torres
        for c in LINEAS_S18[2:]:
            _crear_linea(c, con_torres=True)

        importer = ProgramacionSemanalImporter()
        with open(S18_PATH, 'rb') as f:
            resultado = importer.importar(f, opciones={})

        assert resultado['exito'] is True
        # Verificar que se creó la torre placeholder
        torres_817 = Torre.objects.filter(linea=linea_sin_torres)
        assert torres_817.exists(), (
            "Debería haberse creado al menos una torre placeholder para "
            "línea 817 que no tenía torres"
        )
        assert torres_817.filter(numero='T-AUTO').exists(), (
            "La torre placeholder debe llamarse 'T-AUTO'"
        )

    def test_b5_avisos_individuales_se_expanden(self):
        """B5: el archivo S18 tiene avisos multivalor (separados por \\n)
        en columna AVISOS. Cada aviso debe crear una Actividad
        independiente con su `aviso_sap` propio."""
        from apps.actividades.models import Actividad

        for c in LINEAS_S18:
            _crear_linea(c, con_torres=True)

        importer = ProgramacionSemanalImporter()
        with open(S18_PATH, 'rb') as f:
            resultado = importer.importar(f, opciones={})

        # Row #1 del archivo tiene avisos '5720794\n5720796' → 2 actividades
        assert Actividad.objects.filter(aviso_sap='5720794').count() == 1
        assert Actividad.objects.filter(aviso_sap='5720796').count() == 1


# ============================================================================
# Tests de regresión: legacy S06 sigue funcionando
# ============================================================================

@pytest.mark.django_db
class TestB5LegacyS06Preservado:
    """B5 regression: el archivo S06 que YA funcionaba en prod (ver issue
    #48 comentario validación) sigue produciendo actividades tras el fix.
    """

    def test_b5_legacy_s06_sigue_creando_actividades(self):
        """El path legacy del importer no debe romperse: S06 sigue creando
        al menos N actividades como antes del fix B5."""
        from apps.actividades.models import Actividad

        if not S06_PATH.exists():
            pytest.skip(f'Archivo legacy {S06_PATH} no presente en worktree')

        for c in LINEAS_S06:
            _crear_linea(c, con_torres=True)

        importer = ProgramacionSemanalImporter()
        with open(S06_PATH, 'rb') as f:
            resultado = importer.importar(f, opciones={})

        assert resultado['exito'] is True
        assert resultado['actividades_creadas'] >= 1, (
            f"S06 (legacy) debería seguir creando actividades; "
            f"resumen: {resultado}"
        )
        # Avisos conocidos del comentario de validación previa en #48
        assert Actividad.objects.filter(aviso_sap='5720784').exists() or \
               Actividad.objects.filter(aviso_sap='5720788').exists() or \
               Actividad.objects.filter(aviso_sap='5720782').exists(), (
            'Al menos uno de los avisos conocidos de S06 debe estar creado'
        )

    def test_b5_legacy_hojas_excluidas_siguen_excluyendose(self):
        """Hojas como 'vc', 'Hoja1' deben seguir siendo ignoradas."""
        if not S06_PATH.exists():
            pytest.skip(f'Archivo legacy {S06_PATH} no presente en worktree')

        for c in LINEAS_S06:
            _crear_linea(c, con_torres=True)

        importer = ProgramacionSemanalImporter()
        with open(S06_PATH, 'rb') as f:
            resultado = importer.importar(f, opciones={})

        sheets = resultado.get('sheets_procesadas', [])
        assert 'vc' not in sheets
        assert 'Hoja1' not in [s.lower() for s in sheets]
