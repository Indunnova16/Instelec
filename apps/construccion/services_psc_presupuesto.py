"""Snapshots, cálculo y contrato de presupuesto de Programación Semanal (#225)."""
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models_psc import (
    ProgramacionSemanalConstruccion,
    ProgramacionSemanalConstruccionPersonal,
    ProgramacionSemanalConstruccionPlanPresupuesto,
)


DIVISOR_MENSUAL = 30
CUANTIA_DIARIA = Decimal('0.0001')
CUANTIA_MONEDA = Decimal('0.01')


@dataclass(frozen=True)
class TarifaSnapshotPSC:
    salario_mensual: Decimal
    divisor: int
    tarifa_diaria: Decimal
    fuente: str
    cargo_codigo: str


@dataclass(frozen=True)
class PersonaPlanPresupuestoPSC:
    personal_id: str
    nombre: str
    rol: str
    es_supervisor: bool
    salario_mensual_snapshot: Optional[Decimal]
    divisor_snapshot: Optional[int]
    tarifa_diaria_snapshot: Optional[Decimal]
    fuente_tarifa: str
    cargo_snapshot_codigo: str
    subtotal_persona: Decimal


@dataclass(frozen=True)
class PlanPresupuestoPSC:
    programacion_id: str
    estado: str
    fecha_inicio: date
    fecha_fin: date
    dias_programados: int
    supervisor: Optional[PersonaPlanPresupuestoPSC]
    personas: tuple[PersonaPlanPresupuestoPSC, ...]
    presupuesto_total: Decimal
    congelado_en: Optional[datetime]
    primer_real_id: Optional[str]


def resolver_tarifa_diaria(personal) -> TarifaSnapshotPSC:
    """Resuelve la tarifa vigente, priorizando salario individual positivo."""
    salario_personal = Decimal(personal.salario_base or 0)
    cargo = getattr(personal, 'rol_cuadrilla', None)
    if salario_personal > 0:
        salario, fuente = salario_personal, ProgramacionSemanalConstruccionPersonal.FuenteTarifa.PERSONAL
    else:
        salario, fuente = Decimal(getattr(cargo, 'salario_base', 0) or 0), ProgramacionSemanalConstruccionPersonal.FuenteTarifa.CARGO
    return TarifaSnapshotPSC(
        salario_mensual=salario.quantize(CUANTIA_MONEDA),
        divisor=DIVISOR_MENSUAL,
        tarifa_diaria=(salario / DIVISOR_MENSUAL).quantize(CUANTIA_DIARIA, rounding=ROUND_HALF_UP),
        fuente=fuente,
        cargo_codigo=getattr(cargo, 'codigo', '') or '',
    )


def aplicar_snapshot_tarifa(asignacion, *, reemplazar=False):
    """Carga datos trazables una única vez salvo edición explícita antes del congelamiento."""
    if asignacion.tarifa_diaria_snapshot is not None and not reemplazar:
        return asignacion
    snapshot = resolver_tarifa_diaria(asignacion.personal)
    asignacion.salario_mensual_snapshot = snapshot.salario_mensual
    asignacion.divisor_snapshot = snapshot.divisor
    asignacion.tarifa_diaria_snapshot = snapshot.tarifa_diaria
    asignacion.fuente_tarifa = snapshot.fuente
    asignacion.cargo_snapshot_codigo = snapshot.cargo_codigo
    asignacion.snapshot_tomado_en = timezone.now()
    return asignacion


def construir_asignacion_presupuestada(programacion, personal, **kwargs):
    """Construye una asignación lista para persistir (también vía bulk_create)."""
    asignacion = ProgramacionSemanalConstruccionPersonal(
        programacion=programacion, personal=personal, **kwargs,
    )
    return aplicar_snapshot_tarifa(asignacion)


def _dias_programados(programacion):
    return (programacion.fecha_fin - programacion.fecha_inicio).days + 1


def _persona_desde_asignacion(asignacion, dias):
    tarifa = asignacion.tarifa_diaria_snapshot
    subtotal = Decimal('0.00') if tarifa is None else (tarifa * dias).quantize(CUANTIA_MONEDA, rounding=ROUND_HALF_UP)
    return PersonaPlanPresupuestoPSC(
        personal_id=str(asignacion.personal_id), nombre=asignacion.personal.nombre,
        rol=asignacion.rol_presupuesto,
        es_supervisor=asignacion.rol_presupuesto == asignacion.RolPresupuesto.SUPERVISOR,
        salario_mensual_snapshot=asignacion.salario_mensual_snapshot,
        divisor_snapshot=asignacion.divisor_snapshot,
        tarifa_diaria_snapshot=tarifa, fuente_tarifa=asignacion.fuente_tarifa,
        cargo_snapshot_codigo=asignacion.cargo_snapshot_codigo, subtotal_persona=subtotal,
    )


def _plan_editable(programacion):
    dias = _dias_programados(programacion)
    personas = tuple(_persona_desde_asignacion(a, dias) for a in programacion.asignaciones_personal.select_related('personal').all())
    supervisor = next((persona for persona in personas if persona.es_supervisor), None)
    return PlanPresupuestoPSC(
        programacion_id=str(programacion.pk), estado='EDITABLE', fecha_inicio=programacion.fecha_inicio,
        fecha_fin=programacion.fecha_fin, dias_programados=dias, supervisor=supervisor, personas=personas,
        presupuesto_total=sum((persona.subtotal_persona for persona in personas), Decimal('0.00')),
        congelado_en=None, primer_real_id=None,
    )


def _serializar_plan(plan):
    def serializar_persona(persona):
        data = asdict(persona)
        for campo in ('salario_mensual_snapshot', 'tarifa_diaria_snapshot', 'subtotal_persona'):
            data[campo] = str(data[campo]) if data[campo] is not None else None
        return data
    return {
        'programacion_id': plan.programacion_id, 'fecha_inicio': plan.fecha_inicio.isoformat(),
        'fecha_fin': plan.fecha_fin.isoformat(), 'dias_programados': plan.dias_programados,
        'supervisor': serializar_persona(plan.supervisor) if plan.supervisor else None,
        'personas': [serializar_persona(persona) for persona in plan.personas],
        'presupuesto_total': str(plan.presupuesto_total),
    }


def _deserializar_persona(data):
    data = dict(data)
    for campo in ('salario_mensual_snapshot', 'tarifa_diaria_snapshot', 'subtotal_persona'):
        if data[campo] is not None:
            data[campo] = Decimal(data[campo])
    return PersonaPlanPresupuestoPSC(**data)


def _plan_congelado(plan_congelado):
    data = plan_congelado.snapshot
    personas = tuple(_deserializar_persona(persona) for persona in data['personas'])
    supervisor = _deserializar_persona(data['supervisor']) if data['supervisor'] else None
    return PlanPresupuestoPSC(
        programacion_id=data['programacion_id'], estado='CONGELADO',
        fecha_inicio=date.fromisoformat(data['fecha_inicio']), fecha_fin=date.fromisoformat(data['fecha_fin']),
        dias_programados=data['dias_programados'], supervisor=supervisor, personas=personas,
        presupuesto_total=Decimal(data['presupuesto_total']), congelado_en=plan_congelado.congelado_en,
        primer_real_id=str(plan_congelado.primer_real_id),
    )


def obtener_plan_presupuesto_para_real(programacion_id) -> PlanPresupuestoPSC:
    """Contrato de lectura para #252; no infiere ProducciónDiaria por fechas ni texto."""
    programacion = ProgramacionSemanalConstruccion.objects.get(pk=programacion_id)
    try:
        return _plan_congelado(programacion.plan_presupuesto_congelado)
    except ProgramacionSemanalConstruccionPlanPresupuesto.DoesNotExist:
        return _plan_editable(programacion)


@transaction.atomic
def congelar_plan_presupuesto_por_primer_real(programacion_id, produccion_diaria_id, ocurrido_en):
    """Fija la primera versión del plan de forma idempotente y con vínculo explícito."""
    programacion = ProgramacionSemanalConstruccion.objects.select_for_update().get(pk=programacion_id)
    existente = ProgramacionSemanalConstruccionPlanPresupuesto.objects.filter(programacion=programacion).first()
    if existente:
        return _plan_congelado(existente)
    plan = _plan_editable(programacion)
    congelado = ProgramacionSemanalConstruccionPlanPresupuesto.objects.create(
        programacion=programacion, primer_real_id=produccion_diaria_id,
        congelado_en=ocurrido_en, snapshot=_serializar_plan(plan),
    )
    return _plan_congelado(congelado)
