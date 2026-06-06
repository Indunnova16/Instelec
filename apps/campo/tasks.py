"""
Celery tasks for field data processing.
"""
from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def procesar_evidencia(self, evidencia_id: str):
    """
    Process uploaded evidence:
    1. Generate thumbnail
    2. Run AI validation (blur, lighting)
    3. Stamp metadata on image
    """
    from apps.campo.models import Evidencia
    from apps.core.utils import upload_to_gcs, download_from_gcs
    from PIL import Image
    import io

    try:
        evidencia = Evidencia.objects.get(id=evidencia_id)
        logger.info(f"Processing evidence {evidencia_id}")

        # Download original image
        imagen_bytes = download_from_gcs(evidencia.url_original)
        imagen = Image.open(io.BytesIO(imagen_bytes))

        # 1. Generate thumbnail
        thumb = imagen.copy()
        thumb.thumbnail((400, 400), Image.Resampling.LANCZOS)

        thumb_buffer = io.BytesIO()
        thumb.save(thumb_buffer, format='JPEG', quality=85)
        thumb_buffer.seek(0)

        thumb_path = evidencia.url_original.replace('/evidencias/', '/thumbs/')
        thumb_url = upload_to_gcs(thumb_buffer.getvalue(), thumb_path)

        # 2. AI Validation (simplified - in production use TensorFlow)
        validacion = validar_imagen_simple(imagen)

        # 3. Update evidence record
        evidencia.url_thumbnail = thumb_url
        evidencia.validacion_ia = validacion
        evidencia.save(update_fields=['url_thumbnail', 'validacion_ia', 'updated_at'])

        logger.info(f"Evidence {evidencia_id} processed successfully")
        return {'status': 'ok', 'validacion': validacion}

    except Evidencia.DoesNotExist:
        logger.error(f"Evidence {evidencia_id} not found")
        return {'status': 'error', 'message': 'Evidence not found'}
    except (IOError, OSError) as e:
        logger.error(f"I/O error processing evidence {evidencia_id}: {e}")
        self.retry(exc=e)
    except (ValueError, TypeError) as e:
        logger.error(f"Data error processing evidence {evidencia_id}: {e}")
        self.retry(exc=e)


def validar_imagen_simple(imagen: 'Image') -> dict:
    """
    Simple image validation.
    In production, this would use a TensorFlow Lite model.
    """
    import numpy as np

    # Convert to numpy array
    img_array = np.array(imagen)

    # Calculate basic metrics
    # Brightness (simple average)
    brightness = np.mean(img_array) / 255.0

    # Contrast (standard deviation)
    contrast = np.std(img_array) / 128.0

    # Blur detection (Laplacian variance)
    # Simplified version - in production use cv2.Laplacian
    gray = np.mean(img_array, axis=2) if len(img_array.shape) == 3 else img_array
    laplacian_var = np.var(np.gradient(np.gradient(gray)))
    nitidez = min(laplacian_var / 500.0, 1.0)

    # Determine if image is valid
    es_valida = (
        brightness > 0.15 and brightness < 0.95 and  # Not too dark or bright
        nitidez > 0.3 and  # Not too blurry
        contrast > 0.1  # Has some contrast
    )

    mensaje = "Imagen válida" if es_valida else ""
    if not es_valida:
        if brightness < 0.15:
            mensaje = "Imagen muy oscura"
        elif brightness > 0.95:
            mensaje = "Imagen sobreexpuesta"
        elif nitidez < 0.3:
            mensaje = "Imagen borrosa"
        elif contrast < 0.1:
            mensaje = "Imagen sin contraste suficiente"

    return {
        'valida': es_valida,
        'nitidez': round(nitidez, 2),
        'iluminacion': round(brightness, 2),
        'contraste': round(contrast, 2),
        'mensaje': mensaje,
    }


@shared_task
def estampar_metadata_imagen(evidencia_id: str):
    """
    Stamp date, time, and coordinates on image.
    """
    from apps.campo.models import Evidencia
    from apps.core.utils import upload_to_gcs, download_from_gcs
    from PIL import Image, ImageDraw, ImageFont
    import io

    evidencia = Evidencia.objects.select_related(
        'registro_campo__actividad__torre',
        'registro_campo__actividad__linea'
    ).get(id=evidencia_id)

    # Download original
    imagen_bytes = download_from_gcs(evidencia.url_original)
    imagen = Image.open(io.BytesIO(imagen_bytes))

    # Add stamp
    draw = ImageDraw.Draw(imagen)

    # Prepare text
    torre = evidencia.registro_campo.actividad.torre
    linea = evidencia.registro_campo.actividad.linea

    texto = f"""Torre: {torre.numero_display} | Línea: {linea.codigo}
Fecha: {evidencia.fecha_captura.strftime('%Y-%m-%d %H:%M')}
GPS: {evidencia.latitud}, {evidencia.longitud}
Tipo: {evidencia.get_tipo_display()}"""

    # Draw background rectangle
    bbox = draw.textbbox((10, imagen.height - 100), texto)
    draw.rectangle(
        [bbox[0] - 5, bbox[1] - 5, bbox[2] + 5, bbox[3] + 5],
        fill=(0, 0, 0, 180)
    )

    # Draw text
    draw.text(
        (10, imagen.height - 100),
        texto,
        fill=(255, 255, 255),
    )

    # Save stamped image
    buffer = io.BytesIO()
    imagen.save(buffer, format='JPEG', quality=90)
    buffer.seek(0)

    path = evidencia.url_original.replace('/evidencias/', '/estampadas/')
    url = upload_to_gcs(buffer.getvalue(), path)

    evidencia.url_estampada = url
    evidencia.save(update_fields=['url_estampada', 'updated_at'])

    return {'url': url}
