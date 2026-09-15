"""Servicios puros y persistentes compartidos por Producción Diaria (#252)."""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from .models_base import Asistencia, CuadrillaMiembro, PersonalCuadrilla
from .models_produccion_diaria import AlertaProduccion, ProduccionDiaria, RegistroPersonalProduccion

UMBRAL_DESVIACION_PCT = Decimal("20")

MOTIVOS_ASISTENCIA = {
    Asistencia.TipoNovedad.AUSENTE: RegistroPersonalProduccion.MotivoAusencia.NO_INFORMO,
    Asistencia.TipoNovedad.INCAPACIDAD: RegistroPersonalProduccion.MotivoAusencia.ENFERMEDAD,
    Asistencia.TipoNovedad.PERMISO: RegistroPersonalProduccion.MotivoAusencia.PERMISO,
    Asistencia.TipoNovedad.LICENCIA: RegistroPersonalProduccion.MotivoAusencia.OTRO,
    Asistencia.TipoNovedad.VACACIONES: RegistroPersonalProduccion.MotivoAusencia.OTRO,
    Asistencia.TipoNovedad.CAPACITACION: RegistroPersonalProduccion.MotivoAusencia.OTRO,
    Asistencia.TipoNovedad.COMPENSATORIO: RegistroPersonalProduccion.MotivoAusencia.OTRO,
    Asistencia.TipoNovedad.DESCANSO: RegistroPersonalProduccion.MotivoAusencia.OTRO,
    Asistencia.TipoNovedad.DIA_GANADO: RegistroPersonalProduccion.MotivoAusencia.OTRO,
    Asistencia.TipoNovedad.FESTIVO: RegistroPersonalProduccion.MotivoAusencia.OTRO,
}


def horas_de_asistencia(asistencia):
    """Calcula horas reales, incluyendo HE, sin inventar jornada para ausencias."""
    if asistencia.tipo_novedad != Asistencia.TipoNovedad.PRESENTE:
        return Decimal("0")
    if asistencia.hora_entrada and asistencia.hora_salida:
        inicio = datetime.combine(asistencia.fecha, asistencia.hora_entrada)
        fin = datetime.combine(asistencia.fecha, asistencia.hora_salida)
        horas = Decimal(str(max((fin - inicio).total_seconds() / 3600, 0)))
    else:
        horas = Decimal(str(asistencia.JORNADA_POR_DIA.get(asistencia.fecha.weekday(), 0)))
    return min(horas + Decimal(str(asistencia.horas_extra or 0)), Decimal("24"))


def _personal_para_asistencia(asistencia):
    """Resuelve el catálogo existente; no crea colaboradores implícitamente."""
    miembro = CuadrillaMiembro.objects.filter(
        cuadrilla=asistencia.cuadrilla, usuario=asistencia.usuario
    ).select_related("usuario").first()
    if miembro:
        documento = miembro.usuario.documento
    else:
        documento = asistencia.usuario.documento
    return PersonalCuadrilla.objects.filter(documento=documento).first() if documento else None


@transaction.atomic
def importar_asistencias(programacion, fecha, registrado_por=None):
    """Importa una jornada de TransMaint de forma idempotente y trazable.

    Las filas sin contraparte en ``PersonalCuadrilla`` se devuelven como aviso;
    crear personal a partir de asistencia ocultaría un error de catálogo.
    """
    iso = fecha.isocalendar()
    if (iso.year, iso.week) != (programacion.anio, programacion.semana):
        raise ValueError("La fecha no pertenece a la semana ISO de la programación.")
    produccion, creada = ProduccionDiaria.objects.get_or_create(
        programacion=programacion, fecha=fecha,
        defaults={"registrado_por": registrado_por, "importada_en": timezone.now()},
    )
    omitidas = []
    asistencias = Asistencia.objects.filter(cuadrilla=programacion.cuadrilla, fecha=fecha).select_related("usuario")
    for asistencia in asistencias:
        personal = _personal_para_asistencia(asistencia)
        if personal is None:
            omitidas.append(str(asistencia.usuario))
            continue
        horas = horas_de_asistencia(asistencia)
        defaults = {
            "produccion": produccion,
            "personal": personal,
            "horas_trabajadas": horas,
            "motivo_ausencia": MOTIVOS_ASISTENCIA.get(asistencia.tipo_novedad, ""),
            "observacion": asistencia.observacion or "Importado desde Asistencia",
        }
        RegistroPersonalProduccion.objects.update_or_create(
            asistencia_origen=asistencia, defaults=defaults
        )
    return produccion, creada, omitidas


def filas_diarias(fecha=None, proyecto_id=None):
    """Une programación y producción para que el listado muestre pendientes."""
    from datetime import date
    from .models_pc import ProgramacionSemanalCuadrilla

    fecha = fecha or timezone.localdate()
    iso = fecha.isocalendar()
    programaciones = ProgramacionSemanalCuadrilla.objects.filter(anio=iso.year, semana=iso.week)
    if proyecto_id:
        programaciones = programaciones.filter(proyecto_id=proyecto_id)
    existentes = {
        item.programacion_id: item
        for item in ProduccionDiaria.objects.filter(programacion__in=programaciones, fecha=fecha)
        .select_related("programacion", "programacion__cuadrilla", "programacion__proyecto", "alerta_desviacion")
        .prefetch_related("registros_personal")
    }
    return [
        {"programacion": programacion, "produccion": existentes.get(programacion.pk),
         "estado": "REGISTRADO" if programacion.pk in existentes else "PENDIENTE"}
        for programacion in programaciones.select_related("cuadrilla", "proyecto").order_by("cuadrilla__codigo")
    ]


def calcular_desviacion_pct(real, programado):
    """Retorna la desviación porcentual; sin base programada no inventa un valor."""
    real = Decimal(str(real or 0))
    programado = Decimal(str(programado or 0))
    if programado <= 0:
        return None
    return ((real - programado) / programado * 100).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def sincronizar_alerta_desviacion(produccion, real, programado):
    """Crea/actualiza una alerta solamente cuando la desviación supera 20 %."""
    desviacion = calcular_desviacion_pct(real, programado)
    if desviacion is None or abs(desviacion) <= UMBRAL_DESVIACION_PCT:
        AlertaProduccion.objects.filter(produccion=produccion).delete()
        return None
    return AlertaProduccion.objects.update_or_create(
        produccion=produccion,
        defaults={
            "desviacion_pct": desviacion,
            "mensaje": f"Desviación de {desviacion}% frente a lo programado.",
        },
    )[0]
