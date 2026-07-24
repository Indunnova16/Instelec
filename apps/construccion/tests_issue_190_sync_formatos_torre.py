"""Tests #190 — Sincronización de formatos únicos por torre + backfill.

Archivo dedicado (NO tests.py ni tests_b3_oc_detalle_modelo.py compartidos)
para evitar colisión con #191, que también toca `apps/construccion/` en
este mismo RUN (mismo patrón ya usado por tests_issue_171.py).

Bug reportado por Gabriel Valencia: `exc_ft023_ok`, `exc_ft058_ok`,
`exc_ft922_ok` (Excavación) y `com_ft914_ok` (Compactación) representan un
formato técnico ÚNICO por torre (no por pata), pero no existía ningún
mecanismo que los mantuviera sincronizados entre las 4 filas
torre×pata — el usuario los marcaba en la pata que estaba viendo en ese
momento y las otras 3 quedaban desactualizadas.

Fix (arquitectura ya decidida — NO re-evaluar):
  1. Signal `sincronizar_formatos_unicos_por_torre` (signals_b3_oc_detalle.py):
     propaga el valor VIGENTE de los 4 campos de la pata recién guardada a
     las otras 3 — propagación DIRECTA (last-write-wins), NO un "OR
     acumulativo": si una pata guarda False, ESO se propaga aunque otra
     pata tuviera True (confirmado en F2_OUTPUT — ver test 2 abajo).
  2. Data migration 0048 (`sync_formatos_torre_backfill`): reconcilia UNA
     VEZ los datos históricos que quedaron divergentes ANTES de este fix,
     con política "gana True" (solo aplica al backfill, no al signal).
  3. `unique_together = [('torre', 'pata')]` queda INTACTO — no se toca el
     schema (guardrail de no-regresión, test 4).
"""
import importlib

import pytest
from django.db import IntegrityError

# Los 4 campos que deben quedar sincronizados entre las 4 patas de una torre.
CAMPOS_SYNC_TORRE = ['exc_ft023_ok', 'exc_ft058_ok', 'exc_ft922_ok', 'com_ft914_ok']


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def proyecto_190(db):
    """ProyectoConstruccion dedicado a los tests de #190."""
    from apps.construccion.models import ProyectoConstruccion
    from apps.contratos.models import Contrato

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-190-001',
        nombre='Contrato test #190 sync formatos torre',
        cliente='Test Cliente',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto test #190',
        estado='EJECUCION',
    )


@pytest.fixture
def torre_190(proyecto_190):
    """Torre única — las 4 patas se crean en cada test según lo que necesite."""
    from apps.construccion.models import TorreConstruccion
    return TorreConstruccion.objects.create(
        proyecto=proyecto_190,
        numero='190',
        tipo='D6',
    )


@pytest.fixture
def cuatro_patas(proyecto_190, torre_190):
    """Crea las 4 patas (A/B/C/D) de `torre_190`, todas en default (False).

    Devuelve un dict {'A': detalle, 'B': detalle, ...} para acceso directo.
    """
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle

    return {
        pata: ObraCivilTorreDetalle.objects.create(
            proyecto=proyecto_190, torre=torre_190, pata=pata,
        )
        for pata in ['A', 'B', 'C', 'D']
    }


# ===========================================================================
# 1. Guardar pata A (True) propaga a B/C/D
# ===========================================================================

@pytest.mark.django_db
def test_signal_propaga_pata_a_true_a_b_c_d(cuatro_patas):
    """Marcar los 4 campos en True en la pata A debe reflejarse en B/C/D
    tras el `post_save` (sin necesidad de refresh manual del lado de quien
    escribe — cada UPDATE del signal es inmediato en BD)."""
    pata_a = cuatro_patas['A']
    for campo in CAMPOS_SYNC_TORRE:
        setattr(pata_a, campo, True)
    pata_a.save()

    for letra in ['B', 'C', 'D']:
        cuatro_patas[letra].refresh_from_db()
        for campo in CAMPOS_SYNC_TORRE:
            assert getattr(cuatro_patas[letra], campo) is True, (
                f'pata {letra}.{campo} no se sincronizó tras guardar pata A'
            )

    # La propia pata A conserva su valor (no se pisa a sí misma).
    pata_a.refresh_from_db()
    for campo in CAMPOS_SYNC_TORRE:
        assert getattr(pata_a, campo) is True


# ===========================================================================
# 2. Propagación DIRECTA (no "OR acumulativo"): True -> False también propaga
# ===========================================================================

@pytest.mark.django_db
def test_signal_propagacion_directa_false_sobrescribe_true_previo(cuatro_patas):
    """Confirma el comportamiento EXACTO decidido en F2_OUTPUT: el signal
    propaga el valor VIGENTE de la pata recién guardada, sin importar si
    "empeora" (True -> False) el valor que tenían las otras patas. NO es un
    OR acumulativo que solo deja "ganar" a True.

    Escenario (mismo que el journey E2E de F2, com_ft914_ok):
      1. Pata A guarda com_ft914_ok=True -> se propaga True a B/C/D.
      2. Pata A guarda com_ft914_ok=False -> se propaga False a B/C/D
         (incluida A misma, que ya lo tenía en False).
    """
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle

    pata_a = cuatro_patas['A']
    pata_a.com_ft914_ok = True
    pata_a.save()

    for letra in ['B', 'C', 'D']:
        assert ObraCivilTorreDetalle.objects.get(
            torre=pata_a.torre, pata=letra,
        ).com_ft914_ok is True

    # Ahora pata A vuelve a False y guarda de nuevo.
    pata_a.refresh_from_db()
    pata_a.com_ft914_ok = False
    pata_a.save()

    for letra in ['A', 'B', 'C', 'D']:
        assert ObraCivilTorreDetalle.objects.get(
            torre=pata_a.torre, pata=letra,
        ).com_ft914_ok is False, (
            f'pata {letra}.com_ft914_ok debía propagarse a False '
            '(propagación directa, no OR acumulativo)'
        )


# ===========================================================================
# 2b. El resto de campos de la pata NO se re-sincronizan (solo los 4 FT)
# ===========================================================================

@pytest.mark.django_db
def test_signal_no_toca_campos_fuera_de_la_lista_sync(cuatro_patas):
    """Un campo que NO está en CAMPOS_SYNC_TORRE (ej. `exc_ft022_ok`, otro FT
    de Excavación NO listado como "único por torre") debe seguir siendo
    independiente por pata — el signal no debe sobre-generalizar."""
    pata_a = cuatro_patas['A']
    pata_a.exc_ft022_ok = True  # NO está en CAMPOS_SYNC_TORRE
    pata_a.save()

    for letra in ['B', 'C', 'D']:
        cuatro_patas[letra].refresh_from_db()
        assert cuatro_patas[letra].exc_ft022_ok is False, (
            f'exc_ft022_ok de pata {letra} no debía sincronizarse '
            '(no está en CAMPOS_SYNC_TORRE)'
        )


# ===========================================================================
# 3. Backfill (migration 0048) — política "gana True", idempotente
# ===========================================================================

@pytest.mark.django_db
def test_backfill_0048_politica_gana_true_reconcilia_divergencia(
    proyecto_190,
):
    """2-3 torres fixture con divergencia simulada (creada ANTES del fix,
    emulando datos legacy) -> tras correr la RunPython, las 4 patas de cada
    torre quedan consistentes con "gana True" para cada uno de los 4 campos.

    Se llama al signal explícitamente para simular la escritura pre-fix: se
    desconecta el receiver nuevo mientras se siembra la divergencia (si no,
    el propio signal ya sincronizaría al crear/guardar y no podríamos
    reproducir el estado histórico divergente que el backfill necesita
    reconciliar).
    """
    from django.db.models.signals import post_save

    from apps.construccion.models import TorreConstruccion
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle
    from apps.construccion.signals_b3_oc_detalle import (
        sincronizar_formatos_unicos_por_torre,
    )

    mig = importlib.import_module(
        'apps.construccion.migrations.0048_sync_formatos_torre_backfill'
    )

    # Desconectar el signal nuevo para poder sembrar divergencia histórica
    # (tal como habría quedado la BD real ANTES de este fix).
    post_save.disconnect(
        sincronizar_formatos_unicos_por_torre, sender=ObraCivilTorreDetalle,
    )
    try:
        # Torre 1: divergencia en exc_ft023_ok (A=True, resto False) y
        # com_ft914_ok (mixto, ver evidencia real de F2: A=false,B=true,C=true,D=false)
        torre1 = TorreConstruccion.objects.create(proyecto=proyecto_190, numero='190-1')
        ObraCivilTorreDetalle.objects.create(
            proyecto=proyecto_190, torre=torre1, pata='A',
            exc_ft023_ok=True, com_ft914_ok=False,
        )
        ObraCivilTorreDetalle.objects.create(
            proyecto=proyecto_190, torre=torre1, pata='B',
            exc_ft023_ok=False, com_ft914_ok=True,
        )
        ObraCivilTorreDetalle.objects.create(
            proyecto=proyecto_190, torre=torre1, pata='C',
            exc_ft023_ok=False, com_ft914_ok=True,
        )
        ObraCivilTorreDetalle.objects.create(
            proyecto=proyecto_190, torre=torre1, pata='D',
            exc_ft023_ok=False, com_ft914_ok=False,
        )

        # Torre 2: SIN divergencia (control) — el backfill no debe tocarla.
        torre2 = TorreConstruccion.objects.create(proyecto=proyecto_190, numero='190-2')
        for pata in ['A', 'B', 'C', 'D']:
            ObraCivilTorreDetalle.objects.create(
                proyecto=proyecto_190, torre=torre2, pata=pata,
                exc_ft058_ok=False, com_ft914_ok=False,
            )

        # Torre 3: TODAS en True en los 4 campos (ya consistente) — control.
        torre3 = TorreConstruccion.objects.create(proyecto=proyecto_190, numero='190-3')
        for pata in ['A', 'B', 'C', 'D']:
            ObraCivilTorreDetalle.objects.create(
                proyecto=proyecto_190, torre=torre3, pata=pata,
                exc_ft923_ok=True,
            )

        # FORWARD — invoca la migration real.
        from django.apps import apps as django_apps
        mig.sync_formatos_torre_backfill(django_apps, None)

        # Torre 1: "gana True" -> exc_ft023_ok y com_ft914_ok quedan True en
        # las 4 patas (alguna pata tenía True para ambos campos).
        for pata in ['A', 'B', 'C', 'D']:
            det = ObraCivilTorreDetalle.objects.get(torre=torre1, pata=pata)
            assert det.exc_ft023_ok is True, f'torre1 pata {pata} exc_ft023_ok'
            assert det.com_ft914_ok is True, f'torre1 pata {pata} com_ft914_ok'

        # Torre 2: sin divergencia -> nada cambia (sigue todo False).
        for pata in ['A', 'B', 'C', 'D']:
            det = ObraCivilTorreDetalle.objects.get(torre=torre2, pata=pata)
            assert det.exc_ft058_ok is False
            assert det.com_ft914_ok is False

        # Torre 3: ya consistente en True -> sigue en True (no-op real).
        for pata in ['A', 'B', 'C', 'D']:
            det = ObraCivilTorreDetalle.objects.get(torre=torre3, pata=pata)
            assert det.exc_ft923_ok is True

        # IDEMPOTENCIA: correr la migration una 2da vez no cambia nada.
        snapshot_antes = list(
            ObraCivilTorreDetalle.objects.filter(
                torre__in=[torre1, torre2, torre3],
            ).order_by('torre_id', 'pata').values(
                'torre_id', 'pata', *CAMPOS_SYNC_TORRE,
            )
        )
        mig.sync_formatos_torre_backfill(django_apps, None)
        snapshot_despues = list(
            ObraCivilTorreDetalle.objects.filter(
                torre__in=[torre1, torre2, torre3],
            ).order_by('torre_id', 'pata').values(
                'torre_id', 'pata', *CAMPOS_SYNC_TORRE,
            )
        )
        assert snapshot_antes == snapshot_despues, (
            'la migration de backfill NO es idempotente — la 2da corrida '
            'cambió datos'
        )
    finally:
        # Reconectar el signal — no contaminar otros tests del módulo.
        post_save.connect(
            sincronizar_formatos_unicos_por_torre, sender=ObraCivilTorreDetalle,
        )


@pytest.mark.django_db
def test_backfill_0048_data_safe_con_cero_filas(proyecto_190):
    """Correr la migration sin ningún ObraCivilTorreDetalle en BD no falla."""
    from django.apps import apps as django_apps

    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle

    mig = importlib.import_module(
        'apps.construccion.migrations.0048_sync_formatos_torre_backfill'
    )
    assert not ObraCivilTorreDetalle.objects.filter(proyecto=proyecto_190).exists()
    mig.sync_formatos_torre_backfill(django_apps, None)  # no debe lanzar


# ===========================================================================
# 4. No-regresión: unique_together(torre, pata) sigue intacto
# ===========================================================================

@pytest.mark.django_db
def test_unique_together_torre_pata_no_se_rompe(proyecto_190, torre_190):
    """Guardrail: el fix de #190 es un signal de sincronización, NO una
    migración de schema — crear 2 filas con la misma (torre, pata) debe
    seguir fallando con IntegrityError, exactamente igual que antes."""
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle

    ObraCivilTorreDetalle.objects.create(
        proyecto=proyecto_190, torre=torre_190, pata='A',
    )
    with pytest.raises(IntegrityError):
        ObraCivilTorreDetalle.objects.create(
            proyecto=proyecto_190, torre=torre_190, pata='A',
        )


@pytest.mark.django_db
def test_sync_no_crea_filas_nuevas_solo_actualiza_las_4_existentes(cuatro_patas):
    """Guardrail complementario: tras guardar y sincronizar, siguen
    existiendo EXACTAMENTE 4 filas por torre (el signal usa `.update()`,
    nunca `.create()`)."""
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle

    torre = cuatro_patas['A'].torre
    pata_a = cuatro_patas['A']
    pata_a.exc_ft058_ok = True
    pata_a.save()

    assert ObraCivilTorreDetalle.objects.filter(torre=torre).count() == 4
