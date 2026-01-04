"""
Core utility functions for GCP integration and general utilities.

Includes:
- Google Cloud Storage upload/download
- Google Secret Manager access
- Google Cloud Tasks integration
- Formatting utilities
"""
from django.conf import settings
from functools import lru_cache
import io
import json
import logging
import os

logger = logging.getLogger(__name__)


# =============================================================================
# Google Cloud Storage Functions
# =============================================================================

def get_storage_client():
    """Get GCS client, creating if necessary."""
    from google.cloud import storage
    return storage.Client(project=getattr(settings, 'GS_PROJECT_ID', None))


def upload_to_gcs(file_content, destination_path: str) -> str:
    """
    Upload file to Google Cloud Storage.

    Args:
        file_content: File content (bytes or file-like object)
        destination_path: Path in the bucket (e.g., 'evidencias/123/foto.jpg')

    Returns:
        Public URL of the uploaded file
    """
    if not settings.GS_BUCKET_NAME:
        # Local development - save to media folder
        from django.core.files.storage import default_storage
        path = default_storage.save(destination_path, io.BytesIO(file_content))
        return default_storage.url(path)

    client = storage.Client(project=settings.GS_PROJECT_ID)
    bucket = client.bucket(settings.GS_BUCKET_NAME)
    blob = bucket.blob(destination_path)

    if isinstance(file_content, bytes):
        blob.upload_from_string(file_content)
    else:
        blob.upload_from_file(file_content)

    blob.make_public()
    return blob.public_url


def download_from_gcs(url: str) -> bytes:
    """
    Download file from Google Cloud Storage.

    Args:
        url: Public URL or gs:// path

    Returns:
        File content as bytes
    """
    if not settings.GS_BUCKET_NAME:
        # Local development
        import requests
        response = requests.get(url)
        return response.content

    # Parse bucket and blob name from URL
    if url.startswith('https://storage.googleapis.com/'):
        path = url.replace('https://storage.googleapis.com/', '')
        bucket_name, blob_name = path.split('/', 1)
    else:
        bucket_name = settings.GS_BUCKET_NAME
        blob_name = url

    client = storage.Client(project=settings.GS_PROJECT_ID)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    return blob.download_as_bytes()


def format_currency(value, currency='COP'):
    """Format number as currency."""
    if value is None:
        return '-'
    if currency == 'COP':
        return f"${value:,.0f}".replace(',', '.')
    return f"${value:,.2f}"


def format_percentage(value, decimals=1):
    """Format number as percentage."""
    if value is None:
        return '-'
    return f"{value:.{decimals}f}%"


def truncate_string(text: str, max_length: int = 50) -> str:
    """Truncate string with ellipsis."""
    if not text:
        return ''
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + '...'


# =============================================================================
# Google Secret Manager Functions
# =============================================================================

@lru_cache(maxsize=32)
def get_secret(secret_id: str, version: str = 'latest') -> str:
    """
    Retrieve a secret from Google Secret Manager.

    Args:
        secret_id: The ID of the secret (e.g., 'DATABASE_URL')
        version: Secret version (default: 'latest')

    Returns:
        The secret value as a string

    Raises:
        Exception if secret cannot be retrieved
    """
    project_id = getattr(settings, 'GS_PROJECT_ID', None) or os.environ.get('GOOGLE_CLOUD_PROJECT')

    if not project_id:
        # Local development - use environment variable directly
        return os.environ.get(secret_id, '')

    try:
        from google.cloud import secretmanager

        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_id}/versions/{version}"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")

    except Exception as e:
        logger.error(f"Error retrieving secret {secret_id}: {e}")
        # Fallback to environment variable
        return os.environ.get(secret_id, '')


def get_secret_json(secret_id: str, version: str = 'latest') -> dict:
    """
    Retrieve a JSON secret from Google Secret Manager.

    Args:
        secret_id: The ID of the secret
        version: Secret version (default: 'latest')

    Returns:
        The secret value as a dictionary
    """
    secret_value = get_secret(secret_id, version)
    try:
        return json.loads(secret_value)
    except json.JSONDecodeError:
        logger.error(f"Secret {secret_id} is not valid JSON")
        return {}


# =============================================================================
# Google Cloud Tasks Functions
# =============================================================================

def create_cloud_task(
    queue_name: str,
    url: str,
    payload: dict = None,
    schedule_time: int = None,
    task_name: str = None
) -> str:
    """
    Create a Cloud Task to execute an HTTP request.

    Args:
        queue_name: Name of the Cloud Tasks queue
        url: HTTP URL to call
        payload: JSON payload for the request
        schedule_time: Unix timestamp for scheduled execution
        task_name: Optional unique task name

    Returns:
        The name of the created task
    """
    project_id = getattr(settings, 'GS_PROJECT_ID', None)
    location = getattr(settings, 'GCP_REGION', 'us-central1')

    if not project_id:
        logger.warning("Cloud Tasks not available in local development")
        return None

    try:
        from google.cloud import tasks_v2
        from google.protobuf import timestamp_pb2

        client = tasks_v2.CloudTasksClient()
        parent = client.queue_path(project_id, location, queue_name)

        task = {
            'http_request': {
                'http_method': tasks_v2.HttpMethod.POST,
                'url': url,
                'headers': {'Content-Type': 'application/json'},
            }
        }

        if payload:
            task['http_request']['body'] = json.dumps(payload).encode()

        if schedule_time:
            timestamp = timestamp_pb2.Timestamp()
            timestamp.FromSeconds(schedule_time)
            task['schedule_time'] = timestamp

        if task_name:
            task['name'] = client.task_path(project_id, location, queue_name, task_name)

        response = client.create_task(parent=parent, task=task)
        logger.info(f"Created task: {response.name}")
        return response.name

    except Exception as e:
        logger.error(f"Error creating Cloud Task: {e}")
        raise


# =============================================================================
# Google Cloud Pub/Sub Functions
# =============================================================================

def publish_message(topic_id: str, message: dict, attributes: dict = None) -> str:
    """
    Publish a message to a Pub/Sub topic.

    Args:
        topic_id: The Pub/Sub topic ID
        message: Message data as dictionary
        attributes: Optional message attributes

    Returns:
        The message ID
    """
    project_id = getattr(settings, 'GS_PROJECT_ID', None)

    if not project_id:
        logger.warning("Pub/Sub not available in local development")
        return None

    try:
        from google.cloud import pubsub_v1

        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(project_id, topic_id)

        data = json.dumps(message).encode('utf-8')
        future = publisher.publish(topic_path, data, **(attributes or {}))
        message_id = future.result()

        logger.info(f"Published message {message_id} to {topic_id}")
        return message_id

    except Exception as e:
        logger.error(f"Error publishing to Pub/Sub: {e}")
        raise


# =============================================================================
# Cloud Run Utilities
# =============================================================================

def get_service_url(service_name: str = None) -> str:
    """
    Get the URL of a Cloud Run service.

    Args:
        service_name: Name of the service (default: current service)

    Returns:
        The service URL
    """
    # Check if running in Cloud Run
    if 'K_SERVICE' in os.environ:
        if service_name is None or service_name == os.environ.get('K_SERVICE'):
            # Return URL of current service
            return f"https://{os.environ.get('K_SERVICE')}-{os.environ.get('K_REVISION', '')}.run.app"

    # For production, use configured base URL
    return getattr(settings, 'SITE_URL', 'http://localhost:8000')


def is_cloud_run() -> bool:
    """Check if running in Cloud Run environment."""
    return 'K_SERVICE' in os.environ


def get_instance_id() -> str:
    """Get the Cloud Run instance ID."""
    return os.environ.get('K_REVISION', 'local')


# =============================================================================
# Logging Utilities for Cloud Logging
# =============================================================================

def log_structured(severity: str, message: str, **kwargs):
    """
    Log a structured message for Google Cloud Logging.

    Args:
        severity: Log severity (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        message: Log message
        **kwargs: Additional fields to include
    """
    import json
    import sys

    if is_cloud_run():
        # Structured logging for Cloud Run
        log_entry = {
            'severity': severity.upper(),
            'message': message,
            **kwargs
        }
        print(json.dumps(log_entry), file=sys.stdout if severity != 'ERROR' else sys.stderr)
    else:
        # Standard logging for local development
        log_func = getattr(logger, severity.lower(), logger.info)
        log_func(f"{message} - {kwargs}" if kwargs else message)
