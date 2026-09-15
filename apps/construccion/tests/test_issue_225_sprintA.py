from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.contratos.models import Contrato
from apps.construccion.models import (
    ProgramacionSemanalConstruccion,
    ProgramacionSemanalConstruccionPersonal,
    ProyectoConstruccion,
)
from apps.construccion.services_psc_presupuesto import (
    congelar_plan_presupuesto_por_primer_real,
    construir_asignacion_presupuestada,
    obtener_plan_presupuesto_para_real,
    resolver_tarifa_diaria,
)
from apps.cuadrillas.models import Cargo, Cuadrilla, PersonalCuadrilla
from apps.cuadrillas.models_pc import ProgramacionSemanalCuadrilla
from apps.cuadrillas.models_produccion_diaria import ProduccionDiaria


@pytest.fixture
def psc_presupuesto():
    contrato = Contrato.objects.create(
        codigo='PSC-225-A', nombre='Contrato presupuesto PSC', unidad_negocio='CONSTRUCCION',
    )
    proyecto = ProyectoConstruccion.objects.create(contrato=contrato, nombre='Proyecto presupuesto PSC')
    cargo = Cargo.objects.create(codigo='PSC225-CARGO', nombre='Cargo PSC', salario_base=Decimal('3000.00'))
    individual = PersonalCuadrilla.objects.create(
        nombre='Individual PSC', documento='PSC-225-A-1', rol_cuadrilla=cargo,
        salario_base=Decimal('6000.00'), area='CONSTRUCCION',
    )
    fallback = PersonalCuadrilla.objects.create(
        nombre='Fallback PSC', documento='PSC-225-A-2', rol_cuadrilla=cargo,
        salario_base=Decimal('0.00'), area='CONSTRUCCION',
    )
    programacion = ProgramacionSemanalConstruccion.objects.create(
        proyecto=proyecto, tipo_actividad='OBRA_CIVIL', subactividad='Excavación',
        fecha_inicio=date(2026, 9, 14), fecha_fin=date(2026, 9, 16),
    )
    supervisor = construir_asignacion_presupuestada(
        programacion, individual,
        rol_presupuesto=ProgramacionSemanalConstruccionPersonal.RolPresupuesto.SUPERVISOR,
    )
    supervisor.save()
    colaborador = construir_asignacion_presupuestada(programacion, fallback)
    colaborador.save()
    return programacion, individual, fallback, cargo, supervisor, colaborador


@pytest.mark.django_db
def test_tarifa_prioriza_personal_y_fallback_cargo_con_snapshot_inmutable(psc_presupuesto):
    _, individual, fallback, cargo, supervisor, colaborador = psc_presupuesto

    assert resolver_tarifa_diaria(individual).tarifa_diaria == Decimal('200.0000')
    assert resolver_tarifa_diaria(individual).fuente == 'PERSONAL'
    assert resolver_tarifa_diaria(fallback).tarifa_diaria == Decimal('100.0000')
    assert colaborador.fuente_tarifa == 'CARGO'
    assert colaborador.cargo_snapshot_codigo == cargo.codigo

    individual.salario_base = Decimal('9000.00')
    individual.save(update_fields=['salario_base'])
    cargo.salario_base = Decimal('4500.00')
    cargo.save(update_fields=['salario_base'])
    supervisor.refresh_from_db()
    colaborador.refresh_from_db()
    assert supervisor.tarifa_diaria_snapshot == Decimal('200.0000')
    assert colaborador.tarifa_diaria_snapshot == Decimal('100.0000')


@pytest.mark.django_db
def test_plan_editable_calcula_dias_inclusivos_y_legacy_sin_snapshot_permanece_legible(psc_presupuesto):
    programacion, _, fallback, _, _, _ = psc_presupuesto
    plan = obtener_plan_presupuesto_para_real(programacion.pk)

    assert plan.estado == 'EDITABLE'
    assert plan.dias_programados == 3
    assert plan.supervisor.nombre == 'Individual PSC'
    assert plan.presupuesto_total == Decimal('900.00')

    # Una PSC previa conserva los campos nulos: el contrato la devuelve sin error ni inventar salario.
    legado_programacion = ProgramacionSemanalConstruccion.objects.create(
        proyecto=programacion.proyecto, tipo_actividad='TENDIDO', subactividad='Legacy',
        fecha_inicio=date(2026, 9, 20), fecha_fin=date(2026, 9, 20),
    )
    ProgramacionSemanalConstruccionPersonal.objects.create(programacion=legado_programacion, personal=fallback)
    legado = obtener_plan_presupuesto_para_real(legado_programacion.pk)
    assert legado.personas[0].tarifa_diaria_snapshot is None
    assert legado.presupuesto_total == Decimal('0.00')


@pytest.mark.django_db
def test_un_solo_supervisor_presupuestario_por_programacion(psc_presupuesto):
    programacion, _, _, cargo, _, _ = psc_presupuesto
    otro = PersonalCuadrilla.objects.create(
        nombre='Segundo supervisor', documento='PSC-225-A-3', rol_cuadrilla=cargo,
        salario_base=Decimal('2000.00'), area='CONSTRUCCION',
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        construir_asignacion_presupuestada(
            programacion, otro,
            rol_presupuesto=ProgramacionSemanalConstruccionPersonal.RolPresupuesto.SUPERVISOR,
        ).save()


@pytest.mark.django_db
def test_congelamiento_es_idempotente_y_aisla_ediciones_posteriores(psc_presupuesto):
    programacion, _, _, _, _, colaborador = psc_presupuesto
    cuadrilla = Cuadrilla.objects.create(codigo='PSC225-A', nombre='Cuadrilla PSC 225')
    semanal = ProgramacionSemanalCuadrilla.objects.create(cuadrilla=cuadrilla, anio=2026, semana=38)
    primer_real = ProduccionDiaria.objects.create(programacion=semanal, fecha=date(2026, 9, 14))
    segundo_real = ProduccionDiaria.objects.create(programacion=semanal, fecha=date(2026, 9, 15))

    congelado = congelar_plan_presupuesto_por_primer_real(programacion.pk, primer_real.pk, timezone.now())
    programacion.fecha_fin = date(2026, 9, 20)
    programacion.save(update_fields=['fecha_fin'])
    colaborador.tarifa_diaria_snapshot = Decimal('999.0000')
    colaborador.save(update_fields=['tarifa_diaria_snapshot'])
    repetido = congelar_plan_presupuesto_por_primer_real(programacion.pk, segundo_real.pk, timezone.now())

    assert congelado.estado == 'CONGELADO'
    assert congelado.primer_real_id == str(primer_real.pk)
    assert repetido.primer_real_id == str(primer_real.pk)
    assert repetido.dias_programados == 3
    assert repetido.presupuesto_total == Decimal('900.00')
