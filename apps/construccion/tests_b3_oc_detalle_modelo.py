"""Tests B2a (#74) — ObraCivilTorreDetalle modelo + migration + signal.

Cubre los 8 tests declarados en BLUEPRINT.sub_features.B2a.tests_e2e:

1. test_oc_detalle_defaults_avance_ponderado_cero
2. test_oc_detalle_avance_ponderado_sumproduct_pesos_proyecto
3. test_oc_detalle_sub_bloque_solado_desviacion_real_menos_calc
4. test_oc_detalle_unique_together_torre_pata
5. test_oc_detalle_signal_recalcula_obracivil_torre_cache
6. test_migration_0019_seed_avance_legacy_a_detalle_4_patas
7. test_oc_detalle_fk_proyecto_cascade
8. test_oc_detalle_ordering_por_torre_numero

Las pruebas usan pytest + @pytest.mark.django_db. El test (6) de seed legacy
verifica el invariante post-migrate (4 patas por torre con avance propagado),
NO ejecuta la RunPython manualmente — el test se apoya en que pytest-django
corre todas las migrations al inicio del test_run.
"""
from decimal import Decimal

import pytest
from django.db import IntegrityError


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def proyecto_oc(db):
    """ProyectoConstruccion con pesos default (5/30/5/15/30/15 = 100)."""
    from apps.contratos.models import Contrato
    from apps.construccion.models import ProyectoConstruccion

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-B2A-001',
        nombre='Contrato test B2a',
        cliente='Test Cliente',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto OC paridad test',
        estado='EJECUCION',
    )


@pytest.fixture
def torre_oc(proyecto_oc):
    """Torre única para los tests."""
    from apps.construccion.models import TorreConstruccion
    return TorreConstruccion.objects.create(
        proyecto=proyecto_oc,
        numero='42',
        tipo='D6',
    )


@pytest.fixture
def detalle_default(proyecto_oc, torre_oc):
    """ObraCivilTorreDetalle con defaults (todo ceros / False)."""
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle
    return ObraCivilTorreDetalle.objects.create(
        proyecto=proyecto_oc,
        torre=torre_oc,
        pata='A',
    )


# ===========================================================================
# 1. Defaults → avance_ponderado == 0
# ===========================================================================

@pytest.mark.django_db
def test_oc_detalle_defaults_avance_ponderado_cero(detalle_default):
    """Un detalle recién creado con defaults debe tener avance_ponderado = 0."""
    assert detalle_default.avance_ponderado == Decimal('0')
    assert detalle_default.avance_ponderado_pct == 0.0
    # Sanity: cerr_finalizado_ok inicia en False
    assert detalle_default.cerr_finalizado_ok is False
    # Y los `_pct` arrancan en Decimal('0')
    assert detalle_default.exc_ejecutada_pct == Decimal('0')
    assert detalle_default.sol_ejecutado_pct == Decimal('0')


# ===========================================================================
# 2. SUMPRODUCT con pesos del proyecto
# ===========================================================================

@pytest.mark.django_db
def test_oc_detalle_avance_ponderado_sumproduct_pesos_proyecto(
    proyecto_oc, torre_oc
):
    """Con pesos default 5/30/5/15/30/15 (=100), cerr_finalizado_ok=True
    aporta 5 (1*5), exc_ejecutada_pct=0.5 aporta 15 (0.5*30) → avance = 20/100.
    """
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle

    # Confirmar los pesos del fixture (defaults declarados en el modelo)
    assert proyecto_oc.peso_cerramiento_pct == 5
    assert proyecto_oc.peso_excavacion_pct == 30
    assert proyecto_oc.peso_solado_pct == 5
    assert proyecto_oc.peso_acero_pct == 15
    assert proyecto_oc.peso_vaciado_pct == 30
    assert proyecto_oc.peso_compactacion_pct == 15

    det = ObraCivilTorreDetalle.objects.create(
        proyecto=proyecto_oc,
        torre=torre_oc,
        pata='A',
        cerr_finalizado_ok=True,
        exc_ejecutada_pct=Decimal('0.5'),
    )

    # (1.0 * 5 + 0.5 * 30 + 0 + 0 + 0 + 0) / 100 = 20/100 = 0.2
    esperado = Decimal('20') / Decimal('100')
    assert det.avance_ponderado == esperado
    assert det.avance_ponderado_pct == 20.0


# ===========================================================================
# 3. Sub-bloque solado: desv = real - calc
# ===========================================================================

@pytest.mark.django_db
def test_oc_detalle_sub_bloque_solado_desviacion_real_menos_calc(
    proyecto_oc, torre_oc
):
    """sol_agua_real=5, sol_agua_calc=4 → sol_agua_desv = 1."""
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle

    det = ObraCivilTorreDetalle.objects.create(
        proyecto=proyecto_oc,
        torre=torre_oc,
        pata='A',
        sol_agua_calc=Decimal('4'),
        sol_agua_real=Decimal('5'),
        sol_arena_calc=Decimal('10'),
        sol_arena_real=Decimal('11.5'),
    )
    assert det.sol_agua_desv == Decimal('1')
    assert det.sol_arena_desv == Decimal('1.5')
    # Cuando falta uno de los dos, la property devuelve None
    assert det.sol_grava_desv is None
    assert det.sol_cemento_desv is None


# ===========================================================================
# 4. unique_together (torre, pata)
# ===========================================================================

@pytest.mark.django_db
def test_oc_detalle_unique_together_torre_pata(proyecto_oc, torre_oc):
    """Crear dos detalles con la misma (torre, pata) revienta IntegrityError."""
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle

    ObraCivilTorreDetalle.objects.create(
        proyecto=proyecto_oc, torre=torre_oc, pata='A',
    )
    with pytest.raises(IntegrityError):
        ObraCivilTorreDetalle.objects.create(
            proyecto=proyecto_oc, torre=torre_oc, pata='A',
        )


# ===========================================================================
# 5. Signal post_save → recalcula ObraCivilTorre cache
# ===========================================================================

@pytest.mark.django_db
def test_oc_detalle_signal_recalcula_obracivil_torre_cache(
    proyecto_oc, torre_oc
):
    """Al guardar un detalle con exc_ejecutada_pct=0.7 el cache
    ObraCivilTorre.avance_excavacion debe reflejarlo (promedio sobre patas
    existentes — acá una sola).
    """
    from apps.construccion.models import ObraCivilTorre
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle

    ObraCivilTorreDetalle.objects.create(
        proyecto=proyecto_oc,
        torre=torre_oc,
        pata='A',
        exc_ejecutada_pct=Decimal('0.7'),
        cerr_finalizado_ok=True,
    )

    cache = ObraCivilTorre.objects.get(torre=torre_oc)
    assert cache.avance_excavacion == Decimal('0.7')
    assert cache.avance_cerramiento == Decimal('1')  # True → 1.0

    # Agregar 3 patas más con exc=0.3 → promedio 4 patas = (0.7+0.3*3)/4 = 0.4
    for pata_letra in ['B', 'C', 'D']:
        ObraCivilTorreDetalle.objects.create(
            proyecto=proyecto_oc,
            torre=torre_oc,
            pata=pata_letra,
            exc_ejecutada_pct=Decimal('0.3'),
        )
    cache.refresh_from_db()
    # Promedio: (0.7 + 0.3 + 0.3 + 0.3) / 4 = 1.6/4 = 0.4
    assert cache.avance_excavacion == Decimal('0.4')


# ===========================================================================
# 6. Data migration 0019 — seed legacy a detalle 4 patas
# ===========================================================================

@pytest.mark.django_db
def test_migration_0019_seed_avance_legacy_a_detalle_4_patas(
    proyecto_oc, torre_oc
):
    """Verifica el comportamiento del seed `seed_desde_legacy` invocándolo
    manualmente sobre un dato legacy creado tras el setUp (la migration ya
    corrió al iniciar el test_run, pero comprobamos la regla de propagación).

    Fixtures:
      - ObraCivilTorre legacy con avance_excavacion=0.7, avance_cerramiento=1.0
    Espera:
      - 4 ObraCivilTorreDetalle (uno por pata A/B/C/D)
      - cada uno con exc_ejecutada_pct=0.7, cerr_finalizado_ok=True
    """
    from apps.construccion.models import ObraCivilTorre
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle

    # Cargar dinámicamente el módulo de migration (nombre empieza con dígito,
    # no se puede `import` directo) y obtener `seed_desde_legacy`.
    import importlib.util
    from pathlib import Path

    mig_path = (
        Path(__file__).resolve().parent
        / 'migrations' / '0019_oc_detalle.py'
    )
    spec = importlib.util.spec_from_file_location(
        'construccion_mig_0019', str(mig_path),
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    seed_fn = mod.seed_desde_legacy

    # ObraCivilTorre legacy con avances agregados
    legacy = ObraCivilTorre.objects.create(
        proyecto=proyecto_oc,
        torre=torre_oc,
        avance_cerramiento=Decimal('1'),
        avance_excavacion=Decimal('0.7'),
        avance_solado=Decimal('0.2'),
        avance_acero=Decimal('0.4'),
        avance_vaciado=Decimal('0.5'),
        avance_compactacion=Decimal('0.0'),
    )

    # Borrar cualquier detalle preexistente (puede haber sido creado por
    # la migration sobre ObraCivilTorre vacíos previos en tests)
    ObraCivilTorreDetalle.objects.filter(torre=torre_oc).delete()

    # Stub mínimo de "apps" para emular el contexto histórico:
    # passing the real `django.apps.apps` works porque los modelos están
    # registrados.
    from django.apps import apps as django_apps
    seed_fn(django_apps, schema_editor=None)

    detalles = ObraCivilTorreDetalle.objects.filter(torre=torre_oc)
    assert detalles.count() == 4
    for det in detalles:
        assert det.cerr_finalizado_ok is True  # 1.0 >= 0.99
        assert det.exc_ejecutada_pct == Decimal('0.7')
        assert det.sol_ejecutado_pct == Decimal('0.2')
        assert det.ace_instalacion_pct == Decimal('0.4')
        assert det.vac_ejecutado_pct == Decimal('0.5')
        assert det.com_finalizada_pct == Decimal('0.0')
    assert sorted(det.pata for det in detalles) == ['A', 'B', 'C', 'D']


# ===========================================================================
# 7. FK proyecto → on_delete CASCADE
# ===========================================================================

@pytest.mark.django_db
def test_oc_detalle_fk_proyecto_cascade(proyecto_oc, torre_oc):
    """Borrar el ProyectoConstruccion cascadea borrado de los detalles."""
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle

    for pata_letra in ['A', 'B', 'C', 'D']:
        ObraCivilTorreDetalle.objects.create(
            proyecto=proyecto_oc, torre=torre_oc, pata=pata_letra,
        )
    assert ObraCivilTorreDetalle.objects.count() == 4

    proyecto_oc.delete()
    assert ObraCivilTorreDetalle.objects.count() == 0


# ===========================================================================
# 8. Ordering por torre__numero, luego pata
# ===========================================================================

@pytest.mark.django_db
def test_oc_detalle_ordering_por_torre_numero(proyecto_oc):
    """Ordering del Meta: torre__numero asc, pata asc."""
    from apps.construccion.models import TorreConstruccion
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle

    # Crear torres deliberadamente en orden inverso para validar ordering
    # Usamos numeros que ordenen como string: '03', '07', '15'
    for numero in ['15', '03', '07']:
        torre = TorreConstruccion.objects.create(
            proyecto=proyecto_oc, numero=numero,
        )
        for pata_letra in ['D', 'A']:  # también desordenado
            ObraCivilTorreDetalle.objects.create(
                proyecto=proyecto_oc, torre=torre, pata=pata_letra,
            )

    qs = list(ObraCivilTorreDetalle.objects.all())
    assert len(qs) == 6
    # Primero debe venir torre 03 pata A
    assert qs[0].torre.numero == '03'
    assert qs[0].pata == 'A'
    # Último: torre 15 pata D
    assert qs[-1].torre.numero == '15'
    assert qs[-1].pata == 'D'
    # Y la torre más alta numéricamente (string) es 15 > 07 > 03
    numeros_distintos = [d.torre.numero for d in qs]
    assert numeros_distintos[0] == '03'
    assert numeros_distintos[-1] == '15'


# ===========================================================================
# 9. (#132) verbose_name de cerr_lona_m incluye 'alambre de púa'
# ===========================================================================

@pytest.mark.django_db
def test_oc_detalle_cerr_lona_verbose_incluye_alambre_pua(detalle_default):
    """#132 — la etiqueta de cerramiento debe mencionar lona O alambre de púa.

    El cliente registra el cerramiento tanto en lona como en alambre de púa
    sobre el mismo campo (cantidades no cambian, solo la descripción).
    """
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle

    field = ObraCivilTorreDetalle._meta.get_field('cerr_lona_m')
    assert field.verbose_name == 'Cerramiento — lona o alambre de púa (m)'
    # No tocamos cerramiento en madera (ítem separado, ya correcto)
    madera = ObraCivilTorreDetalle._meta.get_field('cerr_madera_un')
    assert madera.verbose_name == 'Cerramiento — madera (un)'


@pytest.mark.django_db
def test_oc_detalle_cerr_lona_form_mensaje_error_legacy(detalle_default):
    """#132 — el form rechaza lona negativa con la etiqueta actualizada.

    Valida contra dato legacy: el detalle ya existe (detalle_default), se
    edita su campo lona con un valor inválido y se espera el mensaje nuevo.
    """
    from apps.construccion.forms_b3_oc_detalle import OCSeccionCerramientoForm

    form = OCSeccionCerramientoForm(
        data={'cerr_lona_m': '-3', 'cerr_madera_un': '', 'cerr_notas': ''},
        instance=detalle_default,
    )
    assert not form.is_valid()
    assert 'cerr_lona_m' in form.errors
    assert 'Lona o alambre de púa (m)' in ' '.join(form.errors['cerr_lona_m'])
