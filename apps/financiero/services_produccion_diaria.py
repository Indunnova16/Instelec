"""Consulta financiera idempotente para Producción Diaria (#252).

Este adaptador deliberadamente no crea ``FacturaGasto``, ``FacturaIngreso`` ni
movimientos contables: esos documentos necesitan una llave de negocio que el
registro operativo no tiene. Sus retornos son diccionarios de ``Decimal`` y
fechas para que los consumidores financieros puedan conservar la trazabilidad
del registro de origen sin introducir efectos secundarios.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from apps.cuadrillas.models_produccion_diaria import ProduccionDiaria

CERO = Decimal("0")
HORAS_LABORALES_MES = Decimal("240")


def agregado_financiero_produccion(produccion: ProduccionDiaria) -> dict[str, Any]:
    """Devuelve los valores financieros y operativos de un registro diario.

    La función sólo lee relaciones del objeto recibido. Acepta tanto una
    instancia recién consultada como una con sus relaciones prefetched, por lo
    que repetirla con los mismos datos devuelve el mismo resultado y no escribe
    en ninguna tabla.
    """
    registros = produccion.registros_personal.all()
    materiales = produccion.materiales.all()
    actividades = produccion.actividades.all()

    horas_trabajadas = sum((registro.horas_trabajadas or CERO for registro in registros), CERO)
    costo_nomina = sum(
        (
            (registro.horas_trabajadas or CERO)
            * ((registro.personal.salario_base or CERO) / HORAS_LABORALES_MES)
            for registro in produccion.registros_personal.all()
        ),
        CERO,
    )
    costo_materiales = sum((material.costo_estimado for material in materiales), CERO)
    actividades_trazables = [
        {
            "id": actividad.pk,
            "descripcion": actividad.descripcion,
            "avance_pct": actividad.avance_pct,
            "observacion": actividad.observacion,
        }
        for actividad in actividades
    ]
    avance_promedio = (
        sum((actividad["avance_pct"] for actividad in actividades_trazables), CERO)
        / len(actividades_trazables)
        if actividades_trazables
        else CERO
    )
    programacion = produccion.programacion

    return {
        "produccion_id": produccion.pk,
        "fecha": produccion.fecha,
        "programacion_id": programacion.pk,
        "proyecto_id": programacion.proyecto_id,
        "horas_trabajadas": horas_trabajadas,
        "costo_nomina": costo_nomina,
        "costo_materiales": costo_materiales,
        "costo_total_estimado": costo_nomina + costo_materiales,
        "avance_promedio_pct": avance_promedio,
        "actividades": actividades_trazables,
    }


def agregado_financiero_periodo(
    *,
    fecha_inicio: date,
    fecha_fin: date,
    proyecto: Any | None = None,
    contrato: Any | None = None,
) -> dict[str, Any]:
    """Agrega producción de un rango inclusivo, opcionalmente por proyecto.

    ``contrato`` es un alias de compatibilidad para consumidores que nombran al
    proyecto así. No puede combinarse con ``proyecto`` para evitar una consulta
    ambigua. Los argumentos de fecha inválidos se rechazan antes de consultar.
    """
    if not isinstance(fecha_inicio, date) or not isinstance(fecha_fin, date):
        raise TypeError("fecha_inicio y fecha_fin deben ser date")
    if fecha_inicio > fecha_fin:
        raise ValueError("fecha_inicio no puede ser posterior a fecha_fin")
    if proyecto is not None and contrato is not None:
        raise ValueError("use proyecto o contrato, no ambos")

    proyecto_o_contrato = proyecto if proyecto is not None else contrato
    producciones = (
        ProduccionDiaria.objects.filter(fecha__range=(fecha_inicio, fecha_fin))
        .select_related("programacion__proyecto")
        .prefetch_related("registros_personal__personal", "materiales", "actividades")
        .order_by("fecha", "pk")
    )
    if proyecto_o_contrato is not None:
        proyecto_id = getattr(proyecto_o_contrato, "pk", proyecto_o_contrato)
        producciones = producciones.filter(programacion__proyecto_id=proyecto_id)

    detalle = [agregado_financiero_produccion(produccion) for produccion in producciones]
    total_actividades = [actividad for item in detalle for actividad in item["actividades"]]
    return {
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "proyecto_id": getattr(proyecto_o_contrato, "pk", proyecto_o_contrato),
        "producciones": detalle,
        "cantidad_producciones": len(detalle),
        "horas_trabajadas": sum((item["horas_trabajadas"] for item in detalle), CERO),
        "costo_nomina": sum((item["costo_nomina"] for item in detalle), CERO),
        "costo_materiales": sum((item["costo_materiales"] for item in detalle), CERO),
        "costo_total_estimado": sum((item["costo_total_estimado"] for item in detalle), CERO),
        "avance_promedio_pct": (
            sum((actividad["avance_pct"] for actividad in total_actividades), CERO)
            / len(total_actividades)
            if total_actividades
            else CERO
        ),
        "actividades": total_actividades,
    }


# Nombres explícitos que facilitan la adopción gradual desde los consumidores
# financieros existentes sin abrir ningún flujo de facturación.
resumen_financiero_produccion_diaria = agregado_financiero_produccion
resumen_financiero_produccion_periodo = agregado_financiero_periodo
