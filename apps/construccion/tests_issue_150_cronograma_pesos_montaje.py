"""Tests Instelec#150 — 6ta ronda del cierre (bounce 5), 2 pendientes del QA
report 2026-07-10 (comment 15) tras mover B1/B4 (freeze-header) a #183:

  1. Cronograma: pesos de fases que no suman 100 (ej. 200) inflaban la curva
     "planeado" del Dashboard Avance más allá de 100%.
  2. Cronograma: columna "% real" de Montaje mostraba "—%" (0.0 escondido por
     `default`, no `default_if_none`) porque `pct_avance_real` leía la
     propiedad legacy `porcentaje_avance_montaje` en vez de la fuente real
     que ya usan los demás dashboards (`calculators_avance_real._pct_montaje`).

Archivo POR-ISSUE dedicado (convención de este repo — ver
tests_issue_150_actividades_finales_cierre.py) para no chocar con el otro
operario trabajando Instelec#176/#179 en paralelo en otro worktree.
"""

from datetime import date

import pytest


@pytest.fixture
def proyecto_150(db):
    from apps.construccion.models import ProyectoConstruccion
    from apps.contratos.models import Contrato

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo="TEST-150-CRONO-001",
        nombre="Contrato test 150 cronograma",
        cliente="Test Cliente 150",
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre="Proyecto 150 cronograma test",
        estado="EJECUCION",
    )


def _primero_de_mes_hace(n_meses):
    """1er día del mes que fue hace `n_meses` meses (helper sin dependencias
    externas tipo dateutil) — usado para que las fechas de fase caigan en un
    'cursor' exacto de curva_s_data() (que solo genera 1º-de-mes) y así el
    tope normalizado (100) se alcance de forma determinística en el test,
    sin depender de en qué día del mes se corra la suite."""
    hoy = date.today()
    year, month = hoy.year, hoy.month - n_meses
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


def _fase(proyecto, seccion, peso_pct, meses_atras_inicio=4, meses_atras_fin=2):
    from apps.construccion.models import ProgramacionFase

    return ProgramacionFase.objects.create(
        proyecto=proyecto,
        seccion=seccion,
        fecha_inicio_planeada=_primero_de_mes_hace(meses_atras_inicio),
        fecha_fin_planeada=_primero_de_mes_hace(meses_atras_fin),
        peso_pct=peso_pct,
    )


@pytest.mark.django_db
def test_curva_s_data_normaliza_pesos_que_suman_200(proyecto_150):
    """#150: 2 fases YA terminadas con pesos 100+100=200 no deben inflar
    'planeado' por encima de 100 en ningún mes de la curva."""
    from apps.construccion.models import ProgramacionFase

    _fase(proyecto_150, ProgramacionFase.Seccion.INGENIERIA, 100)
    _fase(proyecto_150, ProgramacionFase.Seccion.MONTAJE, 100)

    data = proyecto_150.curva_s_data()
    assert data, "curva_s_data() no debería estar vacía con 2 fases con fechas"
    assert all(row["planeado"] <= 100 for row in data), (
        f"con pesos sumando 200, 'planeado' se infló por encima de 100: "
        f"{[row['planeado'] for row in data if row['planeado'] > 100]}"
    )
    # Ambas fases ya terminaron (fecha_fin en el pasado) → el tope real debe
    # llegar a 100 en algún punto de la curva (no solo quedar por debajo por
    # la normalización). Se usa max() en vez del último elemento porque el
    # bucketing mensual no siempre alinea el último 'mes' generado con la
    # fecha_fin exacta.
    assert max(row["planeado"] for row in data) == 100


@pytest.mark.django_db
def test_curva_s_data_pesos_100_sin_cambio_de_comportamiento(proyecto_150):
    """Sanity/no-regresión: con pesos que YA suman 100 (caso normal), el
    fix de normalización no debe alterar el resultado."""
    from apps.construccion.models import ProgramacionFase

    _fase(proyecto_150, ProgramacionFase.Seccion.INGENIERIA, 40)
    _fase(proyecto_150, ProgramacionFase.Seccion.MONTAJE, 60)

    data = proyecto_150.curva_s_data()
    assert max(row["planeado"] for row in data) == 100


@pytest.mark.django_db
def test_curva_s_data_pesos_todos_en_cero_no_divide_por_cero(proyecto_150):
    """Fallback: si nadie cargó pesos (todos 0, estado real de varios
    proyectos en prod), no debe reventar por división por cero."""
    from apps.construccion.models import ProgramacionFase

    _fase(proyecto_150, ProgramacionFase.Seccion.INGENIERIA, 0)
    _fase(proyecto_150, ProgramacionFase.Seccion.MONTAJE, 0)

    data = proyecto_150.curva_s_data()
    assert all(row["planeado"] == 0 for row in data)


@pytest.mark.django_db
def test_pct_avance_real_montaje_usa_fuente_correcta_no_legacy_cero(proyecto_150):
    """#150: MONTAJE debe leer MontajeEstructuraTorreDetalle.avance_ponderado
    (vía _pct_montaje), NO la propiedad legacy que siempre daba 0.0/'—%'."""
    from apps.construccion.models import ProgramacionFase, TorreConstruccion
    from apps.construccion.models_b3_mont_detalle import MontajeEstructuraTorreDetalle

    fase = _fase(proyecto_150, ProgramacionFase.Seccion.MONTAJE, 100)
    torre = TorreConstruccion.objects.create(proyecto=proyecto_150, numero="T001", tipo="B4")
    MontajeEstructuraTorreDetalle.objects.create(
        torre=torre,
        proyecto=proyecto_150,
        estructura_en_sitio_ok=True,
        torre_montada_ok=True,  # 10 + 45 = 55%
    )

    assert fase.pct_avance_real == 55.0
    # No debe haber quedado None/0 escondido detrás del legacy `porcentaje_avance_montaje`.
    assert proyecto_150.porcentaje_avance_montaje == 0.0, (
        "sanity: confirma que el gap real seguía existiendo en la propiedad legacy "
        "(FaseTorre nunca se pobló) — si esto falla, la fixture cambió y el test ya no prueba el gap"
    )


@pytest.mark.django_db
def test_pct_avance_real_montaje_excluye_torres_no_aplica(proyecto_150):
    """#150/#160: una torre marcada No aplica no debe contar en el % real
    de Montaje del Cronograma — misma regla global que Obra Civil/Tendido."""
    from apps.construccion.models import ProgramacionFase, TorreConstruccion
    from apps.construccion.models_b3_mont_detalle import MontajeEstructuraTorreDetalle

    fase = _fase(proyecto_150, ProgramacionFase.Seccion.MONTAJE, 100)
    torre_aplica = TorreConstruccion.objects.create(
        proyecto=proyecto_150, numero="T001", tipo="B4", aplica=True
    )
    torre_no_aplica = TorreConstruccion.objects.create(
        proyecto=proyecto_150, numero="T002", tipo="B4", aplica=False
    )
    MontajeEstructuraTorreDetalle.objects.create(
        torre=torre_aplica,
        proyecto=proyecto_150,
        estructura_en_sitio_ok=True,
        prearmada_ok=True,
        torre_montada_ok=True,
        revisada_ok=True,  # 100%
    )
    MontajeEstructuraTorreDetalle.objects.create(
        torre=torre_no_aplica,
        proyecto=proyecto_150,
        # todo en False → 0%, y encima aplica=False → debe excluirse del denominador
    )

    # Con la torre no-aplica excluida del denominador, la única torre que
    # cuenta está en 100% → el % real del proyecto debe ser 100, no 50.
    assert fase.pct_avance_real == 100.0
