"""Instelec#171 (Sprint final, GRUPO A) — B3: regresión OBLIGATORIA (gate
bloqueante) del refactor de `ObraCivilTorre.avance_ponderado` y
`MontajeEstructuraTorre.avance_ponderado` para leer pesos + columnas activas
desde `ColumnaConfigurable` (B2) en vez de los campos hardcodeados
`proyecto.peso_*_pct`.

## Vía usada: datos REALES de BD prod (no el fallback sintético puro)

Se leyeron, vía el proxy de solo-lectura ya autorizado a F2/F3 para testing
(`127.0.0.1:5434`, `instelec_db`, usuario `postgres`, SOLO SELECT — nunca
INSERT/UPDATE/DELETE), los 65 registros reales de `ObraCivilTorre` y
`MontajeEstructuraTorre` del proyecto QA #49 "Puerta de Oro"
(`ec2a68aa-47fe-4772-89bc-2cd2b1c8b5c7`), junto con los pesos vigentes del
proyecto — mismos valores ya verificados por F2 en
`PLAN_2026-07-19_171_sprint_final.md` y usados por B2
(`test_issue_171_b2_columna_configurable.py`):

    Obra Civil: 5 / 30 / 5 / 15 / 30 / 15
    Montaje:    10 / 20 / 45 / 25

Esos 65×2 registros se embeben abajo como literales CONGELADOS
(`OC_TORRES_REALES`, `MONT_TORRES_REALES`) — el test NO vuelve a consultar
prod en cada corrida (corre contra la BD de test de pytest, `--nomigrations`,
igual que el resto de la suite). Es la "vía real BD" que pide el prompt F3,
no el fallback sintético.

## Metodología

Se reconstruye la fórmula LEGACY tal cual estaba ANTES de B3 (copiada
literal — `SUMPRODUCT(peso hardcodeado de proyecto.peso_*_pct, avance) /
SUM(peso)`, congelada acá para que este test siga siendo una regresión
válida aunque el código de producción siga cambiando) y se compara, torre
por torre, contra la property REAL post-refactor (`.avance_ponderado_pct`,
que ahora lee de `ColumnaConfigurable`). **0 diffs esperados.**

Como los pesos reales del proyecto QA son IDÉNTICOS a los defaults
hardcodeados (ver arriba), esta comparación por sí sola NO alcanza para
probar que el refactor realmente lee de `ColumnaConfigurable` (un bug que
ignorara `ColumnaConfigurable` y siguiera leyendo `proyecto.peso_*_pct`
pasaría este test igual, por coincidencia numérica). Por eso la sección 2
de este archivo añade tests SINTÉTICOS con pesos DISTINTOS entre
`ColumnaConfigurable` y `proyecto.peso_*_pct` (columna desactivada =
redistribución, edición directa de `ColumnaConfigurable.peso_pct`) — esos
sí distinguen "lee `ColumnaConfigurable`" de "lee `proyecto.peso_*_pct`".

## Hueco encontrado durante B3 (fuera del scope original de F2)

`ObraCivilPesosUpdateView`/`MontajePesosUpdateView` (panel legacy de edición
de pesos) siguen escribiendo en `proyecto.peso_*_pct` — pero como
`avance_ponderado` ya no lee esos campos directo, sin sincronización esa
edición se volvería un no-op silencioso sobre el avance calculado. Se agregó
`sync_columnas_sistema_pesos_proyecto` (models.py) disparado por el signal
`post_save` de `ProyectoConstruccion` (signals.py) en CUALQUIER `.save()`
(no solo esas 2 vistas) — sección 4 de este archivo lo cubre.

## Convención de colección

Vive en `tests/unit/` (no `apps/construccion/tests_issue_171.py`) — mismo
motivo documentado en `test_issue_171_b2_columna_configurable.py`:
`pyproject.toml` define `testpaths = ["tests"]`, el patrón legacy
`apps/<app>/tests_*.py` no colecta.
"""
from decimal import Decimal

import pytest

from apps.construccion.models import (
    ColumnaConfigurable,
    ColumnaConfigurableValor,
    MontajeEstructuraTorre,
    ObraCivilTorre,
    ProyectoConstruccion,
    TorreConstruccion,
)
from apps.contratos.models import Contrato

# ==============================================================================
# 0) Datos congelados — 65 torres reales, prod `instelec_db` (SOLO SELECT,
#    proxy 127.0.0.1:5434, 2026-07-19), proyecto QA #49 "Puerta de Oro".
# ==============================================================================

_PESOS_PROD_VERIFICADOS = {
    'peso_cerramiento_pct': 5,
    'peso_excavacion_pct': 30,
    'peso_solado_pct': 5,
    'peso_acero_pct': 15,
    'peso_vaciado_pct': 30,
    'peso_compactacion_pct': 15,
    'peso_mont_estructura_sitio_pct': 10,
    'peso_mont_prearamada_pct': 20,
    'peso_mont_torre_montada_pct': 45,
    'peso_mont_revisada_pct': 25,
    # Tendido (B4) — se incluyen acá también para que el proyecto fixture
    # de este archivo quede con los MISMOS 21 pesos verificados en prod que
    # usa el resto del sprint (B2/B4), aunque este archivo no ejercite
    # Tendido directamente.
    'peso_tend_riega_manila_pct': 20,
    'peso_tend_riega_guaya_pct': 20,
    'peso_tend_tendido_conductor_pct': 30,
    'peso_tend_grapado_pct': 10,
    'peso_tend_accesorios_pct': 10,
    'peso_tend_balizas_pct': 10,
    'peso_tend_riega_manila_fibra_pct': 10,
    'peso_tend_riega_guaya_opgw_pct': 20,
    'peso_tend_tendido_opgw_pct': 40,
    'peso_tend_grapado_fibra_pct': 20,
    'peso_tend_empalmes_opgw_pct': 10,
}

# (numero, cerramiento, excavacion, solado, acero, vaciado, compactacion)
OC_TORRES_REALES = [
    ('E1', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E10', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E11', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E12', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E13', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E14', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E15', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E16', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E17', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E18', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E19', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E2', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E20', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E21', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E22', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E23', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E24', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E25', '0.0000', '0.0000', '0.0000', '0.0000', '0.0000', '0.0000'),
    ('E26', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E27', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E28', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E29', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E3', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E30', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E31', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E32', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E33', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E34', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E35', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E36', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E37', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E38', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E39', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E4', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E40', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E41', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E42', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E43', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E44', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E45', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E46', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E47', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E48', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E49', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E5', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E50', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E51', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E52', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E53', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E54', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E55', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E56', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E57', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E58', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E59', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E6', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E60', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E61', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E62', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E63', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E64', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E65', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E7', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E8', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E9', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000', '1.0000'),
]

# (numero, estructura_sitio, prearamada, torre_montada, revisada)
MONT_TORRES_REALES = [
    ('E1', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E10', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E11', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E12', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E13', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E14', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E15', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E16', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E17', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E18', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E19', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E2', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E20', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E21', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E22', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E23', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E24', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E25', '0.0000', '0.0000', '0.0000', '0.0000'),
    ('E26', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E27', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E28', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E29', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E3', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E30', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E31', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E32', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E33', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E34', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E35', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E36', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E37', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E38', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E39', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E4', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E40', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E41', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E42', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E43', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E44', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E45', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E46', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E47', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E48', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E49', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E5', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E50', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E51', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E52', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E53', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E54', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E55', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E56', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E57', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E58', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E59', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E6', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E60', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E61', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E62', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E63', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E64', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E65', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E7', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E8', '1.0000', '1.0000', '1.0000', '1.0000'),
    ('E9', '1.0000', '1.0000', '1.0000', '1.0000'),
]

assert len(OC_TORRES_REALES) == 65
assert len(MONT_TORRES_REALES) == 65


# ==============================================================================
# Fórmulas LEGACY — congeladas, copiadas literal de models.py ANTES de B3.
# NO deben cambiar nunca (son la referencia fija contra la que se regresiona).
# ==============================================================================

def _avance_ponderado_legacy_obra_civil(proyecto, avances):
    pesos = {
        'cerramiento': proyecto.peso_cerramiento_pct,
        'excavacion': proyecto.peso_excavacion_pct,
        'solado': proyecto.peso_solado_pct,
        'acero': proyecto.peso_acero_pct,
        'vaciado': proyecto.peso_vaciado_pct,
        'compactacion': proyecto.peso_compactacion_pct,
    }
    total_peso = sum(pesos.values()) or 1
    suma = Decimal('0')
    for columna, peso in pesos.items():
        suma += avances[columna] * Decimal(peso)
    return suma / Decimal(total_peso)


def _avance_ponderado_legacy_montaje(proyecto, avances):
    pesos = {
        'estructura_sitio': proyecto.peso_mont_estructura_sitio_pct,
        'prearamada': proyecto.peso_mont_prearamada_pct,
        'torre_montada': proyecto.peso_mont_torre_montada_pct,
        'revisada': proyecto.peso_mont_revisada_pct,
    }
    total = sum(pesos.values()) or 1
    suma = Decimal('0')
    for col, peso in pesos.items():
        suma += avances[col] * Decimal(peso)
    return suma / Decimal(total)


# ==============================================================================
# 1) Fixture — proyecto QA (pesos reales) + 65 torres reales, OC + Montaje
# ==============================================================================

@pytest.fixture
def proyecto_qa_65_torres(db):
    """Reproduce el proyecto QA real (#49 Puerta de Oro) con sus pesos
    vigentes y las 65 torres reales (ObraCivilTorre/MontajeEstructuraTorre)
    con los avances REALES leídos de prod. El signal post_save ya crea las
    21 filas ColumnaConfigurable con estos mismos pesos (B2)."""
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-171-B3-001',
        nombre='Proyecto test #171 B3 — 65 torres reales',
        cliente='Test',
    )
    proyecto = ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='QA test #49 - Puerta de Oro (fixture B3)',
        estado='EJECUCION',
        **_PESOS_PROD_VERIFICADOS,
    )
    assert ColumnaConfigurable.objects.filter(proyecto=proyecto).count() == 21, (
        "Fixture inválida: el signal post_save debía crear las 21 columnas "
        "de fábrica al crear el proyecto."
    )

    torres = {}
    for numero, *_ in OC_TORRES_REALES:
        torres[numero] = TorreConstruccion.objects.create(proyecto=proyecto, numero=numero)

    for numero, cerr, exc, sol, ace, vac, com in OC_TORRES_REALES:
        ObraCivilTorre.objects.create(
            proyecto=proyecto, torre=torres[numero],
            avance_cerramiento=Decimal(cerr), avance_excavacion=Decimal(exc),
            avance_solado=Decimal(sol), avance_acero=Decimal(ace),
            avance_vaciado=Decimal(vac), avance_compactacion=Decimal(com),
        )

    for numero, est, prea, tm, rev in MONT_TORRES_REALES:
        MontajeEstructuraTorre.objects.create(
            proyecto=proyecto, torre=torres[numero],
            avance_estructura_sitio=Decimal(est), avance_prearamada=Decimal(prea),
            avance_torre_montada=Decimal(tm), avance_revisada=Decimal(rev),
        )

    return proyecto, torres


# ==============================================================================
# 2) Regresión OBLIGATORIA — 0 diffs esperados, las 2 fórmulas × 65 torres
# ==============================================================================

@pytest.mark.django_db
def test_regresion_avance_ponderado_obra_civil_65_torres_reales_0_diffs(proyecto_qa_65_torres):
    """#171 B3 — gate bloqueante: avance_ponderado_pct de ObraCivilTorre debe
    ser IDÉNTICO (legacy hardcodeado vs ColumnaConfigurable post-refactor)
    para las 65 torres reales del proyecto QA."""
    proyecto, torres = proyecto_qa_65_torres
    diffs = []
    for numero, cerr, exc, sol, ace, vac, com in OC_TORRES_REALES:
        oc = ObraCivilTorre.objects.get(proyecto=proyecto, torre=torres[numero])
        avances = {
            'cerramiento': Decimal(cerr), 'excavacion': Decimal(exc),
            'solado': Decimal(sol), 'acero': Decimal(ace),
            'vaciado': Decimal(vac), 'compactacion': Decimal(com),
        }
        legacy_pct = round(float(_avance_ponderado_legacy_obra_civil(proyecto, avances)) * 100, 1)
        nuevo_pct = oc.avance_ponderado_pct
        if abs(legacy_pct - nuevo_pct) > 1e-9:
            diffs.append((numero, legacy_pct, nuevo_pct))
    assert diffs == [], f"Regresión detectada en avance_ponderado (Obra Civil): {diffs}"


@pytest.mark.django_db
def test_regresion_avance_ponderado_montaje_65_torres_reales_0_diffs(proyecto_qa_65_torres):
    """#171 B3 — gate bloqueante: avance_ponderado_pct de
    MontajeEstructuraTorre debe ser IDÉNTICO para las 65 torres reales."""
    proyecto, torres = proyecto_qa_65_torres
    diffs = []
    for numero, est, prea, tm, rev in MONT_TORRES_REALES:
        m = MontajeEstructuraTorre.objects.get(proyecto=proyecto, torre=torres[numero])
        avances = {
            'estructura_sitio': Decimal(est), 'prearamada': Decimal(prea),
            'torre_montada': Decimal(tm), 'revisada': Decimal(rev),
        }
        legacy_pct = round(float(_avance_ponderado_legacy_montaje(proyecto, avances)) * 100, 1)
        nuevo_pct = m.avance_ponderado_pct
        if abs(legacy_pct - nuevo_pct) > 1e-9:
            diffs.append((numero, legacy_pct, nuevo_pct))
    assert diffs == [], f"Regresión detectada en avance_ponderado (Montaje): {diffs}"


# ==============================================================================
# 3) Unit — redistribución de peso al desactivar una columna (SINTÉTICO,
#    distingue "lee ColumnaConfigurable" de "coincide con proyecto.peso_*_pct
#    por casualidad" — ver docstring del módulo).
# ==============================================================================

@pytest.fixture
def proyecto_simple(db):
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-171-B3-002',
        nombre='Proyecto test #171 B3 — redistribución de peso',
        cliente='Test',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato, nombre='Proyecto simple B3', estado='EJECUCION',
    )


@pytest.mark.django_db
def test_columna_sistema_desactivada_se_excluye_y_redistribuye_peso_obra_civil(proyecto_simple):
    """#171 B3: si se desactiva 'excavacion' (peso 30 de 100), el cálculo
    debe excluirla del SUMPRODUCT y dividir solo entre el peso de las
    columnas restantes (redistribución), NO seguir dividiendo entre 100
    (que sería el comportamiento legacy, ciego a `activa`)."""
    torre = TorreConstruccion.objects.create(proyecto=proyecto_simple, numero='T-REDIST-1')
    oc = ObraCivilTorre.objects.create(
        proyecto=proyecto_simple, torre=torre,
        avance_cerramiento=Decimal('1.0000'),   # peso 5, activa
        avance_excavacion=Decimal('0.0000'),    # peso 30, se va a DESACTIVAR
        avance_solado=Decimal('1.0000'),        # peso 5, activa
        avance_acero=Decimal('1.0000'),         # peso 15, activa
        avance_vaciado=Decimal('1.0000'),       # peso 30, activa
        avance_compactacion=Decimal('1.0000'),  # peso 15, activa
    )
    # Baseline: con las 6 columnas activas, avance_ponderado = (5+5+15+30+15)/100 = 0.70
    assert oc.avance_ponderado_pct == 70.0

    ColumnaConfigurable.objects.filter(
        proyecto=proyecto_simple, capitulo=ColumnaConfigurable.CAPITULO_OBRA_CIVIL,
        clave='excavacion',
    ).update(activa=False)

    oc.refresh_from_db()
    # Tras desactivar excavación (peso 30, avance 0): total_peso pasa a 70
    # (5+5+15+30+15), suma = 5*1+5*1+15*1+30*1+15*1 = 70 → 70/70 = 1.0 (100%)
    assert oc.avance_ponderado_pct == 100.0, (
        "Al desactivar una columna, su peso debe EXCLUIRSE del total "
        "(redistribución), no seguir contando contra 100."
    )


@pytest.mark.django_db
def test_peso_editado_via_columna_configurable_afecta_avance_ponderado(proyecto_simple):
    """#171 B3: si el peso de una columna se edita DIRECTAMENTE en
    ColumnaConfigurable (ej. futuro panel B6), el cálculo debe reflejarlo —
    prueba que `avance_ponderado` realmente lee `ColumnaConfigurable.peso_pct`
    y no `proyecto.peso_*_pct` (que se deja sin tocar en este test)."""
    torre = TorreConstruccion.objects.create(proyecto=proyecto_simple, numero='T-PESO-1')
    oc = ObraCivilTorre.objects.create(
        proyecto=proyecto_simple, torre=torre,
        avance_cerramiento=Decimal('1.0000'), avance_excavacion=Decimal('0.0000'),
        avance_solado=Decimal('0.0000'), avance_acero=Decimal('0.0000'),
        avance_vaciado=Decimal('0.0000'), avance_compactacion=Decimal('0.0000'),
    )
    # Baseline: cerramiento peso 5/100, avance=1 -> avance_ponderado = 0.05 (5%)
    assert oc.avance_ponderado_pct == 5.0

    # proyecto.peso_cerramiento_pct sigue siendo 5 (sin tocar) — pero
    # ColumnaConfigurable.peso_pct se sube a 50.
    ColumnaConfigurable.objects.filter(
        proyecto=proyecto_simple, capitulo=ColumnaConfigurable.CAPITULO_OBRA_CIVIL,
        clave='cerramiento',
    ).update(peso_pct=50)
    assert proyecto_simple.peso_cerramiento_pct == 5, "Sanity: proyecto.peso_cerramiento_pct no se tocó."

    oc.refresh_from_db()
    # total_peso = 50(cerr)+30(exc)+5(sol)+15(ace)+30(vac)+15(com) = 145
    # suma = 50*1 = 50 -> 50/145 = 0.344827... -> 34.5%
    assert oc.avance_ponderado_pct == pytest.approx(34.5, abs=0.05), (
        f"avance_ponderado no reflejó el peso editado en ColumnaConfigurable "
        f"(obtenido: {oc.avance_ponderado_pct}) — indicio de que el refactor "
        f"sigue leyendo proyecto.peso_*_pct en vez de ColumnaConfigurable."
    )


@pytest.mark.django_db
def test_editar_proyecto_peso_directo_y_save_sigue_afectando_avance_ponderado(proyecto_simple):
    """#171 B3 (hueco encontrado, fuera del scope original de F2): editar
    `proyecto.peso_cerramiento_pct` DIRECTO (sin pasar por ninguna vista) y
    llamar `.save()` debe seguir afectando `avance_ponderado` — el signal
    post_save de ProyectoConstruccion (signals.py) re-sincroniza
    ColumnaConfigurable en CUALQUIER `.save()`, no solo vía los paneles
    legacy. Mismo escenario que
    `tests/unit/test_obra_civil_matriz.py::test_avance_ponderado_respeta_cambio_de_pesos_del_proyecto`
    (ya existía, se rompió con el refactor B3 hasta agregar este signal)."""
    torre = TorreConstruccion.objects.create(proyecto=proyecto_simple, numero='T-DIRECTO-1')
    oc = ObraCivilTorre.objects.create(
        proyecto=proyecto_simple, torre=torre, avance_cerramiento=Decimal('1.0'),
    )
    assert oc.avance_ponderado_pct == pytest.approx(5.0, abs=0.05)  # default cerramiento=5

    proyecto_simple.peso_cerramiento_pct = 40
    proyecto_simple.peso_excavacion_pct = 30
    proyecto_simple.peso_solado_pct = 5
    proyecto_simple.peso_acero_pct = 15
    proyecto_simple.peso_vaciado_pct = 10
    proyecto_simple.peso_compactacion_pct = 0
    proyecto_simple.save()

    oc.refresh_from_db()
    assert oc.avance_ponderado_pct == pytest.approx(40.0, abs=0.05)


# ==============================================================================
# 4) Panel legacy de edición de pesos sigue teniendo efecto sobre el avance
#    (hueco encontrado durante B3: ver sync_columnas_sistema_pesos_proyecto en
#    models.py, disparado por el signal post_save de ProyectoConstruccion en
#    signals.py — cubre ObraCivilPesosUpdateView/MontajePesosUpdateView Y
#    cualquier otro código que edite proyecto.peso_*_pct directo, ver
#    sección 3 arriba).
# ==============================================================================

@pytest.mark.django_db
def test_panel_legacy_pesos_obra_civil_sigue_afectando_avance_ponderado(
    authenticated_client, proyecto_simple,
):
    """#171 B3 (hueco encontrado, fuera del scope original de F2): editar
    pesos vía el endpoint legacy `obra_civil_pesos_update` debe seguir
    surtiendo efecto sobre `avance_ponderado` — sin el signal post_save
    (`sync_columnas_sistema_pesos_proyecto`) esta edición se volvería un
    no-op silencioso porque avance_ponderado ya no lee `proyecto.peso_*_pct`."""
    from django.urls import reverse

    torre = TorreConstruccion.objects.create(proyecto=proyecto_simple, numero='T-PANEL-1')
    oc = ObraCivilTorre.objects.create(
        proyecto=proyecto_simple, torre=torre,
        avance_cerramiento=Decimal('1.0000'), avance_excavacion=Decimal('0.0000'),
        avance_solado=Decimal('0.0000'), avance_acero=Decimal('0.0000'),
        avance_vaciado=Decimal('0.0000'), avance_compactacion=Decimal('0.0000'),
    )
    assert oc.avance_ponderado_pct == 5.0  # baseline: solo cerramiento (peso 5) en 100%

    url = reverse('construccion:obra_civil_pesos_update', kwargs={'proyecto_id': proyecto_simple.id})
    resp = authenticated_client.post(url, {
        'cerramiento': '50', 'excavacion': '20', 'solado': '5',
        'acero': '10', 'vaciado': '10', 'compactacion': '5',
    })
    assert resp.status_code == 200, resp.content[:300]
    assert resp.json().get('ok') is True

    oc.refresh_from_db()
    # cerramiento ahora pesa 50/100, avance=1 en esa columna -> 50%
    assert oc.avance_ponderado_pct == 50.0, (
        "El panel legacy de pesos dejó de afectar avance_ponderado — falta "
        "sincronizar ColumnaConfigurable.peso_pct tras el POST."
    )

    columna_cerramiento = ColumnaConfigurable.objects.get(
        proyecto=proyecto_simple, capitulo=ColumnaConfigurable.CAPITULO_OBRA_CIVIL,
        clave='cerramiento',
    )
    assert columna_cerramiento.peso_pct == 50


# ==============================================================================
# 5) FIX regresión post-deploy (revisión instelec-api-00202-hg7 → auto-rollback
#    del gate E2E): columna custom `tipo_valor=BOOLEAN` en capítulo OBRA_CIVIL
#    o MONTAJE tiraba HTTP 500 al cargar la matriz.
#
#    Root cause: `ColumnaConfigurable.valor_para_torre()` devuelve un `bool`
#    Python (`True`/`False`) para columnas BOOLEAN — `Decimal(str(True))` /
#    `Decimal(str(False))` no son literales Decimal válidos
#    (`decimal.InvalidOperation`). El helper equivalente que SÍ funciona
#    (`TendidoTorre._avance_ponderado_capitulo`, ya cubierto por
#    `columna_custom_boolean_tendido` en test_issue_171_b7) evalúa el booleano
#    directo sin pasar por `Decimal(str(...))` — B3 (este archivo) tenía el
#    mismo bug copy-pasteado en 2 lugares y NUNCA se probó con
#    tipo_valor=BOOLEAN en OBRA_CIVIL/MONTAJE (el único boolean custom
#    cubierto en B7 era TENDIDO_CONDUCTOR, que ya usa el path correcto).
# ==============================================================================

@pytest.mark.django_db
def test_columna_custom_boolean_obra_civil_sin_fila_valor_no_explota(proyecto_simple):
    """Columna custom BOOLEAN en OBRA_CIVIL, torre que NUNCA la tocó (sin
    ColumnaConfigurableValor) — antes del fix: decimal.InvalidOperation
    (HTTP 500). Después: no participa, contribuye 0 al SUMPRODUCT."""
    torre = TorreConstruccion.objects.create(proyecto=proyecto_simple, numero='T-BOOL-OC-1')
    oc = ObraCivilTorre.objects.create(
        proyecto=proyecto_simple, torre=torre,
        avance_cerramiento=Decimal('1.0000'), avance_excavacion=Decimal('1.0000'),
        avance_solado=Decimal('1.0000'), avance_acero=Decimal('1.0000'),
        avance_vaciado=Decimal('1.0000'), avance_compactacion=Decimal('1.0000'),
    )
    ColumnaConfigurable.objects.create(
        proyecto=proyecto_simple, capitulo=ColumnaConfigurable.CAPITULO_OBRA_CIVIL,
        clave='chequeo_extra', etiqueta='Chequeo extra', orden=99,
        peso_pct=50, tipo_valor=ColumnaConfigurable.TIPO_BOOLEAN,
        es_sistema=False, activa=True,
    )
    # NO se crea ColumnaConfigurableValor — la torre nunca tocó esta columna.
    # Pesos activos: 6 de sistema (suman 100, default) + custom (50) = 150.
    # Custom no participa (raw=False) -> suma=100, total_peso=150 -> 66.7%.
    oc.refresh_from_db()
    assert oc.avance_ponderado_pct == pytest.approx(66.7, abs=0.05), (
        f"avance_ponderado explotó o dio un valor inesperado con columna custom "
        f"BOOLEAN sin fila de valor (obtenido: {oc.avance_ponderado_pct})"
    )


@pytest.mark.django_db
def test_columna_custom_boolean_obra_civil_con_valor_true_contribuye_peso_completo(proyecto_simple):
    """Misma columna custom BOOLEAN en OBRA_CIVIL, pero con
    ColumnaConfigurableValor(valor_boolean=True) creada — debe contribuir el
    peso completo (no 0, no explotar)."""
    torre = TorreConstruccion.objects.create(proyecto=proyecto_simple, numero='T-BOOL-OC-2')
    oc = ObraCivilTorre.objects.create(
        proyecto=proyecto_simple, torre=torre,
        avance_cerramiento=Decimal('1.0000'), avance_excavacion=Decimal('1.0000'),
        avance_solado=Decimal('1.0000'), avance_acero=Decimal('1.0000'),
        avance_vaciado=Decimal('1.0000'), avance_compactacion=Decimal('1.0000'),
    )
    columna = ColumnaConfigurable.objects.create(
        proyecto=proyecto_simple, capitulo=ColumnaConfigurable.CAPITULO_OBRA_CIVIL,
        clave='chequeo_extra', etiqueta='Chequeo extra', orden=99,
        peso_pct=50, tipo_valor=ColumnaConfigurable.TIPO_BOOLEAN,
        es_sistema=False, activa=True,
    )
    ColumnaConfigurableValor.objects.create(columna=columna, torre=torre, valor_boolean=True)

    oc.refresh_from_db()
    # suma=100+50*1=150, total_peso=150 -> 100.0%
    assert oc.avance_ponderado_pct == pytest.approx(100.0, abs=0.05), (
        f"columna custom BOOLEAN con valor True no contribuyó el peso completo "
        f"(obtenido: {oc.avance_ponderado_pct})"
    )


@pytest.mark.django_db
def test_columna_custom_boolean_montaje_sin_fila_valor_no_explota(proyecto_simple):
    """Mismo escenario que OBRA_CIVIL pero para capítulo MONTAJE
    (`MontajeEstructuraTorre.avance_ponderado` — el otro de los 2 lugares
    con el mismo bug copy-pasteado)."""
    torre = TorreConstruccion.objects.create(proyecto=proyecto_simple, numero='T-BOOL-MONT-1')
    m = MontajeEstructuraTorre.objects.create(
        proyecto=proyecto_simple, torre=torre,
        avance_estructura_sitio=Decimal('1.0000'), avance_prearamada=Decimal('1.0000'),
        avance_torre_montada=Decimal('1.0000'), avance_revisada=Decimal('1.0000'),
    )
    ColumnaConfigurable.objects.create(
        proyecto=proyecto_simple, capitulo=ColumnaConfigurable.CAPITULO_MONTAJE,
        clave='chequeo_extra_mont', etiqueta='Chequeo extra montaje', orden=99,
        peso_pct=25, tipo_valor=ColumnaConfigurable.TIPO_BOOLEAN,
        es_sistema=False, activa=True,
    )
    # Pesos activos: 4 de sistema (suman 100, default) + custom (25) = 125.
    # Custom no participa (raw=False) -> suma=100, total_peso=125 -> 80.0%.
    m.refresh_from_db()
    assert m.avance_ponderado_pct == pytest.approx(80.0, abs=0.05), (
        f"avance_ponderado (Montaje) explotó o dio un valor inesperado con "
        f"columna custom BOOLEAN sin fila de valor (obtenido: {m.avance_ponderado_pct})"
    )


@pytest.mark.django_db
def test_columna_custom_boolean_montaje_con_valor_true_contribuye_peso_completo(proyecto_simple):
    """Misma columna custom BOOLEAN en MONTAJE, pero con
    ColumnaConfigurableValor(valor_boolean=True) creada — debe contribuir el
    peso completo."""
    torre = TorreConstruccion.objects.create(proyecto=proyecto_simple, numero='T-BOOL-MONT-2')
    m = MontajeEstructuraTorre.objects.create(
        proyecto=proyecto_simple, torre=torre,
        avance_estructura_sitio=Decimal('1.0000'), avance_prearamada=Decimal('1.0000'),
        avance_torre_montada=Decimal('1.0000'), avance_revisada=Decimal('1.0000'),
    )
    columna = ColumnaConfigurable.objects.create(
        proyecto=proyecto_simple, capitulo=ColumnaConfigurable.CAPITULO_MONTAJE,
        clave='chequeo_extra_mont', etiqueta='Chequeo extra montaje', orden=99,
        peso_pct=25, tipo_valor=ColumnaConfigurable.TIPO_BOOLEAN,
        es_sistema=False, activa=True,
    )
    ColumnaConfigurableValor.objects.create(columna=columna, torre=torre, valor_boolean=True)

    m.refresh_from_db()
    # suma=100+25*1=125, total_peso=125 -> 100.0%
    assert m.avance_ponderado_pct == pytest.approx(100.0, abs=0.05), (
        f"columna custom BOOLEAN (Montaje) con valor True no contribuyó el "
        f"peso completo (obtenido: {m.avance_ponderado_pct})"
    )


@pytest.mark.django_db
def test_columna_custom_decimal_obra_civil_no_regresiona_con_el_fix(proyecto_simple):
    """Columna custom `tipo_valor=DECIMAL` (el branch NO-bool) debe seguir
    funcionando exactamente igual que antes del fix — `valor_para_torre`
    devuelve `Decimal('0')` (sin fila) o el `Decimal` real cargado, nunca
    `bool`, así que debe seguir yendo por `Decimal(str(raw))`."""
    torre = TorreConstruccion.objects.create(proyecto=proyecto_simple, numero='T-DEC-OC-1')
    oc = ObraCivilTorre.objects.create(
        proyecto=proyecto_simple, torre=torre,
        avance_cerramiento=Decimal('1.0000'), avance_excavacion=Decimal('1.0000'),
        avance_solado=Decimal('1.0000'), avance_acero=Decimal('1.0000'),
        avance_vaciado=Decimal('1.0000'), avance_compactacion=Decimal('1.0000'),
    )
    columna = ColumnaConfigurable.objects.create(
        proyecto=proyecto_simple, capitulo=ColumnaConfigurable.CAPITULO_OBRA_CIVIL,
        clave='avance_extra_decimal', etiqueta='Avance extra decimal', orden=99,
        peso_pct=20, tipo_valor=ColumnaConfigurable.TIPO_DECIMAL,
        es_sistema=False, activa=True,
    )
    # Sin fila de valor: valor_para_torre devuelve Decimal('0') -> no aporta.
    # total_peso=100+20=120, suma=100+20*0=100 -> 83.3%.
    oc.refresh_from_db()
    assert oc.avance_ponderado_pct == pytest.approx(83.3, abs=0.05)

    ColumnaConfigurableValor.objects.create(columna=columna, torre=torre, valor_decimal=Decimal('0.6'))
    oc.refresh_from_db()
    # suma=100+20*0.6=112, total_peso=120 -> 93.3%.
    assert oc.avance_ponderado_pct == pytest.approx(93.3, abs=0.05), (
        "El branch DECIMAL (no-bool) de avance_ponderado regresionó con el fix "
        "del bug BOOLEAN."
    )
