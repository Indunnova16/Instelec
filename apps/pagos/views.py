import hashlib
import json
import logging
import uuid
from calendar import monthrange
from datetime import date
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView, ListView
from .models import PlanServicio, Suscripcion, Pago, DatosFacturacion
from . import wompi
from . import alegra

logger = logging.getLogger(__name__)


def _avanzar_fecha_proximo_pago(suscripcion, monto_pagado):
    """Avanza fecha_proximo_pago N meses segun monto/precio plan. Mantiene dia 20."""
    plan = suscripcion.plan
    if not plan or plan.precio <= 0:
        return
    meses = max(1, int(round(Decimal(str(monto_pagado)) / plan.precio)))
    actual = suscripcion.fecha_proximo_pago or timezone.localdate()
    y, m = actual.year, actual.month
    m += meses
    while m > 12:
        m -= 12
        y += 1
    dia = min(20, monthrange(y, m)[1])
    suscripcion.fecha_proximo_pago = date(y, m, dia)
    suscripcion.save(update_fields=['fecha_proximo_pago', 'estado', 'updated_at'])
    logger.info(
        f'Suscripcion {suscripcion.id}: avanzada {meses} mes(es), '
        f'proximo pago = {suscripcion.fecha_proximo_pago}'
    )


class DatosFacturacionView(LoginRequiredMixin, TemplateView):
    template_name = 'pagos/datos_facturacion.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        suscripcion = Suscripcion.objects.first()
        datos = suscripcion.datos_facturacion if suscripcion else None
        if datos:
            context['d'] = {
                'tipo_persona': datos.tipo_persona,
                'razon_social': datos.razon_social,
                'tipo_identificacion': datos.tipo_identificacion,
                'numero_identificacion': datos.numero_identificacion,
                'dv': datos.dv or '',
                'email': datos.email,
                'telefono': datos.telefono,
                'direccion': datos.direccion,
                'ciudad': datos.ciudad,
                'departamento': datos.departamento,
                'regimen': datos.regimen,
            }
        else:
            context['d'] = {
                'tipo_persona': '',
                'razon_social': '',
                'tipo_identificacion': 'CC',
                'numero_identificacion': '',
                'dv': '',
                'email': '',
                'telefono': '',
                'direccion': '',
                'ciudad': '',
                'departamento': '',
                'regimen': 'COMMON_REGIME',
            }
        return context

    def post(self, request, *args, **kwargs):
        suscripcion = Suscripcion.objects.first()
        if not suscripcion:
            messages.error(request, 'No hay suscripcion activa.')
            return redirect('pagos:portal')

        fields = [
            'tipo_persona', 'razon_social', 'tipo_identificacion',
            'numero_identificacion', 'dv', 'email', 'telefono',
            'direccion', 'ciudad', 'departamento', 'regimen',
        ]
        data = {f: request.POST.get(f, '').strip() for f in fields}

        # Basic validation
        required = ['tipo_persona', 'razon_social', 'tipo_identificacion',
                     'numero_identificacion', 'email', 'telefono',
                     'direccion', 'ciudad', 'departamento']
        missing = [f for f in required if not data[f]]
        if missing:
            messages.error(request, 'Por favor complete todos los campos obligatorios.')
            return self.get(request, *args, **kwargs)

        # Create or update DatosFacturacion
        if suscripcion.datos_facturacion:
            datos = suscripcion.datos_facturacion
            for key, val in data.items():
                setattr(datos, key, val)
            datos.save()
        else:
            datos = DatosFacturacion.objects.create(**data)
            suscripcion.datos_facturacion = datos
            suscripcion.save(update_fields=['datos_facturacion'])

        messages.success(request, 'Datos de facturacion guardados correctamente.')
        return redirect('pagos:portal')


class PagoPortalView(LoginRequiredMixin, TemplateView):
    template_name = 'pagos/portal.html'

    def get(self, request, *args, **kwargs):
        # Process WOMPI redirect with transaction ID
        tx_id = request.GET.get('id')
        if tx_id:
            self._procesar_transaccion_wompi(tx_id)
        return super().get(request, *args, **kwargs)

    def _procesar_transaccion_wompi(self, tx_id):
        # Skip if already processed
        if Pago.objects.filter(wompi_transaction_id=tx_id).exists():
            return

        try:
            # wompi.get_transaction returns full json, need ['data'] for transaction
            resp = wompi.get_transaction(tx_id)
            tx = resp['data']
            status = tx.get('status')
            amount = tx.get('amount_in_cents', 0) / 100
            reference = tx.get('reference', '')

            suscripcion = Suscripcion.objects.first()
            if not suscripcion:
                return

            estado_map = {
                'APPROVED': 'APROBADO',
                'DECLINED': 'RECHAZADO',
                'ERROR': 'ERROR',
                'PENDING': 'PENDIENTE',
                'VOIDED': 'RECHAZADO',
            }

            pago = Pago.objects.create(
                suscripcion=suscripcion,
                monto=amount,
                estado=estado_map.get(status, 'PENDIENTE'),
                wompi_transaction_id=tx_id,
                wompi_reference=reference,
                detalle_respuesta=tx,
            )

            if status == 'APPROVED':
                suscripcion.estado = 'ACTIVA'
                _avanzar_fecha_proximo_pago(suscripcion, amount)
                try:
                    alegra.generar_factura_desde_pago(pago)
                except Exception as e:
                    logger.error(f'Error generando factura Alegra: {e}')

            logger.info(f'Pago {pago.id} creado desde redirect WOMPI tx={tx_id} status={status}')
        except Exception as e:
            logger.error(f'Error procesando transaccion WOMPI {tx_id}: {e}')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        suscripcion = Suscripcion.objects.select_related('plan').first()
        context['suscripcion'] = suscripcion
        context['plan'] = suscripcion.plan if suscripcion else PlanServicio.objects.filter(activo=True).first()
        context['wompi_public_key'] = settings.WOMPI_PUBLIC_KEY
        context['wompi_sandbox'] = getattr(settings, 'WOMPI_SANDBOX', True)
        plan = context['plan']

        meses_adeudados = 1
        if suscripcion and suscripcion.fecha_proximo_pago and suscripcion.estado != 'ACTIVA':
            delta = (timezone.localdate() - suscripcion.fecha_proximo_pago).days
            if delta >= 0:
                meses_adeudados = max(1, (delta // 30) + 1)
        context['meses_adeudados'] = meses_adeudados

        if plan:
            context['monto_centavos'] = int(plan.precio * 100 * meses_adeudados)
        if suscripcion:
            context['pagos_recientes'] = suscripcion.pagos.order_by('-fecha_pago')[:10]
        else:
            context['pagos_recientes'] = []
        # Check if billing data exists
        context['datos_facturacion'] = (
            suscripcion.datos_facturacion if suscripcion and suscripcion.datos_facturacion_id else None
        )
        # Generate WOMPI integrity signature (unique per month)
        if plan and suscripcion:
            now = timezone.now()
            reference = f"FUNDMED-{suscripcion.id}-{plan.id}-{now:%Y%m}-{meses_adeudados}M"
            amount_cents = int(plan.precio * 100 * meses_adeudados)
            currency = 'COP'
            integrity_key = settings.WOMPI_INTEGRITY_KEY
            concat = f"{reference}{amount_cents}{currency}{integrity_key}"
            context['wompi_signature'] = hashlib.sha256(concat.encode()).hexdigest()
            context['wompi_reference'] = reference
        else:
            context['payment_reference'] = f"FUNDMED-{uuid.uuid4().hex[:12].upper()}"
        return context


class HistorialPagosView(LoginRequiredMixin, ListView):
    template_name = 'pagos/historial.html'
    context_object_name = 'pagos'
    paginate_by = 20

    def get_queryset(self):
        return Pago.objects.select_related('suscripcion__plan').order_by('-fecha_pago')


@method_decorator(csrf_exempt, name='dispatch')
class WompiWebhookView(View):
    def post(self, request, *args, **kwargs):
        try:
            event_data = json.loads(request.body)
        except json.JSONDecodeError:
            return HttpResponseBadRequest('Invalid JSON')

        if not wompi.verify_webhook_signature(event_data):
            return JsonResponse({'error': 'Invalid signature'}, status=401)

        event = event_data.get('event')

        if event == 'transaction.updated':
            transaction = event_data.get('data', {}).get('transaction', {})
            transaction_id = transaction.get('id', '')
            reference = transaction.get('reference', '')
            status = transaction.get('status', '')
            amount_in_cents = transaction.get('amount_in_cents', 0)

            status_map = {
                'APPROVED': 'APROBADO',
                'DECLINED': 'RECHAZADO',
                'ERROR': 'ERROR',
                'VOIDED': 'ANULADO',
                'PENDING': 'PENDIENTE',
            }
            local_status = status_map.get(status, 'PENDIENTE')

            pago, created = Pago.objects.get_or_create(
                wompi_transaction_id=transaction_id,
                defaults={
                    'suscripcion': Suscripcion.objects.first(),
                    'monto': amount_in_cents / 100,
                    'estado': 'PENDIENTE',
                    'wompi_reference': reference,
                }
            )

            pago.estado = local_status
            pago.detalle_respuesta = transaction
            pago.save()

            if status == 'APPROVED':
                if pago.suscripcion:
                    pago.suscripcion.estado = 'ACTIVA'
                    _avanzar_fecha_proximo_pago(pago.suscripcion, pago.monto)
                if not pago.alegra_invoice_id:
                    try:
                        alegra.generar_factura_desde_pago(pago)
                    except Exception as e:
                        logger.error(f'Error generando factura Alegra: {e}')

            logger.info(f'WOMPI webhook: tx={transaction_id} status={status} created={created}')

        return JsonResponse({'status': 'ok'})
