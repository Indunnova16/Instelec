import hashlib
import requests
from django.conf import settings


def get_base_url():
    if getattr(settings, 'WOMPI_SANDBOX', True):
        return 'https://sandbox.wompi.co/v1'
    return 'https://production.wompi.co/v1'


def get_headers():
    return {
        'Authorization': f'Bearer {settings.WOMPI_PRIVATE_KEY}',
        'Content-Type': 'application/json',
    }


def get_acceptance_token():
    url = f"{get_base_url()}/merchants/{settings.WOMPI_PUBLIC_KEY}"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()['data']['presigned_acceptance']['acceptance_token']


def get_transaction(transaction_id):
    url = f"{get_base_url()}/transactions/{transaction_id}"
    resp = requests.get(url, headers=get_headers(), timeout=10)
    resp.raise_for_status()
    return resp.json()


def verify_webhook_signature(event_data):
    try:
        props = event_data.get('signature', {}).get('properties', [])
        timestamp = event_data.get('timestamp', '')
        values = []
        for prop in props:
            keys = prop.split('.')
            val = event_data.get('data', {})
            for k in keys:
                val = val.get(k, '') if isinstance(val, dict) else ''
            values.append(str(val))
        values.append(str(timestamp))
        concat = ''.join(values) + settings.WOMPI_EVENTS_KEY
        computed = hashlib.sha256(concat.encode()).hexdigest()
        received = event_data.get('signature', {}).get('checksum', '')
        return computed == received
    except Exception:
        return False


def listar_transacciones(from_date, until_date, page_size=200):
    """Lista transacciones del merchant entre 2 fechas (paginado completo).

    OJO: el merchant de WOMPI es COMPARTIDO por todo el portafolio Indunnova
    (una sola cuenta, un solo wompi-router) -- esto devuelve transacciones de
    TODAS las apps. Filtrar por prefijo de referencia (WOMPI_REFERENCE_PREFIX)
    antes de usar. Formato de fecha: 'YYYY-MM-DDTHH:MM:SS'.
    """
    txs = []
    page = 1
    while True:
        resp = requests.get(
            f"{get_base_url()}/transactions",
            headers=get_headers(),
            params={
                'from_date': from_date,
                'until_date': until_date,
                'page_size': page_size,
                'page': page,
            },
            timeout=20,
        )
        resp.raise_for_status()
        payload = resp.json()
        data = payload.get('data', [])
        txs.extend(data)
        total = payload.get('meta', {}).get('total_results', len(txs))
        if len(data) < page_size or len(txs) >= total:
            break
        page += 1
    return txs
