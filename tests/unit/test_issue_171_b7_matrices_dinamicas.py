"""Instelec#171 (Sprint final, GRUPO A) — B7 (epic): matrices dinámicas —
Obra Civil/Montaje/Tendido renderizan columnas CUSTOM activas (además de
las columnas de sistema, sin cambio de comportamiento en esas). Integra
B3+B4 (avance_ponderado/avance_conductor/avance_fibra ya leen
ColumnaConfigurable), B5 (ColumnaConfigurableValor EAV) y B6 (UI de
administración que crea las columnas custom).

Cubre:
1. `ColumnaValorUpdateView` (endpoint genérico) — persiste valor decimal y
   boolean, rechaza columnas de sistema, valida rango, devuelve el avance
   recalculado de la torre.
2. Las 3 vistas de matriz (`ObraCivilMatrizView`/`MontajeMatrizView`/
   `TendidoMatrizView`) exponen `columnas_custom_activas` en el contexto,
   en el orden correcto (campo `orden`), y NO incluyen columnas
   desactivadas.
3. Integración end-to-end: crear columna custom (B6) → escribir su valor
   por torre (B7, este endpoint) → el avance recalculado (B3/B4) refleja
   el nuevo valor.

Convención de colección: `tests/unit/` (`pyproject.toml` → `testpaths =
["tests"]`).
"""
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.construccion.models import (
    ColumnaConfigurable,
    ColumnaConfigurableValor,
    MontajeEstructuraTorre,
    ObraCivilTorre,
    ProyectoConstruccion,
    TendidoTorre,
    TorreConstruccion,
)
from apps.contratos.models import Contrato


@pytest.fixture
def proyecto(db):
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-171-B7-001',
        nombre='Proyecto test #171 B7 — matrices dinámicas',
        cliente='Test',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato, nombre='Proyecto B7', estado='EJECUCION',
    )


@pytest.fixture
def torre(proyecto):
    return TorreConstruccion.objects.create(proyecto=proyecto, numero='T-B7-1')


@pytest.fixture
def columna_custom_decimal_oc(proyecto):
    return ColumnaConfigurable.objects.create(
        proyecto=proyecto, capitulo=ColumnaConfigurable.CAPITULO_OBRA_CIVIL,
        clave='pintura_extra', etiqueta='Pintura extra', orden=99,
        peso_pct=10, tipo_valor=ColumnaConfigurable.TIPO_DECIMAL,
        es_sistema=False, activa=True,
    )


@pytest.fixture
def columna_custom_boolean_tendido(proyecto):
    return ColumnaConfigurable.objects.create(
        proyecto=proyecto, capitulo=ColumnaConfigurable.CAPITULO_TENDIDO_CONDUCTOR,
        clave='inspeccion_extra', etiqueta='Inspección extra', orden=99,
        peso_pct=5, tipo_valor=ColumnaConfigurable.TIPO_BOOLEAN,
        es_sistema=False, activa=True,
    )


# ==============================================================================
# 1) ColumnaValorUpdateView — persistencia decimal y boolean
# ==============================================================================

@pytest.mark.django_db
def test_columna_valor_update_decimal_persiste(
    authenticated_client, proyecto, torre, columna_custom_decimal_oc,
):
    ObraCivilTorre.objects.create(proyecto=proyecto, torre=torre)
    url = reverse('construccion:columna_valor_update', kwargs={
        'proyecto_id': proyecto.id, 'columna_id': columna_custom_decimal_oc.id, 'torre_id': torre.id,
    })
    resp = authenticated_client.post(url, {'valor': '0.5'})
    assert resp.status_code == 200, resp.content[:300]
    data = resp.json()
    assert data['ok'] is True
    assert 'avance_ponderado_pct' in data

    fila = ColumnaConfigurableValor.objects.get(columna=columna_custom_decimal_oc, torre=torre)
    assert fila.valor_decimal == Decimal('0.5')


@pytest.mark.django_db
def test_columna_valor_update_boolean_persiste(
    authenticated_client, proyecto, torre, columna_custom_boolean_tendido,
):
    TendidoTorre.objects.create(proyecto=proyecto, torre=torre)
    url = reverse('construccion:columna_valor_update', kwargs={
        'proyecto_id': proyecto.id, 'columna_id': columna_custom_boolean_tendido.id, 'torre_id': torre.id,
    })
    resp = authenticated_client.post(url, {'valor': '1'})
    assert resp.status_code == 200, resp.content[:300]
    data = resp.json()
    assert data['ok'] is True
    assert 'avance_conductor_pct' in data

    fila = ColumnaConfigurableValor.objects.get(columna=columna_custom_boolean_tendido, torre=torre)
    assert fila.valor_boolean is True


@pytest.mark.django_db
def test_columna_valor_update_rechaza_columna_de_sistema(authenticated_client, proyecto, torre):
    columna_sistema = ColumnaConfigurable.objects.get(
        proyecto=proyecto, capitulo=ColumnaConfigurable.CAPITULO_OBRA_CIVIL, clave='cerramiento',
    )
    url = reverse('construccion:columna_valor_update', kwargs={
        'proyecto_id': proyecto.id, 'columna_id': columna_sistema.id, 'torre_id': torre.id,
    })
    resp = authenticated_client.post(url, {'valor': '0.5'})
    assert resp.status_code == 400
    assert 'sistema' in resp.json()['error'].lower()


@pytest.mark.django_db
def test_columna_valor_update_rechaza_decimal_fuera_de_rango(
    authenticated_client, proyecto, torre, columna_custom_decimal_oc,
):
    url = reverse('construccion:columna_valor_update', kwargs={
        'proyecto_id': proyecto.id, 'columna_id': columna_custom_decimal_oc.id, 'torre_id': torre.id,
    })
    resp = authenticated_client.post(url, {'valor': '1.5'})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_columna_valor_update_rechaza_valor_no_numerico(
    authenticated_client, proyecto, torre, columna_custom_decimal_oc,
):
    url = reverse('construccion:columna_valor_update', kwargs={
        'proyecto_id': proyecto.id, 'columna_id': columna_custom_decimal_oc.id, 'torre_id': torre.id,
    })
    resp = authenticated_client.post(url, {'valor': 'no-es-numero'})
    assert resp.status_code == 400


# ==============================================================================
# 2) Contexto de las 3 vistas de matriz — columnas_custom_activas
# ==============================================================================

@pytest.mark.django_db
def test_obra_civil_matriz_expone_columnas_custom_activas_ordenadas(authenticated_client, proyecto):
    c1 = ColumnaConfigurable.objects.create(
        proyecto=proyecto, capitulo=ColumnaConfigurable.CAPITULO_OBRA_CIVIL,
        clave='custom_b', etiqueta='Custom B', orden=1,
        peso_pct=5, tipo_valor=ColumnaConfigurable.TIPO_DECIMAL, es_sistema=False, activa=True,
    )
    c0 = ColumnaConfigurable.objects.create(
        proyecto=proyecto, capitulo=ColumnaConfigurable.CAPITULO_OBRA_CIVIL,
        clave='custom_a', etiqueta='Custom A', orden=0,
        peso_pct=5, tipo_valor=ColumnaConfigurable.TIPO_DECIMAL, es_sistema=False, activa=True,
    )
    c_inactiva = ColumnaConfigurable.objects.create(
        proyecto=proyecto, capitulo=ColumnaConfigurable.CAPITULO_OBRA_CIVIL,
        clave='custom_inactiva', etiqueta='Custom Inactiva', orden=2,
        peso_pct=5, tipo_valor=ColumnaConfigurable.TIPO_DECIMAL, es_sistema=False, activa=False,
    )

    url = reverse('construccion:obra_civil_lista', kwargs={'proyecto_id': proyecto.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    columnas_ctx = resp.context['columnas_custom_activas']
    assert [c.id for c in columnas_ctx] == [c0.id, c1.id]  # ordenadas por `orden`, inactiva excluida
    assert c_inactiva.id not in [c.id for c in columnas_ctx]


@pytest.mark.django_db
def test_montaje_matriz_expone_columnas_custom_activas(authenticated_client, proyecto):
    columna = ColumnaConfigurable.objects.create(
        proyecto=proyecto, capitulo=ColumnaConfigurable.CAPITULO_MONTAJE,
        clave='custom_montaje', etiqueta='Custom Montaje', orden=99,
        peso_pct=5, tipo_valor=ColumnaConfigurable.TIPO_DECIMAL, es_sistema=False, activa=True,
    )
    url = reverse('construccion:montaje_lista', kwargs={'proyecto_id': proyecto.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    assert [c.id for c in resp.context['columnas_custom_activas']] == [columna.id]


@pytest.mark.django_db
def test_tendido_matriz_expone_columnas_custom_conductor_y_fibra_por_separado(authenticated_client, proyecto):
    columna_conductor = ColumnaConfigurable.objects.create(
        proyecto=proyecto, capitulo=ColumnaConfigurable.CAPITULO_TENDIDO_CONDUCTOR,
        clave='custom_conductor', etiqueta='Custom Conductor', orden=99,
        peso_pct=5, tipo_valor=ColumnaConfigurable.TIPO_BOOLEAN, es_sistema=False, activa=True,
    )
    columna_fibra = ColumnaConfigurable.objects.create(
        proyecto=proyecto, capitulo=ColumnaConfigurable.CAPITULO_TENDIDO_FIBRA,
        clave='custom_fibra', etiqueta='Custom Fibra', orden=99,
        peso_pct=5, tipo_valor=ColumnaConfigurable.TIPO_BOOLEAN, es_sistema=False, activa=True,
    )
    url = reverse('construccion:tendido_lista', kwargs={'proyecto_id': proyecto.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    assert [c.id for c in resp.context['columnas_custom_conductor']] == [columna_conductor.id]
    assert [c.id for c in resp.context['columnas_custom_fibra']] == [columna_fibra.id]
    # colspan del <th> agrupador crece con las columnas custom (6+1=7, 5+1=6)
    assert resp.context['colspan_conductor'] == 7
    assert resp.context['colspan_fibra'] == 6


@pytest.mark.django_db
def test_obra_civil_matriz_renderiza_data_testid_columna_custom(authenticated_client, proyecto):
    """View test: la matriz renderiza tanto las columnas de SISTEMA (thead
    ya existente, sin cambio) como la columna CUSTOM nueva (data-testid),
    en el orden correcto."""
    torre_local = TorreConstruccion.objects.create(proyecto=proyecto, numero='T-B7-RENDER')
    ObraCivilTorre.objects.create(proyecto=proyecto, torre=torre_local)
    columna = ColumnaConfigurable.objects.create(
        proyecto=proyecto, capitulo=ColumnaConfigurable.CAPITULO_OBRA_CIVIL,
        clave='render_test', etiqueta='Render Test', orden=99,
        peso_pct=5, tipo_valor=ColumnaConfigurable.TIPO_DECIMAL, es_sistema=False, activa=True,
    )
    url = reverse('construccion:obra_civil_lista', kwargs={'proyecto_id': proyecto.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    html = resp.content.decode()
    assert 'data-testid="columna-custom-render_test"' in html
    assert f'data-testid="valor-columna-{columna.id}-torre-{torre_local.id}"' in html
    assert 'Render Test' in html
    # Columnas de sistema siguen presentes sin cambio (Cerramiento, etc.)
    assert 'Cerramiento' in html


@pytest.mark.django_db
def test_montaje_matriz_renderiza_data_testid_columna_custom(authenticated_client, proyecto):
    torre_local = TorreConstruccion.objects.create(proyecto=proyecto, numero='T-B7-RENDER-M')
    MontajeEstructuraTorre.objects.create(proyecto=proyecto, torre=torre_local)
    columna = ColumnaConfigurable.objects.create(
        proyecto=proyecto, capitulo=ColumnaConfigurable.CAPITULO_MONTAJE,
        clave='render_test_m', etiqueta='Render Test M', orden=99,
        peso_pct=5, tipo_valor=ColumnaConfigurable.TIPO_DECIMAL, es_sistema=False, activa=True,
    )
    url = reverse('construccion:montaje_lista', kwargs={'proyecto_id': proyecto.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    html = resp.content.decode()
    assert 'data-testid="columna-custom-render_test_m"' in html
    assert f'data-testid="valor-columna-{columna.id}-torre-{torre_local.id}"' in html


@pytest.mark.django_db
def test_tendido_matriz_renderiza_data_testid_columna_custom_conductor(authenticated_client, proyecto):
    torre_local = TorreConstruccion.objects.create(proyecto=proyecto, numero='T-B7-RENDER-T')
    TendidoTorre.objects.create(proyecto=proyecto, torre=torre_local)
    columna = ColumnaConfigurable.objects.create(
        proyecto=proyecto, capitulo=ColumnaConfigurable.CAPITULO_TENDIDO_CONDUCTOR,
        clave='render_test_t', etiqueta='Render Test T', orden=99,
        peso_pct=5, tipo_valor=ColumnaConfigurable.TIPO_BOOLEAN, es_sistema=False, activa=True,
    )
    url = reverse('construccion:tendido_lista', kwargs={'proyecto_id': proyecto.id})
    resp = authenticated_client.get(url)
    assert resp.status_code == 200
    html = resp.content.decode()
    assert 'data-testid="columna-custom-render_test_t"' in html
    assert f'data-testid="valor-columna-{columna.id}-torre-{torre_local.id}"' in html


# ==============================================================================
# 3) Integración end-to-end — B6 (crear) → B7 (escribir valor) → B3/B4 (avance)
# ==============================================================================

@pytest.mark.django_db
def test_integracion_crear_columna_escribir_valor_y_ver_reflejado_en_avance(
    authenticated_client, proyecto,
):
    """Flujo completo: admin crea una columna custom en Obra Civil (B6),
    escribe su valor para una torre real (B7), y el avance_ponderado de esa
    torre (B3) refleja el nuevo valor — sin romper las columnas de sistema."""
    torre_local = TorreConstruccion.objects.create(proyecto=proyecto, numero='T-B7-INTEG')
    oc = ObraCivilTorre.objects.create(proyecto=proyecto, torre=torre_local)  # todo en 0

    # B6: crear columna custom
    url_crear = reverse('construccion:columna_crear', kwargs={'proyecto_id': proyecto.id})
    resp = authenticated_client.post(url_crear, {
        'capitulo': ColumnaConfigurable.CAPITULO_OBRA_CIVIL,
        'etiqueta': 'Extra integración',
        'tipo_valor': ColumnaConfigurable.TIPO_DECIMAL,
        'peso_pct': '10',
    })
    assert resp.status_code == 200
    columna_id = resp.json()['id']

    # B7: escribir el valor de esa columna para la torre
    url_valor = reverse('construccion:columna_valor_update', kwargs={
        'proyecto_id': proyecto.id, 'columna_id': columna_id, 'torre_id': torre_local.id,
    })
    resp = authenticated_client.post(url_valor, {'valor': '1.0'})
    assert resp.status_code == 200
    # Pesos sistema (5/30/5/15/30/15=100) + columna custom peso=10 → total=110.
    # Único aporte activo: la columna custom (peso 10, valor 1.0) → 10/110 ≈ 9.1%
    assert resp.json()['avance_ponderado_pct'] == pytest.approx(9.1, abs=0.05)

    oc.refresh_from_db()
    assert oc.avance_ponderado_pct == pytest.approx(9.1, abs=0.05)

    # La matriz renderiza la nueva columna
    url_matriz = reverse('construccion:obra_civil_lista', kwargs={'proyecto_id': proyecto.id})
    resp = authenticated_client.get(url_matriz)
    assert resp.status_code == 200
    columnas_ctx = resp.context['columnas_custom_activas']
    assert len(columnas_ctx) == 1
    assert columnas_ctx[0].etiqueta == 'Extra integración'
