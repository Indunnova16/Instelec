"""
API endpoints for crews (Django Ninja).
"""
from typing import Any, Optional, Union
from uuid import UUID
from decimal import Decimal
from datetime import datetime, date, time

from ninja import Router, Schema
from django.http import HttpRequest

from apps.api.auth import OptionalJWTAuth
from .models import Cuadrilla, CuadrillaMiembro, TrackingUbicacion, Asistencia

router = Router(auth=OptionalJWTAuth())


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


# ==================== ASISTENCIA ENDPOINTS ====================

class AsistenciaIn(Schema):
    usuario_id: UUID
    cuadrilla_id: UUID
    fecha: date
    tipo_novedad: str = "PRESENTE"
    hora_entrada: Optional[time] = None
    hora_salida: Optional[time] = None
    observacion: str = ""


class AsistenciaBulkIn(Schema):
    cuadrilla_id: UUID
    fecha: date
    asistencias: list[AsistenciaIn]


class AsistenciaOut(Schema):
    id: UUID
    usuario_id: UUID
    usuario_nombre: str
    cuadrilla_id: UUID
    cuadrilla_codigo: str
    fecha: date
    tipo_novedad: str
    tipo_novedad_display: str
    hora_entrada: Optional[time]
    hora_salida: Optional[time]
    observacion: str
    horas_trabajadas: Optional[float]
    esta_presente: bool


@router.post('/asistencia')
def registrar_asistencia(
    request: HttpRequest,
    data: AsistenciaIn
) -> Union[dict[str, Any], tuple[int, dict[str, str]]]:
    """
    Registra la asistencia de un usuario para una fecha específica.
    Si ya existe un registro, lo actualiza.
    """
    from apps.usuarios.models import Usuario

    try:
        usuario = Usuario.objects.get(id=data.usuario_id)
        cuadrilla = Cuadrilla.objects.get(id=data.cuadrilla_id)
    except (Usuario.DoesNotExist, Cuadrilla.DoesNotExist) as e:
        return 404, {'detail': str(e)}

    asistencia, created = Asistencia.objects.update_or_create(
        usuario=usuario,
        cuadrilla=cuadrilla,
        fecha=data.fecha,
        defaults={
            'tipo_novedad': data.tipo_novedad,
            'hora_entrada': data.hora_entrada,
            'hora_salida': data.hora_salida,
            'observacion': data.observacion,
            'registrado_por': request.auth,
        }
    )

    return {
        'id': str(asistencia.id),
        'status': 'created' if created else 'updated',
        'message': f'Asistencia {"registrada" if created else "actualizada"} correctamente'
    }


@router.post('/asistencia/bulk')
def registrar_asistencia_masiva(
    request: HttpRequest,
    data: AsistenciaBulkIn
) -> dict[str, Any]:
    """
    Registra asistencia masiva para una cuadrilla completa en una fecha.
    """
    from apps.usuarios.models import Usuario

    resultados = []
    cuadrilla = Cuadrilla.objects.get(id=data.cuadrilla_id)

    for item in data.asistencias:
        try:
            usuario = Usuario.objects.get(id=item.usuario_id)
            asistencia, created = Asistencia.objects.update_or_create(
                usuario=usuario,
                cuadrilla=cuadrilla,
                fecha=data.fecha,
                defaults={
                    'tipo_novedad': item.tipo_novedad,
                    'hora_entrada': item.hora_entrada,
                    'hora_salida': item.hora_salida,
                    'observacion': item.observacion,
                    'registrado_por': request.auth,
                }
            )
            resultados.append({
                'usuario_id': str(item.usuario_id),
                'status': 'ok',
                'created': created
            })
        except Usuario.DoesNotExist:
            resultados.append({
                'usuario_id': str(item.usuario_id),
                'status': 'error',
                'message': 'Usuario no encontrado'
            })

    return {
        'cuadrilla_id': str(data.cuadrilla_id),
        'fecha': str(data.fecha),
        'total_procesados': len(resultados),
        'resultados': resultados
    }


@router.get('/asistencia/{fecha}', response=list[AsistenciaOut])
def obtener_asistencia_por_fecha(
    request: HttpRequest,
    fecha: date,
    cuadrilla_id: Optional[UUID] = None
) -> list[AsistenciaOut]:
    """
    Obtiene la asistencia de una fecha específica.
    Opcionalmente filtra por cuadrilla.
    """
    qs = Asistencia.objects.filter(fecha=fecha).select_related('usuario', 'cuadrilla')

    if cuadrilla_id:
        qs = qs.filter(cuadrilla_id=cuadrilla_id)

    return [
        AsistenciaOut(
            id=a.id,
            usuario_id=a.usuario.id,
            usuario_nombre=a.usuario.get_full_name(),
            cuadrilla_id=a.cuadrilla.id,
            cuadrilla_codigo=a.cuadrilla.codigo,
            fecha=a.fecha,
            tipo_novedad=a.tipo_novedad,
            tipo_novedad_display=a.get_tipo_novedad_display(),
            hora_entrada=a.hora_entrada,
            hora_salida=a.hora_salida,
            observacion=a.observacion,
            horas_trabajadas=a.horas_trabajadas,
            esta_presente=a.esta_presente,
        )
        for a in qs
    ]


@router.get('/asistencia/cuadrilla/{cuadrilla_id}', response=list[AsistenciaOut])
def obtener_asistencia_cuadrilla(
    request: HttpRequest,
    cuadrilla_id: UUID,
    fecha_inicio: Optional[date] = None,
    fecha_fin: Optional[date] = None
) -> list[AsistenciaOut]:
    """
    Obtiene la asistencia de una cuadrilla en un rango de fechas.
    Si no se especifican fechas, retorna la asistencia del día actual.
    """
    from django.utils import timezone

    qs = Asistencia.objects.filter(cuadrilla_id=cuadrilla_id).select_related('usuario', 'cuadrilla')

    if fecha_inicio:
        qs = qs.filter(fecha__gte=fecha_inicio)
    if fecha_fin:
        qs = qs.filter(fecha__lte=fecha_fin)
    if not fecha_inicio and not fecha_fin:
        qs = qs.filter(fecha=timezone.now().date())

    return [
        AsistenciaOut(
            id=a.id,
            usuario_id=a.usuario.id,
            usuario_nombre=a.usuario.get_full_name(),
            cuadrilla_id=a.cuadrilla.id,
            cuadrilla_codigo=a.cuadrilla.codigo,
            fecha=a.fecha,
            tipo_novedad=a.tipo_novedad,
            tipo_novedad_display=a.get_tipo_novedad_display(),
            hora_entrada=a.hora_entrada,
            hora_salida=a.hora_salida,
            observacion=a.observacion,
            horas_trabajadas=a.horas_trabajadas,
            esta_presente=a.esta_presente,
        )
        for a in qs
    ]
