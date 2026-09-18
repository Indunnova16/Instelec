"""Lectura y validación sin efectos de la carga masiva de facturas de gasto (#248).

Mismo patrón UPSERT que `importers_facturas_ingreso.py` (#249): "crear si es
nuevo, actualizar con auditoría si ya existe" en vez de rechazar como
duplicado. La clave de upsert es (proveedor_nit, fecha_factura) -- el CSV del
checklist del cliente (#248 sección 5) NO incluye número de documento, y
`FacturaGasto` exige uno único por proveedor
(`uq_finv2_gasto_proveedor_doc`). Las filas nuevas reciben un
`numero_documento` generado determinísticamente por la vista que confirma la
carga (`views_finv2_gastos.py::GastoImportarPreviewView`), documentado como
supuesto igual que el consecutivo de #249.
"""

import io
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError

COLUMNAS = (
    "proveedor_nit",
    "fecha_factura",
    "concepto",
    "valor_neto",
    "proyecto",
    "centro_costo",
    "requiere_aprobacion",
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


def _parse_bool(valor):
    texto = str(valor or "").strip().lower()
    return texto in {"si", "sí", "true", "1", "x", "yes"}


def validar_filas(archivo, proveedor_model, contrato_model, homologacion_model, facturagasto_model):
    """Valida el plano y decide crear/actualizar por fila (checklist #248 sección 5).

    Reglas del cliente: proveedor debe existir y estar ACTIVO en
    `financiero_proveedores` (#262); proyecto (contrato) debe existir y
    estar ACTIVO; fecha no puede ser futura; valor_neto > 0; centro_costo
    debe existir en el catálogo de Homologación Projects→Contabilidad activo
    (#247) -- "Centro Costo vinculado a #247" del checklist, sección 6.
    `requiere_aprobacion` es ADITIVO: si viene SI/TRUE fuerza aprobación
    aunque el total no supere el umbral, pero nunca la QUITA si el total sí
    lo supera -- la regla del umbral $1.000.000 (sección Cálculos
    Automáticos del checklist) es obligatoria, no un valor que un CSV pueda
    apagar.
    """
    filas = leer_archivo(archivo)
    if not filas:
        return [], [{"fila": 1, "error": "El archivo no contiene filas para importar."}]
    requeridas = set(COLUMNAS)
    faltantes = requeridas - set(filas[0])
    if faltantes:
        return [], [{"fila": 1, "error": f"Faltan columnas: {', '.join(sorted(faltantes))}."}]

    centros_costo_validos = {
        valor.strip().lower()
        for valor in homologacion_model.objects.filter(activo=True)
        .exclude(centro_costo="")
        .values_list("centro_costo", flat=True)
    }

    errores, limpias = [], []
    vistos_en_archivo = set()
    hoy = date.today()
    for numero, fila in enumerate(filas, start=2):
        dato = {campo: fila.get(campo) for campo in requeridas}
        dato = {campo: ("" if valor is None else valor) for campo, valor in dato.items()}
        try:
            nit = str(dato["proveedor_nit"]).strip()
            if not nit:
                raise ValidationError("proveedor_nit es obligatorio")
            proveedor = proveedor_model.objects.filter(nit=nit).first()
            if not proveedor:
                raise ValidationError(f"no existe un proveedor con NIT '{nit}'")
            if not proveedor.activo:
                raise ValidationError(f"el proveedor con NIT '{nit}' está inactivo")

            fecha_factura = _parse_fecha(dato["fecha_factura"])
            if fecha_factura > hoy:
                raise ValidationError("fecha_factura no puede ser futura")

            clave = (nit, fecha_factura.isoformat())
            if clave in vistos_en_archivo:
                raise ValidationError(
                    "fila duplicada dentro del archivo (mismo proveedor_nit + fecha_factura)"
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

            codigo_proyecto = str(dato["proyecto"]).strip()
            if not codigo_proyecto:
                raise ValidationError("proyecto es obligatorio")
            contrato = contrato_model.objects.filter(codigo=codigo_proyecto).first()
            if not contrato:
                raise ValidationError(
                    f"no existe un proyecto/contrato con código '{codigo_proyecto}'"
                )
            if contrato.estado != contrato_model.Estado.ACTIVO:
                raise ValidationError(f"el proyecto '{codigo_proyecto}' no está activo")

            centro_costo = str(dato["centro_costo"]).strip()
            if not centro_costo:
                raise ValidationError("centro_costo es obligatorio")
            if centros_costo_validos and centro_costo.lower() not in centros_costo_validos:
                raise ValidationError(
                    f"centro_costo '{centro_costo}' no existe en Homologación "
                    "Projects→Contabilidad activa"
                )

            requiere_aprobacion = _parse_bool(dato["requiere_aprobacion"])

            existente = facturagasto_model.objects.filter(
                proveedor=proveedor, fecha=fecha_factura
            ).first()

            limpias.append(
                {
                    "fila": numero,
                    "proveedor_id": str(proveedor.pk),
                    "proveedor_nombre": proveedor.nombre,
                    "proveedor_nit": nit,
                    "contrato_id": str(contrato.pk),
                    "fecha_factura": fecha_factura,
                    "concepto": concepto,
                    "valor_neto": valor_neto,
                    "centro_costo": centro_costo,
                    "requiere_aprobacion": requiere_aprobacion,
                    "accion_carga": "actualizar" if existente else "crear",
                    "_factura_id": str(existente.pk) if existente else None,
                }
            )
        except ValidationError as exc:
            mensaje = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            errores.append({"fila": numero, "error": mensaje})
    return limpias, errores
