"""
API endpoints for crews (Django Ninja).
"""
from typing import Any, Optional, Union
from uuid import UUID
from decimal import Decimal
from datetime import datetime

from ninja import Router, Schema
from django.http import HttpRequest

from apps.api.auth import JWTAuth
from .models import Cuadrilla, CuadrillaMiembro, TrackingUbicacion

router = Router(auth=JWTAuth())


class MiembroOut(Schema):
    id: UUID
    usuario_id: UUID
    usuario_nombre: str
    rol_cuadrilla: str
    activo: bool


class CuadrillaOut(Schema):
    id: UUID
    codigo: str
    nombre: str
    supervisor_nombre: Optional[str]
    vehiculo_placa: Optional[str]
    linea_codigo: Optional[str]
    total_miembros: int


class CuadrillaDetailOut(CuadrillaOut):
    miembros: list[MiembroOut]


class UbicacionIn(Schema):
    latitud: Decimal
    longitud: Decimal
    precision_metros: Optional[Decimal] = None
    velocidad: Optional[Decimal] = None
    bateria: Optional[int] = None


class UbicacionOut(Schema):
    cuadrilla_codigo: str
    lat: float
    lng: float
    precision: Optional[float]
    timestamp: datetime


@router.get('/cuadrillas', response=list[CuadrillaOut])
def listar_cuadrillas(request: HttpRequest, activa: bool = True) -> list[CuadrillaOut]:
    """List all crews."""
    cuadrillas = Cuadrilla.objects.filter(activa=activa).select_related(
        'supervisor', 'vehiculo', 'linea_asignada'
    )

    return [
        CuadrillaOut(
            id=c.id,
            codigo=c.codigo,
            nombre=c.nombre,
            supervisor_nombre=c.supervisor.get_full_name() if c.supervisor else None,
            vehiculo_placa=c.vehiculo.placa if c.vehiculo else None,
            linea_codigo=c.linea_asignada.codigo if c.linea_asignada else None,
            total_miembros=c.total_miembros,
        )
        for c in cuadrillas
    ]


@router.get('/cuadrillas/{cuadrilla_id}', response=CuadrillaDetailOut)
def obtener_cuadrilla(request: HttpRequest, cuadrilla_id: UUID) -> CuadrillaDetailOut:
    """Get crew details with members."""
    cuadrilla = Cuadrilla.objects.select_related(
        'supervisor', 'vehiculo', 'linea_asignada'
    ).get(id=cuadrilla_id)

    miembros = [
        MiembroOut(
            id=m.id,
            usuario_id=m.usuario.id,
            usuario_nombre=m.usuario.get_full_name(),
            rol_cuadrilla=m.rol_cuadrilla,
            activo=m.activo,
        )
        for m in cuadrilla.miembros.filter(activo=True).select_related('usuario')
    ]

    return CuadrillaDetailOut(
        id=cuadrilla.id,
        codigo=cuadrilla.codigo,
        nombre=cuadrilla.nombre,
        supervisor_nombre=cuadrilla.supervisor.get_full_name() if cuadrilla.supervisor else None,
        vehiculo_placa=cuadrilla.vehiculo.placa if cuadrilla.vehiculo else None,
        linea_codigo=cuadrilla.linea_asignada.codigo if cuadrilla.linea_asignada else None,
        total_miembros=cuadrilla.total_miembros,
        miembros=miembros,
    )


@router.post('/ubicacion')
def registrar_ubicacion(
    request: HttpRequest,
    data: UbicacionIn
) -> Union[dict[str, str], tuple[int, dict[str, str]]]:
    """Register current location (from mobile app)."""
    usuario = request.auth
    cuadrilla = usuario.cuadrilla_actual

    if not cuadrilla:
        return 400, {'detail': 'Usuario no asignado a ninguna cuadrilla'}

    ubicacion = TrackingUbicacion.objects.create(
        cuadrilla=cuadrilla,
        usuario=usuario,
        latitud=data.latitud,
        longitud=data.longitud,
        precision_metros=data.precision_metros,
        velocidad=data.velocidad,
        bateria=data.bateria,
    )

    return {'status': 'ok', 'id': str(ubicacion.id)}


@router.get('/ubicaciones', response=list[UbicacionOut])
def obtener_ubicaciones(request: HttpRequest) -> list[UbicacionOut]:
    """Get latest location for all active crews."""
    cuadrillas = Cuadrilla.objects.filter(activa=True)
    ubicaciones: list[UbicacionOut] = []

    for cuadrilla in cuadrillas:
        ultima = TrackingUbicacion.objects.filter(
            cuadrilla=cuadrilla
        ).order_by('-created_at').first()

        if ultima:
            ubicaciones.append(UbicacionOut(
                cuadrilla_codigo=cuadrilla.codigo,
                lat=float(ultima.latitud),
                lng=float(ultima.longitud),
                precision=float(ultima.precision_metros) if ultima.precision_metros else None,
                timestamp=ultima.created_at,
            ))

    return ubicaciones
