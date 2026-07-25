"""Tests #190 — Sincronización de formatos únicos por torre + backfill.

Archivo dedicado (NO tests.py ni tests_b3_oc_detalle_modelo.py compartidos)
para evitar colisión con #191, que también toca `apps/construccion/` en
este mismo RUN (mismo patrón ya usado por tests_issue_171.py).

Bug reportado por Gabriel Valencia: 17 campos FT (11 `exc_ft0XX_ok` de
Excavación, `ace_ft028_ok`/`ace_ft930_ok` de Acero, `vac_ft916_ok`/
`vac_it380_ok`/`vac_ft056_ok` de Vaciado, `com_ft914_ok` de Compactación)
representan un formato técnico ÚNICO por torre (no por pata), pero no
existía ningún mecanismo que los mantuviera sincronizados entre las 4 filas
torre×pata — el usuario los marcaba en la pata que estaba viendo en ese
momento y las otras 3 quedaban desactualizadas.

REOPEN 2026-07-25 (bounce=1, FIX_INCOMPLETO): el fix original (`4715f85`,
cerrado 🟢 2026-07-24) solo sincronizó 4 de los 17 campos reales y no tocó
la UI. Este archivo cubre la extensión completa:
  1. Signal `sincronizar_formatos_unicos_por_torre` (signals_b3_oc_detalle.py):
     `CAMPOS_SYNC_TORRE` extendido de 4 a 17 campos — propaga el valor
     VIGENTE de la pata recién guardada a las otras 3 — propagación DIRECTA
     (last-write-wins), NO un "OR acumulativo": si una pata guarda False,
     ESO se propaga aunque otra pata tuviera True (confirmado en
     F2_OUTPUT — ver test 2 abajo).
  2. Data migration 0048 (4 campos, histórico) + 0049 (13 campos nuevos):
     reconcilian UNA VEZ los datos históricos que quedaron divergentes
     ANTES de este fix, con política "gana True" (solo aplica al backfill,
     no al signal).
  3. `OCTorreFormatosForm` + `ObraCivilTorreFormatosView`/
     `ObraCivilTorreFormatosGuardarView` (A2): único lugar editable de los
     17 campos, persiste sobre la pata canónica 'A', reusa el signal (1)
     para propagar — NO reimplementa un `update()` manual paralelo.
  4. Los 17 campos se removieron de los 4 forms/templates de sección de
     Pata (A4) — ya NO son editables ahí.
  5. `unique_together = [('torre', 'pata')]` queda INTACTO — no se toca el
     schema (guardrail de no-regresión, test 4).
"""
import importlib

import pytest
from django.db import IntegrityError
from django.urls import reverse

from apps.construccion.signals_b3_oc_detalle import CAMPOS_SYNC_TORRE


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
    """Marcar los 17 campos (CAMPOS_SYNC_TORRE extendido, A1) en True en la
    pata A debe reflejarse en B/C/D tras el `post_save` (sin necesidad de
    refresh manual del lado de quien escribe — cada UPDATE del signal es
    inmediato en BD). Cubre los 13 campos nuevos del reopen, incluyendo
    `ace_ft930_ok` (cruza de sección Acero — NO estaba en la lista vieja de
    4) y `exc_ft022_ok` (uno de los 11 de Excavación NO cubiertos antes)."""
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
    """Un campo que NO está en CAMPOS_SYNC_TORRE (ej. `exc_penetrometro_ok`,
    un booleano de Excavación que NO es un FT "único por torre") debe seguir
    siendo independiente por pata — el signal no debe sobre-generalizar.

    NOTA #190 reopen: antes de la extensión a 17 campos, este test usaba
    `exc_ft022_ok` como ejemplo de campo "fuera de la lista" — con
    CAMPOS_SYNC_TORRE extendido (A1), `exc_ft022_ok` SÍ está en la lista
    ahora (ver test_signal_extendido_17_campos_propaga_incluyendo_exc_ft022_ok
    abajo), así que este guardrail usa un campo genuinamente ajeno.
    """
    assert 'exc_penetrometro_ok' not in CAMPOS_SYNC_TORRE

    pata_a = cuatro_patas['A']
    pata_a.exc_penetrometro_ok = True  # NO está en CAMPOS_SYNC_TORRE
    pata_a.save()

    for letra in ['B', 'C', 'D']:
        cuatro_patas[letra].refresh_from_db()
        assert cuatro_patas[letra].exc_penetrometro_ok is False, (
            f'exc_penetrometro_ok de pata {letra} no debía sincronizarse '
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


# ===========================================================================
# 5. Extensión 17 campos — foco explícito en ace_ft930_ok (reopen)
# ===========================================================================

@pytest.mark.django_db
def test_signal_incluye_ace_ft930_ok_extension_13_campos_nuevos(cuatro_patas):
    """#190 reopen (bounce=1): `ace_ft930_ok` es uno de los 13 campos NUEVOS
    que la extensión de CAMPOS_SYNC_TORRE (A1, 4 -> 17) cubre. Antes del
    reopen, este campo NO tenía NINGÚN mecanismo de sincronización (ni
    siquiera el signal viejo de 4 campos lo cubría) — es el gap literal que
    el cliente reportó (validado en vivo por Andrea contra QA#49 con la
    torre E63). También es el campo cuya sección de MODELO (Acero) difiere
    de su etiqueta de AGRUPAMIENTO EN LA UI (Vaciado) — ver PLAN, tabla de
    desalineamiento."""
    assert 'ace_ft930_ok' in CAMPOS_SYNC_TORRE

    pata_a = cuatro_patas['A']
    pata_a.ace_ft930_ok = True
    pata_a.save()

    for letra in ['B', 'C', 'D']:
        cuatro_patas[letra].refresh_from_db()
        assert cuatro_patas[letra].ace_ft930_ok is True, (
            f'ace_ft930_ok de pata {letra} no se sincronizó — este es '
            'justo el campo que el fix anterior (4 campos) no cubría'
        )


# ===========================================================================
# 6. Ausencia de los 17 campos en los 4 forms de sección de Pata (A4)
# ===========================================================================

@pytest.mark.parametrize('campo', CAMPOS_SYNC_TORRE)
def test_campo_ft_no_esta_en_ningun_form_de_pata(campo):
    """A4: ninguno de los 17 campos FT debe seguir expuesto en los 4 forms
    de sección de Pata (Excavación/Acero/Vaciado/Compactación) — el ÚNICO
    lugar editable pasa a ser `OCTorreFormatosForm` (pestaña Torre, A2/A3).
    """
    from apps.construccion.forms_b3_oc_detalle import (
        OCSeccionAceroForm, OCSeccionCompactacionForm,
        OCSeccionExcavacionForm, OCSeccionVaciadoForm,
    )

    for FormClass in (
        OCSeccionExcavacionForm, OCSeccionAceroForm,
        OCSeccionVaciadoForm, OCSeccionCompactacionForm,
    ):
        assert campo not in FormClass.Meta.fields, (
            f'{campo} sigue expuesto en {FormClass.__name__}.Meta.fields '
            '— A4 debía removerlo (único lugar editable: OCTorreFormatosForm)'
        )


def test_los_17_campos_ft_estan_en_oc_torre_formatos_form():
    """Guardrail complementario: los 17 campos SÍ están en
    `OCTorreFormatosForm.Meta.fields` (único lugar editable) — evita que A4
    remueva de más y deje un campo sin ningún form que lo exponga."""
    from apps.construccion.forms_b3_oc_detalle import OCTorreFormatosForm

    for campo in CAMPOS_SYNC_TORRE:
        assert campo in OCTorreFormatosForm.Meta.fields, (
            f'{campo} no está en OCTorreFormatosForm.Meta.fields — quedaría '
            'sin NINGÚN form que lo exponga'
        )
    assert len(OCTorreFormatosForm.Meta.fields) == 17


# ===========================================================================
# 7. Vista "Torre" (A2) — GET puebla desde pata canónica 'A' + POST persiste
# ===========================================================================

@pytest.fixture
def torre_190_view(proyecto_190):
    """Torre dedicada a los tests de vista (evita compartir estado con los
    tests de signal de arriba, que usan `torre_190`/`cuatro_patas`)."""
    from apps.construccion.models import TorreConstruccion
    return TorreConstruccion.objects.create(
        proyecto=proyecto_190, numero='190-VIEW', tipo='D6',
    )


@pytest.mark.django_db
def test_torre_formatos_view_get_200_puebla_17_campos_desde_pata_a(
    authenticated_client, proyecto_190, torre_190_view,
):
    """GET renderiza el form con los 17 campos, poblados desde la pata
    canónica 'A' (creada on-demand vía get_or_create, igual que
    ObraCivilDetalleView)."""
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle

    ObraCivilTorreDetalle.objects.create(
        proyecto=proyecto_190, torre=torre_190_view, pata='A',
        exc_ft022_ok=True, ace_ft930_ok=True,
    )

    url = reverse(
        'construccion:obra_civil_torre_formatos',
        kwargs={'proyecto_id': proyecto_190.id, 'torre_id': torre_190_view.id},
    )
    resp = authenticated_client.get(url)
    assert resp.status_code == 200

    form = resp.context['form']
    assert set(form.fields.keys()) == set(CAMPOS_SYNC_TORRE)
    assert form.initial.get('exc_ft022_ok') is True or \
        form['exc_ft022_ok'].value() is True
    assert form['ace_ft930_ok'].value() is True


@pytest.mark.django_db
def test_torre_formatos_view_post_persiste_y_dispara_signal(
    authenticated_client, proyecto_190, torre_190_view,
):
    """POST AJAX persiste sobre la pata 'A' y dispara el signal de A1, que
    propaga a B/C/D — el mismo mecanismo, sin `update()` manual paralelo."""
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle

    for pata in ['A', 'B', 'C', 'D']:
        ObraCivilTorreDetalle.objects.create(
            proyecto=proyecto_190, torre=torre_190_view, pata=pata,
        )

    url = reverse(
        'construccion:obra_civil_torre_formatos_guardar',
        kwargs={'proyecto_id': proyecto_190.id, 'torre_id': torre_190_view.id},
    )
    data = {campo: 'on' for campo in ['ace_ft930_ok', 'com_ft914_ok']}
    resp = authenticated_client.post(url, data)

    assert resp.status_code == 200, resp.content[:500]
    assert resp.json() == {'ok': True}

    for pata in ['A', 'B', 'C', 'D']:
        det = ObraCivilTorreDetalle.objects.get(torre=torre_190_view, pata=pata)
        assert det.ace_ft930_ok is True, f'pata {pata} no sincronizó ace_ft930_ok'
        assert det.com_ft914_ok is True, f'pata {pata} no sincronizó com_ft914_ok'
        # Los campos no marcados en el POST quedan en su default (False) —
        # confirma que no hubo "OR acumulativo" con un valor previo.
        assert det.exc_ft022_ok is False


def test_torre_formatos_form_no_tiene_validacion_de_invalidez_por_diseno():
    """`OCTorreFormatosForm` expone ÚNICAMENTE BooleanField (17 checkboxes,
    sin ningún `clean_*` propio) — a diferencia de `ObraCivilDetalleSeccionView`
    (que sí puede devolver 400 en secciones con campos numéricos/pct
    validados), NO existe un POST "inválido" real para este form: un
    checkbox no marcado simplemente no viaja en el POST y Django lo
    interpreta como False (Django marca `BooleanField.required=False` por
    diseño para inputs checkbox, sin importar `blank` en el modelo — mismo
    comportamiento ya usado por los 4 forms de sección de Pata, confirmado
    por `test_post_excavacion_metros_m3_persiste` en
    `tests_b3_oc_detalle_views.py`, que postea sin todos los booleans).

    Este test documenta esa decisión en vez de fabricar un escenario de
    invalidez que no existe. `ObraCivilTorreFormatosGuardarView.post` SÍ
    implementa el contrato `{'ok': False, 'errors': ...}` (mismo patrón que
    `ObraCivilDetalleSeccionView`) por si en el futuro se agrega un campo
    con validación propia — en ese caso, agregar acá un test POST-inválido
    real (400)."""
    from django import forms as django_forms

    from apps.construccion.forms_b3_oc_detalle import OCTorreFormatosForm

    for name, field in OCTorreFormatosForm.base_fields.items():
        assert isinstance(field, django_forms.BooleanField), (
            f'{name} no es BooleanField — agregar test POST-inválido real '
            '(400) para ObraCivilTorreFormatosGuardarView'
        )
        assert field.required is False


@pytest.mark.django_db
def test_torre_formatos_view_cross_proyecto_404(
    authenticated_client, proyecto_190, torre_190_view,
):
    """Guardrail de aislamiento: la torre no pertenece al proyecto en la
    URL -> 404 (mismo contrato que ObraCivilDetalleView)."""
    from apps.construccion.models import ProyectoConstruccion
    from apps.contratos.models import Contrato

    contrato_otro = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-190-OTRO',
        nombre='Contrato test #190 otro proyecto',
        cliente='Test Cliente Otro',
    )
    proyecto_otro = ProyectoConstruccion.objects.create(
        contrato=contrato_otro, nombre='Proyecto test #190 otro', estado='EJECUCION',
    )

    url = reverse(
        'construccion:obra_civil_torre_formatos',
        kwargs={'proyecto_id': proyecto_otro.id, 'torre_id': torre_190_view.id},
    )
    resp = authenticated_client.get(url)
    assert resp.status_code == 404


@pytest.mark.django_db
def test_link_torre_en_detalle_patas_apunta_a_la_vista_torre(
    authenticated_client, proyecto_190, torre_190_view,
):
    """A3: `ObraCivilDetalleView` (pestaña Patas) expone `pestanas_torre`
    (1 solo ítem, `slug='torre'`) apuntando a la URL de la pestaña Torre —
    la integración del nav ANTES de "Patas"."""
    url = reverse(
        'construccion:obra_civil_detalle',
        kwargs={'proyecto_id': proyecto_190.id, 'torre_id': torre_190_view.id},
    )
    resp = authenticated_client.get(url)
    assert resp.status_code == 200

    pestanas_torre = resp.context['pestanas_torre']
    assert len(pestanas_torre) == 1
    assert pestanas_torre[0]['slug'] == 'torre'
    assert pestanas_torre[0]['active'] is False

    url_torre_formatos = reverse(
        'construccion:obra_civil_torre_formatos',
        kwargs={'proyecto_id': proyecto_190.id, 'torre_id': torre_190_view.id},
    )
    assert pestanas_torre[0]['url'] == url_torre_formatos


# ===========================================================================
# 8. Migración 0049 — backfill de los 13 campos nuevos (espejo de 0048)
# ===========================================================================

@pytest.mark.django_db
def test_backfill_0049_politica_gana_true_reconcilia_los_13_campos_nuevos(
    proyecto_190,
):
    """Espejo de `test_backfill_0048_politica_gana_true_reconcilia_divergencia`
    (arriba), pero para 0049 — cubre 2 de los 13 campos NUEVOS
    (`exc_ft022_ok` de Excavación y `ace_ft930_ok` de Acero, este último la
    prueba explícita del gap que el reopen reportó) para confirmar que
    0049 reconcilia lo que 0048 NO cubría."""
    from django.db.models.signals import post_save

    from apps.construccion.models import TorreConstruccion
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle
    from apps.construccion.signals_b3_oc_detalle import (
        sincronizar_formatos_unicos_por_torre,
    )

    mig = importlib.import_module(
        'apps.construccion.migrations.0049_sync_17_formatos_torre_backfill'
    )

    post_save.disconnect(
        sincronizar_formatos_unicos_por_torre, sender=ObraCivilTorreDetalle,
    )
    try:
        # Torre 1: divergencia real en exc_ft022_ok y ace_ft930_ok (espejo
        # de la evidencia BD prod de F2: Torre E63, pata D en False, A/B/C
        # en True).
        torre1 = TorreConstruccion.objects.create(proyecto=proyecto_190, numero='190-49-1')
        ObraCivilTorreDetalle.objects.create(
            proyecto=proyecto_190, torre=torre1, pata='A',
            exc_ft022_ok=True, ace_ft930_ok=True,
        )
        ObraCivilTorreDetalle.objects.create(
            proyecto=proyecto_190, torre=torre1, pata='B',
            exc_ft022_ok=True, ace_ft930_ok=True,
        )
        ObraCivilTorreDetalle.objects.create(
            proyecto=proyecto_190, torre=torre1, pata='C',
            exc_ft022_ok=True, ace_ft930_ok=True,
        )
        ObraCivilTorreDetalle.objects.create(
            proyecto=proyecto_190, torre=torre1, pata='D',
            exc_ft022_ok=False, ace_ft930_ok=False,
        )

        # Torre 2: sin divergencia (control) — 0049 no debe tocarla.
        torre2 = TorreConstruccion.objects.create(proyecto=proyecto_190, numero='190-49-2')
        for pata in ['A', 'B', 'C', 'D']:
            ObraCivilTorreDetalle.objects.create(
                proyecto=proyecto_190, torre=torre2, pata=pata,
                exc_ft022_ok=False, ace_ft930_ok=False,
            )

        from django.apps import apps as django_apps
        mig.sync_17_formatos_torre_backfill(django_apps, None)

        for pata in ['A', 'B', 'C', 'D']:
            det = ObraCivilTorreDetalle.objects.get(torre=torre1, pata=pata)
            assert det.exc_ft022_ok is True, f'torre1 pata {pata} exc_ft022_ok'
            assert det.ace_ft930_ok is True, f'torre1 pata {pata} ace_ft930_ok'

        for pata in ['A', 'B', 'C', 'D']:
            det = ObraCivilTorreDetalle.objects.get(torre=torre2, pata=pata)
            assert det.exc_ft022_ok is False
            assert det.ace_ft930_ok is False

        # Idempotencia.
        snapshot_antes = list(
            ObraCivilTorreDetalle.objects.filter(
                torre__in=[torre1, torre2],
            ).order_by('torre_id', 'pata').values(
                'torre_id', 'pata', *CAMPOS_SYNC_TORRE,
            )
        )
        mig.sync_17_formatos_torre_backfill(django_apps, None)
        snapshot_despues = list(
            ObraCivilTorreDetalle.objects.filter(
                torre__in=[torre1, torre2],
            ).order_by('torre_id', 'pata').values(
                'torre_id', 'pata', *CAMPOS_SYNC_TORRE,
            )
        )
        assert snapshot_antes == snapshot_despues, (
            'la migration 0049 NO es idempotente — la 2da corrida cambió datos'
        )
    finally:
        post_save.connect(
            sincronizar_formatos_unicos_por_torre, sender=ObraCivilTorreDetalle,
        )


@pytest.mark.django_db
def test_backfill_0049_data_safe_con_cero_filas(proyecto_190):
    """Correr la migration 0049 sin ningún ObraCivilTorreDetalle en BD no
    falla (espejo del guardrail de 0048)."""
    from django.apps import apps as django_apps

    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle

    mig = importlib.import_module(
        'apps.construccion.migrations.0049_sync_17_formatos_torre_backfill'
    )
    assert not ObraCivilTorreDetalle.objects.filter(proyecto=proyecto_190).exists()
    mig.sync_17_formatos_torre_backfill(django_apps, None)  # no debe lanzar
