import hashlib
import json
import logging
import uuid
from calendar import monthrange
from datetime import date
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView, ListView
from .models import PlanServicio, Suscripcion, Pago, DatosFacturacion, calcular_n_meses
from .context_processors import MESES_ES
from . import wompi
from . import alegra

logger = logging.getLogger(__name__)


class AdminRequiredMixin(UserPassesTestMixin):
    """Exige que el usuario autenticado sea admin -- issue #197 (Datos de
    Facturacion / Portal de Pagos / Historial son admin-only, el pago de la
    suscripcion Instelec-Indunnova no le compete a cualquier usuario
    logueado). Sigue el mismo patron UserPassesTestMixin + PermissionDenied
    de `apps.core.mixins.NivelAdminRequiredMixin`, pero gateando por la
    property legacy `Usuario.is_admin` (rol == ADMIN o is_superuser) en vez
    del nivel RBAC v2 (`user_es_admin`), tal como pide el issue."""

    def test_func(self):
        return getattr(self.request.user, 'is_admin', False)

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        raise PermissionDenied('Esta seccion es exclusiva para administradores.')


def _avanzar_fecha_proximo_pago(suscripcion, pago):
    """Avanza fecha_proximo_pago `pago.n_meses` meses. Mantiene dia 20.

    Issue #199 (sub-item A2): antes recibia el monto pagado suelto y
    recalculaba `meses` por su cuenta (duplicando la logica que hoy vive en
    `calcular_n_meses`). Ahora recibe el `Pago` ya creado -- `n_meses` fue
    calculado y persistido en el momento de crear el registro (unica fuente
    de verdad, ver `calcular_n_meses` en models.py), asi que aca solo se lee.
    """
    plan = suscripcion.plan
    if not plan or plan.precio <= 0:
        return
    meses = max(1, pago.n_meses)
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


def _construir_grid_meses(suscripcion, pagos_recientes):
    """Ventana informativa de 6 meses "Estado por mes" (issue #199, A5 --
    SOLO LECTURA, SIN selector/checkbox interactivo, decision Miguel
    2026-07-30: Instelec mantiene el pago forzado total). 3 meses hacia
    atras + el mes de `fecha_proximo_pago` + 2 meses hacia adelante.

    Anclada en `fecha_proximo_pago`: los meses ANTERIORES se marcan
    `pagado` SOLO si estan efectivamente cubiertos por la cobertura real de
    `pagos_recientes` (Pago.n_meses persistido -- A2), acumulando desde el
    pago APROBADO mas reciente hacia atras. NO se asume "pagado" solo por
    estar antes de fecha_proximo_pago -- una Suscripcion PENDIENTE que
    nunca se ha pagado (caso real de prod hoy: 0 Pago historicos) no debe
    mostrar meses pasados como pagados solo porque son anteriores a la
    fecha. Desde `fecha_proximo_pago` en adelante, `meses_atraso` (A3)
    determina cuantos de esos meses estan VENCIDOS hoy vs. simplemente
    PENDIENTES (aun no vencen).
    """
    if not suscripcion or not suscripcion.fecha_proximo_pago:
        return []

    meses_atraso = suscripcion.meses_atraso
    anio_base, mes_base = suscripcion.fecha_proximo_pago.year, suscripcion.fecha_proximo_pago.month
    pagos_aprobados = [p for p in pagos_recientes if p.estado == 'APROBADO']

    def _cubierto_por_pago(offset_meses_atras):
        # offset_meses_atras=1 -> el mes inmediatamente anterior a
        # fecha_proximo_pago, 2 -> dos meses antes, etc. pagos_recientes ya
        # viene ordenado mas reciente primero (order_by('-fecha_pago')).
        acumulado = 0
        for pago in pagos_aprobados:
            acumulado += pago.n_meses
            if offset_meses_atras <= acumulado:
                return True
        return False

    grid = []
    for offset in range(-3, 3):
        mes = mes_base + offset
        anio = anio_base
        while mes < 1:
            mes += 12
            anio -= 1
        while mes > 12:
            mes -= 12
            anio += 1

        if offset < 0:
            pagado = _cubierto_por_pago(-offset)
            estado = 'pagado' if pagado else 'sin_registro'
        elif offset < max(meses_atraso, 0):
            pagado = False
            estado = 'vencido'
        else:
            pagado = False
            estado = 'pendiente' if offset == 0 else 'proximo'

        grid.append({
            'anio': anio,
            'mes': mes,
            'label': f"{MESES_ES[mes]} {anio}",
            'pagado': pagado,
            'estado': estado,
            'es_mes_actual_cobro': offset == 0,
        })
    return grid


class DatosFacturacionView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
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


class PagoPortalView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
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

            n_meses = (
                calcular_n_meses(amount, suscripcion.plan.precio)
                if suscripcion.plan_id else 1
            )

            pago = Pago.objects.create(
                suscripcion=suscripcion,
                monto=amount,
                n_meses=n_meses,
                estado=estado_map.get(status, 'PENDIENTE'),
                wompi_transaction_id=tx_id,
                wompi_reference=reference,
                detalle_respuesta=tx,
            )

            if status == 'APPROVED':
                suscripcion.estado = 'ACTIVA'
                _avanzar_fecha_proximo_pago(suscripcion, pago)
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

        # Issue #199 (A3): fuente unica -- Suscripcion.meses_atraso (ya
        # gatea estado != 'ACTIVA' y fecha_proximo_pago vacia/no vencida).
        meses_adeudados = suscripcion.meses_atraso if suscripcion and suscripcion.meses_atraso else 1
        context['meses_adeudados'] = meses_adeudados

        if plan:
            context['monto_centavos'] = int(plan.precio * 100 * meses_adeudados)
        if suscripcion:
            context['pagos_recientes'] = suscripcion.pagos.order_by('-fecha_pago')[:10]
        else:
            context['pagos_recientes'] = []
        # Issue #199 (A5): grilla informativa "Estado por mes", SOLO LECTURA.
        context['grid_meses'] = _construir_grid_meses(suscripcion, context['pagos_recientes'])
        # Check if billing data exists
        context['datos_facturacion'] = (
            suscripcion.datos_facturacion if suscripcion and suscripcion.datos_facturacion_id else None
        )
        # Generate WOMPI integrity signature (unique per month)
        if plan and suscripcion:
            now = timezone.now()
            reference = f"{settings.WOMPI_REFERENCE_PREFIX}-{suscripcion.id}-{plan.id}-{now:%Y%m%d%H%M%S%f}-{meses_adeudados}M"
            amount_cents = int(plan.precio * 100 * meses_adeudados)
            currency = 'COP'
            integrity_key = settings.WOMPI_INTEGRITY_KEY
            concat = f"{reference}{amount_cents}{currency}{integrity_key}"
            context['wompi_signature'] = hashlib.sha256(concat.encode()).hexdigest()
            context['wompi_reference'] = reference
        else:
            context['payment_reference'] = f"{settings.WOMPI_REFERENCE_PREFIX}-{uuid.uuid4().hex[:12].upper()}"
        return context


class HistorialPagosView(LoginRequiredMixin, AdminRequiredMixin, ListView):
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

            suscripcion = Suscripcion.objects.first()
            monto = amount_in_cents / 100
            n_meses = (
                calcular_n_meses(monto, suscripcion.plan.precio)
                if suscripcion and suscripcion.plan_id else 1
            )

            pago, created = Pago.objects.get_or_create(
                wompi_transaction_id=transaction_id,
                defaults={
                    'suscripcion': suscripcion,
                    'monto': monto,
                    'n_meses': n_meses,
                    'estado': 'PENDIENTE',
                    'wompi_reference': reference,
                }
            )

            # Guard de idempotencia: si el Pago YA estaba APROBADO antes de este
            # evento, una redelivery del mismo webhook (o un reprocesamiento por
            # otra via) no debe re-avanzar fecha_proximo_pago ni re-facturar.
            ya_estaba_aprobado = (not created) and (pago.estado == 'APROBADO')

            pago.estado = local_status
            pago.detalle_respuesta = transaction
            pago.save()

            if status == 'APPROVED' and not ya_estaba_aprobado:
                if pago.suscripcion:
                    pago.suscripcion.estado = 'ACTIVA'
                    _avanzar_fecha_proximo_pago(pago.suscripcion, pago)
                if not pago.alegra_invoice_id:
                    try:
                        alegra.generar_factura_desde_pago(pago)
                    except Exception as e:
                        logger.error(f'Error generando factura Alegra: {e}')

            logger.info(
                f'WOMPI webhook: tx={transaction_id} status={status} '
                f'created={created} ya_estaba_aprobado={ya_estaba_aprobado}'
            )

        return JsonResponse({'status': 'ok'})
