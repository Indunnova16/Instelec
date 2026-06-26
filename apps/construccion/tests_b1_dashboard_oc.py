"""Tests B1 (#139) — cableado del avance REAL al Dashboard de Obra Civil.

Cubre los 3 tests E2E del BLUEPRINT.sub_features.B1.tests_e2e:
  - b1_curva_s_oc_ejecutado_real
  - b1_avance_etapa_oc_6etapas
  - b1_vista_torre_oc

más edge cases del dominio (proyecto sin avance → curva vacía sin error,
torre parcial → no completa, drill-down URL presente) y un test contra dato
"legacy" (oc_detalle sin avance reciente preservado).

B1 reusa el backbone S1 ``calculators_avance_real`` (no re-implementa el
cálculo) y cablea la Curva S + las 6 etapas + la vista por torre al avance real
de los ``ObraCivilTorreDetalle`` (oc_detalle, 257 filas en prod).

Nombre de archivo ``tests_b1_*.py`` por paridad con los tests B2–B5; se ejecuta
pasando la ruta a pytest (igual que tests_b3_dashboard.py).
"""
import json
from decimal import Decimal

import pytest
from django.urls import reverse

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def proyecto_oc(db):
    """ProyectoConstruccion base para colgar oc_detalle."""
    from apps.construccion.models import ProyectoConstruccion
    from apps.contratos.models import Contrato

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-B1-001',
        nombre='Contrato test B1',
        cliente='Test Cliente B1',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto B1 test',
        estado='EJECUCION',
    )


def _torre(proyecto, numero):
    from apps.construccion.models import TorreConstruccion
    return TorreConstruccion.objects.create(proyecto=proyecto, numero=numero, tipo='D6')


def _oc_detalle(proyecto, torre, pata, **flags):
    """Crea un ObraCivilTorreDetalle (pata) con los campos de etapa dados.

    Los pct de etapa (exc/sol/ace/vac/com) son 0..1; cerr_finalizado_ok es bool.
    Defaults: todo en 0 / False (pata sin avance).
    """
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle
    base = {
        'cerr_finalizado_ok': False,
        'exc_ejecutada_pct': Decimal('0'),
        'sol_ejecutado_pct': Decimal('0'),
        'ace_instalacion_pct': Decimal('0'),
        'vac_ejecutado_pct': Decimal('0'),
        'com_finalizada_pct': Decimal('0'),
    }
    base.update(flags)
    return ObraCivilTorreDetalle.objects.create(
        proyecto=proyecto, torre=torre, pata=pata, **base)


def _torre_oc_completa(proyecto, numero):
    """Torre con 4 patas, TODAS las 6 etapas completas → avance 100%."""
    torre = _torre(proyecto, numero)
    for p in ('A', 'B', 'C', 'D'):
        _oc_detalle(
            proyecto, torre, p,
            cerr_finalizado_ok=True,
            exc_ejecutada_pct=Decimal('1'),
            sol_ejecutado_pct=Decimal('1'),
            ace_instalacion_pct=Decimal('1'),
            vac_ejecutado_pct=Decimal('1'),
            com_finalizada_pct=Decimal('1'),
        )
    return torre


# ===========================================================================
# 1. b1_curva_s_oc_ejecutado_real — serie "Ejecutado" > 0% desde oc_detalle
# ===========================================================================

@pytest.mark.django_db
def test_b1_curva_s_oc_ejecutado_real(authenticated_client, proyecto_oc):
    """La Curva S de OC toma "Ejecutado" del avance real, NO del
    DashboardAvanceSemanal vacío → con 1 torre cerrada el último punto > 0%.

    #122 Fase 2: el dashboard ahora ancla el "Ejecutado" en el CONTEO de torres
    por su ``ObraCivilTorre.fecha_final`` (fecha real), no en el avance ponderado
    por pata. La serie ``serie_curva_s_real`` (por avance ponderado) sigue
    existiendo; la tarjeta del dashboard usa la serie por fechas.
    """
    from datetime import date

    from apps.construccion import calculators_avance_real as car
    from apps.construccion.models import ObraCivilTorre

    t1 = _torre_oc_completa(proyecto_oc, 'T1')
    t2 = _torre(proyecto_oc, 'T2')  # 2ª torre sin cerrar → arrastra el promedio
    # #122: la tarjeta ejecutada cuenta torres con fecha_final. T1 cerrada en
    # 2025, T2 sin fecha_final → 1 de 2 torres = 50%. El cache ObraCivilTorre de
    # T1 ya lo creó el signal de oc_detalle → update_or_create para fijar fechas.
    ObraCivilTorre.objects.update_or_create(
        torre=t1, defaults={
            'proyecto': proyecto_oc,
            'fecha_inicio': date(2025, 1, 2), 'fecha_esperada': date(2025, 1, 10),
            'fecha_final': date(2025, 1, 15),
        },
    )
    ObraCivilTorre.objects.update_or_create(
        torre=t2, defaults={
            'proyecto': proyecto_oc,
            'fecha_inicio': date(2025, 2, 1), 'fecha_esperada': date(2025, 2, 10),
            'fecha_final': None,
        },
    )

    # La serie por avance ponderado (legacy) sigue funcionando.
    serie = car.serie_curva_s_real(proyecto_oc, 'OOCC')
    assert serie['ejecutado'], 'la serie Ejecutado no debe estar vacía'
    # 1 de 2 torres al 100% → acumulado final = 50% del proyecto.
    assert serie['ejecutado'][-1] == pytest.approx(50.0, abs=0.01)

    # #122: la serie por fechas reales (la que cablea el dashboard) ancla en 2025.
    serie_fechas = car.serie_ejecutado_oc_fechas(proyecto_oc)
    assert serie_fechas['ejecutado'][-1] == pytest.approx(50.0, abs=0.01)
    assert serie_fechas['labels'][-1].startswith('2025')

    # Render del dashboard: la línea Ejecutado se cablea en datos_chart real.
    url = reverse('construccion:dashboard_obra_civil',
                  kwargs={'proyecto_id': proyecto_oc.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200, resp.content[:500]
    body = resp.content.decode()
    assert 'id="curva-s-chart"' in body
    assert 'data-charts-ready' in body
    # La tarjeta % Ejecutado refleja el real (50.0%), no 0.
    assert 'data-pct-ejecutado' in body
    assert '50.0%' in body


@pytest.mark.django_db
def test_b1_curva_s_proyecto_sin_avance_curva_vacia_sin_error(
        authenticated_client, proyecto_oc):
    """Edge: proyecto sin oc_detalle → serie Ejecutado vacía, dashboard 200
    (no 500, no división por cero)."""
    from apps.construccion import calculators_avance_real as car
    _torre(proyecto_oc, 'T1')  # torre sin detalles

    serie = car.serie_curva_s_real(proyecto_oc, 'OOCC')
    assert serie == {'labels': [], 'ejecutado': []}

    url = reverse('construccion:dashboard_obra_civil',
                  kwargs={'proyecto_id': proyecto_oc.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    body = resp.content.decode()
    # datos_chart presente y parseable aunque vacío (no rompe Chart.js init).
    assert 'id="curva-s-chart"' in body
    assert 'data-charts-ready' in body


# ===========================================================================
# 2. b1_avance_etapa_oc_6etapas — 6 etapas con Cerramiento
# ===========================================================================

@pytest.mark.django_db
def test_b1_avance_etapa_oc_6etapas(authenticated_client, proyecto_oc):
    """El avance por etapa de OC muestra las 6 etapas (incluye Cerramiento),
    en el orden del backbone, con los pesos del Excel del cliente."""
    from apps.construccion import calculators_avance_real as car

    # T1: cerramiento + excavación completos en las 4 patas; resto 0.
    t1 = _torre(proyecto_oc, 'T1')
    for p in ('A', 'B', 'C', 'D'):
        _oc_detalle(proyecto_oc, t1, p,
                    cerr_finalizado_ok=True, exc_ejecutada_pct=Decimal('1'))
    # T2: nada completo.
    t2 = _torre(proyecto_oc, 'T2')
    for p in ('A', 'B', 'C', 'D'):
        _oc_detalle(proyecto_oc, t2, p)

    etapas = car.avance_por_etapa(proyecto_oc, 'OOCC')
    assert [e['etapa'] for e in etapas] == [
        'CERRAMIENTO', 'EXCAVACION', 'SOLADO', 'ACERO', 'VACIADO', 'COMPACTACION']
    assert len(etapas) == 6, 'deben ser 6 etapas, no las 5 legacy'

    cerr = next(e for e in etapas if e['etapa'] == 'CERRAMIENTO')
    assert cerr['totales'] == 2 and cerr['completas'] == 1 and cerr['pct'] == 50.0
    exc = next(e for e in etapas if e['etapa'] == 'EXCAVACION')
    assert exc['completas'] == 1 and exc['pct'] == 50.0
    sol = next(e for e in etapas if e['etapa'] == 'SOLADO')
    assert sol['completas'] == 0 and sol['pct'] == 0.0

    # En el HTML la etapa Cerramiento aparece como texto visible (journey).
    url = reverse('construccion:dashboard_obra_civil',
                  kwargs={'proyecto_id': proyecto_oc.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    body = resp.content.decode()
    assert 'Cerramiento' in body
    assert 'data-etapas-oc6' in body
    # Las 6 etapas como filas con data-etapa.
    for codigo in ('CERRAMIENTO', 'EXCAVACION', 'SOLADO', 'ACERO', 'VACIADO', 'COMPACTACION'):
        assert f'data-etapa="{codigo}"' in body, f'etapa {codigo} faltante en HTML'


@pytest.mark.django_db
def test_b1_avance_etapa_completa_solo_si_todas_las_patas(proyecto_oc):
    """Edge dominio: una torre cuenta completa en una etapa SOLO si TODAS sus
    patas la tienen (3/4 patas con vaciado → torre NO completa)."""
    from apps.construccion import calculators_avance_real as car
    t = _torre(proyecto_oc, 'T9')
    for p, ok in (('A', '1'), ('B', '1'), ('C', '1'), ('D', '0')):
        _oc_detalle(proyecto_oc, t, p, vac_ejecutado_pct=Decimal(ok))
    etapas = {e['etapa']: e for e in car.avance_por_etapa(proyecto_oc, 'OOCC')}
    assert etapas['VACIADO']['totales'] == 1
    assert etapas['VACIADO']['completas'] == 0
    assert etapas['VACIADO']['pct'] == 0.0


# ===========================================================================
# 3. b1_vista_torre_oc — cuáles 100% / pendientes + drill-down
# ===========================================================================

@pytest.mark.django_db
def test_b1_vista_torre_oc(authenticated_client, proyecto_oc):
    """Vista por torre: clasifica 100% vs en-curso, lista etapas pendientes y
    enlaza al drill-down obra_civil_torre del punto bajo."""
    from apps.construccion import calculators_avance_real as car

    _torre_oc_completa(proyecto_oc, 'T1')  # 100%
    t2 = _torre(proyecto_oc, 'T2')         # parcial: solo cerramiento
    for p in ('A', 'B', 'C', 'D'):
        _oc_detalle(proyecto_oc, t2, p, cerr_finalizado_ok=True)

    vista = car.vista_por_torre(proyecto_oc, 'OOCC')
    by_num = {v['numero']: v for v in vista}
    assert by_num['T1']['completa'] is True
    assert by_num['T1']['pct'] == 100.0
    assert by_num['T1']['pendientes'] == []
    assert by_num['T2']['completa'] is False
    # T2 tiene cerramiento → Cerramiento NO está en pendientes; el resto sí.
    assert 'Cerramiento' not in by_num['T2']['pendientes']
    assert 'Excavación' in by_num['T2']['pendientes']

    url = reverse('construccion:dashboard_obra_civil',
                  kwargs={'proyecto_id': proyecto_oc.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    body = resp.content.decode()
    assert 'data-vista-torres-oc' in body
    assert 'data-torre-pct' in body
    # Drill-down: el href a obra_civil_torre de T1 está presente.
    t1 = next(t for t in proyecto_oc.torres.all() if t.numero == 'T1')
    drill = reverse('construccion:obra_civil_torre',
                    kwargs={'proyecto_id': proyecto_oc.id, 'torre_id': t1.id})
    assert drill in body, 'falta el enlace de drill-down a obra_civil_torre'
    # Contador de torres completas (1 de 2).
    assert 'torres al 100%' in body


@pytest.mark.django_db
def test_b1_vista_torre_proyecto_sin_avance_vacia_sin_error(
        authenticated_client, proyecto_oc):
    """Edge: proyecto sin oc_detalle → vista vacía, dashboard 200 con el aviso
    'Sin avance de obra civil'."""
    from apps.construccion import calculators_avance_real as car
    _torre(proyecto_oc, 'T1')
    vista = car.vista_por_torre(proyecto_oc, 'OOCC')
    assert vista == []

    url = reverse('construccion:dashboard_obra_civil',
                  kwargs={'proyecto_id': proyecto_oc.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    body = resp.content.decode()
    assert 'Sin avance de obra civil' in body


# ===========================================================================
# Payload bundle (calculators.dashboard_oc_real_payload) + dato legacy
# ===========================================================================

@pytest.mark.django_db
def test_b1_payload_bundle_estructura_y_carry(proyecto_oc):
    """El payload bundle del dashboard de OC trae curva_s, 6 etapas, vista y
    tarjetas, alineando las dos series sobre un eje X común (carry forward)."""
    from apps.construccion.calculators import dashboard_oc_real_payload
    _torre_oc_completa(proyecto_oc, 'T1')

    payload = dashboard_oc_real_payload(proyecto_oc)
    assert set(payload) == {'curva_s', 'avance_etapas', 'vista_torres', 'tarjetas'}
    assert len(payload['avance_etapas']) == 6
    cs = payload['curva_s']
    # Eje X común: planeado y ejecutado tienen la MISMA longitud que labels.
    assert len(cs['planeado']) == len(cs['labels'])
    assert len(cs['ejecutado']) == len(cs['labels'])
    assert payload['tarjetas']['pct_construido'] == 100.0
    # curva_s viaja como JSON al template (guard es-CO: nunca floats crudos en
    # JS inline) — debe ser JSON-serializable tal cual.
    assert json.loads(json.dumps(cs)) == cs
    # vista_torres trae torre_id UUID (se serializa por-campo / se usa en reverse
    # en la vista); el resto de cada fila es JSON-serializable.
    for fila in payload['vista_torres']:
        plano = {k: v for k, v in fila.items() if k != 'torre_id'}
        assert json.loads(json.dumps(plano)) == plano


@pytest.mark.django_db
def test_b1_dato_legacy_oc_detalle_sin_avance_preservado(proyecto_oc):
    """Test contra dato 'legacy': un oc_detalle viejo sin etapas (todo 0/False,
    como las filas pre-#139) NO rompe el cálculo y aporta 0% — preservado, no
    inventado."""
    from apps.construccion import calculators_avance_real as car
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle

    t = _torre(proyecto_oc, 'LEG-1')
    # Registro creado SOLO con los NOT NULL mínimos (como el legacy en prod).
    legacy = ObraCivilTorreDetalle.objects.create(
        proyecto=proyecto_oc, torre=t, pata='A')
    legacy.refresh_from_db()
    # avance_ponderado del legacy = 0 (sin etapas), nunca None.
    assert float(legacy.avance_ponderado) == 0.0

    serie = car.serie_curva_s_real(proyecto_oc, 'OOCC')
    # Con 1 torre al 0% → curva con punto(s) pero acumulado 0.0 (no lanza).
    assert all(v == 0.0 for v in serie['ejecutado'])
    vista = car.vista_por_torre(proyecto_oc, 'OOCC')
    assert vista[0]['pct'] == 0.0
    assert vista[0]['completa'] is False
