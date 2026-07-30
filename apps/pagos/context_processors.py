from django.utils import timezone
from datetime import date
from .models import Suscripcion


MESES_ES = [
    '', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
]


def recordatorio_pago(request):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {}

    try:
        suscripcion = Suscripcion.objects.select_related('plan').first()
    except Exception:
        return {}

    if not suscripcion:
        return {}

    ctx = {}

    if suscripcion.estado == 'CANCELADA':
        return ctx

    # Issue #197: banner de alerta de pago vencido -- SOLO expuesto a admins
    # (`request.user.is_admin`), independiente del recordatorio de abajo (que
    # sigue siendo visible a cualquier usuario autenticado).
    if getattr(user, 'is_admin', False) and suscripcion.alerta_pago_vencido:
        ctx['alerta_pago_vencido'] = True

    fecha_venc = suscripcion.fecha_proximo_pago
    if not fecha_venc:
        return ctx

    today = timezone.localdate()
    delta = (today - fecha_venc).days

    if delta < -5:
        return ctx

    if delta < 0:
        estado = 'proximo'
        horas = 24
        meses = 1
    else:
        estado = 'vencido'
        horas = 6
        meses = max(1, (delta // 30) + 1)

    plan = suscripcion.plan
    monto_total = float(plan.precio) * meses if plan else 0.0

    periodos = []
    y, m = fecha_venc.year, fecha_venc.month
    for _ in range(meses):
        periodos.append(f"{MESES_ES[m]} {y}")
        m += 1
        if m > 12:
            m = 1
            y += 1

    ctx['recordatorio_pago'] = {
        'estado': estado,
        'fecha_vencimiento': fecha_venc,
        'horas_entre_avisos': horas,
        'meses_adeudados': meses,
        'monto_total': monto_total,
        'periodos': periodos,
        'plan_nombre': plan.nombre if plan else '',
    }
    return ctx
