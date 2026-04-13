"""
API endpoints for transmission lines (Django Ninja).
"""
from typing import Any, Optional, Union
from uuid import UUID
from decimal import Decimal

from ninja import Router, Schema
from django.http import HttpRequest

from apps.api.auth import OptionalJWTAuth
from .models import Linea, Torre, PoligonoServidumbre

router = Router(auth=OptionalJWTAuth())


class LineaOut(Schema):
    id: UUID
    codigo: str
    nombre: str
    cliente: str
    contrato_id: Optional[UUID]
    contrato_nombre: Optional[str]
    tension_kv: Optional[int]
    longitud_km: Optional[Decimal]
    tipo_estructura: str
    cantidad_torres: Optional[int]
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
    search: Optional[str] = None,
    cliente: Optional[str] = None,
    contrato_id: Optional[UUID] = None,
    tipo_estructura: Optional[str] = None,
    activa: bool = True
) -> list[LineaOut]:
    """
    List all transmission lines with filtering options.

    Query parameters:
    - search: Search by codigo or nombre (case-insensitive)
    - cliente: Filter by client (TRANSELCA, INTERCOLOMBIA)
    - contrato_id: Filter by contract/project ID
    - tipo_estructura: Filter by structure type (TORRES, POSTES, MIXTO)
    - activa: Filter by active status (default: true)
    """
    qs = Linea.objects.filter(activa=activa).select_related('contrato')

    if search:
        from django.db.models import Q
        qs = qs.filter(
            Q(codigo__icontains=search) |
            Q(nombre__icontains=search) |
            Q(codigo_transelca__icontains=search)
        )

    if cliente:
        qs = qs.filter(cliente=cliente)

    if contrato_id:
        qs = qs.filter(contrato_id=contrato_id)

    if tipo_estructura:
        qs = qs.filter(tipo_estructura=tipo_estructura)

    return [
        LineaOut(
            id=linea.id,
            codigo=linea.codigo,
            nombre=linea.nombre,
            cliente=linea.cliente,
            contrato_id=linea.contrato_id,
            contrato_nombre=linea.contrato.nombre if linea.contrato else None,
            tension_kv=linea.tension_kv,
            longitud_km=linea.longitud_km,
            tipo_estructura=linea.tipo_estructura,
            cantidad_torres=linea.cantidad_torres,
            activa=linea.activa,
        )
        for linea in qs.order_by('codigo')
    ]


@router.get('/torres', response=list[TorreOut])
def listar_torres(
    request: HttpRequest,
    linea_id: Optional[UUID] = None,
    search: Optional[str] = None,
    tipo: Optional[str] = None,
    estado: Optional[str] = None,
    municipio: Optional[str] = None,
    contrato_id: Optional[UUID] = None
) -> list[TorreOut]:
    """
    List all towers with filtering options.

    Query parameters:
    - linea_id: Filter by line ID
    - search: Search by tower number (case-insensitive)
    - tipo: Filter by tower type (SUSPENSION, ANCLAJE, TERMINAL, REMATE, DERIVACION)
    - estado: Filter by tower state (BUENO, REGULAR, MALO, CRITICO)
    - municipio: Filter by municipality (case-insensitive)
    - contrato_id: Filter by contract/project (through line)
    """
    qs = Torre.objects.select_related('linea')

    if linea_id:
        qs = qs.filter(linea_id=linea_id)

    if search:
        qs = qs.filter(numero__icontains=search)

    if tipo:
        qs = qs.filter(tipo=tipo)

    if estado:
        qs = qs.filter(estado=estado)

    if municipio:
        qs = qs.filter(municipio__icontains=municipio)

    if contrato_id:
        qs = qs.filter(linea__contrato_id=contrato_id)

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
        for t in qs.order_by('linea__codigo', 'numero')
    ]


@router.get('/lineas/{linea_id}/torres', response=list[TorreOut])
def listar_torres_linea(
    request: HttpRequest,
    linea_id: UUID,
    search: Optional[str] = None,
    tipo: Optional[str] = None,
    estado: Optional[str] = None
) -> list[TorreOut]:
    """
    List all towers for a specific line with filtering options.

    Query parameters:
    - search: Search by tower number (case-insensitive)
    - tipo: Filter by tower type
    - estado: Filter by tower state
    """
    qs = Torre.objects.filter(linea_id=linea_id).select_related('linea')

    if search:
        qs = qs.filter(numero__icontains=search)

    if tipo:
        qs = qs.filter(tipo=tipo)

    if estado:
        qs = qs.filter(estado=estado)

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
        for t in qs.order_by('numero')
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
