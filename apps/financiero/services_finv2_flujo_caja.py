"""Cálculos deterministas para la proyección de caja por proyecto (#251)."""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils.timezone import localdate

from .models import (
    CajaProyecto,
    CicloFacturacion,
    EgresoFijoProyecto,
    FacturaGasto,
    PersonalAdministrativo,
)

ESCENARIOS = {
    "base": (Decimal("1.00"), Decimal("1.00")),
    "optimista": (Decimal("1.10"), Decimal("0.90")),
    "estres": (Decimal("0.75"), Decimal("1.15")),
}


def _total(queryset, field="total"):
    return queryset.aggregate(total=Sum(field))["total"] or Decimal("0.00")


def proyectar_flujo_caja(
    *, contrato=None, horizonte_dias=90, porcentaje_cobro=Decimal("90"), escenario="base"
):
    """Devuelve una proyección sin persistir parámetros ni alterar documentos origen."""
    porcentaje_cobro = Decimal(porcentaje_cobro) / Decimal("100")
    ingreso_factor, egreso_factor = ESCENARIOS.get(escenario, ESCENARIOS["base"])
    fecha_corte = localdate() + timedelta(days=horizonte_dias)
    ingresos_qs = CicloFacturacion.objects.filter(
        estado=CicloFacturacion.Estado.FACTURA_EMITIDA,
        fecha_factura__lte=fecha_corte,
    )
    ingresos_brutos = sum(
        (max(Decimal("0.00"), ciclo.total - ciclo.monto_pagado) for ciclo in ingresos_qs),
        Decimal("0.00"),
    )
    gastos_qs = FacturaGasto.objects.filter(
        estado__in=[FacturaGasto.Estado.PENDIENTE_APROBACION, FacturaGasto.Estado.PENDIENTE_PAGO],
        fecha__lte=fecha_corte,
    )
    if contrato:
        gastos_qs = gastos_qs.filter(contrato=contrato)
    gastos_pendientes = _total(gastos_qs)
    egresos_fijos_qs = EgresoFijoProyecto.objects.filter(activo=True)
    nomina_qs = PersonalAdministrativo.objects.filter(activo=True)
    saldo_inicial = Decimal("0.00")
    if contrato:
        saldo_inicial = CajaProyecto.objects.filter(contrato=contrato).values_list(
            "saldo_inicial", flat=True
        ).first() or Decimal("0.00")
        egresos_fijos_qs = egresos_fijos_qs.filter(contrato=contrato)
        nomina_qs = nomina_qs.filter(contrato=contrato)
    meses = max(1, (horizonte_dias + 29) // 30)
    egresos_fijos = _total(egresos_fijos_qs, "monto") * meses
    nomina = _total(nomina_qs, "salario_mensual") * meses
    ingresos_proyectados = (ingresos_brutos * porcentaje_cobro * ingreso_factor).quantize(
        Decimal("0.01")
    )
    egresos_proyectados = ((gastos_pendientes + egresos_fijos + nomina) * egreso_factor).quantize(
        Decimal("0.01")
    )
    saldo_proyectado = saldo_inicial + ingresos_proyectados - egresos_proyectados
    return {
        "fecha_corte": fecha_corte,
        "horizonte_dias": horizonte_dias,
        "saldo_inicial": saldo_inicial,
        "ingresos_emitidos": ingresos_brutos,
        "ingresos_proyectados": ingresos_proyectados,
        "gastos_pendientes": gastos_pendientes,
        "egresos_fijos": egresos_fijos,
        "nomina": nomina,
        "egresos_proyectados": egresos_proyectados,
        "saldo_proyectado": saldo_proyectado,
        "hay_deficit": saldo_proyectado < 0,
        "escenario": escenario,
        "alertas": _alertas(saldo_proyectado, gastos_pendientes, horizonte_dias),
    }


def _alertas(saldo, gastos, horizonte):
    alertas = []
    if saldo < 0:
        alertas.append("Déficit proyectado: priorice cobros o reprograme egresos.")
    if gastos > 0:
        alertas.append("Hay facturas pendientes de aprobación o pago dentro del horizonte.")
    if horizonte > 180:
        alertas.append("Horizontes largos son estimativos; revise periódicamente los supuestos.")
    return alertas
