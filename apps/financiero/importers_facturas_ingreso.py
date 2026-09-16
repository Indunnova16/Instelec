"""Lectura y validación sin efectos de la carga masiva de facturas de ingreso.

#249 gap 3: mismo patrón UPSERT de `importers_terceros.py` (#261/#262) —
"crear si es nuevo, actualizar con auditoría si ya existe" en vez del bug
"solo inserta, rechaza NIT+fecha existente como duplicado". La clave de
upsert es (cliente_nit, fecha_factura) porque la carga masiva no captura
número de factura -- lo asigna el sistema (`generar_numero_factura`, mismo
consecutivo global que la emisión manual).
"""

import io
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.validators import validate_email  # noqa: F401 (paridad de import con terceros)

COLUMNAS = (
    "cliente_nit",
    "fecha_factura",
    "concepto",
    "valor_neto",
    "metodo_pago",
    "observaciones",
)


def columnas_para():
    return COLUMNAS


def leer_archivo(archivo):
    nombre = archivo.name.lower()
    if nombre.endswith(".csv"):
        import csv

        texto = io.TextIOWrapper(archivo.file, encoding="utf-8-sig")
        return list(csv.DictReader(texto))
    if nombre.endswith(".xlsx"):
        from openpyxl import load_workbook

        libro = load_workbook(archivo, read_only=True, data_only=True)
        filas = list(libro.active.values)
        if not filas:
            return []
        cabeceras = [str(valor or "").strip() for valor in filas[0]]
        return [dict(zip(cabeceras, fila, strict=False)) for fila in filas[1:]]
    raise ValidationError("El archivo debe ser CSV UTF-8 o XLSX.")


def _parse_fecha(valor):
    if hasattr(valor, "isoformat") and not isinstance(valor, str):
        return valor if isinstance(valor, date) else valor.date()
    texto = str(valor or "").strip()
    if not texto:
        raise ValidationError("fecha_factura es obligatoria")
    return date.fromisoformat(texto)


def validar_filas(archivo, cliente_model, metodo_pago_model, ciclo_model):
    """Valida el plano y decide crear/actualizar por fila.

    Reglas del cliente (#249): NIT debe existir y estar ACTIVO en
    `financiero_clientes`, fecha válida, valor_neto > 0. El método de pago es
    opcional (texto libre resuelto contra el maestro si existe, sin bloquear
    la fila si no hay maestro con ese nombre -- se guarda para revisión).
    """
    filas = leer_archivo(archivo)
    if not filas:
        return [], [{"fila": 1, "error": "El archivo no contiene filas para importar."}]
    requeridas = set(COLUMNAS)
    faltantes = requeridas - set(filas[0])
    if faltantes:
        return [], [{"fila": 1, "error": f"Faltan columnas: {', '.join(sorted(faltantes))}."}]

    errores, limpias = [], []
    vistos_en_archivo = set()
    for numero, fila in enumerate(filas, start=2):
        dato = {campo: fila.get(campo) for campo in requeridas}
        dato = {campo: ("" if valor is None else valor) for campo, valor in dato.items()}
        try:
            nit = str(dato["cliente_nit"]).strip()
            if not nit:
                raise ValidationError("cliente_nit es obligatorio")
            cliente = cliente_model.objects.filter(nit=nit).first()
            if not cliente:
                raise ValidationError(f"no existe un cliente con NIT '{nit}'")
            if not cliente.activo:
                raise ValidationError(f"el cliente con NIT '{nit}' está inactivo")

            fecha_factura = _parse_fecha(dato["fecha_factura"])

            clave = (nit, fecha_factura.isoformat())
            if clave in vistos_en_archivo:
                raise ValidationError(
                    "fila duplicada dentro del archivo (mismo cliente_nit + fecha_factura)"
                )
            vistos_en_archivo.add(clave)

            concepto = str(dato["concepto"]).strip()
            if not concepto:
                raise ValidationError("concepto es obligatorio")

            try:
                valor_neto = Decimal(str(dato["valor_neto"]).strip().replace(",", ""))
            except (InvalidOperation, ValueError) as exc:
                raise ValidationError(f"valor_neto inválido: '{dato['valor_neto']}'") from exc
            if valor_neto <= 0:
                raise ValidationError("valor_neto debe ser mayor que cero")

            metodo_nombre = str(dato["metodo_pago"]).strip()
            metodo_pago = (
                metodo_pago_model.objects.filter(nombre__iexact=metodo_nombre).first()
                if metodo_nombre
                else None
            )

            existente = ciclo_model.objects.filter(
                cliente=cliente, fecha_factura=fecha_factura, numero_secuencial__isnull=False
            ).first()

            # La factura no tiene FK a MetodoPago (eso vive en
            # PagoFacturaIngreso, que se registra al cobrar, no al emitir) --
            # se conserva el dato capturado en el CSV como texto legible en
            # observaciones para no perderlo silenciosamente.
            observaciones = str(dato["observaciones"]).strip()
            if metodo_nombre:
                prefijo = f"Método de pago (carga): {metodo_nombre}"
                observaciones = f"{prefijo}. {observaciones}" if observaciones else prefijo

            limpias.append(
                {
                    "cliente_id": str(cliente.pk),
                    "cliente_nombre": cliente.nombre,
                    "fecha_factura": fecha_factura,
                    "concepto": concepto,
                    "valor_neto": valor_neto,
                    "metodo_pago_id": str(metodo_pago.pk) if metodo_pago else None,
                    "metodo_pago_nombre": metodo_nombre,
                    "observaciones": observaciones,
                    "accion_carga": "actualizar" if existente else "crear",
                    "_ciclo_id": str(existente.pk) if existente else None,
                }
            )
        except ValidationError as exc:
            mensaje = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            errores.append({"fila": numero, "error": mensaje})
    return limpias, errores
