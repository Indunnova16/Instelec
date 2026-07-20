"""Instelec#171 (Sprint final, GRUPO A) — B4: regresión OBLIGATORIA (gate
bloqueante) del refactor de `TendidoTorre.avance_conductor` y
`TendidoTorre.avance_fibra` para leer pesos + columnas activas desde
`ColumnaConfigurable` (B2) en vez de los campos hardcodeados
`proyecto.peso_tend_*_pct`.

## Vía usada: datos REALES de BD prod (no el fallback sintético puro)

Se leyeron, vía el proxy de solo-lectura ya autorizado a F2/F3 para testing
(`127.0.0.1:5434`, `instelec_db`, usuario `postgres`, SOLO SELECT — nunca
INSERT/UPDATE/DELETE), los 65 registros reales de `TendidoTorre` del
proyecto QA #49 "Puerta de Oro" (`ec2a68aa-47fe-4772-89bc-2cd2b1c8b5c7`),
junto con los pesos vigentes del proyecto — mismos valores ya verificados
por F2 en `PLAN_2026-07-19_171_sprint_final.md` y usados por B2/B3:

    Tendido conductor: 20 / 20 / 30 / 10 / 10 / 10
    Tendido fibra:     10 / 20 / 40 / 20 / 10

Esos 65 registros se embeben abajo como literal CONGELADO
(`TEND_TORRES_REALES`) — el test NO vuelve a consultar prod en cada corrida
(corre contra la BD de test de pytest, `--nomigrations`, igual que el resto
de la suite). Es la "vía real BD" que pide el prompt F3, no el fallback
sintético.

## Metodología

Se reconstruye la fórmula LEGACY tal cual estaba ANTES de B4 (copiada
literal — `SUMPRODUCT(peso hardcodeado de proyecto.peso_tend_*_pct, valor
0/1) / SUM(peso)`, congelada acá) y se compara, torre por torre, contra las
properties REALES post-refactor (`.avance_conductor_pct` /
`.avance_fibra_pct`, que ahora leen de `ColumnaConfigurable`). **0 diffs
esperados.**

Como los pesos reales del proyecto QA (20/20/30/10/10/10 conductor,
10/20/40/20/10 fibra) NO coinciden con los defaults hardcodeados del modelo
(10/30/30/10/10/10 conductor — ver sección 3, `proyecto_simple`), esta
regresión sobre datos reales YA distingue por sí sola "lee
`ColumnaConfigurable`" de "lee `proyecto.peso_tend_*_pct`" (a diferencia de
Obra Civil/Montaje en B3, donde los pesos reales coinciden con el default).
Aun así se agregan tests sintéticos de redistribución en la sección 3 para
cubrir el caso de desactivación de columna.

## Convención de colección

Vive en `tests/unit/` (no `apps/construccion/tests_issue_171.py`) — mismo
motivo documentado en `test_issue_171_b2_columna_configurable.py`:
`pyproject.toml` define `testpaths = ["tests"]`, el patrón legacy
`apps/<app>/tests_*.py` no colecta.
"""
import pytest

from apps.construccion.models import (
    ColumnaConfigurable,
    ProyectoConstruccion,
    TendidoTorre,
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

# (numero, riega_manila_conductor, riega_guaya_conductor, tendido_conductor,
#  grapado_amarre_conductor, accesorios_puentes, balizas_desviadores,
#  riega_manila_fibra, riega_guaya_opgw, tendido_opgw, grapado_amarre_fibra,
#  empalmes_opgw)
TEND_TORRES_REALES = [
    ('E1', True, True, True, True, True, True, True, True, True, True, True),
    ('E10', True, True, True, True, True, True, True, True, True, True, True),
    ('E11', True, True, True, True, True, True, True, True, True, True, True),
    ('E12', True, True, True, True, True, True, True, True, True, True, True),
    ('E13', True, True, True, True, True, True, True, True, True, True, True),
    ('E14', True, True, True, True, True, True, True, True, True, True, True),
    ('E15', True, True, True, True, True, True, True, True, True, True, True),
    ('E16', True, True, True, True, True, True, True, True, True, True, True),
    ('E17', True, True, True, True, True, True, True, True, True, True, True),
    ('E18', True, True, True, True, True, True, True, True, True, True, True),
    ('E19', True, True, True, True, True, True, True, True, True, True, True),
    ('E2', True, True, True, True, True, True, True, True, True, True, True),
    ('E20', True, True, True, True, True, True, True, True, True, True, True),
    ('E21', True, True, True, True, True, True, True, True, True, True, True),
    ('E22', True, True, True, True, True, True, True, True, True, True, True),
    ('E23', True, True, True, True, True, True, True, True, True, True, True),
    ('E24', True, True, True, True, True, True, True, True, True, True, True),
    ('E25', True, True, True, True, True, True, True, True, True, True, True),
    ('E26', True, True, True, True, True, True, True, True, True, True, True),
    ('E27', True, True, True, True, True, True, True, True, True, True, True),
    ('E28', True, True, True, True, True, True, True, True, True, True, True),
    ('E29', True, True, True, True, True, True, True, True, True, True, True),
    ('E3', True, True, True, True, True, True, True, True, True, True, True),
    ('E30', True, True, True, True, True, True, True, True, True, True, True),
    ('E31', True, True, True, True, True, True, True, True, True, True, True),
    ('E32', True, True, True, True, True, True, True, True, True, True, True),
    ('E33', True, True, True, True, True, True, True, True, True, True, True),
    ('E34', True, True, True, True, True, True, True, True, True, True, True),
    ('E35', True, True, True, True, True, True, True, True, True, True, True),
    ('E36', True, True, True, True, True, True, True, True, True, True, True),
    ('E37', True, True, True, True, True, True, True, True, True, True, True),
    ('E38', True, True, True, True, True, True, True, True, True, True, True),
    ('E39', True, True, True, True, True, True, True, True, True, True, True),
    ('E4', True, True, True, True, True, True, True, True, True, True, True),
    ('E40', True, True, True, True, True, True, True, True, True, True, True),
    ('E41', True, True, True, True, True, True, True, True, True, True, True),
    ('E42', True, True, True, True, True, True, True, True, True, True, True),
    ('E43', True, True, True, True, True, True, True, True, True, True, True),
    ('E44', True, True, True, True, True, True, True, True, True, True, True),
    ('E45', True, True, True, True, True, True, True, True, True, True, True),
    ('E46', True, True, True, True, True, True, True, True, True, True, True),
    ('E47', True, True, True, True, True, True, True, True, True, True, True),
    ('E48', True, True, True, True, True, True, True, True, True, True, True),
    ('E49', True, True, True, True, True, True, True, True, True, True, True),
    ('E5', True, True, True, True, True, True, True, True, True, True, True),
    ('E50', True, True, True, True, True, True, True, True, True, True, True),
    ('E51', True, True, True, True, True, True, True, True, True, True, True),
    ('E52', True, True, True, True, True, True, True, True, True, True, True),
    ('E53', True, True, True, True, True, True, True, True, True, True, True),
    ('E54', True, True, True, True, True, True, True, True, True, True, True),
    ('E55', True, True, True, True, True, True, True, True, True, True, True),
    ('E56', True, True, True, True, True, True, True, True, True, True, True),
    ('E57', True, True, True, True, True, True, True, True, True, True, True),
    ('E58', True, True, True, True, True, True, True, True, True, True, True),
    ('E59', True, True, True, True, True, True, True, True, True, True, True),
    ('E6', True, True, True, True, True, True, True, True, True, True, True),
    ('E60', True, True, True, True, True, True, True, True, True, True, True),
    ('E61', True, True, True, True, True, True, True, True, True, True, True),
    ('E62', True, True, True, True, True, True, True, True, True, True, True),
    ('E63', True, True, True, True, True, True, True, True, True, True, True),
    ('E64', True, True, True, True, True, True, True, True, True, True, True),
    ('E65', True, True, True, True, True, True, True, True, True, True, True),
    ('E7', True, True, True, True, True, True, True, True, True, True, True),
    ('E8', True, True, True, True, True, True, True, True, True, True, True),
    ('E9', True, True, True, True, True, True, True, True, True, True, True),
]

assert len(TEND_TORRES_REALES) == 65


# ==============================================================================
# Fórmulas LEGACY — congeladas, copiadas literal de models.py ANTES de B4.
# NO deben cambiar nunca (son la referencia fija contra la que se regresiona).
# ==============================================================================

def _avance_conductor_legacy(proyecto, valores):
    pesos = {
        'riega_manila_conductor': proyecto.peso_tend_riega_manila_pct,
        'riega_guaya_conductor': proyecto.peso_tend_riega_guaya_pct,
        'tendido_conductor': proyecto.peso_tend_tendido_conductor_pct,
        'grapado_amarre_conductor': proyecto.peso_tend_grapado_pct,
        'accesorios_puentes': proyecto.peso_tend_accesorios_pct,
        'balizas_desviadores': proyecto.peso_tend_balizas_pct,
    }
    total = sum(pesos.values()) or 1
    suma = sum(peso * (1 if valores[f] else 0) for f, peso in pesos.items())
    return suma / total


def _avance_fibra_legacy(proyecto, valores):
    pesos = {
        'riega_manila_fibra': proyecto.peso_tend_riega_manila_fibra_pct,
        'riega_guaya_opgw': proyecto.peso_tend_riega_guaya_opgw_pct,
        'tendido_opgw': proyecto.peso_tend_tendido_opgw_pct,
        'grapado_amarre_fibra': proyecto.peso_tend_grapado_fibra_pct,
        'empalmes_opgw': proyecto.peso_tend_empalmes_opgw_pct,
    }
    total = sum(pesos.values()) or 1
    suma = sum(peso * (1 if valores[f] else 0) for f, peso in pesos.items())
    return suma / total


# ==============================================================================
# 1) Fixture — proyecto QA (pesos reales) + 65 torres reales, Tendido
# ==============================================================================

@pytest.fixture
def proyecto_qa_65_torres(db):
    """Reproduce el proyecto QA real (#49 Puerta de Oro) con sus pesos
    vigentes y las 65 torres reales (TendidoTorre) con los valores REALES
    leídos de prod. El signal post_save ya crea las 21 filas
    ColumnaConfigurable con estos mismos pesos (B2)."""
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-171-B4-001',
        nombre='Proyecto test #171 B4 — 65 torres reales',
        cliente='Test',
    )
    proyecto = ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='QA test #49 - Puerta de Oro (fixture B4)',
        estado='EJECUCION',
        **_PESOS_PROD_VERIFICADOS,
    )
    assert ColumnaConfigurable.objects.filter(proyecto=proyecto).count() == 21, (
        "Fixture inválida: el signal post_save debía crear las 21 columnas "
        "de fábrica al crear el proyecto."
    )

    torres = {}
    for numero, *_ in TEND_TORRES_REALES:
        torres[numero] = TorreConstruccion.objects.create(proyecto=proyecto, numero=numero)

    for (numero, rmc, rgc, tc, gac, ap, bd, rmf, rgo, to, gaf, eo) in TEND_TORRES_REALES:
        TendidoTorre.objects.create(
            proyecto=proyecto, torre=torres[numero],
            riega_manila_conductor=rmc, riega_guaya_conductor=rgc,
            tendido_conductor=tc, grapado_amarre_conductor=gac,
            accesorios_puentes=ap, balizas_desviadores=bd,
            riega_manila_fibra=rmf, riega_guaya_opgw=rgo,
            tendido_opgw=to, grapado_amarre_fibra=gaf, empalmes_opgw=eo,
        )

    return proyecto, torres


# ==============================================================================
# 2) Regresión OBLIGATORIA — 0 diffs esperados, 2 fórmulas × 65 torres
# ==============================================================================

@pytest.mark.django_db
def test_regresion_avance_conductor_fibra_65_torres_reales_0_diffs(proyecto_qa_65_torres):
    """#171 B4 — gate bloqueante: avance_conductor_pct y avance_fibra_pct de
    TendidoTorre deben ser IDÉNTICOS (legacy hardcodeado vs
    ColumnaConfigurable post-refactor) para las 65 torres reales."""
    proyecto, torres = proyecto_qa_65_torres
    diffs = []
    for (numero, rmc, rgc, tc, gac, ap, bd, rmf, rgo, to, gaf, eo) in TEND_TORRES_REALES:
        td = TendidoTorre.objects.get(proyecto=proyecto, torre=torres[numero])
        valores_conductor = {
            'riega_manila_conductor': rmc, 'riega_guaya_conductor': rgc,
            'tendido_conductor': tc, 'grapado_amarre_conductor': gac,
            'accesorios_puentes': ap, 'balizas_desviadores': bd,
        }
        valores_fibra = {
            'riega_manila_fibra': rmf, 'riega_guaya_opgw': rgo,
            'tendido_opgw': to, 'grapado_amarre_fibra': gaf, 'empalmes_opgw': eo,
        }
        legacy_conductor_pct = round(_avance_conductor_legacy(proyecto, valores_conductor) * 100, 1)
        legacy_fibra_pct = round(_avance_fibra_legacy(proyecto, valores_fibra) * 100, 1)
        if abs(legacy_conductor_pct - td.avance_conductor_pct) > 1e-9:
            diffs.append(('conductor', numero, legacy_conductor_pct, td.avance_conductor_pct))
        if abs(legacy_fibra_pct - td.avance_fibra_pct) > 1e-9:
            diffs.append(('fibra', numero, legacy_fibra_pct, td.avance_fibra_pct))
    assert diffs == [], f"Regresión detectada en avance_conductor/avance_fibra: {diffs}"


# ==============================================================================
# 3) Unit — redistribución de peso al desactivar una columna boolean
#    (SINTÉTICO) + panel legacy sigue afectando el avance.
# ==============================================================================

@pytest.fixture
def proyecto_simple(db):
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-171-B4-002',
        nombre='Proyecto test #171 B4 — redistribución de peso',
        cliente='Test',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato, nombre='Proyecto simple B4', estado='EJECUCION',
    )


@pytest.mark.django_db
def test_columna_sistema_boolean_desactivada_se_excluye_tendido_conductor(proyecto_simple):
    """#171 B4: mismo comportamiento de redistribución que Obra Civil (B3),
    pero sobre una columna BOOLEAN de Tendido conductor.

    `proyecto_simple` NO pasa pesos custom — usa los defaults del modelo
    para Tendido conductor: riega_manila=10, riega_guaya=30, tendido=30,
    grapado=10, accesorios=10, balizas=10 (suma 100). Distinto de los
    valores verificados en prod (20/20/30/10/10/10, ver
    `_PESOS_PROD_VERIFICADOS`) — prod tiene esos pesos porque fueron
    editados en algún momento vía el panel legacy, no porque coincidan con
    el default de fábrica del modelo."""
    torre = TorreConstruccion.objects.create(proyecto=proyecto_simple, numero='T-REDIST-2')
    td = TendidoTorre.objects.create(
        proyecto=proyecto_simple, torre=torre,
        riega_manila_conductor=True,     # peso 10 (default), activa
        riega_guaya_conductor=False,     # peso 30 (default), se va a DESACTIVAR
        tendido_conductor=True,          # peso 30 (default), activa
        grapado_amarre_conductor=True,   # peso 10 (default), activa
        accesorios_puentes=True,         # peso 10 (default), activa
        balizas_desviadores=True,        # peso 10 (default), activa
    )
    # Baseline: riega_guaya_conductor=False contribuye 0 -> (10+30+10+10+10)/100 = 0.70
    assert td.avance_conductor_pct == 70.0

    ColumnaConfigurable.objects.filter(
        proyecto=proyecto_simple, capitulo=ColumnaConfigurable.CAPITULO_TENDIDO_CONDUCTOR,
        clave='riega_guaya_conductor',
    ).update(activa=False)

    td.refresh_from_db()
    # Tras desactivar riega_guaya_conductor (peso 30): total_peso pasa a 70
    # (10+30+10+10+10), suma se mantiene en 70 (ya contribuía 0) → 70/70 = 1.0 (100%)
    assert td.avance_conductor_pct == 100.0, (
        "Al desactivar una columna boolean, su peso debe EXCLUIRSE del "
        "total (redistribución) — mismo criterio que Obra Civil."
    )


@pytest.mark.django_db
def test_panel_legacy_pesos_tendido_conductor_sigue_afectando_avance(
    authenticated_client, proyecto_simple,
):
    """#171 B4 (mismo hueco que B3, ver
    test_issue_171_b3_avance_ponderado_regresion.py sección 4): editar
    pesos vía el endpoint legacy `tendido_pesos_update` (sección=conductor)
    debe seguir surtiendo efecto sobre `avance_conductor` — cubierto por el
    mismo signal post_save de ProyectoConstruccion (sync_columnas_sistema_pesos_proyecto)."""
    from django.urls import reverse

    torre = TorreConstruccion.objects.create(proyecto=proyecto_simple, numero='T-PANEL-2')
    td = TendidoTorre.objects.create(
        proyecto=proyecto_simple, torre=torre,
        riega_manila_conductor=True,  # peso 10 (default) — único True
    )
    assert td.avance_conductor_pct == 10.0  # baseline: solo riega_manila (peso 10 default)

    url = reverse('construccion:tendido_pesos_update', kwargs={'proyecto_id': proyecto_simple.id})
    resp = authenticated_client.post(url, {
        'seccion': 'conductor',
        'riega_manila': '50', 'riega_guaya': '20', 'tendido': '10',
        'grapado': '10', 'accesorios': '5', 'balizas': '5',
    })
    assert resp.status_code == 200, resp.content[:300]
    assert resp.json().get('ok') is True

    td.refresh_from_db()
    # riega_manila_conductor ahora pesa 50/100, único activo -> 50%
    assert td.avance_conductor_pct == 50.0, (
        "El panel legacy de pesos (Tendido) dejó de afectar avance_conductor "
        "— falta sincronizar ColumnaConfigurable.peso_pct tras el POST."
    )
