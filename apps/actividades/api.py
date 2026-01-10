"""
API endpoints for activities (Django Ninja).
"""
from typing import Any, Optional
from uuid import UUID
from datetime import date, time
from decimal import Decimal

from ninja import Router, Schema
from django.http import HttpRequest

from apps.api.auth import JWTAuth
from .models import Actividad, TipoActividad

router = Router(auth=JWTAuth())


class TipoActividadOut(Schema):
    id: UUID
    codigo: str
    nombre: str
    categoria: str
    requiere_fotos_antes: bool
    requiere_fotos_durante: bool
    requiere_fotos_despues: bool
    min_fotos: int
    campos_formulario: list[Any]
    tiempo_estimado_horas: Decimal


class ActividadOut(Schema):
    id: UUID
    linea_id: UUID
    linea_codigo: str
    linea_nombre: str
    torre_id: UUID
    torre_numero: str
    torre_latitud: Decimal
    torre_longitud: Decimal
    tipo_actividad_id: UUID
    tipo_actividad_nombre: str
    tipo_actividad_categoria: str
    fecha_programada: date
    estado: str
    prioridad: str
    campos_formulario: list[Any]


class ActividadDetailOut(ActividadOut):
    cuadrilla_codigo: Optional[str]
    hora_inicio_estimada: Optional[time]
    observaciones_programacion: str
    requiere_fotos_antes: bool
    requiere_fotos_durante: bool
    requiere_fotos_despues: bool
    min_fotos: int


@router.get('/tipos', response=list[TipoActividadOut])
def listar_tipos_actividad(request: HttpRequest, activo: bool = True) -> list[TipoActividad]:
    """List all activity types."""
    tipos = TipoActividad.objects.filter(activo=activo)
    return list(tipos)


@router.get('/mis-actividades', response=list[ActividadOut])
def listar_mis_actividades(
    request: HttpRequest,
    fecha: Optional[date] = None,
    estado: Optional[str] = None
) -> list[ActividadOut]:
    """
    List activities assigned to the current user's crew.
    Used by mobile app to show pending work.
    """
    usuario = request.auth
    cuadrilla = usuario.cuadrilla_actual

    if not cuadrilla:
        return []

    qs = Actividad.objects.filter(
        cuadrilla=cuadrilla
    ).select_related('linea', 'torre', 'tipo_actividad')

    if fecha:
        qs = qs.filter(fecha_programada=fecha)
    else:
        # Default: show pending and in-progress
        qs = qs.filter(estado__in=['PENDIENTE', 'PROGRAMADA', 'EN_CURSO'])

    if estado:
        qs = qs.filter(estado=estado)

    return [
        ActividadOut(
            id=a.id,
            linea_id=a.linea.id,
            linea_codigo=a.linea.codigo,
            linea_nombre=a.linea.nombre,
            torre_id=a.torre.id,
            torre_numero=a.torre.numero,
            torre_latitud=a.torre.latitud,
            torre_longitud=a.torre.longitud,
            tipo_actividad_id=a.tipo_actividad.id,
            tipo_actividad_nombre=a.tipo_actividad.nombre,
            tipo_actividad_categoria=a.tipo_actividad.categoria,
            fecha_programada=a.fecha_programada,
            estado=a.estado,
            prioridad=a.prioridad,
            campos_formulario=a.tipo_actividad.campos_formulario or [],
        )
        for a in qs
    ]


@router.get('/{actividad_id}', response=ActividadDetailOut)
def obtener_actividad(request: HttpRequest, actividad_id: UUID) -> ActividadDetailOut:
    """Get activity details."""
    actividad = Actividad.objects.select_related(
        'linea', 'torre', 'tipo_actividad', 'cuadrilla'
    ).get(id=actividad_id)

    return ActividadDetailOut(
        id=actividad.id,
        linea_id=actividad.linea.id,
        linea_codigo=actividad.linea.codigo,
        linea_nombre=actividad.linea.nombre,
        torre_id=actividad.torre.id,
        torre_numero=actividad.torre.numero,
        torre_latitud=actividad.torre.latitud,
        torre_longitud=actividad.torre.longitud,
        tipo_actividad_id=actividad.tipo_actividad.id,
        tipo_actividad_nombre=actividad.tipo_actividad.nombre,
        tipo_actividad_categoria=actividad.tipo_actividad.categoria,
        fecha_programada=actividad.fecha_programada,
        estado=actividad.estado,
        prioridad=actividad.prioridad,
        campos_formulario=actividad.tipo_actividad.campos_formulario or [],
        cuadrilla_codigo=actividad.cuadrilla.codigo if actividad.cuadrilla else None,
        hora_inicio_estimada=actividad.hora_inicio_estimada,
        observaciones_programacion=actividad.observaciones_programacion,
        requiere_fotos_antes=actividad.tipo_actividad.requiere_fotos_antes,
        requiere_fotos_durante=actividad.tipo_actividad.requiere_fotos_durante,
        requiere_fotos_despues=actividad.tipo_actividad.requiere_fotos_despues,
        min_fotos=actividad.tipo_actividad.min_fotos,
    )


@router.post('/{actividad_id}/iniciar')
def iniciar_actividad(
    request: HttpRequest,
    actividad_id: UUID,
    latitud: Decimal,
    longitud: Decimal
) -> dict[str, Any]:
    """
    Mark activity as started and create field record.
    Returns the created record ID for further updates.
    """
    from apps.campo.models import RegistroCampo
    from apps.lineas.models import PoligonoServidumbre
    from django.utils import timezone

    actividad = Actividad.objects.select_related('torre').get(id=actividad_id)

    # Check location against easement polygon
    poligono = PoligonoServidumbre.objects.filter(torre=actividad.torre).first()
    dentro_poligono = True
    if poligono:
        dentro_poligono = poligono.punto_dentro(float(latitud), float(longitud))

    # Create field record
    registro = RegistroCampo.objects.create(
        actividad=actividad,
        usuario=request.auth,
        fecha_inicio=timezone.now(),
        latitud_inicio=latitud,
        longitud_inicio=longitud,
        dentro_poligono=dentro_poligono,
    )

    # Update activity status
    actividad.estado = Actividad.Estado.EN_CURSO
    actividad.save(update_fields=['estado', 'updated_at'])

    return {
        'registro_id': str(registro.id),
        'dentro_poligono': dentro_poligono,
        'mensaje': 'Actividad iniciada correctamente' if dentro_poligono else 'ADVERTENCIA: Ubicación fuera del área autorizada'
    }
