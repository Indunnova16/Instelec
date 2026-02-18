"""
Importers for geographic data (KMZ/KML files).
"""
import os
import re
import tempfile
import logging

from django.db import transaction

logger = logging.getLogger(__name__)


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
