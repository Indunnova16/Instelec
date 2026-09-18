"""Agregadores de sólo lectura para el dashboard integrado (#246 Sprint C).

Combina 4 fuentes YA DESPLEGADAS en producción -- nunca crea facturas ni
movimientos contables nuevos, y nunca reimplementa un cálculo que ya existe:

- **Nómina**: delega en ``services_produccion_diaria.agregado_financiero_periodo``
  (#252, ya en ``main``) -- no reimplementa el costo de personal.
- **Gastos**: lee ``FacturaGasto.total`` directamente. NUNCA se suma también
  ``PagoFacturaGasto`` -- eso duplicaría el gasto (un pago es la liquidación
  de una factura que ya se contó una vez al leer ``FacturaGasto``).
- **Ingresos**: lee ``CicloFacturacion.total`` -- sólo de ciclos con
  ``numero_secuencial`` asignado (una factura realmente emitida; un
  ``CicloFacturacion`` todavía en borrador -- ``INFORME_GENERADO``/
  ``EN_VALIDACION`` sin secuencial -- no es un ingreso). ``LineaFacturaIngreso``
  se expone sólo como desglose por concepto de cada ciclo, nunca se vuelve a
  sumar en el total (ya está contenido en ``CicloFacturacion.total``).
- **Clientes**: se agrupan a partir de los mismos ``CicloFacturacion`` ya
  leídos para ingresos -- ningún query adicional que pueda desalinearse del
  total de ingresos.

``contrato`` es una instancia de ``contratos.Contrato`` (la misma que
``CargaFinancieraView._proyecto_seleccionado()`` resuelve) o ``None`` para
agregar todos los contratos del período.

``linea`` se recibe por consistencia con la firma hermana
``indicadores_finv2.contexto_indicadores_finv2(anio, mes, contrato, linea)``
(mismo patrón de nombres en este mismo app). Ninguna de las 4 fuentes de
este agregador tiene hoy una dimensión "línea" (``apps.lineas.Linea``):
``FacturaGasto``/``CicloFacturacion``/``Cliente`` sólo conocen
``contrato``/``Contrato``, y ``ProduccionDiaria`` sólo conoce
``ProyectoConstruccion`` (evidencia: ``Read`` completo de
``models_finv2_facturas.py`` y ``models_produccion_diaria.py``, ningún FK
``linea``). El parámetro se acepta para no romper la firma exigida
(Kaizen #47) pero hoy no filtra nada -- si un futuro issue pide desglose por
línea de transmisión hay que agregar ese FK a los modelos de origen primero.
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal
from typing import Any

from apps.contratos.models import Contrato

from .models_finv2_facturas import CicloFacturacion, Cliente, FacturaGasto
from .services_produccion_diaria import agregado_financiero_periodo

CERO = Decimal("0.00")


def _rango_mes(anio: int, mes: int) -> tuple[date, date]:
    ultimo_dia = calendar.monthrange(anio, mes)[1]
    return date(anio, mes, 1), date(anio, mes, ultimo_dia)


def _agregado_nomina(anio: int, mes: int, contrato: Contrato | None) -> dict[str, Any]:
    """Nómina real del período, vía el agregador ya publicado de #252.

    ``ProyectoConstruccion`` (de donde cuelga toda la producción diaria) es
    ``OneToOne`` con ``Contrato`` y sólo existe para contratos de unidad de
    negocio CONSTRUCCION (``limit_choices_to`` en el modelo, confirmado por
    Read de ``apps/construccion/models.py``). Si el contrato filtrado no
    tiene proyecto de construcción asociado (p.ej. es de MANTENIMIENTO), no
    es un error: simplemente no hay nómina que agregar para ese contrato.
    """
    proyecto_construccion = None
    if contrato is not None:
        proyecto_construccion = getattr(contrato, "proyecto_construccion", None)
        if proyecto_construccion is None:
            return {
                "costo_nomina": CERO,
                "horas_trabajadas": CERO,
                "cantidad_producciones": 0,
                "producciones": [],
                "con_datos": False,
            }
    fecha_inicio, fecha_fin = _rango_mes(anio, mes)
    periodo = agregado_financiero_periodo(
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        proyecto=proyecto_construccion,
    )
    return {
        "costo_nomina": periodo["costo_nomina"],
        "horas_trabajadas": periodo["horas_trabajadas"],
        "cantidad_producciones": periodo["cantidad_producciones"],
        "producciones": periodo["producciones"],
        "con_datos": periodo["cantidad_producciones"] > 0,
    }


def _agregado_gastos(anio: int, mes: int, contrato: Contrato | None) -> dict[str, Any]:
    gastos_qs = FacturaGasto.objects.select_related("proveedor").filter(
        fecha__year=anio,
        fecha__month=mes,
    )
    if contrato is not None:
        gastos_qs = gastos_qs.filter(contrato=contrato)
    gastos = list(gastos_qs.order_by("-fecha", "-created_at"))

    total = sum((gasto.total for gasto in gastos), CERO)
    pendiente_pago = sum(
        (gasto.total for gasto in gastos if gasto.estado != FacturaGasto.Estado.PAGADA),
        CERO,
    )
    detalle = [
        {
            "id": gasto.pk,
            "proveedor": str(gasto.proveedor),
            "numero_documento": gasto.numero_documento,
            "fecha": gasto.fecha,
            "categoria": gasto.categoria,
            "total": gasto.total,
            "estado": gasto.estado,
            "estado_display": gasto.get_estado_display(),
        }
        for gasto in gastos
    ]
    return {
        "total": total,
        "pendiente_pago": pendiente_pago,
        "cantidad": len(gastos),
        "detalle": detalle,
        "con_datos": bool(gastos),
    }


def _agregado_ingresos_y_clientes(
    anio: int, mes: int, contrato: Contrato | None
) -> tuple[dict[str, Any], dict[str, Any]]:
    ingresos_qs = (
        CicloFacturacion.objects.filter(
            numero_secuencial__isnull=False,
            fecha_factura__year=anio,
            fecha_factura__month=mes,
        )
        .select_related("cliente", "proyecto")
        .prefetch_related("lineas_factura")
    )
    if contrato is not None:
        ingresos_qs = ingresos_qs.filter(proyecto=contrato)
    ciclos = list(ingresos_qs.order_by("-fecha_factura"))

    total = sum((ciclo.total for ciclo in ciclos), CERO)
    cobrado = sum(
        (ciclo.total for ciclo in ciclos if ciclo.estado == CicloFacturacion.Estado.PAGO_RECIBIDO),
        CERO,
    )

    detalle: list[dict[str, Any]] = []
    por_cliente: dict[Any, dict[str, Any]] = {}
    for ciclo in ciclos:
        detalle.append(
            {
                "id": ciclo.pk,
                "numero_factura": ciclo.numero_factura,
                "cliente": str(ciclo.cliente) if ciclo.cliente_id else "Sin cliente",
                "fecha_factura": ciclo.fecha_factura,
                "total": ciclo.total,
                "estado": ciclo.estado,
                "estado_display": ciclo.get_estado_display(),
                "lineas": [
                    {
                        "descripcion": linea.descripcion,
                        "cantidad": linea.cantidad,
                        "valor_unitario": linea.valor_unitario,
                        "total": linea.total,
                    }
                    for linea in ciclo.lineas_factura.all()
                ],
            }
        )
        clave = ciclo.cliente_id or "sin_cliente"
        entrada = por_cliente.setdefault(
            clave,
            {
                "cliente_id": ciclo.cliente_id,
                "cliente": str(ciclo.cliente) if ciclo.cliente_id else "Sin cliente",
                "total_facturado": CERO,
                "cantidad_facturas": 0,
            },
        )
        entrada["total_facturado"] += ciclo.total
        entrada["cantidad_facturas"] += 1

    ingresos = {
        "total": total,
        "cobrado": cobrado,
        "cantidad": len(ciclos),
        "detalle": detalle,
        "con_datos": bool(ciclos),
    }
    clientes_facturados = sorted(
        por_cliente.values(),
        key=lambda item: item["total_facturado"],
        reverse=True,
    )
    clientes = {
        # Maestro global de clientes activos (#261) -- no depende del período.
        "activos_total": Cliente.objects.filter(activo=True).count(),
        "facturados_periodo": len(clientes_facturados),
        "detalle": clientes_facturados,
        "con_datos": bool(clientes_facturados),
    }
    return ingresos, clientes


def construir_contexto_dashboard_integrado(
    anio: int, mes: int, contrato: Contrato | None = None, linea: Any | None = None
) -> dict[str, Any]:
    """Contrato de servicio (Kaizen #47) -- B4 lo reutiliza literal.

    Retorna un dict con 4 claves de nivel superior --
    ``integracion_nomina``/``integracion_gastos``/``integracion_ingresos``/
    ``integracion_clientes`` -- listo para mezclarse en el contexto de
    ``CargaFinancieraView`` (dashboard HTML) o para que B4 lo reutilice sin
    reimplementar agregación ni duplicar conteo en sus 3 generadores de
    reporte (PDF/Excel/PPT).

    No lanza si no hay datos: cada sub-dict trae ``con_datos: bool`` para que
    la UI muestre el estado vacío con claridad en vez de un total en cero sin
    contexto.
    """
    nomina = _agregado_nomina(anio, mes, contrato)
    gastos = _agregado_gastos(anio, mes, contrato)
    ingresos, clientes = _agregado_ingresos_y_clientes(anio, mes, contrato)
    return {
        "integracion_nomina": nomina,
        "integracion_gastos": gastos,
        "integracion_ingresos": ingresos,
        "integracion_clientes": clientes,
    }
