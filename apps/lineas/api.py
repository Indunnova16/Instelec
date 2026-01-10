"""
API endpoints for transmission lines (Django Ninja).
"""
from typing import Any, Optional, Union
from uuid import UUID
from decimal import Decimal

from ninja import Router, Schema
from django.http import HttpRequest

from apps.api.auth import JWTAuth
from .models import Linea, Torre, PoligonoServidumbre

router = Router(auth=JWTAuth())


class LineaOut(Schema):
    id: UUID
    codigo: str
    nombre: str
    cliente: str
    tension_kv: Optional[int]
    longitud_km: Optional[Decimal]
    activa: bool


class TorreOut(Schema):
    id: UUID
    numero: str
    tipo: str
    estado: str
    latitud: Decimal
    longitud: Decimal
    altitud: Optional[Decimal]
    municipio: str
    linea_codigo: str
    linea_nombre: str


class TorreDetailOut(TorreOut):
    propietario_predio: str
    vereda: str
    altura_estructura: Optional[Decimal]
    observaciones: str
    tiene_poligono: bool


class PoligonoOut(Schema):
    id: UUID
    nombre: str
    area_hectareas: Optional[Decimal]
    ancho_franja: Optional[Decimal]
    # GeoJSON geometry
    geometria: dict[str, Any]


class ValidarUbicacionIn(Schema):
    latitud: Decimal
    longitud: Decimal
    torre_id: UUID


class ValidarUbicacionOut(Schema):
    dentro_poligono: bool
    torre_numero: str
    linea_codigo: str
    mensaje: str


@router.get('/lineas', response=list[LineaOut])
def listar_lineas(
    request: HttpRequest,
    cliente: Optional[str] = None,
    activa: bool = True
) -> list[Linea]:
    """List all transmission lines."""
    qs = Linea.objects.filter(activa=activa)
    if cliente:
        qs = qs.filter(cliente=cliente)
    return list(qs)


@router.get('/lineas/{linea_id}/torres', response=list[TorreOut])
def listar_torres_linea(request: HttpRequest, linea_id: UUID) -> list[TorreOut]:
    """List all towers for a specific line."""
    torres = Torre.objects.filter(linea_id=linea_id).select_related('linea')
    return [
        TorreOut(
            id=t.id,
            numero=t.numero,
            tipo=t.tipo,
            estado=t.estado,
            latitud=t.latitud,
            longitud=t.longitud,
            altitud=t.altitud,
            municipio=t.municipio,
            linea_codigo=t.linea.codigo,
            linea_nombre=t.linea.nombre,
        )
        for t in torres
    ]


@router.get('/torres/{torre_id}', response=TorreDetailOut)
def obtener_torre(request: HttpRequest, torre_id: UUID) -> TorreDetailOut:
    """Get tower details."""
    torre = Torre.objects.select_related('linea').get(id=torre_id)
    return TorreDetailOut(
        id=torre.id,
        numero=torre.numero,
        tipo=torre.tipo,
        estado=torre.estado,
        latitud=torre.latitud,
        longitud=torre.longitud,
        altitud=torre.altitud,
        municipio=torre.municipio,
        linea_codigo=torre.linea.codigo,
        linea_nombre=torre.linea.nombre,
        propietario_predio=torre.propietario_predio,
        vereda=torre.vereda,
        altura_estructura=torre.altura_estructura,
        observaciones=torre.observaciones,
        tiene_poligono=torre.poligonos.exists(),
    )


@router.get('/torres/{torre_id}/poligono', response=PoligonoOut)
def obtener_poligono_torre(
    request: HttpRequest,
    torre_id: UUID
) -> Union[PoligonoOut, tuple[int, dict[str, str]]]:
    """Get easement polygon for a tower."""
    poligono = PoligonoServidumbre.objects.filter(torre_id=torre_id).first()
    if not poligono:
        return 404, {'detail': 'No hay polígono definido para esta torre'}

    # Convert geometry to GeoJSON
    import json
    geojson = json.loads(poligono.geometria.geojson)

    return PoligonoOut(
        id=poligono.id,
        nombre=poligono.nombre,
        area_hectareas=poligono.area_hectareas,
        ancho_franja=poligono.ancho_franja,
        geometria=geojson,
    )


@router.post('/validar-ubicacion', response=ValidarUbicacionOut)
def validar_ubicacion(request: HttpRequest, data: ValidarUbicacionIn) -> ValidarUbicacionOut:
    """
    Validate if GPS coordinates are within the tower's easement polygon.
    Used by mobile app before allowing field data capture.
    """
    torre = Torre.objects.select_related('linea').get(id=data.torre_id)
    poligono = PoligonoServidumbre.objects.filter(torre=torre).first()

    if not poligono:
        # No polygon defined - allow but warn
        return ValidarUbicacionOut(
            dentro_poligono=True,
            torre_numero=torre.numero,
            linea_codigo=torre.linea.codigo,
            mensaje='No hay polígono de servidumbre definido. Ubicación aceptada.',
        )

    dentro = poligono.punto_dentro(float(data.latitud), float(data.longitud))

    if dentro:
        mensaje = 'Ubicación dentro del área de servidumbre autorizada.'
    else:
        mensaje = 'ADVERTENCIA: Ubicación fuera del área de servidumbre.'

    return ValidarUbicacionOut(
        dentro_poligono=dentro,
        torre_numero=torre.numero,
        linea_codigo=torre.linea.codigo,
        mensaje=mensaje,
    )
