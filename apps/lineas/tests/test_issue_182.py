"""
Tests #182 — Fallback manual (lxml) para KMZ cuando OGR no puede abrirlo.

Causa raíz (F2, reproducida contra la imagen REAL de prod
`ghcr.io/osgeo/gdal:ubuntu-small-3.8.5`): esa imagen no trae compilado el
driver LIBKML de GDAL/OGR. Sin LIBKML, `ogr.Open()` devuelve None para KMZs
con estructura Document→Style/StyleMap→Folder→Placemarks mixtos
(LineString+Point), como el "LN 804 MOD.kmz" del cliente. Esto disparaba
`ValueError: No se pudo leer el archivo. Verifique que sea un KMZ/KML
válido.` tanto en `kmz_to_geojson()` (usado por `/lineas/{uuid}/subir-kmz/`)
como en `KMZImporter.importar()` (usado por `/lineas/importar-kmz/` modo
single-línea).

Fix: cuando `ogr.Open()` devuelve None, un fallback parsea el KML a mano con
`lxml`, navegando Document→Folder (anidado)→Placemark de forma
namespace-aware, detectando `<Point>` vs `<LineString>`. Se activa SOLO
cuando OGR falla — cero cambio de comportamiento cuando el driver LIBKML SI
está disponible (el path OGR original queda intacto).

Cubre:
- Parseo manual aislado (`_parse_kml_manual_features`) contra la estructura
  exacta del issue (Document→Style/StyleMap→Folder→1 LineString + 3 Points).
- `kmz_to_geojson()` con OGR forzado a fallar (simula la imagen de prod sin
  LIBKML) → debe producir el GeoJSON correcto (no debe lanzar ValueError).
- `kmz_to_geojson()` SIN forzar el fallo (OGR real, disponible en este venv
  local) → mismo resultado, cero cambio de comportamiento en el happy path.
- `KMZImporter.importar()` con OGR forzado a fallar → crea las Torres
  esperadas sobre una Línea existente (equivalente al dato legacy: la línea
  ya existe en BD antes de la carga, igual que LN5114 en prod).
- `KMZImporter.importar()` SIN forzar el fallo (OGR real) → mismo resultado
  (paridad de comportamiento entre ambos paths).
- Edge case: KMZ solo-Points (sin LineString).
- Edge case: KMZ malformado (no es ZIP ni XML válido) → debe seguir
  rechazándose con el MISMO mensaje de error que antes del fix.
- Edge case: KMZ válido pero sin Placemarks reconocibles (Point/LineString)
  → mismo mensaje de error (no hay nada útil que importar).

Ejecutar:  pytest apps/lineas/tests/test_issue_182.py -v
"""
import io
import zipfile
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.lineas.importers import (
    KMZImporter,
    _parse_kml_manual_features,
    kmz_to_geojson,
)
from apps.lineas.models import Linea, Torre

# Nota: el mensaje difiere en el acento entre las dos funciones ya en el
# código ORIGINAL (pre-fix) — kmz_to_geojson() usa "válido" (con tilde) y
# KMZImporter.importar() usa "valido" (sin tilde). El fix preserva ambas
# variantes literales tal cual estaban (no es parte del scope de #182).
MSG_ERROR_KMZ_GEOJSON = 'No se pudo leer el archivo. Verifique que sea un KMZ/KML válido.'
MSG_ERROR_KMZ_IMPORTAR = 'No se pudo leer el archivo. Verifique que sea un KMZ/KML valido.'

# KML con la estructura EXACTA reportada en el issue: Document → 2x Style +
# 2x StyleMap → Folder "Ruta LN 804 MOD" → 1 Placemark LineString + 3
# Placemark Point (geometría mixta dentro del mismo Folder — el patrón que
# rompe el driver "KML" mínimo cuando LIBKML no está compilado).
KML_MIXTO = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:gx="http://www.google.com/kml/ext/2.2" xmlns:kml="http://www.opengis.net/kml/2.2" xmlns:atom="http://www.w3.org/2005/Atom">
<Document>
\t<name>LN 804 MOD.kmz</name>
\t<StyleMap id="m_ylw-pushpin">
\t\t<Pair><key>normal</key><styleUrl>#s_ylw-pushpin</styleUrl></Pair>
\t\t<Pair><key>highlight</key><styleUrl>#s_ylw-pushpin_hl</styleUrl></Pair>
\t</StyleMap>
\t<Style id="s_ylw-pushpin">
\t\t<IconStyle><scale>1.1</scale><Icon><href>http://maps.google.com/mapfiles/kml/pushpin/ylw-pushpin.png</href></Icon></IconStyle>
\t</Style>
\t<StyleMap id="m_line">
\t\t<Pair><key>normal</key><styleUrl>#s_line</styleUrl></Pair>
\t\t<Pair><key>highlight</key><styleUrl>#s_line_hl</styleUrl></Pair>
\t</StyleMap>
\t<Style id="s_line"><LineStyle><color>ff0000ff</color><width>3</width></LineStyle></Style>
\t<Folder>
\t\t<name>Ruta LN 804 MOD</name>
\t\t<open>1</open>
\t\t<Placemark>
\t\t\t<name>Ruta LN 804 MOD</name>
\t\t\t<styleUrl>#m_line</styleUrl>
\t\t\t<LineString>
\t\t\t\t<tessellate>1</tessellate>
\t\t\t\t<coordinates>-74.123456,10.987654,0 -74.120456,10.985654,0 -74.117456,10.983654,0 -74.114456,10.981654,0</coordinates>
\t\t\t</LineString>
\t\t</Placemark>
\t\t<Placemark>
\t\t\t<name>PTKD</name>
\t\t\t<styleUrl>#m_ylw-pushpin</styleUrl>
\t\t\t<Point><coordinates>-74.123456,10.987654,0</coordinates></Point>
\t\t</Placemark>
\t\t<Placemark>
\t\t\t<name>TINT</name>
\t\t\t<styleUrl>#m_ylw-pushpin</styleUrl>
\t\t\t<Point><coordinates>-74.118456,10.984654,0</coordinates></Point>
\t\t</Placemark>
\t\t<Placemark>
\t\t\t<name>PK03</name>
\t\t\t<styleUrl>#m_ylw-pushpin</styleUrl>
\t\t\t<Point><coordinates>-74.114456,10.981654,0</coordinates></Point>
\t\t</Placemark>
\t</Folder>
</Document>
</kml>
"""

# Edge case: KMZ solo con Placemarks Point, sin ningún LineString.
KML_SOLO_PUNTOS = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
\t<name>Solo puntos.kmz</name>
\t<Folder>
\t\t<name>Torres sueltas</name>
\t\t<Placemark><name>T-1</name><Point><coordinates>-74.10,10.10,0</coordinates></Point></Placemark>
\t\t<Placemark><name>T-2</name><Point><coordinates>-74.11,10.11,0</coordinates></Point></Placemark>
\t\t<Placemark><name>T-3</name><Point><coordinates>-74.12,10.12,0</coordinates></Point></Placemark>
\t</Folder>
</Document>
</kml>
"""

# Edge case: XML válido, KML válido, pero sin ningún Placemark con geometría
# reconocida (solo un Folder vacío).
KML_SIN_PLACEMARKS = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
\t<name>Vacio.kmz</name>
\t<Folder>
\t\t<name>Nada aqui</name>
\t</Folder>
</Document>
</kml>
"""


def _kmz_bytes(kml_text, kml_filename='doc.kml'):
    """Empaqueta un texto KML en bytes de un .kmz (zip) válido."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(kml_filename, kml_text)
    return buf.getvalue()


def _kmz_upload(kml_text, name='LN 804 MOD.kmz'):
    return SimpleUploadedFile(name, _kmz_bytes(kml_text), content_type='application/vnd.google-earth.kmz')


def _linea_existente(codigo='LN5114'):
    """Linea de mantenimiento pre-existente en BD — equivalente al dato
    legacy: en prod, LN5114 (14d79066-060b-4713-a642-6580105a85f7) ya existe
    ANTES de que el cliente intente cargar el KMZ (issue #182)."""
    return Linea.objects.create(codigo=codigo, nombre='LN 804 MOD', cliente=Linea.Cliente.TRANSELCA)


# ==============================================================================
# 1) Parseo manual aislado (sin DB, sin OGR) — estructura exacta del issue
# ==============================================================================

def test_parse_kml_manual_features_estructura_mixta_del_issue():
    features = _parse_kml_manual_features(_kmz_bytes_path_helper(KML_MIXTO))

    assert len(features) == 4
    por_tipo = {}
    for f in features:
        por_tipo.setdefault(f['geom_type'], []).append(f)

    assert len(por_tipo.get('Point', [])) == 3
    assert len(por_tipo.get('LineString', [])) == 1

    nombres_puntos = sorted(f['name'] for f in por_tipo['Point'])
    assert nombres_puntos == ['PK03', 'PTKD', 'TINT']

    linea = por_tipo['LineString'][0]
    assert linea['name'] == 'Ruta LN 804 MOD'
    assert len(linea['coordinates']) == 4
    # Primer vértice == coordenadas del Placemark PTKD (comparten origen)
    assert linea['coordinates'][0][0] == pytest.approx(-74.123456)
    assert linea['coordinates'][0][1] == pytest.approx(10.987654)


def test_parse_kml_manual_features_solo_puntos():
    features = _parse_kml_manual_features(_kmz_bytes_path_helper(KML_SOLO_PUNTOS))
    assert len(features) == 3
    assert all(f['geom_type'] == 'Point' for f in features)
    assert sorted(f['name'] for f in features) == ['T-1', 'T-2', 'T-3']


def test_parse_kml_manual_features_sin_placemarks_retorna_vacio():
    features = _parse_kml_manual_features(_kmz_bytes_path_helper(KML_SIN_PLACEMARKS))
    assert features == []


def _kmz_bytes_path_helper(kml_text):
    """_parse_kml_manual_features acepta un path o un file-like; para el
    parseo aislado (sin pasar por kmz_to_geojson/importar) usamos un
    BytesIO con .read(), que _leer_texto_kml también soporta."""
    class _FileLike(io.BytesIO):
        name = 'doc.kmz'
    return _FileLike(_kmz_bytes(kml_text))


# ==============================================================================
# 2) kmz_to_geojson() — happy path del fallback (reproduce el bug + fix)
# ==============================================================================

def test_kmz_to_geojson_fallback_cuando_ogr_falla():
    """Reproduce el bug del issue #182: en prod, ogr.Open() devuelve None
    para este KMZ (driver LIBKML ausente). Antes del fix esto lanzaba
    ValueError; con el fix, el fallback manual produce el GeoJSON correcto."""
    archivo = _kmz_upload(KML_MIXTO)

    with patch('osgeo.ogr.Open', return_value=None) as mock_open:
        geojson = kmz_to_geojson(archivo)
        assert mock_open.called  # confirma que sí pasamos por la rama ds is None

    assert geojson['type'] == 'FeatureCollection'
    assert len(geojson['features']) == 4

    tipos = sorted(f['geometry']['type'] for f in geojson['features'])
    assert tipos == ['LineString', 'Point', 'Point', 'Point']

    nombres = sorted(f['properties'].get('Name') for f in geojson['features'])
    assert nombres == ['PK03', 'PTKD', 'Ruta LN 804 MOD', 'TINT']

    puntos = [f for f in geojson['features'] if f['geometry']['type'] == 'Point']
    ptkd = next(f for f in puntos if f['properties']['Name'] == 'PTKD')
    assert ptkd['geometry']['coordinates'][0] == pytest.approx(-74.123456)
    assert ptkd['geometry']['coordinates'][1] == pytest.approx(10.987654)


def test_kmz_to_geojson_solo_puntos_fallback():
    """Edge case: KMZ sin ningún LineString, solo Points."""
    archivo = _kmz_upload(KML_SOLO_PUNTOS, name='solo_puntos.kmz')

    with patch('osgeo.ogr.Open', return_value=None):
        geojson = kmz_to_geojson(archivo)

    assert len(geojson['features']) == 3
    assert all(f['geometry']['type'] == 'Point' for f in geojson['features'])
    assert sorted(f['properties']['Name'] for f in geojson['features']) == ['T-1', 'T-2', 'T-3']


def test_kmz_to_geojson_ogr_disponible_no_cambia_comportamiento():
    """Edge case obligatorio: cuando OGR SÍ puede abrir el archivo (LIBKML
    disponible, como en este venv local), el fix NO debe alterar el
    resultado — el path OGR original permanece intacto y no pasa por el
    fallback manual en absoluto."""
    archivo = _kmz_upload(KML_MIXTO)

    with patch('apps.lineas.importers._parse_kml_manual_features') as mock_fallback:
        geojson = kmz_to_geojson(archivo)
        mock_fallback.assert_not_called()  # el fallback NUNCA se invoca si OGR abre OK

    assert geojson['type'] == 'FeatureCollection'
    assert len(geojson['features']) == 4
    tipos = sorted(f['geometry']['type'] for f in geojson['features'])
    assert tipos == ['LineString', 'Point', 'Point', 'Point']


def test_kmz_to_geojson_malformado_mismo_mensaje_error():
    """Edge case: KMZ realmente corrupto (ni ZIP ni XML válido) — debe
    seguir rechazándose con el MISMO mensaje que antes del fix, no un
    traceback ni un GeoJSON vacío silencioso."""
    archivo = SimpleUploadedFile(
        'corrupto.kmz', b'esto no es un zip ni xml valido \x00\x01\x02',
        content_type='application/vnd.google-earth.kmz',
    )

    with pytest.raises(ValueError, match=MSG_ERROR_KMZ_GEOJSON):
        kmz_to_geojson(archivo)


def test_kmz_to_geojson_sin_placemarks_reconocidos_mismo_mensaje_error():
    """Edge case: XML/KML válido pero sin Placemarks Point/LineString
    reconocibles — el fallback no tiene nada útil que devolver, así que debe
    fallar igual que el path OGR original (no un FeatureCollection vacío)."""
    archivo = _kmz_upload(KML_SIN_PLACEMARKS, name='vacio.kmz')

    with patch('osgeo.ogr.Open', return_value=None):
        with pytest.raises(ValueError, match=MSG_ERROR_KMZ_GEOJSON):
            kmz_to_geojson(archivo)


# ==============================================================================
# 3) KMZImporter.importar() — contra una Línea existente (dato legacy)
# ==============================================================================

@pytest.mark.django_db
def test_importar_fallback_crea_torres_sobre_linea_existente():
    """Reproduce el segundo síntoma del issue: /lineas/importar-kmz/ modo
    single-línea (ImportarKMZView) comparte la misma causa raíz. La Línea ya
    existe en BD (equivalente a LN5114 en prod, dato "legacy" pre-carga)."""
    linea = _linea_existente()
    archivo = _kmz_upload(KML_MIXTO)

    with patch('osgeo.ogr.Open', return_value=None):
        resultado = KMZImporter().importar(archivo, linea)

    assert resultado['exito'] is True
    assert resultado['torres_creadas'] == 4  # 3 Points + 1 centroide de la LineString

    numeros = set(Torre.objects.filter(linea=linea).values_list('numero', flat=True))
    assert {'PTKD', 'TINT', 'PK03', 'Ruta LN 804 MOD'} == numeros

    ptkd = Torre.objects.get(linea=linea, numero='PTKD')
    assert float(ptkd.longitud) == pytest.approx(-74.123456, abs=1e-6)
    assert float(ptkd.latitud) == pytest.approx(10.987654, abs=1e-6)

    # El centroide de la LineString debe caer DENTRO del rango de sus vértices
    # (no exigimos igualdad exacta con geom.Centroid() de OGR — el fallback
    # usa un promedio simple como sustituto liviano, ver importers.py).
    ruta = Torre.objects.get(linea=linea, numero='Ruta LN 804 MOD')
    assert -74.123456 <= float(ruta.longitud) <= -74.114456
    assert 10.981654 <= float(ruta.latitud) <= 10.987654


@pytest.mark.django_db
def test_importar_ogr_disponible_no_cambia_comportamiento():
    """Edge case obligatorio: mismo import, pero SIN forzar el fallo de OGR
    (LIBKML disponible localmente) — debe producir el MISMO resultado que el
    fallback manual, probando paridad de comportamiento."""
    linea = _linea_existente(codigo='LN5114-OGR')
    archivo = _kmz_upload(KML_MIXTO)

    with patch('apps.lineas.importers._parse_kml_manual_features') as mock_fallback:
        resultado = KMZImporter().importar(archivo, linea)
        mock_fallback.assert_not_called()

    assert resultado['exito'] is True
    assert resultado['torres_creadas'] == 4
    numeros = set(Torre.objects.filter(linea=linea).values_list('numero', flat=True))
    assert {'PTKD', 'TINT', 'PK03', 'Ruta LN 804 MOD'} == numeros


@pytest.mark.django_db
def test_importar_solo_puntos_fallback():
    """Edge case: KMZ solo-Points vía KMZImporter.importar()."""
    linea = _linea_existente(codigo='LN-PTS')
    archivo = _kmz_upload(KML_SOLO_PUNTOS, name='solo_puntos.kmz')

    with patch('osgeo.ogr.Open', return_value=None):
        resultado = KMZImporter().importar(archivo, linea)

    assert resultado['exito'] is True
    assert resultado['torres_creadas'] == 3
    numeros = set(Torre.objects.filter(linea=linea).values_list('numero', flat=True))
    # _extraer_numero_torre() extrae el dígito de "T-1"/"T-2"/"T-3" (mismo
    # comportamiento pre-existente que el path OGR — no es parte del fix).
    assert numeros == {'1', '2', '3'}


@pytest.mark.django_db
def test_importar_malformado_mismo_mensaje_error():
    """Edge case: KMZ corrupto vía KMZImporter.importar() — mismo mensaje de
    error que el path OGR original, sin crear ninguna Torre."""
    linea = _linea_existente(codigo='LN-BAD')
    archivo = SimpleUploadedFile(
        'corrupto.kmz', b'\x00\x01no es zip ni xml\x02\x03',
        content_type='application/vnd.google-earth.kmz',
    )

    resultado = KMZImporter().importar(archivo, linea)

    assert resultado['exito'] is False
    assert resultado['error'] == MSG_ERROR_KMZ_IMPORTAR
    assert Torre.objects.filter(linea=linea).count() == 0
