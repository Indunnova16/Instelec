"""Lectura y validación sin efectos de los planos de terceros."""

import csv
import io
from datetime import date

from django.core.exceptions import ValidationError
from django.core.validators import validate_email


COMUNES = ("nombre", "nit", "email", "telefono", "direccion", "plazo_pago_dias", "fecha_inicio_contrato", "fecha_fin_contrato")
CAMPO_ESPECIFICO = {"CLIENTE": "industria", "PROVEEDOR": "tipo_servicio"}


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


def validar_filas(archivo, tipo, modelo):
    filas = leer_archivo(archivo)
    requeridas = set(columnas_para(tipo))
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
            if dato["nit"] in nits or modelo.objects.filter(nit=dato["nit"]).exists():
                raise ValidationError("NIT duplicado en archivo o base de datos")
            nits.add(dato["nit"])
            if dato["email"]:
                validate_email(dato["email"])
            plazo = int(dato["plazo_pago_dias"] or 30)
            if not 1 <= plazo <= 365:
                raise ValidationError("plazo_pago_dias debe estar entre 1 y 365")
            dato["plazo_pago_dias"] = plazo
            for campo in ("fecha_inicio_contrato", "fecha_fin_contrato"):
                dato[campo] = date.fromisoformat(dato[campo]) if dato[campo] else None
            if dato["fecha_inicio_contrato"] and dato["fecha_fin_contrato"] and dato["fecha_fin_contrato"] < dato["fecha_inicio_contrato"]:
                raise ValidationError("la fecha final no puede ser anterior al inicio")
            limpias.append(dato)
        except (ValueError, ValidationError) as exc:
            mensaje = "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
            errores.append({"fila": numero, "error": mensaje})
    return limpias, errores
