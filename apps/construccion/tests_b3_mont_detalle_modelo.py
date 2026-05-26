"""Tests B3a — MontajeEstructuraTorreDetalle (#76).

Cubre las 7 specs E2E del BLUEPRINT:
  1. test_funcion_property_A_esp_suspension_B_retencion
  2. test_dias_montaje_ambas_fechas_int_else_None
  3. test_peso_desviacion_pct_cinco_diez_diseno_cero_none
  4. test_peso_alerta_umbral_5_porciento
  5. test_avance_ponderado_4_booleans_true_100pct
  6. test_signal_recalcula_montaje_torre_cache
  7. test_migration_0020_seed_torre_montada_propaga_a_detalle

Suite real corre en F4 (no hay venv local). Sintaxis verificada con py_compile.
"""
from datetime import date
from decimal import Decimal

import pytest


# ===========================================================================
# Fixtures locales
# ===========================================================================

@pytest.fixture
def proyecto_b3a(db):
    """ProyectoConstruccion mínimo para colgar el detalle B3a."""
    from apps.contratos.models import Contrato
    from apps.construccion.models import ProyectoConstruccion

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-B3A-001',
        nombre='Contrato test B3a',
        cliente='Test Cliente B3a',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto B3a test',
        estado='EJECUCION',
    )


@pytest.fixture
def torre_b3a(proyecto_b3a):
    """TorreConstruccion mínima para OneToOne con el detalle."""
    from apps.construccion.models import TorreConstruccion

    return TorreConstruccion.objects.create(
        proyecto=proyecto_b3a,
        numero='T001',
        tipo='B4',
    )


def _make_detalle(torre, proyecto, **kwargs):
    """Helper: crea un MontajeEstructuraTorreDetalle con defaults razonables."""
    from apps.construccion.models_b3_mont_detalle import MontajeEstructuraTorreDetalle

    defaults = {'torre': torre, 'proyecto': proyecto}
    defaults.update(kwargs)
    return MontajeEstructuraTorreDetalle.objects.create(**defaults)


# ===========================================================================
# Tests E2E del BLUEPRINT
# ===========================================================================

@pytest.mark.django_db
def test_funcion_property_A_esp_suspension_B_retencion(torre_b3a, proyecto_b3a):
    """@funcion mapea tipo_torre → 'Suspensión' (A, A_esp) / 'Retención' (B,C,D,portico)."""
    from apps.construccion.models_b3_mont_detalle import MontajeEstructuraTorreDetalle

    # Caso A → Suspensión
    detalle = MontajeEstructuraTorreDetalle(
        torre=torre_b3a, proyecto=proyecto_b3a, tipo_torre='A',
    )
    assert detalle.funcion == 'Suspensión'

    # Caso A_esp → Suspensión
    detalle.tipo_torre = 'A_esp'
    assert detalle.funcion == 'Suspensión'

    # Caso B → Retención
    detalle.tipo_torre = 'B'
    assert detalle.funcion == 'Retención'

    # Caso C / D / portico → Retención
    for tipo in ('C', 'D', 'portico'):
        detalle.tipo_torre = tipo
        assert detalle.funcion == 'Retención', f'tipo={tipo} debería ser Retención'

    # Caso edge: tipo_torre vacío → '' (no asumir)
    detalle.tipo_torre = ''
    assert detalle.funcion == ''


@pytest.mark.django_db
def test_dias_montaje_ambas_fechas_int_else_None(torre_b3a, proyecto_b3a):
    """@dias_montaje: int días si ambas fechas; None si alguna falta."""
    from apps.construccion.models_b3_mont_detalle import MontajeEstructuraTorreDetalle

    # Ambas fechas → días enteros
    detalle = MontajeEstructuraTorreDetalle(
        torre=torre_b3a, proyecto=proyecto_b3a,
        montaje_fecha_inicio=date(2026, 5, 1),
        montaje_fecha_fin=date(2026, 5, 8),
    )
    assert detalle.dias_montaje == 7

    # Sólo inicio → None
    detalle.montaje_fecha_fin = None
    assert detalle.dias_montaje is None

    # Sólo fin → None
    detalle.montaje_fecha_inicio = None
    detalle.montaje_fecha_fin = date(2026, 5, 8)
    assert detalle.dias_montaje is None

    # Ninguna → None
    detalle.montaje_fecha_inicio = None
    detalle.montaje_fecha_fin = None
    assert detalle.dias_montaje is None

    # Mismo día → 0
    detalle.montaje_fecha_inicio = date(2026, 5, 1)
    detalle.montaje_fecha_fin = date(2026, 5, 1)
    assert detalle.dias_montaje == 0


@pytest.mark.django_db
def test_peso_desviacion_pct_cinco_diez_diseno_cero_none(torre_b3a, proyecto_b3a):
    """@peso_desviacion_pct: |Z-Y|/Y*100; None si Y=0 o si falta dato."""
    from apps.construccion.models_b3_mont_detalle import MontajeEstructuraTorreDetalle

    # diseño=100, instalado=105 → 5.00
    detalle = MontajeEstructuraTorreDetalle(
        torre=torre_b3a, proyecto=proyecto_b3a,
        peso_diseno_kl=Decimal('100'),
        peso_instalado_kl=Decimal('105'),
    )
    assert detalle.peso_desviacion_pct == Decimal('5.00')

    # diseño=100, instalado=110 → 10.00
    detalle.peso_instalado_kl = Decimal('110')
    assert detalle.peso_desviacion_pct == Decimal('10.00')

    # diseño=100, instalado=90 → 10.00 (valor absoluto)
    detalle.peso_instalado_kl = Decimal('90')
    assert detalle.peso_desviacion_pct == Decimal('10.00')

    # diseño=0 → None (división por cero)
    detalle.peso_diseno_kl = Decimal('0')
    detalle.peso_instalado_kl = Decimal('50')
    assert detalle.peso_desviacion_pct is None

    # diseño=None → None
    detalle.peso_diseno_kl = None
    detalle.peso_instalado_kl = Decimal('50')
    assert detalle.peso_desviacion_pct is None

    # instalado=None → None
    detalle.peso_diseno_kl = Decimal('100')
    detalle.peso_instalado_kl = None
    assert detalle.peso_desviacion_pct is None


@pytest.mark.django_db
def test_peso_alerta_umbral_5_porciento(torre_b3a, proyecto_b3a):
    """@peso_alerta: True si desviación > 5%; False si <=5% o no calculable."""
    from apps.construccion.models_b3_mont_detalle import MontajeEstructuraTorreDetalle

    detalle = MontajeEstructuraTorreDetalle(
        torre=torre_b3a, proyecto=proyecto_b3a,
        peso_diseno_kl=Decimal('100'),
    )

    # Desviación 5.0% → False (no estricto: > 5, no >=)
    detalle.peso_instalado_kl = Decimal('105')
    assert detalle.peso_desviacion_pct == Decimal('5.00')
    assert detalle.peso_alerta is False

    # Desviación 5.01% → True (apenas pasa umbral)
    detalle.peso_instalado_kl = Decimal('105.01')
    assert detalle.peso_alerta is True

    # Desviación 10% → True
    detalle.peso_instalado_kl = Decimal('110')
    assert detalle.peso_alerta is True

    # Desviación 0% → False
    detalle.peso_instalado_kl = Decimal('100')
    assert detalle.peso_alerta is False

    # Sin diseño → False (no calculable)
    detalle.peso_diseno_kl = None
    detalle.peso_instalado_kl = Decimal('100')
    assert detalle.peso_alerta is False


@pytest.mark.django_db
def test_avance_ponderado_4_booleans_true_100pct(torre_b3a, proyecto_b3a):
    """@avance_ponderado: SUMPRODUCT con pesos 10/20/45/25 → 0..1."""
    from apps.construccion.models_b3_mont_detalle import MontajeEstructuraTorreDetalle

    # Los 4 booleans en True → 100% (10+20+45+25=100)
    detalle = MontajeEstructuraTorreDetalle(
        torre=torre_b3a, proyecto=proyecto_b3a,
        estructura_en_sitio_ok=True,
        prearmada_ok=True,
        torre_montada_ok=True,
        revisada_ok=True,
    )
    assert detalle.avance_ponderado == Decimal('1')
    assert detalle.avance_ponderado_pct == 100.0

    # Sólo estructura_en_sitio → 10%
    detalle.estructura_en_sitio_ok = True
    detalle.prearmada_ok = False
    detalle.torre_montada_ok = False
    detalle.revisada_ok = False
    assert detalle.avance_ponderado == Decimal('0.10')
    assert detalle.avance_ponderado_pct == 10.0

    # Estructura + prearmada → 30%
    detalle.prearmada_ok = True
    assert detalle.avance_ponderado == Decimal('0.30')

    # Estructura + prearmada + montada → 75%
    detalle.torre_montada_ok = True
    assert detalle.avance_ponderado == Decimal('0.75')

    # Ninguno → 0
    detalle.estructura_en_sitio_ok = False
    detalle.prearmada_ok = False
    detalle.torre_montada_ok = False
    detalle.revisada_ok = False
    assert detalle.avance_ponderado == Decimal('0')


@pytest.mark.django_db
def test_signal_recalcula_montaje_torre_cache(torre_b3a, proyecto_b3a):
    """post_save MontajeEstructuraTorreDetalle → update_or_create
    MontajeEstructuraTorre con avance_* derivados.
    """
    from apps.construccion.models import MontajeEstructuraTorre
    from apps.construccion.models_b3_mont_detalle import MontajeEstructuraTorreDetalle

    # Sanity: no debe haber cache previo para esta torre
    assert not MontajeEstructuraTorre.objects.filter(torre=torre_b3a).exists()

    # Guardar detalle con torre_montada_ok=True
    detalle = MontajeEstructuraTorreDetalle.objects.create(
        torre=torre_b3a,
        proyecto=proyecto_b3a,
        torre_montada_ok=True,
    )

    # El signal debió crear/actualizar el cache legacy
    cache = MontajeEstructuraTorre.objects.get(torre=torre_b3a)
    assert cache.avance_torre_montada == Decimal('1')
    assert cache.avance_estructura_sitio == Decimal('0')
    assert cache.avance_prearamada == Decimal('0')
    assert cache.avance_revisada == Decimal('0')
    assert cache.proyecto_id == proyecto_b3a.id

    # Editar el detalle → cache se actualiza (no se duplica)
    detalle.estructura_en_sitio_ok = True
    detalle.prearmada_ok = True
    detalle.revisada_ok = True
    detalle.save()

    cache.refresh_from_db()
    assert cache.avance_estructura_sitio == Decimal('1')
    assert cache.avance_prearamada == Decimal('1')
    assert cache.avance_torre_montada == Decimal('1')
    assert cache.avance_revisada == Decimal('1')

    # Sigue habiendo UN solo cache para esta torre (update, no insert)
    assert MontajeEstructuraTorre.objects.filter(torre=torre_b3a).count() == 1


@pytest.mark.django_db
def test_migration_0020_seed_torre_montada_propaga_a_detalle(proyecto_b3a):
    """0020 seed: dado un MontajeEstructuraTorre legacy con avance_torre_montada=1.0,
    tras correr el seed debe existir un detalle con torre_montada_ok=True.

    Implementación: probamos la función seed directa (no full migrate runner,
    que requiere infra). Esto exercita la lógica de mapeo Decimal→Bool.
    """
    import importlib.util
    import os

    from apps.construccion.models import MontajeEstructuraTorre, TorreConstruccion
    from apps.construccion.models_b3_mont_detalle import MontajeEstructuraTorreDetalle

    # Crear una torre + cache legacy con torre_montada=1.0
    torre = TorreConstruccion.objects.create(
        proyecto=proyecto_b3a, numero='TSEED-001', tipo='B4',
    )
    MontajeEstructuraTorre.objects.create(
        proyecto=proyecto_b3a,
        torre=torre,
        avance_estructura_sitio=Decimal('1'),
        avance_prearamada=Decimal('1'),
        avance_torre_montada=Decimal('1'),
        avance_revisada=Decimal('0'),
    )

    # Ningún detalle todavía
    assert not MontajeEstructuraTorreDetalle.objects.filter(torre=torre).exists()

    # Cargar el archivo de migration por path (módulo empieza con dígito, no se
    # puede `import` con sintaxis estándar). Invocar la función seed directa.
    migration_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'migrations', '0020_mont_detalle.py',
    )
    spec = importlib.util.spec_from_file_location('_mig_0020', migration_path)
    migration_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration_mod)

    class _AppsShim:
        """Mock de apps que devuelve los modelos reales (no historical)."""
        @staticmethod
        def get_model(app_label, model_name):
            from django.apps import apps as django_apps
            return django_apps.get_model(app_label, model_name)

    migration_mod.seed_desde_legacy(_AppsShim(), schema_editor=None)

    # Ahora debe existir el detalle con torre_montada_ok=True (avance==1)
    detalle = MontajeEstructuraTorreDetalle.objects.get(torre=torre)
    assert detalle.torre_montada_ok is True
    assert detalle.estructura_en_sitio_ok is True
    assert detalle.prearmada_ok is True
    assert detalle.revisada_ok is False  # avance era 0
    assert detalle.proyecto_id == proyecto_b3a.id
