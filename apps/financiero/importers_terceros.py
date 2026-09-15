"""Lectura y validación sin efectos de los planos de terceros."""

import csv
import io
import re
from datetime import date

from django.core.exceptions import ValidationError
from django.core.validators import validate_email


COMUNES = (
    "nombre", "nit", "email", "telefono", "direccion", "plazo_pago_dias",
    "fecha_inicio_contrato", "fecha_fin_contrato", "activo",
)
CAMPO_ESPECIFICO = {"CLIENTE": "industria", "PROVEEDOR": "tipo_servicio"}

# Valores predefinidos de Industria (Anexo pedido por el cliente en #261,
# sesión 2026-09-12). Proveedor/tipo_servicio no tiene lista cerrada -- el
# cliente lo dejó como texto libre para #262.
INDUSTRIAS_VALIDAS = {
    "Manufactura", "Energía", "Telecomunicaciones", "Infraestructura",
    "Servicios", "Gobierno", "Otro",
}

TELEFONO_RE = re.compile(r"^[\d\s()+.-]{7,20}$")
ACTIVO_VERDADEROS = {"true", "1", "si", "sí", "activo", "x"}
ACTIVO_FALSOS = {"false", "0", "no", "inactivo", ""}


def columnas_para(tipo):
    return (*COMUNES, CAMPO_ESPECIFICO[tipo])


def leer_archivo(archivo):
    nombre = archivo.name.lower()
    if nombre.endswith(".csv"):
        texto = io.TextIOWrapper(archivo.file, encoding="utf-8-sig")
        return list(csv.DictReader(texto))
    if nombre.endswith(".xlsx"):
        from openpyxl import load_workbook
        libro = load_workbook(archivo, read_only=True, data_only=True)
        filas = list(libro.active.values)
        if not filas:
            return []
        cabeceras = [str(valor or "").strip() for valor in filas[0]]
        return [dict(zip(cabeceras, fila)) for fila in filas[1:]]
    raise ValidationError("El archivo debe ser CSV UTF-8 o XLSX.")


def _parsear_activo(valor):
    texto = str(valor or "").strip().lower()
    if texto in ACTIVO_VERDADEROS:
        return True
    if texto in ACTIVO_FALSOS:
        return False
    raise ValidationError(f"activo debe ser TRUE/FALSE o 1/0 (recibido: '{valor}')")


def validar_filas(archivo, tipo, modelo):
    filas = leer_archivo(archivo)
    requeridas = set(columnas_para(tipo))
    campo_especifico = CAMPO_ESPECIFICO[tipo]
    if not filas:
        return [], [{"fila": 1, "error": "El archivo no contiene filas para importar."}]
    faltantes = requeridas - set(filas[0])
    if faltantes:
        return [], [{"fila": 1, "error": f"Faltan columnas: {', '.join(sorted(faltantes))}."}]
    errores, limpias, nits = [], [], set()
    for numero, fila in enumerate(filas, start=2):
        dato = {campo: str(fila.get(campo) or "").strip() for campo in requeridas}
        try:
            if not dato["nombre"] or not dato["nit"]:
                raise ValidationError("nombre y NIT son obligatorios")
            if dato["nit"] in nits:
                raise ValidationError("NIT duplicado dentro del archivo")
            nits.add(dato["nit"])
            dato["_accion"] = (
                "actualizar" if modelo.objects.filter(nit=dato["nit"]).exists()
                else "crear"
            )
            if dato["email"]:
                validate_email(dato["email"])
            if dato["telefono"] and not TELEFONO_RE.match(dato["telefono"]):
                raise ValidationError("telefono tiene un formato inválido")
            plazo = int(dato["plazo_pago_dias"] or 30)
            if not 1 <= plazo <= 120:
                raise ValidationError("plazo_pago_dias debe estar entre 1 y 120")
            dato["plazo_pago_dias"] = plazo
            for campo in ("fecha_inicio_contrato", "fecha_fin_contrato"):
                dato[campo] = date.fromisoformat(dato[campo]) if dato[campo] else None
            if dato["fecha_inicio_contrato"] and dato["fecha_fin_contrato"] and dato["fecha_fin_contrato"] < dato["fecha_inicio_contrato"]:
                raise ValidationError("la fecha final no puede ser anterior al inicio")
            dato["activo"] = _parsear_activo(dato["activo"])
            if tipo == "CLIENTE" and dato[campo_especifico] and dato[campo_especifico] not in INDUSTRIAS_VALIDAS:
                raise ValidationError(
                    f"industria '{dato[campo_especifico]}' no es válida "
                    f"(valores permitidos: {', '.join(sorted(INDUSTRIAS_VALIDAS))})"
                )
            limpias.append(dato)
        except (ValueError, ValidationError) as exc:
            mensaje = "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
            errores.append({"fila": numero, "error": mensaje})
    return limpias, errores
