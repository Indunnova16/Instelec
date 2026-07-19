"""Instelec#185 — date.today() (reloj UTC crudo del contenedor Cloud Run)
reemplazado por django.utils.timezone.localdate() (respeta
settings.TIME_ZONE='America/Bogota', USE_TZ=True) en
apps/construccion/calculators_avance_real.py.

Bug reportado por el cliente + confirmado por F2 con evidencia EN VIVO contra
Cloud SQL (NOW() AT TIME ZONE 'UTC' vs 'America/Bogota'): durante la ventana
~19:00-23:59 hora Bogotá (== ~00:00-04:59 UTC del día siguiente), el reloj del
contenedor (UTC) ya reporta el día siguiente mientras Bogotá sigue en el día
real. date.today() devolvía ese día UTC (falso), desplazando 1 día el punto
"hoy" de la Curva S Planeado (serie_planeado, línea 371) y pudiendo colar/
excluir fechas del guard anti-typo de fecha_avance_tendido (líneas 206/222).

Instante usado en los tests: 2026-07-19 01:32:32 UTC == 2026-07-18 20:32:32
Bogotá — es el instante EXACTO que F2 verificó en vivo con psql contra prod,
dentro de la ventana vulnerable que reportó el cliente (no un dato sintético).

Convención confirmada: `pytest` (bare, `make test`) y CI (.github/workflows/
ci.yml: `pytest tests/unit tests/integration`) solo colectan
`tests/unit/test_*.py` — el patrón `apps/<app>/tests_issue_<N>.py` que existe
hoy en apps/construccion (tests_issue_171.py, tests_issue_147.py, etc.) NO
matchea `python_files = ["test_*.py", "*_test.py"]` de pyproject.toml y
`testpaths = ["tests"]` tampoco lo alcanza -> confirmado con
`pytest apps/construccion --collect-only -q` = 0 items. Ese hallazgo se deja
documentado en el comentario de cierre del issue (candidato a issue de
seguimiento del portafolio, mismo patrón que
`feedback_tests_no_colectan_ocultan_bugs`). Este archivo sigue la convención
que SÍ colecta: tests/unit/test_issue_<N>.py (ver test_issue_164.py,
test_issue_167.py, test_issue_173.py como precedente).
"""
from __future__ import annotations

import inspect
from datetime import date, datetime, timezone as dt_timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.construccion import calculators_avance_real as calc
from apps.construccion.models import FaseTorre, ProgramacionFase, TorreConstruccion
from apps.construccion.models import ProyectoConstruccion
from apps.contratos.models import Contrato

# Instante real verificado por F2 (Cloud SQL, en vivo, dentro de la ventana
# vulnerable ~19:00-23:59 Bogotá == ~00:00-04:59 UTC del día siguiente).
_UTC_VULNERABLE = datetime(2026, 7, 19, 1, 32, 32, tzinfo=dt_timezone.utc)
_HOY_BOGOTA_REAL = date(2026, 7, 18)  # día correcto (Bogotá) en ese instante
_HOY_UTC_FALSO = date(2026, 7, 19)  # día que el bug calculaba (reloj UTC crudo)


def _mock_now():
    """Sustituto de timezone.now() fijado al instante vulnerable."""
    return _UTC_VULNERABLE


@pytest.fixture
def proyecto(db):
    """Proyecto de construcción de prueba (contrato mínimo requerido)."""
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-185-001',
        nombre='Proyecto test #185 timezone',
        cliente='Test',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto test #185',
        estado='EJECUCION',
    )


# ==============================================================================
# 0) Guard estático anti-regresión: el archivo no debe volver a tener
#    date.today() ni perder el import de timezone (kaizen barato, corre
#    siempre, sin BD).
# ==============================================================================

def test_calculators_avance_real_no_usa_date_today_crudo():
    """Regresión: si alguien reintroduce date.today() en este archivo, este
    test debe fallar ANTES de que vuelva a colarse a prod."""
    fuente = inspect.getsource(calc)
    assert 'date.today()' not in fuente, (
        "Regresión #185: calculators_avance_real.py volvió a usar "
        "date.today() (reloj UTC crudo) en vez de timezone.localdate()."
    )
    assert 'from django.utils import timezone' in fuente


# ==============================================================================
# 1) serie_planeado (línea 371) — Curva S Planeado, punto "hoy"
# ==============================================================================

@pytest.mark.django_db
def test_serie_planeado_usa_fecha_bogota_no_utc_para_punto_hoy(proyecto):
    """Reproduce el bug reportado por el cliente (confirmado por F2 con psql
    en vivo): con el reloj del contenedor en 2026-07-19 01:32:32 UTC, el punto
    intermedio "hoy" de la interpolación de serie_planeado NO debe caer en
    2026-07-19 (UTC, falso) sino en 2026-07-18 (Bogotá, real).

    'Registro legacy real': fecha_inicio_planeada = 2025-01-13 es el valor
    REAL de la fase MONTAJE del proyecto QA (Puerta de Oro) que F2 verificó
    contra Cloud SQL; fecha_fin_planeada se extiende para bracketear 'hoy'
    (mismo patrón que usa la journey maestra QA i150_b3_curva_s_planeado y la
    journey E2E de F2 para #185).
    """
    ProgramacionFase.objects.create(
        proyecto=proyecto,
        seccion=ProgramacionFase.Seccion.MONTAJE,
        fecha_inicio_planeada=date(2025, 1, 13),  # legacy real (Puerta de Oro)
        fecha_fin_planeada=date(2026, 12, 31),
        peso_pct=100,
    )

    with patch('django.utils.timezone.now', _mock_now):
        resultado = calc.serie_planeado(proyecto, calc.FASE_MONTAJE)

    assert _HOY_BOGOTA_REAL.isoformat() in resultado['labels'], (
        f"Esperaba el día Bogotá ({_HOY_BOGOTA_REAL.isoformat()}) en la serie "
        f"planeada, no se encontró: {resultado['labels']}"
    )
    assert _HOY_UTC_FALSO.isoformat() not in resultado['labels'], (
        f"BUG #185: la serie planeada coló el día UTC falso "
        f"({_HOY_UTC_FALSO.isoformat()}) en vez del día real de Bogotá."
    )
    # El punto intermedio debe ser el penúltimo label (labels = [inicio, hoy, fin]).
    assert len(resultado['labels']) == 3
    assert resultado['labels'][1] == _HOY_BOGOTA_REAL.isoformat()


@pytest.mark.django_db
def test_serie_planeado_sin_mock_no_usa_utc_crudo(proyecto):
    """Control (sin mock de tiempo): con el reloj real de la máquina, la
    fecha usada por serie_planeado debe coincidir con timezone.localdate()
    (Bogotá) y NUNCA con date.today() (UTC crudo) cuando ambas difieren.
    Guard adicional para detectar si el fix se revierte en un entorno donde
    la ventana vulnerable esté activa en CI."""
    ProgramacionFase.objects.create(
        proyecto=proyecto,
        seccion=ProgramacionFase.Seccion.MONTAJE,
        fecha_inicio_planeada=date(2020, 1, 1),
        fecha_fin_planeada=date(2030, 1, 1),
        peso_pct=100,
    )
    from django.utils import timezone as django_timezone

    resultado = calc.serie_planeado(proyecto, calc.FASE_MONTAJE)
    assert resultado['labels'][1] == django_timezone.localdate().isoformat()


# ==============================================================================
# 2) fecha_avance_tendido (líneas 204-222) — guard anti-typo de fechas futuras
# ==============================================================================

@pytest.mark.django_db
def test_fecha_avance_tendido_guard_anti_typo_usa_hoy_bogota(proyecto):
    """Reproduce el mecanismo exacto del bug para el guard anti-typo (#166
    Hilo A / BD prod: torre E58 con fecha corrupta a 2028).

    Con el bug (hoy = date.today() = 2026-07-19 UTC falso), una fecha
    diligenciada en FaseTorre de 2026-07-19 NO sería excluida como futura
    (2026-07-19 no es > 2026-07-19) — aunque en Bogotá esa fecha SÍ es mañana
    respecto al día real (2026-07-18).

    Con el fix (hoy = timezone.localdate() = 2026-07-18 Bogotá real), esa
    misma fecha (2026-07-19) SÍ debe ser excluida por el guard anti-typo,
    porque es estrictamente mayor al día real de Bogotá.
    """
    torre = TorreConstruccion.objects.create(
        proyecto=proyecto,
        numero='T-185',
        tipo='D',
        aplica=True,
    )
    fase_torre = FaseTorre.objects.create(
        torre=torre,
        proyecto=proyecto,
        fecha_riega_manila=_HOY_UTC_FALSO,  # == "mañana" real en Bogotá
    )
    tendido = SimpleNamespace(
        torre=SimpleNamespace(fase=fase_torre),
        updated_at=None,
        created_at=datetime(2025, 1, 1, tzinfo=dt_timezone.utc),
    )

    with patch('django.utils.timezone.now', _mock_now):
        fecha = calc.fecha_avance_tendido(tendido)

    # El guard anti-typo debe EXCLUIR fecha_riega_manila (2026-07-19) porque
    # es futura respecto al día real de Bogotá (2026-07-18) -> cae a la
    # cascada legacy (created_at -> 2025-01-01), NUNCA cuela el 2026-07-19.
    assert fecha != _HOY_UTC_FALSO, (
        "BUG #185: el guard anti-typo de fecha_avance_tendido usó el día UTC "
        "falso como 'hoy' y dejó colar una fecha que en Bogotá es futura."
    )
    assert fecha == date(2025, 1, 1)


@pytest.mark.django_db
def test_fecha_avance_tendido_acepta_fecha_igual_a_hoy_bogota(proyecto):
    """Caso complementario: una fecha diligenciada EXACTAMENTE en el día real
    de Bogotá (2026-07-18) sí debe pasar el guard (no es > hoy) y ser la
    fecha de avance devuelta — confirma que el fix no volvió el guard
    demasiado estricto."""
    torre = TorreConstruccion.objects.create(
        proyecto=proyecto,
        numero='T-186',
        tipo='D',
        aplica=True,
    )
    fase_torre = FaseTorre.objects.create(
        torre=torre,
        proyecto=proyecto,
        fecha_riega_manila=_HOY_BOGOTA_REAL,
    )
    tendido = SimpleNamespace(
        torre=SimpleNamespace(fase=fase_torre),
        updated_at=None,
        created_at=datetime(2025, 1, 1, tzinfo=dt_timezone.utc),
    )

    with patch('django.utils.timezone.now', _mock_now):
        fecha = calc.fecha_avance_tendido(tendido)

    assert fecha == _HOY_BOGOTA_REAL


# ==============================================================================
# 3) fecha_avance_oc / fecha_avance_montaje (líneas 151/165) — fallback final
#    de la cascada (defensivo: created_at es NOT NULL en BD real, pero el
#    código lo contempla; se prueba con un stub para forzar la rama).
# ==============================================================================

def test_fecha_avance_oc_fallback_usa_localdate_bogota():
    detalle = SimpleNamespace(vac_fecha_vaciado=None, updated_at=None, created_at=None)
    with patch('django.utils.timezone.now', _mock_now):
        fecha = calc.fecha_avance_oc(detalle)
    assert fecha == _HOY_BOGOTA_REAL
    assert fecha != _HOY_UTC_FALSO


def test_fecha_avance_montaje_fallback_usa_localdate_bogota():
    detalle = SimpleNamespace(
        montaje_fecha_fin=None, prearmado_fecha_fin=None,
        updated_at=None, created_at=None,
    )
    with patch('django.utils.timezone.now', _mock_now):
        fecha = calc.fecha_avance_montaje(detalle)
    assert fecha == _HOY_BOGOTA_REAL
    assert fecha != _HOY_UTC_FALSO
