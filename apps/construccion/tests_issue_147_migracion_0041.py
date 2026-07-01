"""Test #147 Sprint A1 — migración 0041: numero_tiro + ft931_ok + backfill.

Nota de infraestructura: este repo corre pytest con --nomigrations (ver
pyproject.toml [tool.pytest.ini_options]) — la BD de test se crea por
syncdb directo desde el estado actual de los modelos, no reproduciendo el
grafo de migraciones. Por eso el test ejercita la función real de backfill
`backfill_numero_tiro` de la migración 0041 (importada por ruta de archivo,
ya que el módulo empieza con dígito) contra un fixture con RiegaManilaTiro
pre-existente (dato legacy), en vez de invocar MigrationExecutor.
"""
import importlib.util
import os

import pytest
from django.apps import apps as real_apps


def _cargar_modulo_migracion_0041():
    ruta = os.path.join(
        os.path.dirname(__file__), 'migrations', '0041_tiro_unico_ft931.py'
    )
    spec = importlib.util.spec_from_file_location(
        'construccion_migracion_0041_tiro_unico_ft931', ruta
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def proyecto_migracion_0041(db):
    from apps.construccion.models import ProyectoConstruccion
    from apps.contratos.models import Contrato

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-I147-0041',
        nombre='Contrato test migración 0041',
        cliente='Cliente #147',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto migración 0041',
        estado='EJECUCION',
    )


@pytest.mark.django_db
def test_migracion_0041_backfill_numero_tiro_desde_legacy(proyecto_migracion_0041):
    """Torre con 1 fila RiegaManilaTiro pre-existente (dato legacy) → tras
    correr la función de backfill de la migración 0041, numero_tiro queda
    poblado con ese valor. Torre sin tiros previos queda NULL (no tocada)."""
    from apps.construccion.models import (
        FaseTorre,
        RiegaManilaTiro,
        TorreConstruccion,
    )

    torre_con_tiro = TorreConstruccion.objects.create(
        proyecto=proyecto_migracion_0041, numero='1', tipo='D6',
    )
    fase_con_tiro = FaseTorre.objects.create(
        torre=torre_con_tiro, proyecto=proyecto_migracion_0041,
    )
    # dato legacy: 1 tiro real (caso limpio 1:1, verificado read-only en
    # prod — 0 torres con >1 fila en construccion_riega_manila_tiro).
    RiegaManilaTiro.objects.create(fase=fase_con_tiro, numero_tiro=4, flecha_tendido_m=12.3)

    torre_sin_tiro = TorreConstruccion.objects.create(
        proyecto=proyecto_migracion_0041, numero='2', tipo='D6',
    )
    fase_sin_tiro = FaseTorre.objects.create(
        torre=torre_sin_tiro, proyecto=proyecto_migracion_0041,
    )

    # Precondición: campos nuevos arrancan sin poblar.
    assert fase_con_tiro.numero_tiro is None
    assert fase_con_tiro.ft931_ok is False

    mod = _cargar_modulo_migracion_0041()
    mod.backfill_numero_tiro(real_apps, None)

    fase_con_tiro.refresh_from_db()
    fase_sin_tiro.refresh_from_db()

    assert fase_con_tiro.numero_tiro == 4, (
        'numero_tiro debe quedar poblado con el (único) tiro legacy de la torre'
    )
    assert fase_sin_tiro.numero_tiro is None, (
        'torre sin RiegaManilaTiro previo queda NULL (aún no tendida)'
    )
    # RiegaManilaTiro NO se borra (queda legacy read-only).
    assert RiegaManilaTiro.objects.filter(fase=fase_con_tiro).count() == 1


@pytest.mark.django_db
def test_migracion_0041_backfill_toma_minimo_si_hay_mas_de_uno(proyecto_migracion_0041):
    """Defensivo: si alguna torre tuviera >1 RiegaManilaTiro (no es el caso
    verificado en prod, pero el backfill debe ser robusto), toma el MÍNIMO."""
    from apps.construccion.models import (
        FaseTorre,
        RiegaManilaTiro,
        TorreConstruccion,
    )

    torre = TorreConstruccion.objects.create(
        proyecto=proyecto_migracion_0041, numero='3', tipo='D6',
    )
    fase = FaseTorre.objects.create(torre=torre, proyecto=proyecto_migracion_0041)
    RiegaManilaTiro.objects.create(fase=fase, numero_tiro=5, flecha_tendido_m=1.0)
    RiegaManilaTiro.objects.create(fase=fase, numero_tiro=2, flecha_tendido_m=2.0)
    RiegaManilaTiro.objects.create(fase=fase, numero_tiro=9, flecha_tendido_m=3.0)

    mod = _cargar_modulo_migracion_0041()
    mod.backfill_numero_tiro(real_apps, None)

    fase.refresh_from_db()
    assert fase.numero_tiro == 2, 'debe tomar el MÍNIMO numero_tiro entre los 3'
    # legacy no se borra
    assert RiegaManilaTiro.objects.filter(fase=fase).count() == 3
