"""
Importers for geographic data (KMZ/KML files).
"""
import io
import os
import re
import tempfile
import logging
import zipfile

from django.db import transaction

logger = logging.getLogger(__name__)

# Patrón Transelca: "LN588 TEBSA - TRIPLE A 1 34.5 KV"
RE_LINEA_TRANSELCA = re.compile(
    r'^(LN\d+)\s+(.+?)\s+(\d+(?:\.\d+)?)\s*KV', re.IGNORECASE
)


class KMZImporter:
    """
    Import towers from KMZ/KML files using GDAL/OGR.

    KMZ files are zipped KML files containing Placemark elements
    with geographic coordinates for towers.
    """

    def __init__(self):
        self.errores = []
        self.advertencias = []
        self.torres_creadas = 0
        self.torres_actualizadas = 0

    def importar(self, archivo, linea, opciones=None):
        """
        Parse KMZ/KML file and create/update Torre objects.

        Args:
            archivo: UploadedFile (KMZ or KML)
            linea: Linea instance to associate towers with
            opciones: dict with 'actualizar_existentes' flag

        Returns:
            dict with import statistics
        """
        opciones = opciones or {}
        actualizar_existentes = opciones.get('actualizar_existentes', False)

        try:
            from osgeo import ogr
        except ImportError:
            return {
                'exito': False,
                'error': 'GDAL/OGR no esta disponible. Instale GDAL para importar archivos KMZ/KML.',
            }

        # Save uploaded file to temp location (OGR needs a file path)
        suffix = '.kmz' if archivo.name.lower().endswith('.kmz') else '.kml'
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                for chunk in archivo.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name

            ds = ogr.Open(tmp_path)
            if ds is None:
                return {
                    'exito': False,
                    'error': 'No se pudo leer el archivo. Verifique que sea un KMZ/KML valido.',
                }

            with transaction.atomic():
                for layer_idx in range(ds.GetLayerCount()):
                    layer = ds.GetLayer(layer_idx)
                    if layer is None:
                        continue

                    layer.ResetReading()
                    for feature in layer:
                        self._procesar_feature(feature, linea, actualizar_existentes)

            ds = None  # Close datasource

            return {
                'exito': True,
                'torres_creadas': self.torres_creadas,
                'torres_actualizadas': self.torres_actualizadas,
                'errores': self.errores,
                'advertencias': self.advertencias,
            }

        except Exception as e:
            logger.exception('Error importing KMZ/KML')
            return {
                'exito': False,
                'error': f'Error al procesar el archivo: {str(e)}',
            }
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def _procesar_feature(self, feature, linea, actualizar_existentes):
        """Process a single OGR feature (Placemark) into a Torre."""
        from apps.lineas.models import Torre

        geom = feature.GetGeometryRef()
        if geom is None:
            return

        # Get point coordinates (handle multigeometry by getting centroid)
        if geom.GetGeometryType() in (1, -2147483647):  # wkbPoint, wkbPoint25D
            lon = geom.GetX()
            lat = geom.GetY()
            alt = geom.GetZ() if geom.GetCoordinateDimension() == 3 else None
        else:
            # For non-point geometries, use centroid
            centroid = geom.Centroid()
            if centroid is None:
                return
            lon = centroid.GetX()
            lat = centroid.GetY()
            alt = None

        # Validate coordinates are within reasonable range for Colombia
        if not (-5.0 <= lat <= 13.0 and -82.0 <= lon <= -66.0):
            nombre = feature.GetField('Name') or 'Sin nombre'
            self.advertencias.append(
                f'Coordenadas fuera de rango para Colombia: {nombre} ({lat}, {lon})'
            )
            # Still process it - user might have valid out-of-range coords

        # Extract tower number from name
        nombre = feature.GetField('Name') or ''
        descripcion = feature.GetField('Description') or ''

        numero = self._extraer_numero_torre(nombre)
        if not numero:
            # Try from description
            numero = self._extraer_numero_torre(descripcion)
        if not numero:
            # Use the full name as-is
            numero = nombre.strip()
        if not numero:
            self.advertencias.append(f'Placemark sin nombre en ({lat}, {lon}), omitido.')
            return

        # Create or update Torre
        try:
            torre_existente = Torre.objects.filter(linea=linea, numero=numero).first()

            if torre_existente:
                if actualizar_existentes:
                    torre_existente.latitud = lat
                    torre_existente.longitud = lon
                    if alt is not None:
                        torre_existente.altitud = alt
                    torre_existente.save()
                    self.torres_actualizadas += 1
                else:
                    self.advertencias.append(
                        f'Torre {numero} ya existe en {linea.codigo}. Use "actualizar existentes" para sobrescribir.'
                    )
            else:
                Torre.objects.create(
                    linea=linea,
                    numero=numero,
                    latitud=lat,
                    longitud=lon,
                    altitud=alt if alt is not None else 0,
                    tipo=Torre.TipoTorre.SUSPENSION,  # Default type
                    estado=Torre.EstadoTorre.BUENO,  # Default state
                )
                self.torres_creadas += 1

        except Exception as e:
            self.errores.append(f'Error al crear torre {numero}: {str(e)}')

    def importar_multilinea(self, archivo, opciones=None):
        """Importa N líneas + sus torres desde un KMZ con varios <Document>.

        A diferencia de `importar()` (1 línea fija), itera los `<Document>` del
        KML, extrae el código `LN###` del `<name>` del Document, y crea/recupera
        una `Linea` por cada uno. Las torres (Placemarks) se asignan a la línea
        de su Document.

        Útil para cargas iniciales con formato Transelca (`Torres Transelca.kmz`,
        40 líneas / 4 586 torres).

        Args:
            archivo: UploadedFile/File con .kmz (zipped) o .kml plano.
            opciones: dict opcional con:
                - actualizar_existentes (bool): si True, sobreescribe coords de
                  torres ya creadas; si False (default), las salta.
                - cliente_default (str): valor de `Linea.cliente` para nuevas
                  líneas (default TRANSELCA).

        Returns:
            dict con: exito, lineas_creadas, lineas_existentes, torres_creadas,
            torres_actualizadas, torres_saltadas, advertencias, errores.

        Nota: usa un parser regex porque algunos KMZ Transelca tienen prefijos
        XML mal cerrados que rompen ElementTree/OGR a mitad del archivo.
        """
        from apps.lineas.models import Linea, Torre

        opciones = opciones or {}
        actualizar = opciones.get('actualizar_existentes', False)
        cliente_default = opciones.get('cliente_default', Linea.Cliente.TRANSELCA)

        try:
            content = self._leer_kml_texto(archivo)
        except Exception as e:
            return {'exito': False, 'error': f'No se pudo leer el archivo: {e}'}

        doc_blocks = re.findall(r'<Document>(.*?)</Document>', content, re.DOTALL)
        if not doc_blocks:
            return {
                'exito': False,
                'error': 'El archivo no contiene <Document> (¿formato single-linea? usa importar() en su lugar).',
            }

        # Parsear todos los Documents → estructura intermedia
        lineas_kmz = []
        for block in doc_blocks:
            m_nombre = re.search(r'<name>([^<]+)</name>', block)
            if not m_nombre:
                continue
            nombre_full = m_nombre.group(1).strip()
            m = RE_LINEA_TRANSELCA.match(nombre_full)
            if m:
                codigo = m.group(1).upper()
                tension = int(float(m.group(3)))
            else:
                codigo = nombre_full.split()[0][:20].upper()
                tension = None

            torres = []
            for pm_match in re.finditer(r'<Placemark>(.*?)</Placemark>', block, re.DOTALL):
                pm = pm_match.group(1)
                m_pn = re.search(r'<name>([^<]+)</name>', pm)
                m_coords = re.search(r'<coordinates>\s*([^<]+?)\s*</coordinates>', pm)
                if not m_pn or not m_coords:
                    continue
                numero = m_pn.group(1).strip()[:20]  # Torre.numero max_length=20
                parts = m_coords.group(1).strip().split(',')
                if len(parts) < 2:
                    continue
                try:
                    lon = float(parts[0])
                    lat = float(parts[1])
                    alt = float(parts[2]) if len(parts) > 2 else 0.0
                except ValueError:
                    continue
                torres.append({'numero': numero, 'lat': lat, 'lon': lon, 'alt': alt})

            lineas_kmz.append({
                'codigo': codigo,
                'nombre': nombre_full[:150],
                'tension_kv': tension,
                'torres': torres,
            })

        # Merge Documents que comparten codigo (KMZs raros pueden repetir LN###)
        merged = {}
        for l in lineas_kmz:
            if l['codigo'] in merged:
                merged[l['codigo']]['torres'].extend(l['torres'])
            else:
                merged[l['codigo']] = dict(l)
        lineas_kmz = list(merged.values())

        # Insertar en BD
        lineas_creadas = 0
        lineas_existentes = 0
        torres_creadas = 0
        torres_actualizadas = 0
        torres_saltadas = 0

        from django.contrib.gis.geos import Point

        with transaction.atomic():
            for l in lineas_kmz:
                linea_obj, created = Linea.objects.get_or_create(
                    codigo=l['codigo'],
                    defaults={
                        'nombre': l['nombre'],
                        'cliente': cliente_default,
                        'tension_kv': l['tension_kv'],
                    },
                )
                if created:
                    lineas_creadas += 1
                else:
                    lineas_existentes += 1

                existing_numeros = set(
                    Torre.objects.filter(linea=linea_obj).values_list('numero', flat=True)
                )

                # Dedup intra-línea (mismo KMZ puede repetir torre)
                seen = set()
                torres_dedup = []
                for t in l['torres']:
                    if t['numero'] in seen:
                        self.advertencias.append(
                            f"{l['codigo']}: torre {t['numero']} duplicada en KMZ, omitida"
                        )
                        continue
                    seen.add(t['numero'])
                    torres_dedup.append(t)

                # Separar existing vs nuevas
                nuevas = []
                for t in torres_dedup:
                    if t['numero'] in existing_numeros:
                        if actualizar:
                            Torre.objects.filter(linea=linea_obj, numero=t['numero']).update(
                                latitud=t['lat'],
                                longitud=t['lon'],
                                altitud=t['alt'],
                                geometria=Point(t['lon'], t['lat'], srid=4326),
                            )
                            torres_actualizadas += 1
                        else:
                            torres_saltadas += 1
                        continue
                    try:
                        pt = Point(t['lon'], t['lat'], srid=4326)
                    except Exception as e:
                        self.errores.append(f"{l['codigo']}/{t['numero']}: {e}")
                        continue
                    nuevas.append(Torre(
                        linea=linea_obj,
                        numero=t['numero'],
                        latitud=t['lat'],
                        longitud=t['lon'],
                        altitud=t['alt'],
                        geometria=pt,
                        tipo=Torre.TipoTorre.SUSPENSION,
                        estado=Torre.EstadoTorre.BUENO,
                    ))

                if nuevas:
                    Torre.objects.bulk_create(nuevas, batch_size=500, ignore_conflicts=True)
                    # ignore_conflicts puede saltar algunas si carrera o duplicado escape;
                    # contar las que realmente quedaron en BD.
                    creadas_real = (
                        Torre.objects.filter(linea=linea_obj).count() - len(existing_numeros)
                    )
                    torres_creadas += creadas_real

        return {
            'exito': True,
            'lineas_creadas': lineas_creadas,
            'lineas_existentes': lineas_existentes,
            'torres_creadas': torres_creadas,
            'torres_actualizadas': torres_actualizadas,
            'torres_saltadas': torres_saltadas,
            'errores': self.errores,
            'advertencias': self.advertencias,
        }

    def _leer_kml_texto(self, archivo):
        """Lee el contenido KML como string desde un KMZ (zip) o KML plano."""
        # Detectar tipo por nombre y/o magic bytes
        nombre = getattr(archivo, 'name', '') or ''
        if hasattr(archivo, 'read'):
            archivo.seek(0) if hasattr(archivo, 'seek') else None
            data = archivo.read() if not hasattr(archivo, 'chunks') else b''.join(archivo.chunks())
        else:
            with open(archivo, 'rb') as f:
                data = f.read()

        if data[:2] == b'PK' or nombre.lower().endswith('.kmz'):
            zf = zipfile.ZipFile(io.BytesIO(data))
            kml_name = next((n for n in zf.namelist() if n.lower().endswith('.kml')), None)
            if not kml_name:
                raise ValueError(f'KMZ sin .kml dentro: {zf.namelist()}')
            return zf.read(kml_name).decode('utf-8', errors='replace')

        return data.decode('utf-8', errors='replace')

    def _extraer_numero_torre(self, texto):
        """Extract tower number from a text string."""
        if not texto:
            return None

        # Common patterns: "Torre 15", "T-15", "T15", "015", "Torre No. 15"
        patterns = [
            r'[Tt]orre\s*(?:No\.?\s*)?(\d+)',
            r'[Tt]-?(\d+)',
            r'^(\d{1,4})$',
            r'[Ee]structura\s*(\d+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, texto.strip())
            if match:
                return match.group(1)

        return None


def kmz_to_geojson(archivo):
    """
    Convert a KMZ/KML uploaded file to a GeoJSON FeatureCollection dict.

    Preserves all feature types (points, lines, polygons) for map visualization.

    Args:
        archivo: Django UploadedFile (KMZ or KML)

    Returns:
        dict: GeoJSON FeatureCollection

    Raises:
        ValueError: If the file cannot be read or parsed
    """
    import json
    from osgeo import ogr, osr

    suffix = '.kmz' if archivo.name.lower().endswith('.kmz') else '.kml'
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            for chunk in archivo.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        ds = ogr.Open(tmp_path)
        if ds is None:
            raise ValueError('No se pudo leer el archivo. Verifique que sea un KMZ/KML válido.')

        features = []
        target_srs = osr.SpatialReference()
        target_srs.ImportFromEPSG(4326)

        for layer_idx in range(ds.GetLayerCount()):
            layer = ds.GetLayer(layer_idx)
            if layer is None:
                continue

            layer.ResetReading()
            for feature in layer:
                geom = feature.GetGeometryRef()
                if geom is None:
                    continue

                # Ensure geometry is in WGS84
                source_srs = geom.GetSpatialReference()
                if source_srs and not source_srs.IsSame(target_srs):
                    geom.TransformTo(target_srs)

                geom_json = json.loads(geom.ExportToJson())

                # Extract properties
                properties = {}
                for field_idx in range(feature.GetFieldCount()):
                    field_name = feature.GetFieldDefnRef(field_idx).GetName()
                    field_value = feature.GetField(field_idx)
                    if field_value is not None:
                        properties[field_name] = field_value

                features.append({
                    'type': 'Feature',
                    'geometry': geom_json,
                    'properties': properties,
                })

        ds = None  # Close datasource

        return {
            'type': 'FeatureCollection',
            'features': features,
        }

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
