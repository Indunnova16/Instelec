"""
API endpoints for field records (Django Ninja).
"""
import logging
from typing import Any, Optional, Union
from uuid import UUID
from datetime import datetime
from decimal import Decimal

from ninja import Router, Schema, File, UploadedFile
from django.db import DatabaseError, IntegrityError
from django.core.exceptions import ValidationError
from django.http import HttpRequest
from ninja.errors import HttpError

from apps.api.auth import OptionalJWTAuth
from apps.api.ratelimit import ratelimit_api, ratelimit_upload
from .models import RegistroCampo, Evidencia, RegistroAvance
from .tasks import procesar_evidencia
from .validators import validate_evidence_mime_type, validate_signature_mime_type

logger = logging.getLogger(__name__)
router = Router(auth=OptionalJWTAuth())


class RegistroIn(Schema):
    actividad_id: UUID
    datos_formulario: dict[str, Any]
    observaciones: str = ""
    latitud_fin: Decimal
    longitud_fin: Decimal
    porcentaje_avance_reportado: Decimal = Decimal("0")
    tiene_pendiente: bool = False
    tipo_pendiente: str = ""
    descripcion_pendiente: str = ""


class RegistroSyncIn(Schema):
    registros: list[RegistroIn]


class EvidenciaOut(Schema):
    id: UUID
    tipo: str
    url_original: str
    url_thumbnail: str
    latitud: Optional[Decimal]
    longitud: Optional[Decimal]
    fecha_captura: datetime
    es_valida: bool


class RegistroOut(Schema):
    id: UUID
    actividad_id: UUID
    fecha_inicio: datetime
    fecha_fin: Optional[datetime]
    dentro_poligono: Optional[bool]
    sincronizado: bool
    total_evidencias: int
    porcentaje_avance_reportado: Decimal
    tiene_pendiente: bool
    tipo_pendiente: str
    descripcion_pendiente: str


class RegistroDetailOut(RegistroOut):
    datos_formulario: dict[str, Any]
    observaciones: str
    evidencias: list[EvidenciaOut]


class SyncResultOut(Schema):
    id: str
    status: str
    message: str = ""


class ErrorOut(Schema):
    detail: str


@router.get('/registros', response={200: list[RegistroOut], 429: ErrorOut})
@ratelimit_api
def listar_registros(
    request: HttpRequest,
    actividad_id: Optional[UUID] = None
) -> list[RegistroOut]:
    """
    List field records, optionally filtered by activity.

    Rate limited: 100 requests per minute per user.
    """
    qs = RegistroCampo.objects.all()

    if actividad_id:
        qs = qs.filter(actividad_id=actividad_id)

    return [
        RegistroOut(
            id=r.id,
            actividad_id=r.actividad_id,
            fecha_inicio=r.fecha_inicio,
            fecha_fin=r.fecha_fin,
            dentro_poligono=r.dentro_poligono,
            sincronizado=r.sincronizado,
            total_evidencias=r.total_evidencias,
            porcentaje_avance_reportado=r.porcentaje_avance_reportado,
            tiene_pendiente=r.tiene_pendiente,
            tipo_pendiente=r.tipo_pendiente,
            descripcion_pendiente=r.descripcion_pendiente,
        )
        for r in qs
    ]


@router.get('/registros/{registro_id}', response={200: RegistroDetailOut, 429: ErrorOut})
@ratelimit_api
def obtener_registro(request: HttpRequest, registro_id: UUID) -> RegistroDetailOut:
    """
    Get field record details.

    Rate limited: 100 requests per minute per user.
    """
    registro = RegistroCampo.objects.prefetch_related('evidencias').get(id=registro_id)

    evidencias = [
        EvidenciaOut(
            id=e.id,
            tipo=e.tipo,
            url_original=e.url_original,
            url_thumbnail=e.url_thumbnail or e.url_original,
            latitud=e.latitud,
            longitud=e.longitud,
            fecha_captura=e.fecha_captura,
            es_valida=e.es_valida,
        )
        for e in registro.evidencias.all()
    ]

    return RegistroDetailOut(
        id=registro.id,
        actividad_id=registro.actividad_id,
        fecha_inicio=registro.fecha_inicio,
        fecha_fin=registro.fecha_fin,
        dentro_poligono=registro.dentro_poligono,
        sincronizado=registro.sincronizado,
        total_evidencias=registro.total_evidencias,
        datos_formulario=registro.datos_formulario,
        observaciones=registro.observaciones,
        evidencias=evidencias,
        porcentaje_avance_reportado=registro.porcentaje_avance_reportado,
        tiene_pendiente=registro.tiene_pendiente,
        tipo_pendiente=registro.tipo_pendiente,
        descripcion_pendiente=registro.descripcion_pendiente,
    )


@router.post('/registros/sync', response={200: list[SyncResultOut], 429: ErrorOut})
@ratelimit_api
def sincronizar_registros(request: HttpRequest, data: RegistroSyncIn) -> list[SyncResultOut]:
    """
    Sync multiple field records from mobile app.
    Used when device comes back online.

    Rate limited: 100 requests per minute per user.
    """
    from django.utils import timezone
    from apps.actividades.models import Actividad

    resultados: list[SyncResultOut] = []

    for reg in data.registros:
        try:
            registro = RegistroCampo.objects.get(actividad_id=reg.actividad_id)

            # Update record
            registro.datos_formulario = reg.datos_formulario
            registro.observaciones = reg.observaciones
            registro.latitud_fin = reg.latitud_fin
            registro.longitud_fin = reg.longitud_fin
            registro.fecha_fin = timezone.now()
            registro.sincronizado = True
            registro.fecha_sincronizacion = timezone.now()
            # New fields for avance and pendientes
            registro.porcentaje_avance_reportado = reg.porcentaje_avance_reportado
            registro.tiene_pendiente = reg.tiene_pendiente
            registro.tipo_pendiente = reg.tipo_pendiente
            registro.descripcion_pendiente = reg.descripcion_pendiente
            registro.save()

            # Update activity status and avance
            actividad = registro.actividad
            # Update porcentaje_avance if reported avance is higher
            if reg.porcentaje_avance_reportado > actividad.porcentaje_avance:
                actividad.porcentaje_avance = reg.porcentaje_avance_reportado
            # Mark as completed only if 100% advance
            if reg.porcentaje_avance_reportado >= 100:
                actividad.estado = Actividad.Estado.COMPLETADA
            actividad.save(update_fields=['estado', 'porcentaje_avance', 'updated_at'])

            resultados.append(SyncResultOut(
                id=str(reg.actividad_id),
                status='ok',
                message='Sincronizado correctamente'
            ))

        except RegistroCampo.DoesNotExist:
            resultados.append(SyncResultOut(
                id=str(reg.actividad_id),
                status='error',
                message='Registro no encontrado'
            ))
        except (DatabaseError, IntegrityError) as e:
            logger.error(f"Database error syncing record {reg.actividad_id}: {e}")
            resultados.append(SyncResultOut(
                id=str(reg.actividad_id),
                status='error',
                message=f'Error de base de datos: {str(e)[:100]}'
            ))
        except (ValueError, TypeError, KeyError) as e:
            logger.warning(f"Data validation error syncing record {reg.actividad_id}: {e}")
            resultados.append(SyncResultOut(
                id=str(reg.actividad_id),
                status='error',
                message=f'Error de validacion: {str(e)}'
            ))

    return resultados


@router.post('/evidencias/upload', response={200: dict, 429: ErrorOut})
@ratelimit_upload
def subir_evidencia(
    request: HttpRequest,
    registro_id: UUID,
    tipo: str,
    latitud: Decimal,
    longitud: Decimal,
    fecha_captura: datetime,
    archivo: UploadedFile = File(...)
) -> dict[str, str]:
    """
    Upload a photo evidence.
    Triggers async processing for thumbnail and AI validation.

    Validates MIME type using magic bytes to ensure file is a valid image
    (JPEG, PNG, or WebP). Does not rely on file extension.

    Rate limited: 20 requests per minute per user.
    """
    from apps.core.utils import upload_to_gcs
    from django.utils import timezone
    import uuid as uuid_module
    import magic

    # Read file content for validation
    file_content = archivo.read()

    # Validate MIME type using magic bytes (security check)
    try:
        validate_evidence_mime_type(file_content, archivo.name)
    except ValidationError as e:
        logger.warning(
            f"MIME type validation failed for evidence upload: "
            f"user={request.auth.id}, file={archivo.name}, error={e.message}"
        )
        raise HttpError(400, str(e.message))

    registro = RegistroCampo.objects.get(id=registro_id)

    # Generate unique filename with validated extension
    # Map MIME types to extensions (we know the file is valid at this point)
    detected_mime = magic.from_buffer(file_content, mime=True)
    mime_to_ext: dict[str, str] = {
        'image/jpeg': 'jpg',
        'image/png': 'png',
        'image/webp': 'webp',
    }
    extension = mime_to_ext.get(detected_mime, 'jpg')
    filename = f"{uuid_module.uuid4()}.{extension}"
    path = f"evidencias/{registro_id}/{tipo}/{filename}"

    # Upload to cloud storage
    url = upload_to_gcs(file_content, path)

    # Create evidence record
    evidencia = Evidencia.objects.create(
        registro_campo=registro,
        tipo=tipo,
        url_original=url,
        latitud=latitud,
        longitud=longitud,
        fecha_captura=fecha_captura,
    )

    # Trigger async processing (thumbnail, AI validation)
    procesar_evidencia.delay(str(evidencia.id))

    return {
        'id': str(evidencia.id),
        'url': url,
        'status': 'processing'
    }


@router.post('/registros/{registro_id}/firma', response={200: dict, 429: ErrorOut})
@ratelimit_upload
def subir_firma(
    request: HttpRequest,
    registro_id: UUID,
    archivo: UploadedFile = File(...)
) -> dict[str, str]:
    """
    Upload signature for a field record.

    Validates that the file is a valid PNG image using magic bytes.
    Signatures must be PNG format (typically with transparency support).

    Rate limited: 20 requests per minute per user.
    """
    from apps.core.utils import upload_to_gcs

    # Read file content for validation
    file_content = archivo.read()

    # Validate MIME type - signatures must be PNG
    try:
        validate_signature_mime_type(file_content, archivo.name)
    except ValidationError as e:
        logger.warning(
            f"MIME type validation failed for signature upload: "
            f"user={request.auth.id}, file={archivo.name}, error={e.message}"
        )
        raise HttpError(400, str(e.message))

    registro = RegistroCampo.objects.get(id=registro_id)

    # Upload signature (always PNG after validation)
    path = f"firmas/{registro_id}/firma.png"
    url = upload_to_gcs(file_content, path)

    registro.firma_responsable_url = url
    registro.save(update_fields=['firma_responsable_url', 'updated_at'])

    return {'url': url}


# ============================================================================
# API Endpoints para Avances de Vanos - Agregado 1 abril 2026
# ============================================================================

class VanoOut(Schema):
    """Schema de salida para un vano."""
    id: UUID
    numero_vano: int
    estado: str
    torre_inicio_numero: str
    torre_fin_numero: str
    es_apoyo: bool
    marcado_por_nombre: Optional[str]
    fecha_marcado: Optional[datetime]
    observaciones: str
    aprobado: bool


class ActividadVanosOut(Schema):
    """Schema de salida para actividad con vanos."""
    actividad_id: UUID
    tipo: str
    linea_codigo: str
    avance: float
    vanos: list[VanoOut]


class MarcarVanoIn(Schema):
    """Schema de entrada para marcar un vano."""
    estado: str
    observaciones: str = ""


@router.get('/cuadrilla/avances', response=ActividadVanosOut, tags=['Vanos'])
@ratelimit_api
def listar_avances_cuadrilla(request: HttpRequest):
    """
    Lista los vanos de la cuadrilla del usuario autenticado.

    Retorna la actividad activa con todos los vanos asignados a la cuadrilla.
    """
    from apps.cuadrillas.models import CuadrillaMiembro
    from apps.actividades.models import Actividad
    from .models import AvanceVano

    # Obtener cuadrilla del usuario
    miembro = CuadrillaMiembro.objects.filter(
        usuario=request.auth,
        activo=True,
        cuadrilla__activa=True
    ).select_related('cuadrilla').first()

    if not miembro:
        raise HttpError(400, 'Usuario no asignado a cuadrilla activa')

    cuadrilla = miembro.cuadrilla

    # Obtener actividad activa
    actividad = Actividad.objects.filter(
        cuadrillas=cuadrilla,
        estado__in=['PROGRAMADA', 'EN_CURSO']
    ).select_related('linea', 'tipo_actividad').first()

    if not actividad:
        raise HttpError(404, 'Sin actividades asignadas')

    # Obtener vanos
    vanos = actividad.avances_vanos.filter(
        cuadrilla=cuadrilla
    ).select_related('torre_inicio', 'torre_fin', 'marcado_por', 'cuadrilla_asignada_original')

    vanos_list = []
    for v in vanos:
        vanos_list.append({
            'id': v.id,
            'numero_vano': v.numero_vano,
            'estado': v.estado,
            'torre_inicio_numero': v.torre_inicio.numero,
            'torre_fin_numero': v.torre_fin.numero,
            'es_apoyo': v.es_apoyo,
            'marcado_por_nombre': v.marcado_por.get_full_name() if v.marcado_por else None,
            'fecha_marcado': v.fecha_marcado,
            'observaciones': v.observaciones,
            'aprobado': v.aprobado,
        })

    return {
        'actividad_id': actividad.id,
        'tipo': actividad.tipo_actividad.nombre,
        'linea_codigo': actividad.linea.codigo,
        'avance': float(actividad.porcentaje_avance),
        'vanos': vanos_list,
    }


@router.post('/vanos/{vano_id}/marcar', response={200: dict}, tags=['Vanos'])
@ratelimit_api
def marcar_vano_api(request: HttpRequest, vano_id: UUID, payload: MarcarVanoIn):
    """
    Marca el estado de un vano.

    Estados válidos: pendiente, ejecutado, sin_permiso, no_ejecutado, en_espera
    """
    from .models import AvanceVano
    from apps.cuadrillas.models import CuadrillaMiembro
    from django.utils import timezone

    vano = AvanceVano.objects.select_related('cuadrilla', 'actividad').get(id=vano_id)

    # Validar que usuario pertenece a la cuadrilla
    es_miembro = CuadrillaMiembro.objects.filter(
        usuario=request.auth,
        cuadrilla=vano.cuadrilla,
        activo=True
    ).exists()

    if not es_miembro:
        raise HttpError(403, 'No autorizado para modificar este vano')

    # Validar estado
    estados_validos = dict(AvanceVano.Estado.choices).keys()
    if payload.estado not in estados_validos:
        raise HttpError(400, f'Estado inválido. Estados permitidos: {", ".join(estados_validos)}')

    # Actualizar vano
    vano.estado = payload.estado
    vano.marcado_por = request.auth
    vano.fecha_marcado = timezone.now()
    vano.observaciones = payload.observaciones
    vano.save()

    # Recalcular avance si se marcó como ejecutado
    if payload.estado == 'ejecutado':
        vano.actividad.recalcular_avance()

    return {
        'success': True,
        'vano_id': str(vano.id),
        'nuevo_estado': vano.estado,
        'fecha_marcado': vano.fecha_marcado.isoformat(),
    }


# ==================== REGISTRO DE AVANCES ====================

class RegistroAvanceIn(Schema):
    """Schema para crear un registro de avance."""
    torre_id: UUID
    tipo_avance: str = "completo"
    observaciones: str = ""
    porcentaje: int = 100


class RegistroAvanceOut(Schema):
    """Schema para respuesta de registro de avance."""
    id: UUID
    usuario_id: UUID
    usuario_nombre: str
    cuadrilla_id: UUID
    cuadrilla_nombre: str
    linea_id: UUID
    linea_codigo: str
    torre_id: UUID
    torre_numero: str
    tipo_avance: str
    fecha_avance: datetime
    observaciones: str
    porcentaje: int


@router.post('/avances', response={201: RegistroAvanceOut}, tags=['Avances'])
@ratelimit_api
def crear_registro_avance(request: HttpRequest, data: RegistroAvanceIn):
    """
    Crear un registro de avance en una torre.
    El usuario debe estar asignado a una cuadrilla.
    Solo puede registrar avances en la línea de su cuadrilla.

    Parámetros:
    - torre_id: UUID de la torre
    - tipo_avance: 'completo', 'parcial', 'sin_avance', 'no_ejecutable'
    - observaciones: Detalles del avance (opcional)
    - porcentaje: Porcentaje completado 0-100 (default: 100)
    """
    from apps.cuadrillas.models import CuadrillaMiembro
    from apps.lineas.models import Torre
    from django.utils import timezone

    if not request.auth:
        raise HttpError(401, 'Autenticación requerida')

    usuario = request.auth

    # Obtener cuadrilla del usuario
    miembro = CuadrillaMiembro.objects.filter(
        usuario=usuario,
        activo=True
    ).select_related('cuadrilla', 'cuadrilla__linea_asignada').first()

    if not miembro:
        raise HttpError(403, 'No estás asignado a ninguna cuadrilla activa')

    cuadrilla = miembro.cuadrilla
    linea = cuadrilla.linea_asignada

    if not linea:
        raise HttpError(400, 'Tu cuadrilla no tiene una línea asignada')

    # Obtener y validar torre
    try:
        torre = Torre.objects.get(id=data.torre_id, linea=linea)
    except Torre.DoesNotExist:
        raise HttpError(400, 'La torre no pertenece a la línea de tu cuadrilla')

    # Validar tipo de avance
    tipos_validos = dict(RegistroAvance.TipoAvance.choices).keys()
    tipo_avance = data.tipo_avance if data.tipo_avance in tipos_validos else 'completo'

    # Validar porcentaje
    porcentaje = max(0, min(100, data.porcentaje))

    # Crear registro
    try:
        registro = RegistroAvance.objects.create(
            usuario=usuario,
            cuadrilla=cuadrilla,
            linea=linea,
            torre=torre,
            tipo_avance=tipo_avance,
            observaciones=data.observaciones.strip(),
            porcentaje=porcentaje
        )

        return 201, RegistroAvanceOut(
            id=registro.id,
            usuario_id=registro.usuario.id,
            usuario_nombre=registro.usuario.get_full_name(),
            cuadrilla_id=registro.cuadrilla.id,
            cuadrilla_nombre=registro.cuadrilla.nombre,
            linea_id=registro.linea.id,
            linea_codigo=registro.linea.codigo,
            torre_id=registro.torre.id,
            torre_numero=registro.torre.numero,
            tipo_avance=registro.tipo_avance,
            fecha_avance=registro.fecha_avance,
            observaciones=registro.observaciones,
            porcentaje=registro.porcentaje,
        )
    except Exception as e:
        logger.error(f"Error crear registro avance: {str(e)}")
        raise HttpError(500, f'Error al registrar avance: {str(e)}')


@router.get('/avances', response=list[RegistroAvanceOut], tags=['Avances'])
def listar_avances(
    request: HttpRequest,
    usuario_id: Optional[UUID] = None,
    cuadrilla_id: Optional[UUID] = None,
    linea_id: Optional[UUID] = None,
    tipo_avance: Optional[str] = None,
    limite: int = 50
):
    """
    Listar registros de avance con filtros opcionales.

    Parámetros:
    - usuario_id: Filtrar por usuario específico
    - cuadrilla_id: Filtrar por cuadrilla
    - linea_id: Filtrar por línea
    - tipo_avance: Filtrar por tipo ('completo', 'parcial', etc)
    - limite: Máximo de registros (default: 50, máximo: 500)
    """
    from apps.cuadrillas.models import CuadrillaMiembro

    qs = RegistroAvance.objects.select_related(
        'usuario', 'cuadrilla', 'linea', 'torre'
    ).order_by('-fecha_avance')

    # Si no es admin, solo ver propios avances o de su cuadrilla
    if request.auth and not request.auth.is_admin:
        miembro = CuadrillaMiembro.objects.filter(
            usuario=request.auth,
            activo=True
        ).first()
        if miembro:
            qs = qs.filter(cuadrilla=miembro.cuadrilla)
        else:
            qs = qs.filter(usuario=request.auth)

    # Aplicar filtros
    if usuario_id:
        qs = qs.filter(usuario_id=usuario_id)

    if cuadrilla_id:
        qs = qs.filter(cuadrilla_id=cuadrilla_id)

    if linea_id:
        qs = qs.filter(linea_id=linea_id)

    if tipo_avance:
        tipos_validos = dict(RegistroAvance.TipoAvance.choices).keys()
        if tipo_avance in tipos_validos:
            qs = qs.filter(tipo_avance=tipo_avance)

    # Limitar resultados
    limite = min(limite, 500)
    qs = qs[:limite]

    return [
        RegistroAvanceOut(
            id=r.id,
            usuario_id=r.usuario.id,
            usuario_nombre=r.usuario.get_full_name(),
            cuadrilla_id=r.cuadrilla.id,
            cuadrilla_nombre=r.cuadrilla.nombre,
            linea_id=r.linea.id,
            linea_codigo=r.linea.codigo,
            torre_id=r.torre.id,
            torre_numero=r.torre.numero,
            tipo_avance=r.tipo_avance,
            fecha_avance=r.fecha_avance,
            observaciones=r.observaciones,
            porcentaje=r.porcentaje,
        )
        for r in qs
    ]
