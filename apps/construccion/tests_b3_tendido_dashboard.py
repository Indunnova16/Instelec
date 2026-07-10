"""Tests B3 — Dashboard de Tendido (Conductor + Fibra OPGW) (#139).

Cubre los tests_e2e del BLUEPRINT.sub_features.B3:
  - b3_dashboard_tendido_conductor: la gráfica/datos de Conductor reflejan el
    avance real por etapa (6 etapas) + Curva S ejecutado > 0.
  - b3_dashboard_tendido_fibra:     la gráfica/datos de Fibra OPGW reflejan el
    avance real por etapa (5 etapas).

Edge cases del dominio (no genéricos):
  - proyecto SIN registros de tendido → HTTP 200, listas vacías, sin 500.
  - torre con conductor 100% pero fibra 0% → conductor completa, fibra pendiente
    (las dos secciones son SUMPRODUCT independientes; no se contaminan).
  - dato "legacy": TendidoTorre creado solo con flags de conductor (como en prod,
    65 filas con tendido_conductor=True) → el dashboard lo computa sin tocar el
    modelo y la vista por torre lo lista con sus pendientes de fibra.

La URL del dashboard la cablea F4 en urls.py (include de urls_dashboards_b3_tendido),
así que aquí ejercemos la vista vía RequestFactory + usuario admin (no depende del
wiring pendiente) y el endpoint de datos por el mismo medio.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.construccion import calculators_avance_real as car
from apps.construccion.views_dashboards_b3_tendido import (
    DashboardTendidoDataView,
    DashboardTendidoView,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def admin(db):
    return User.objects.create_user(
        email='admin-b3-tendido@test.com',
        password='x',
        first_name='Admin',
        last_name='B3',
        rol='admin',
        is_staff=True,
        is_superuser=True,
    )


@pytest.fixture
def proyecto(db):
    from apps.contratos.models import Contrato
    from apps.construccion.models import ProyectoConstruccion

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-B3-TEND-001',
        nombre='Contrato test B3 Tendido',
        cliente='Cliente Test',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto B3 Tendido',
        estado='EJECUCION',
    )


def _torre(proyecto, numero):
    from apps.construccion.models import TorreConstruccion
    return TorreConstruccion.objects.create(proyecto=proyecto, numero=numero)


def _tendido(proyecto, torre, **flags):
    """Crea un TendidoTorre con los flags dados (resto en False por default)."""
    from apps.construccion.models import TendidoTorre
    return TendidoTorre.objects.create(proyecto=proyecto, torre=torre, **flags)


def _fase_torre(proyecto, torre, **fechas):
    """Crea un FaseTorre (A3, #166) con las fechas MANUALES dadas por torre.

    ``TendidoTorre.updated_at``/``created_at`` quedan en la fecha real de
    creación del registro (HOY, 2026 por ``auto_now``/``auto_now_add`` — mismo
    patrón que ``tests_issue_122_curvas.py``): las fixtures pasan fechas 2025
    explícitas en ``FaseTorre`` para probar que la cascada A3 las prefiere.
    """
    from apps.construccion.models import FaseTorre
    return FaseTorre.objects.create(proyecto=proyecto, torre=torre, **fechas)


def _ctx(view_cls, proyecto, admin, **get):
    """Render del contexto de una CBV de dashboard vía RequestFactory."""
    rf = RequestFactory()
    req = rf.get('/', data=get)
    req.user = admin
    view = view_cls()
    view.setup(req, proyecto_id=proyecto.id)
    return view.get_context_data()


def _datos(proyecto, admin):
    rf = RequestFactory()
    req = rf.get('/')
    req.user = admin
    resp = DashboardTendidoDataView.as_view()(req, proyecto_id=proyecto.id)
    return json.loads(resp.content)


# ---------------------------------------------------------------------------
# E2E del BLUEPRINT — Conductor
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_b3_dashboard_tendido_conductor(proyecto, admin):
    """Happy: el dashboard expone las 6 etapas de Conductor con su % real y la
    Curva S ejecutado refleja avance > 0."""
    t1 = _torre(proyecto, '1')
    t2 = _torre(proyecto, '2')
    # Torre 1: conductor 100% (las 6 etapas). Torre 2: solo las 2 primeras.
    _tendido(
        proyecto, t1,
        riega_manila_conductor=True, riega_guaya_conductor=True,
        tendido_conductor=True, grapado_amarre_conductor=True,
        accesorios_puentes=True, balizas_desviadores=True,
    )
    _tendido(
        proyecto, t2,
        riega_manila_conductor=True, riega_guaya_conductor=True,
    )

    ctx = _ctx(DashboardTendidoView, proyecto, admin)

    # 6 etapas de conductor, en orden.
    conductor = ctx['avance_conductor']
    assert [e['etapa'] for e in conductor] == [
        'RIEGA_MANILA', 'RIEGA_GUAYA', 'TENDIDO_CONDUCTOR',
        'GRAPADO', 'ACCESORIOS', 'BALIZAS',
    ]
    by = {e['etapa']: e for e in conductor}
    # Riega manila: ambas torres completas → 100%.
    assert by['RIEGA_MANILA']['pct'] == 100.0
    assert by['RIEGA_MANILA']['completas'] == 2
    # Balizas: solo torre 1 → 50%.
    assert by['BALIZAS']['pct'] == 50.0
    assert by['BALIZAS']['completas'] == 1

    # Curva S real "Ejecutado" > 0 (no cuelga del semanal vacío).
    curva = ctx['curva_real_json']
    assert curva['ejecutado']['ejecutado']
    assert max(curva['ejecutado']['ejecutado']) > 0

    # % conductor global de las tarjetas es > 0.
    assert ctx['pct_conductor'] > 0
    # La gráfica de etapas genérica del parcial base queda apagada (B3 usa 2 propias).
    assert ctx['avance_etapas'] == []


@pytest.mark.django_db
def test_b3_dashboard_tendido_conductor_template_render(proyecto, admin):
    """El template renderiza el canvas #tendido-conductor-chart y [data-fase]."""
    from django.template.loader import render_to_string

    t1 = _torre(proyecto, '1')
    _tendido(proyecto, t1, riega_manila_conductor=True, tendido_conductor=True)
    ctx = _ctx(DashboardTendidoView, proyecto, admin)
    html = render_to_string('construccion/dashboard_tendido.html', ctx)

    assert 'id="tendido-conductor-chart"' in html
    assert 'id="tendido-fibra-chart"' in html
    assert 'data-fase="TENDIDO"' in html
    # json_script genera el id del dataset (no JSON crudo en x-data / inline).
    assert 'id="tendido-etapas-data"' in html
    # Guard es-CO: localize off presente (lo aplica el bloque).
    assert 'tendido-etapas-data' in html


# ---------------------------------------------------------------------------
# E2E del BLUEPRINT — Fibra OPGW
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_b3_dashboard_tendido_fibra(proyecto, admin):
    """Happy: las 5 etapas de Fibra OPGW con su % real, independientes del
    conductor."""
    t1 = _torre(proyecto, '1')
    t2 = _torre(proyecto, '2')
    # Torre 1: fibra 100%. Torre 2: solo tendido OPGW.
    _tendido(
        proyecto, t1,
        riega_manila_fibra=True, riega_guaya_opgw=True, tendido_opgw=True,
        grapado_amarre_fibra=True, empalmes_opgw=True,
    )
    _tendido(proyecto, t2, tendido_opgw=True)

    ctx = _ctx(DashboardTendidoView, proyecto, admin)

    fibra = ctx['avance_fibra']
    assert [e['etapa'] for e in fibra] == [
        'RIEGA_MANILA_FIBRA', 'RIEGA_GUAYA_OPGW', 'TENDIDO_OPGW',
        'GRAPADO_FIBRA', 'EMPALMES_OPGW',
    ]
    by = {e['etapa']: e for e in fibra}
    # Tendido OPGW: ambas → 100%.
    assert by['TENDIDO_OPGW']['pct'] == 100.0
    # Empalmes: solo torre 1 → 50%.
    assert by['EMPALMES_OPGW']['pct'] == 50.0
    assert ctx['pct_fibra'] > 0


@pytest.mark.django_db
def test_b3_secciones_independientes_conductor_lleno_fibra_vacia(proyecto, admin):
    """Edge: una torre con conductor 100% y fibra 0% — las secciones NO se
    contaminan (SUMPRODUCT independiente). En la vista por torre la fibra queda
    como pendiente."""
    t1 = _torre(proyecto, '1')
    _tendido(
        proyecto, t1,
        riega_manila_conductor=True, riega_guaya_conductor=True,
        tendido_conductor=True, grapado_amarre_conductor=True,
        accesorios_puentes=True, balizas_desviadores=True,
        # fibra toda False
    )
    ctx = _ctx(DashboardTendidoView, proyecto, admin)

    # Conductor 100%, fibra 0%.
    assert ctx['pct_conductor'] == 100.0
    assert ctx['pct_fibra'] == 0.0

    # Vista por torre: pct = promedio(100, 0) = 50, NO completa, pendientes de fibra.
    torres = ctx['vista_torres']
    assert len(torres) == 1
    fila = torres[0]
    assert fila['pct'] == 50.0
    assert fila['completa'] is False
    # Las pendientes contienen las etiquetas de fibra, NO las de conductor.
    assert 'Empalmes OPGW' in fila['pendientes']
    assert 'Tendido conductor' not in fila['pendientes']


# ---------------------------------------------------------------------------
# Edge — proyecto sin tendido (robustez, nunca 500)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_b3_dashboard_sin_tendido_no_crashea(proyecto, admin):
    """Edge: proyecto con torres pero sin registros de tendido → listas vacías,
    pct 0, sin excepción."""
    _torre(proyecto, '1')
    ctx = _ctx(DashboardTendidoView, proyecto, admin)

    assert ctx['pct_conductor'] == 0.0
    assert ctx['pct_fibra'] == 0.0
    assert ctx['vista_torres'] == []
    # Las etapas existen con pct=0 (estructura presente, datos vacíos).
    assert all(e['pct'] == 0.0 for e in ctx['avance_conductor'])
    assert all(e['pct'] == 0.0 for e in ctx['avance_fibra'])


@pytest.mark.django_db
def test_b3_dashboard_proyecto_sin_torres_no_crashea(proyecto, admin):
    """Edge: proyecto sin torres → pct 0, sin división por cero / 500."""
    ctx = _ctx(DashboardTendidoView, proyecto, admin)
    assert ctx['pct_conductor'] == 0.0
    assert ctx['pct_fibra'] == 0.0


# ---------------------------------------------------------------------------
# Endpoint de datos JSON
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_b3_datos_endpoint_estructura(proyecto, admin):
    """El endpoint de datos devuelve curva_s + conductor + fibra + vista_torres."""
    t1 = _torre(proyecto, '1')
    _tendido(proyecto, t1, tendido_conductor=True, tendido_opgw=True)

    data = _datos(proyecto, admin)
    assert 'curva_s' in data
    assert 'ejecutado' in data['curva_s']
    assert 'planeado' in data['curva_s']
    assert len(data['avance_conductor']) == 6
    assert len(data['avance_fibra']) == 5
    assert isinstance(data['vista_torres'], list)


# ---------------------------------------------------------------------------
# Dato legacy — TendidoTorre "estilo prod" (solo flags de conductor)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_b3_dato_legacy_conductor_solo(proyecto, admin):
    """En prod hay 65 TendidoTorre con tendido_conductor=True (y fibra sin tocar).

    Verifica que el dashboard computa ese dato legacy SIN modificar el modelo:
    la etapa de conductor 'Tendido conductor' aparece completa y la torre se
    lista en la vista por torre con pendientes de fibra.
    """
    t1 = _torre(proyecto, '1')
    legacy = _tendido(
        proyecto, t1,
        riega_manila_conductor=True, riega_guaya_conductor=True,
        tendido_conductor=True,
    )
    # No tocamos campos nuevos: la fibra queda en su default False (legacy).
    legacy.refresh_from_db()
    assert legacy.tendido_conductor is True
    assert legacy.tendido_opgw is False

    ctx = _ctx(DashboardTendidoView, proyecto, admin)
    by_c = {e['etapa']: e for e in ctx['avance_conductor']}
    assert by_c['TENDIDO_CONDUCTOR']['completas'] == 1
    # La torre legacy está en la vista por torre con pendientes de fibra.
    assert len(ctx['vista_torres']) == 1
    assert any('OPGW' in p or 'fibra' in p.lower()
               for p in ctx['vista_torres'][0]['pendientes'])


# ---------------------------------------------------------------------------
# A1 (#166 Hilo A) — % Ejecutado total nunca seteado
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_a1_pct_construido_total_mayor_a_cero_con_datos_reales(proyecto, admin):
    """Root cause A1: antes del fix el template leía 'pct_construido_total' del
    contexto legacy (DashboardAvanceSemanal, 0 filas TENDIDO en prod) -> 0%
    pese a Conductor/Fibra=100%. Con conductor+fibra completos al 100%, la
    tarjeta '% Ejecutado total' debe reflejar avance real > 0 (y = 100 cuando
    ambas secciones están completas)."""
    t1 = _torre(proyecto, '1')
    _tendido(
        proyecto, t1,
        riega_manila_conductor=True, riega_guaya_conductor=True,
        tendido_conductor=True, grapado_amarre_conductor=True,
        accesorios_puentes=True, balizas_desviadores=True,
        riega_manila_fibra=True, riega_guaya_opgw=True, tendido_opgw=True,
        grapado_amarre_fibra=True, empalmes_opgw=True,
    )

    ctx = _ctx(DashboardTendidoView, proyecto, admin)

    assert ctx['pct_conductor'] == 100.0
    assert ctx['pct_fibra'] == 100.0
    assert ctx['pct_construido_total'] > 0
    assert ctx['pct_construido_total'] == 100.0


@pytest.mark.django_db
def test_a1_pct_construido_total_promedia_conductor_y_fibra_parcial(proyecto, admin):
    """Avance parcial: pct_construido_total = promedio(pct_conductor, pct_fibra),
    NO 0% ni un valor inventado."""
    t1 = _torre(proyecto, '1')
    # Conductor 100% (6/6), fibra 0% (0/5) -> promedio = 50.
    _tendido(
        proyecto, t1,
        riega_manila_conductor=True, riega_guaya_conductor=True,
        tendido_conductor=True, grapado_amarre_conductor=True,
        accesorios_puentes=True, balizas_desviadores=True,
    )

    ctx = _ctx(DashboardTendidoView, proyecto, admin)
    assert ctx['pct_construido_total'] == round((ctx['pct_conductor'] + ctx['pct_fibra']) / 2, 2)
    assert ctx['pct_construido_total'] == 50.0


# ---------------------------------------------------------------------------
# A2 (#166 Hilo A) — card genérico "Avance por etapa" fantasma en Tendido
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_a2_heading_generico_avance_por_etapa_ausente_en_tendido(proyecto, admin):
    """Root cause A2: el parcial base pintaba SIEMPRE el card genérico
    'Avance por etapa — Tendido' aunque B3 le pase avance_etapas=[] a propósito
    (usa sus 2 charts propios de Conductor/Fibra) -> panel vacío fantasma.
    Envuelto en {% if avance_etapas %}, el heading genérico NO debe aparecer
    en el HTML renderizado de Tendido."""
    from django.template.loader import render_to_string

    t1 = _torre(proyecto, '1')
    _tendido(proyecto, t1, riega_manila_conductor=True, tendido_conductor=True)
    ctx = _ctx(DashboardTendidoView, proyecto, admin)
    assert ctx['avance_etapas'] == []

    html = render_to_string('construccion/dashboard_tendido.html', ctx)

    assert 'Avance por etapa — Tendido' not in html
    # Los 2 charts propios de B3 SÍ siguen presentes (no se rompió nada).
    assert 'Avance por etapa — Conductor' in html
    assert 'Avance por etapa — Fibra OPGW' in html


# ---------------------------------------------------------------------------
# A3 (#166 Hilo A) — Curva S anclada en FaseTorre (fechas manuales), no en
# updated_at/created_at de TendidoTorre (fecha de guardado del registro)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_a3_fecha_avance_tendido_usa_fasetorre_no_updated_at(proyecto, admin):
    """Root cause A3 (confirmado en BD prod, proyecto QA#49): FaseTorre tiene
    fechas reales 2025 pobladas para torres cuyo TendidoTorre.updated_at cae en
    2026 (fecha de GUARDADO, por crearse/actualizarse hoy). La Curva S debe
    anclarse en las fechas 2025 de FaseTorre, NO en 2026."""
    t1 = _torre(proyecto, '1')
    _fase_torre(
        proyecto, t1,
        fecha_riega_manila=date(2025, 7, 5),
        tendido_conductor_a_fecha=date(2025, 8, 10),
        tendido_opgw_der_fecha=date(2025, 10, 15),
    )
    tendido = _tendido(
        proyecto, t1,
        riega_manila_conductor=True, riega_guaya_conductor=True,
        tendido_conductor=True, grapado_amarre_conductor=True,
        accesorios_puentes=True, balizas_desviadores=True,
        riega_manila_fibra=True, riega_guaya_opgw=True, tendido_opgw=True,
        grapado_amarre_fibra=True, empalmes_opgw=True,
    )
    # updated_at/created_at quedan HOY (2026 en este entorno) por auto_now(_add).
    assert tendido.updated_at.year >= 2026

    fecha = car.fecha_avance_tendido(tendido)
    assert fecha == date(2025, 10, 15)  # MAX de las fechas pobladas de FaseTorre
    assert fecha.year == 2025

    # La Curva S real de la fase TENDIDO también debe usar 2025, no 2026.
    curva = car.serie_curva_s_real(proyecto, car.FASE_TENDIDO)
    anios = {lab[:4] for lab in curva['labels']}
    assert anios == {'2025'}
    assert '2026' not in anios


@pytest.mark.django_db
def test_a3_fecha_avance_tendido_sin_fasetorre_cae_a_cascada_legacy(proyecto, admin):
    """Si la torre NO tiene FaseTorre (OneToOne reverse inexistente), la
    cascada cae a updated_at -> created_at (comportamiento legacy preservado,
    NUNCA 500 / AttributeError)."""
    t1 = _torre(proyecto, '1')
    tendido = _tendido(proyecto, t1, tendido_conductor=True)

    fecha = car.fecha_avance_tendido(tendido)
    assert fecha == tendido.updated_at.date()


@pytest.mark.django_db
def test_a3_guard_fecha_futura_no_contamina_curva_s(proyecto, admin):
    """Guard anti-typo (hallazgo BD prod: torre E58 con tendido_opgw_der_fecha=
    2028-09-19, único dato futuro del proyecto). Una fecha de FaseTorre > hoy
    se EXCLUYE; si quedan otras fechas válidas pobladas se usa el MAX de esas,
    y solo si TODAS son futuras cae a la cascada legacy."""
    # +3 días (no +1): margen de sobra para que la fecha "typo" nunca coincida
    # por casualidad con la fecha derivada de auto_now/auto_now_add (que
    # persiste en UTC y puede diferir del "hoy" local por el desfase de huso
    # horario — a lo sumo 1 día de skew).
    fecha_futura_typo = date.today() + timedelta(days=3)

    # Torre 1: mezcla de fecha futura (typo) + fechas válidas 2025 -> usa el
    # MAX de las válidas, ignora la futura.
    t1 = _torre(proyecto, '1')
    _fase_torre(
        proyecto, t1,
        fecha_riega_manila=date(2025, 9, 1),
        tendido_opgw_der_fecha=fecha_futura_typo,  # typo simulado (nunca se debe usar)
    )
    tendido1 = _tendido(proyecto, t1, tendido_conductor=True)
    fecha1 = car.fecha_avance_tendido(tendido1)
    assert fecha1 == date(2025, 9, 1)
    assert fecha1 < date.today()

    # Torre 2: TODAS las fechas de FaseTorre son futuras -> cae a la cascada
    # legacy (updated_at), nunca propaga un punto futuro a la Curva S.
    t2 = _torre(proyecto, '2')
    _fase_torre(proyecto, t2, tendido_opgw_der_fecha=fecha_futura_typo)
    tendido2 = _tendido(proyecto, t2, tendido_conductor=True)
    fecha2 = car.fecha_avance_tendido(tendido2)
    # El invariante que importa: NUNCA propaga la fecha futura del typo. El
    # valor exacto de la cascada (updated_at/created_at) queda a criterio de
    # BaseModel (auto_now/auto_now_add en UTC) — no se fija aquí para no
    # acoplar el test a la conversión de zona horaria local vs. UTC.
    assert fecha2 != fecha_futura_typo


# ---------------------------------------------------------------------------
# A3 — contra dato legacy real (documentado; ver también F2 en BD prod)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_a3_dato_legacy_conductor_solo_usa_fasetorre_si_existe(proyecto, admin):
    """Réplica del patrón legacy de prod (65 filas con solo flags de conductor
    en TendidoTorre) + FaseTorre con fecha manual real poblada (como las
    torres E1-E22 del proyecto QA#49, confirmado por F2 vía SELECT directo a
    BD prod — no reproducible 1:1 en este test unitario, documentado aquí como
    la validación complementaria: BD prod SELECT ``construccion_fases_torres``
    vs ``construccion_tendido_torre.updated_at`` para las torres E1-E22, ver
    ``F2_OUTPUT`` de la corrida de #166). Este test cubre el mismo camino de
    código con datos locales: si FaseTorre tiene AL MENOS una fecha poblada,
    se prefiere sobre la cascada updated_at/created_at aunque el TendidoTorre
    sea "legacy" (solo flags de conductor, fibra sin tocar)."""
    t1 = _torre(proyecto, '1')
    _fase_torre(proyecto, t1, tendido_conductor_a_fecha=date(2025, 6, 2))
    legacy = _tendido(
        proyecto, t1,
        riega_manila_conductor=True, riega_guaya_conductor=True,
        tendido_conductor=True,
    )
    legacy.refresh_from_db()
    assert legacy.tendido_opgw is False  # fibra sin tocar, estilo prod

    fecha = car.fecha_avance_tendido(legacy)
    assert fecha == date(2025, 6, 2)


# ---------------------------------------------------------------------------
# A4 (#166 Hilo A) — copy de la columna Pendientes cuando la lista viene vacía
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_a4_pendientes_vacio_muestra_no_hay_pendientes(proyecto, admin):
    """Root cause A4: una torre 100% completa mostraba '—' en la columna
    Pendientes; debe mostrar 'No hay pendientes'."""
    from django.template.loader import render_to_string

    t1 = _torre(proyecto, '1')
    _tendido(
        proyecto, t1,
        riega_manila_conductor=True, riega_guaya_conductor=True,
        tendido_conductor=True, grapado_amarre_conductor=True,
        accesorios_puentes=True, balizas_desviadores=True,
        riega_manila_fibra=True, riega_guaya_opgw=True, tendido_opgw=True,
        grapado_amarre_fibra=True, empalmes_opgw=True,
    )
    ctx = _ctx(DashboardTendidoView, proyecto, admin)
    assert ctx['vista_torres'][0]['completa'] is True
    assert ctx['vista_torres'][0]['pendientes'] == []

    html = render_to_string('construccion/dashboard_tendido.html', ctx)
    assert 'No hay pendientes' in html
    assert '>—<' not in html
