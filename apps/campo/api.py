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

from apps.api.auth import JWTAuth
from apps.api.ratelimit import ratelimit_api, ratelimit_upload
from .models import RegistroCampo, Evidencia
from .tasks import procesar_evidencia
from .validators import validate_evidence_mime_type, validate_signature_mime_type

logger = logging.getLogger(__name__)
router = Router(auth=JWTAuth())


class RegistroIn(Schema):
    actividad_id: UUID
    datos_formulario: dict[str, Any]
    observaciones: str = ""
    latitud_fin: Decimal
    longitud_fin: Decimal


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
            registro.save()

            # Update activity status
            actividad = registro.actividad
            actividad.estado = Actividad.Estado.COMPLETADA
            actividad.save(update_fields=['estado', 'updated_at'])

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
