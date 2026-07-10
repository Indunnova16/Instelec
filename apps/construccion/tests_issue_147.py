"""Tests #147 — Tendido: items 9/10/11 (protecciones/regulación/riega) +
rediseño 2026-07-01 (mockup Gabriel Valencia, 2026-06-29): 1 torre = 1 tiro.

- Item 9: protecciones con "No aplica" (protecciones_no_aplica gana sobre
  protecciones_ok en form_valid).
- Item 11: regulación/flechado por circuito (c1/c2/guarda); regulacion_flechado_ok
  legacy se conserva; si C2 no aplica se limpia regulacion_flechado_c2.
- Rediseño A1-A9: el formset dinámico `RiegaManilaTiro` (botón "+ Agregar
  tiro") se elimina de la UI — reemplazado por `FaseTorre.numero_tiro`
  editable + `FaseTorre.ft931_ok`. `RiegaManilaTiro` (tabla) sigue viva como
  legacy de solo-lectura (backfill migración 0041) para no perder el
  histórico de F.T (`flecha_tendido_m`).
"""

from datetime import date

import pytest
from django.urls import reverse

# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def proyecto_i147(db):
    from apps.construccion.models import ProyectoConstruccion
    from apps.contratos.models import Contrato

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo="TEST-I147-001",
        nombre="Contrato test #147",
        cliente="Cliente #147",
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre="Proyecto tendido #147",
        estado="EJECUCION",
    )


@pytest.fixture
def torre_i147(proyecto_i147):
    from apps.construccion.models import TorreConstruccion

    return TorreConstruccion.objects.create(
        proyecto=proyecto_i147,
        numero="42",
        tipo="D6",
    )


def _tendido_url(proyecto, torre):
    return reverse(
        "construccion:tendido_torre", kwargs={"proyecto_id": proyecto.id, "torre_id": torre.id}
    )


def _matriz_url(proyecto):
    return reverse("construccion:tendido_lista", kwargs={"proyecto_id": proyecto.id})


def _base_post():
    """POST mínimo del form de Tendido (#147 rediseño: sin formset de tiros)."""
    return {
        "circuito_2_aplica": "on",
    }


# ===========================================================================
# 1. Modelo: campos nuevos (numero_tiro, ft931_ok) + RiegaManilaTiro legacy
# ===========================================================================


@pytest.mark.django_db
def test_fasetorre_campos_nuevos_default(torre_i147):
    from apps.construccion.models import FaseTorre

    fase = FaseTorre.objects.create(torre=torre_i147, proyecto=torre_i147.proyecto)
    assert fase.protecciones_ok is False
    assert fase.protecciones_no_aplica is False
    assert fase.protecciones_fecha is None
    assert fase.fecha_riega_manila is None
    assert fase.regulacion_flechado_c1_ok is False
    assert fase.regulacion_flechado_c2_ok is False
    assert fase.regulacion_flechado_guarda_ok is False
    # legacy conservado
    assert hasattr(fase, "regulacion_flechado_ok")
    # #147 rediseño: 1 torre = 1 tiro
    assert fase.numero_tiro is None
    assert fase.ft931_ok is False


@pytest.mark.django_db
def test_riega_manila_tiro_ordering_y_unique(torre_i147):
    """RiegaManilaTiro (tabla legacy, ya no expuesta en UI) conserva su
    integridad — sigue viva de solo-lectura para no perder el histórico
    de F.T (ver migración 0041 backfill)."""
    from django.db import IntegrityError, transaction

    from apps.construccion.models import FaseTorre, RiegaManilaTiro

    fase = FaseTorre.objects.create(torre=torre_i147, proyecto=torre_i147.proyecto)
    RiegaManilaTiro.objects.create(fase=fase, numero_tiro=2, flecha_tendido_m=12.5)
    RiegaManilaTiro.objects.create(fase=fase, numero_tiro=1, flecha_tendido_m=8.0)
    nums = list(fase.tiros_manila.values_list("numero_tiro", flat=True))
    assert nums == [1, 2], "ordering por numero_tiro"
    # unique_together(fase, numero_tiro)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            RiegaManilaTiro.objects.create(fase=fase, numero_tiro=1)


@pytest.mark.django_db
def test_backfill_numero_tiro_desde_legacy_toma_el_minimo(torre_i147):
    """Migración 0041: backfill_numero_tiro() puebla FaseTorre.numero_tiro
    con el MÍNIMO de sus RiegaManilaTiro legacy (caso real: torre con >1 fila
    histórica en la tabla vieja). Llama la función de la migración directo
    (usa solo apps.get_model, no schema_editor) contra los modelos reales."""
    from django.apps import apps as real_apps

    from apps.construccion.migrations import (
        __path__ as _,  # noqa: F401  (asegura el paquete importable)
    )
    from apps.construccion.models import FaseTorre, RiegaManilaTiro
    from importlib import import_module

    backfill = import_module(
        "apps.construccion.migrations.0041_tiro_unico_ft931"
    ).backfill_numero_tiro

    fase_con_tiros = FaseTorre.objects.create(torre=torre_i147, proyecto=torre_i147.proyecto)
    RiegaManilaTiro.objects.create(fase=fase_con_tiros, numero_tiro=5, flecha_tendido_m=1.0)
    RiegaManilaTiro.objects.create(fase=fase_con_tiros, numero_tiro=2, flecha_tendido_m=2.0)

    from apps.construccion.models import TorreConstruccion

    torre_sin_tiros = TorreConstruccion.objects.create(
        proyecto=torre_i147.proyecto, numero="43", tipo="D6"
    )
    fase_sin_tiros = FaseTorre.objects.create(torre=torre_sin_tiros, proyecto=torre_i147.proyecto)

    backfill(real_apps, None)

    fase_con_tiros.refresh_from_db()
    fase_sin_tiros.refresh_from_db()
    assert fase_con_tiros.numero_tiro == 2, "toma el MÍNIMO de los tiros legacy"
    assert fase_sin_tiros.numero_tiro is None, "sin tiros legacy, numero_tiro queda NULL"


# ===========================================================================
# 2. View POST: numero_tiro, ft931_ok, protecciones N/A, circuito 2
# ===========================================================================


@pytest.mark.django_db
def test_post_protecciones_no_aplica_gana(authenticated_client, proyecto_i147, torre_i147):
    """protecciones_no_aplica=True limpia protecciones_ok=False y fecha=None."""
    from apps.construccion.models import FaseTorre

    url = _tendido_url(proyecto_i147, torre_i147)
    data = _base_post()
    data.update(
        {
            "protecciones_no_aplica": "on",
            "protecciones_ok": "on",  # el cliente marcó ambos; N/A gana
            "protecciones_fecha": "2026-06-19",
            "fecha_riega_manila": "2026-06-18",
        }
    )
    resp = authenticated_client.post(url, data)
    assert resp.status_code in (200, 302), resp.content[:600]

    fase = FaseTorre.objects.get(torre=torre_i147)
    assert fase.protecciones_no_aplica is True
    assert fase.protecciones_ok is False, "No aplica gana sobre instaladas"
    assert fase.protecciones_fecha is None
    assert fase.fecha_riega_manila == date(2026, 6, 18)


@pytest.mark.django_db
def test_post_numero_tiro_editable(authenticated_client, proyecto_i147, torre_i147):
    """#147 rediseño: N° de tiro es un campo editable simple (no un formset)."""
    from apps.construccion.models import FaseTorre

    url = _tendido_url(proyecto_i147, torre_i147)
    data = _base_post()
    data.update({"numero_tiro": "4"})
    resp = authenticated_client.post(url, data)
    assert resp.status_code in (200, 302), resp.content[:600]

    fase = FaseTorre.objects.get(torre=torre_i147)
    assert fase.numero_tiro == 4


@pytest.mark.django_db
def test_post_ft931_ok_persiste(authenticated_client, proyecto_i147, torre_i147):
    """Campo nuevo FT-931 (pedido explícito del meeting 23/06): se guarda al marcar
    y se limpia al desmarcar."""
    from apps.construccion.models import FaseTorre

    url = _tendido_url(proyecto_i147, torre_i147)
    data = _base_post()
    data.update({"ft931_ok": "on"})
    resp = authenticated_client.post(url, data)
    assert resp.status_code in (200, 302), resp.content[:600]
    fase = FaseTorre.objects.get(torre=torre_i147)
    assert fase.ft931_ok is True

    # desmarcado (ausente del POST) -> False
    resp2 = authenticated_client.post(url, _base_post())
    assert resp2.status_code in (200, 302)
    fase.refresh_from_db()
    assert fase.ft931_ok is False


@pytest.mark.django_db
def test_post_circuito2_no_aplica_limpia_regulacion_c2(
    authenticated_client, proyecto_i147, torre_i147
):
    """Si circuito_2_aplica=False, regulacion_flechado_c2 queda limpio."""
    from apps.construccion.models import FaseTorre

    url = _tendido_url(proyecto_i147, torre_i147)
    data = _base_post()
    data.pop("circuito_2_aplica")  # checkbox desmarcado = no aplica
    data.update(
        {
            "regulacion_flechado_c2_ok": "on",
            "regulacion_flechado_c2_fecha": "2026-06-15",
            "regulacion_flechado_c1_ok": "on",
        }
    )
    resp = authenticated_client.post(url, data)
    assert resp.status_code in (200, 302), resp.content[:600]
    fase = FaseTorre.objects.get(torre=torre_i147)
    assert fase.circuito_2_aplica is False
    assert fase.regulacion_flechado_c2_ok is False, "C2 no aplica → limpiar regulación C2"
    assert fase.regulacion_flechado_c2_fecha is None
    assert fase.regulacion_flechado_c1_ok is True, "C1 no se toca"


# ===========================================================================
# 3. Render del detalle: campos nuevos, labels renombrados, botón eliminado
# ===========================================================================


@pytest.mark.django_db
def test_render_incluye_campos_nuevos(authenticated_client, proyecto_i147, torre_i147):
    url = _tendido_url(proyecto_i147, torre_i147)
    resp = authenticated_client.get(url)
    assert resp.status_code == 200, resp.content[:600]
    body = resp.content.decode()
    for needle in (
        'name="protecciones_no_aplica"',
        'name="protecciones_ok"',
        'name="fecha_riega_manila"',
        'name="numero_tiro"',
        'name="ft931_ok"',
        'name="regulacion_flechado_c1_ok"',
        'name="regulacion_flechado_c2_ok"',
        'name="regulacion_flechado_guarda_ok"',
    ):
        assert needle in body, f"falta {needle} en el render"
    assert "riega de manila" in body.lower()


@pytest.mark.django_db
def test_render_boton_agregar_tiro_no_existe(authenticated_client, proyecto_i147, torre_i147):
    """#147 rediseño (pedido explícito 2026-06-29): el número de tiros es fijo
    por torre (1); el botón dinámico '+ Agregar tiro' y su formset se eliminan."""
    url = _tendido_url(proyecto_i147, torre_i147)
    resp = authenticated_client.get(url)
    assert resp.status_code == 200, resp.content[:600]
    body = resp.content.decode()
    assert "data-add-tiro" not in body, "el botón '+ Agregar tiro' debe haberse eliminado"
    assert "Agregar tiro" not in body
    assert "tiros_manila-TOTAL_FORMS" not in body, "el formset dinámico ya no se renderiza"
    assert "tirosManila" not in body, "el componente Alpine del formset ya no se registra"


@pytest.mark.django_db
def test_render_labels_renombrados_cable_de_guarda_y_fases(
    authenticated_client, proyecto_i147, torre_i147
):
    """#147 rediseño: OPGW → 'Cable de guarda' y Fase A/B/C → Fase 1/2/3
    (renombrado visual, los nombres de campo Python NO cambian)."""
    url = _tendido_url(proyecto_i147, torre_i147)
    resp = authenticated_client.get(url)
    assert resp.status_code == 200, resp.content[:600]
    body = resp.content.decode()
    assert "Cable de guarda" in body
    assert "OPGW" not in body, "ningún texto visible debe seguir diciendo OPGW"
    assert "Fase 1" in body
    assert "Fase 2" in body
    assert "Fase 3" in body


@pytest.mark.django_db
def test_render_secciones_reorganizadas(authenticated_client, proyecto_i147, torre_i147):
    """#147 rediseño: 'Regulación y flechado' ya no es una sección standalone al
    final — vive dentro de cada circuito/cable de guarda; la sección final
    'Cable de guarda + regulación final + cuadrilla' (con sus duplicados) se
    elimina por completo."""
    url = _tendido_url(proyecto_i147, torre_i147)
    resp = authenticated_client.get(url)
    body = resp.content.decode()
    # la sección standalone vieja ya no existe (el nombre largo era exclusivo de ella)
    assert "Regulación y flechado por circuito" not in body
    # pero SÍ vive, reubicada, dentro de cada circuito/cable de guarda
    assert "Regulación y flechado — Circuito 1" in body
    assert "Regulación y flechado — Circuito 2" in body
    assert "Regulación y flechado — Cable de guarda" in body
    # cuadrilla/%tendido/%facturación/observaciones: 1 sola aparición (fusionados en Tiro)
    assert body.count('name="cuadrilla_tendido"') == 1
    assert body.count('name="pct_tendido"') == 1
    assert body.count('name="pct_facturacion"') == 1
    assert body.count('name="observaciones"') == 1


# ===========================================================================
# 4. #147 (rebote x5) — Tendido editable AUNQUE Montaje no marque "entrega
#    para carga": quitar el candado de la lista + banner no-bloqueante.
#    Decisión Miguel: editable siempre, 🔒 sobrevive como badge INFORMATIVO.
# ===========================================================================


@pytest.mark.django_db
def test_lista_muestra_link_editar_torre_no_marcada(proyecto_i147, torre_i147):
    """Lista de Tendido (tendido_lista.html): una torre con puede_iniciar=False
    (NO marcada 'entrega para carga' en Montaje) DEBE renderizar el link 'Editar'
    a su detalle (antes del fix solo salía el 🔒 sin link → no se podía abrir).
    El 🔒 sobrevive como badge informativo junto al link.

    Se renderiza el template directamente con un contexto de una fila bloqueada
    para aislar el FIX del template del ordenamiento SQL Postgres-only de la
    vista (regexp_replace) que no corre en sqlite."""
    from django.template.loader import render_to_string

    from apps.construccion.models import FaseTorre

    fase = FaseTorre.objects.create(torre=torre_i147, proyecto=torre_i147.proyecto)
    assert fase.puede_iniciar_tendido is False, "precondición: torre bloqueada por Montaje"

    detalle_url = _tendido_url(proyecto_i147, torre_i147)
    html = render_to_string(
        "construccion/tendido_lista.html",
        {
            "proyecto": proyecto_i147,
            "active_tab": "tendido",
            "stats": {"total": 1, "habilitadas": 0, "bloqueadas": 1, "completas": 0},
            "filas": [
                {"torre": torre_i147, "fase": fase, "puede_iniciar": False},
            ],
        },
    )

    # el link 'Editar' al detalle de la torre NO-marcada debe estar presente
    assert detalle_url in html, "la lista debe linkear al detalle aunque la torre no esté marcada"
    assert "Editar" in html
    # el 🔒 sobrevive como badge informativo (no reemplaza al link)
    assert "🔒" in html
    assert "Montaje aún sin marcar entrega para carga" in html


@pytest.mark.django_db
def test_detalle_torre_no_marcada_get_y_post_guarda(
    authenticated_client, proyecto_i147, torre_i147
):
    """El escenario EXACTO de Gabriel: torre con entrega_carga_ok=False.
    GET responde 200 (form editable, banner informativo no-bloqueante) y POST
    GUARDA datos de Tendido sin candado."""
    from apps.construccion.models import FaseTorre

    fase = FaseTorre.objects.create(torre=torre_i147, proyecto=torre_i147.proyecto)
    assert fase.puede_iniciar_tendido is False

    url = _tendido_url(proyecto_i147, torre_i147)

    # GET: 200 + banner informativo (no el viejo 'Edita el módulo Montaje primero')
    resp_get = authenticated_client.get(url)
    assert resp_get.status_code == 200, resp_get.content[:600]
    body = resp_get.content.decode()
    assert "podés registrar el Tendido igualmente" in body
    assert "Edita el módulo Montaje primero" not in body, "el texto bloqueante debe desaparecer"
    assert "disabled" not in body.lower() or "sumaConductor" not in body  # sin disabled del gate

    # POST: guarda datos de tendido aunque la torre NO esté marcada en Montaje
    data = _base_post()
    data.update(
        {
            "tendido_conductor_a_ok": "on",
            "tendido_conductor_a_fecha": "2026-06-20",
            "fecha_riega_manila": "2026-06-19",
        }
    )
    resp_post = authenticated_client.post(url, data)
    assert resp_post.status_code in (200, 302), resp_post.content[:600]

    fase.refresh_from_db()
    assert fase.entrega_carga_ok is False, "el gate de Montaje NO cambia (sigue informativo)"
    assert fase.tendido_conductor_a_ok is True, "el dato de Tendido se guarda sin candado"
    assert fase.tendido_conductor_a_fecha == date(2026, 6, 20)
    assert fase.fecha_riega_manila == date(2026, 6, 19)


@pytest.mark.django_db
def test_detalle_torre_legacy_no_marcada_guarda(authenticated_client, proyecto_i147, torre_i147):
    """Dato LEGACY: torre con una FaseTorre pre-existente (entrega_carga_ok=False)
    que YA tenía algo de tendido marcado; editar y guardar más datos funciona sin
    candado y conserva lo previo."""
    from apps.construccion.models import FaseTorre

    fase = FaseTorre.objects.create(
        torre=torre_i147,
        proyecto=torre_i147.proyecto,
        entrega_carga_ok=False,
        tendido_conductor_a_ok=True,  # avance legacy pre-existente
    )

    url = _tendido_url(proyecto_i147, torre_i147)
    data = _base_post()
    data.update(
        {
            "tendido_conductor_a_ok": "on",  # conservar legacy
            "tendido_conductor_b_ok": "on",  # agregar nuevo
            "tendido_conductor_b_fecha": "2026-06-21",
        }
    )
    resp = authenticated_client.post(url, data)
    assert resp.status_code in (200, 302), resp.content[:600]

    fase.refresh_from_db()
    assert fase.entrega_carga_ok is False
    assert fase.tendido_conductor_a_ok is True, "el avance legacy sobrevive"
    assert fase.tendido_conductor_b_ok is True, "el nuevo avance se guarda sin candado"


# ===========================================================================
# #147 (bug 24/06) — sincronización Montaje → gate Tendido (letrero)
# ===========================================================================


@pytest.mark.django_db
def test_147_entrega_carga_propaga_montaje_a_tendido(proyecto_i147, torre_i147):
    """Marcar 'Entregada para carga' en el detalle de Montaje sincroniza
    FaseTorre.entrega_carga_ok (el gate que lee Tendido) → el letrero 🔒
    desaparece. Antes los flags estaban desacoplados en tablas distintas."""
    from apps.construccion.models import FaseTorre
    from apps.construccion.models_b3_mont_detalle import MontajeEstructuraTorreDetalle

    fase, _ = FaseTorre.objects.get_or_create(
        torre=torre_i147, defaults={"proyecto": proyecto_i147}
    )
    assert fase.entrega_carga_ok is False
    assert fase.puede_iniciar_tendido is False

    # El cliente marca en el detalle de Montaje → post_save dispara el signal.
    det = MontajeEstructuraTorreDetalle.objects.create(
        torre=torre_i147, proyecto=proyecto_i147, entregada_para_carga_ok=True
    )
    fase.refresh_from_db()
    assert fase.entrega_carga_ok is True
    assert fase.puede_iniciar_tendido is True

    # Desmarcar lo revierte (sincroniza en ambos sentidos).
    det.entregada_para_carga_ok = False
    det.save()
    fase.refresh_from_db()
    assert fase.entrega_carga_ok is False


# ===========================================================================
# 5. CANT TENDIDO (matriz) — A6/A7/A8: renombrado, link, columna eliminada
# ===========================================================================


@pytest.mark.django_db
def test_matriz_renombra_fibra_opgw_a_cable_de_guarda(
    authenticated_client, proyecto_i147, torre_i147
):
    """A6: 'Fibra OPGW' -> 'Cable de guarda' en los 5 puntos pedidos por el
    cliente (KPI, panel de pesos, encabezado de grupo de columnas, columna
    '% C. guarda', columna 'Realizó (CG)'). Los slugs/labels internos de
    `COLUMNAS_FIBRA` (tooltips por sub-columna: Riega guaya OPGW, Tendido OPGW,
    Empalmes OPGW) quedan fuera de scope a propósito — son internos, no parte
    de los 5 puntos que el cliente nombró (ver PLAN_2026-07-01_147, A6)."""
    url = _matriz_url(proyecto_i147)
    resp = authenticated_client.get(url)
    assert resp.status_code == 200, resp.content[:600]
    body = resp.content.decode()
    assert "Cable de guarda" in body
    assert "% C. guarda" in body
    assert "Realizó (CG)" in body
    assert "Fibra OPGW" not in body, "el nombre de grupo/KPI/panel viejo no debe sobrevivir"


@pytest.mark.django_db
def test_matriz_torre_clickeable_sin_columna_detalle(
    authenticated_client, proyecto_i147, torre_i147
):
    """A7: la columna Torre es un link directo al detalle; la columna
    Detalle/Editar al extremo derecho se elimina."""
    url = _matriz_url(proyecto_i147)
    resp = authenticated_client.get(url)
    assert resp.status_code == 200, resp.content[:600]
    body = resp.content.decode()
    detalle_url = _tendido_url(proyecto_i147, torre_i147)
    assert f'href="{detalle_url}"' in body, "el número de torre debe linkear al detalle"
    assert ">Detalle<" not in body, "la columna Detalle/Editar debe haberse eliminado"


@pytest.mark.django_db
def test_matriz_columna_aplica_solo_checkbox(authenticated_client, proyecto_i147, torre_i147):
    """A8: la columna 'Aplica' muestra únicamente el checkbox, sin texto
    redundante por fila (el encabezado ya comunica el concepto)."""
    url = _matriz_url(proyecto_i147)
    resp = authenticated_client.get(url)
    assert resp.status_code == 200, resp.content[:600]
    body = resp.content.decode()
    assert 'data-toggle-aplica="aplica"' in body
    # sin texto "Aplica"/"No aplica" repetido dentro de cada fila (solo el <th>)
    assert body.count(">Aplica<") <= 1, "el texto 'Aplica' solo debe aparecer en el encabezado"


# ===========================================================================
# 6. #147 Bloque 2 (PLAN_2026-07-09_tendido_bloque2.md) — Cambios 1-4
# ===========================================================================
#
# Nota de validación manual (Cambio 1): el proyecto QA real (Puerta de Oro,
# ec2a68aa-47fe-4772-89bc-2cd2b1c8b5c7) vive en Cloud SQL prod; los tests de
# este repo corren contra sqlite (config.settings.dev_lite), por lo que NO es
# factible conectarlos directamente al dato legacy. Se validó por fuera del
# test suite (read-only vía cloud-sql-proxy :5434, DB instelec_db):
#   - construccion_fases_torres tiene 65 filas con circuito_2_aplica NOT NULL,
#     ninguna columna c2_vestida_*/c2_riega_*/c2_grapado_ok/c2_accesorios_ok
#     existe aún (confirma que la migración 0042 es puramente additive).
#   - Torre legacy de referencia: fase id b4e52c69-d6a2-44d3-9d34-b6c27de7f412
#     (torre_id 3cf707c8-306d-4e33-948c-bcf8cc220ef6, el mismo UUID que usa el
#     journey QA i147_tendido_entra_al_detalle) tiene circuito_2_aplica=True,
#     por lo que al aplicar 0042 en prod sus 6 campos nuevos nacerán en su
#     default (False/NULL) sin romper nada — smoke post-deploy debe abrir esa
#     torre y marcar/desmarcar los 4 checks + vestida C2 para cerrar el loop.


@pytest.mark.django_db
def test_circuito2_checks_propios_persisten(authenticated_client, proyecto_i147, torre_i147):
    """Cambio 1: los 6 campos nuevos (vestida C2 + 4 checks) se guardan al
    marcar (POST) y se conservan al recargar (GET)."""
    from apps.construccion.models import FaseTorre

    url = _tendido_url(proyecto_i147, torre_i147)
    data = _base_post()
    data.update(
        {
            "c2_vestida_ok": "on",
            "c2_vestida_fecha": "2026-07-05",
            "c2_riega_manila_ok": "on",
            "c2_riega_guaya_ok": "on",
            "c2_grapado_ok": "on",
            "c2_accesorios_ok": "on",
        }
    )
    resp = authenticated_client.post(url, data)
    assert resp.status_code in (200, 302), resp.content[:600]

    fase = FaseTorre.objects.get(torre=torre_i147)
    assert fase.circuito_2_aplica is True
    assert fase.c2_vestida_ok is True
    assert fase.c2_vestida_fecha == date(2026, 7, 5)
    assert fase.c2_riega_manila_ok is True
    assert fase.c2_riega_guaya_ok is True
    assert fase.c2_grapado_ok is True
    assert fase.c2_accesorios_ok is True

    # GET recarga: los 6 campos vienen marcados/con valor en el form renderizado
    resp_get = authenticated_client.get(url)
    assert resp_get.status_code == 200
    body = resp_get.content.decode()
    for needle in (
        'name="c2_vestida_ok"',
        'name="c2_vestida_fecha"',
        'name="c2_riega_manila_ok"',
        'name="c2_riega_guaya_ok"',
        'name="c2_grapado_ok"',
        'name="c2_accesorios_ok"',
    ):
        assert needle in body, f"falta {needle} en el render tras recargar"
    assert "CONDUCTOR — Circuito 2" in body


@pytest.mark.django_db
def test_circuito2_checks_se_limpian_si_no_aplica(authenticated_client, proyecto_i147, torre_i147):
    """Cambio 1: si circuito_2_aplica=False, los 6 campos nuevos se limpian
    (mismo patrón ya existente para tendido_conductor_c2_*/regulacion_flechado_c2_*)."""
    from apps.construccion.models import FaseTorre

    url = _tendido_url(proyecto_i147, torre_i147)

    # Primero se marcan con C2 aplicando.
    data_on = _base_post()
    data_on.update(
        {
            "c2_vestida_ok": "on",
            "c2_vestida_fecha": "2026-07-05",
            "c2_riega_manila_ok": "on",
            "c2_riega_guaya_ok": "on",
            "c2_grapado_ok": "on",
            "c2_accesorios_ok": "on",
        }
    )
    resp_on = authenticated_client.post(url, data_on)
    assert resp_on.status_code in (200, 302)

    # Luego se desmarca "Circuito 2 aplica" -> los 6 campos deben limpiarse.
    data_off = _base_post()
    data_off.pop("circuito_2_aplica")
    resp_off = authenticated_client.post(url, data_off)
    assert resp_off.status_code in (200, 302), resp_off.content[:600]

    fase = FaseTorre.objects.get(torre=torre_i147)
    assert fase.circuito_2_aplica is False
    assert fase.c2_vestida_ok is False, "C2 no aplica → limpiar vestida C2"
    assert fase.c2_vestida_fecha is None
    assert fase.c2_riega_manila_ok is False
    assert fase.c2_riega_guaya_ok is False
    assert fase.c2_grapado_ok is False
    assert fase.c2_accesorios_ok is False


@pytest.mark.django_db
def test_circuito1_muestra_cuadrilla_informativa_readonly(
    authenticated_client, proyecto_i147, torre_i147
):
    """Cambio 2: la sección Circuito 1 muestra un párrafo read-only con
    fase.cuadrilla_tendido (el mismo valor ya guardado desde la sección Tiro),
    y en todo el HTML solo existe 1 input editable name="cuadrilla_tendido"."""
    from apps.construccion.models import FaseTorre

    FaseTorre.objects.create(
        torre=torre_i147, proyecto=torre_i147.proyecto, cuadrilla_tendido="Cuadrilla Alpha"
    )

    url = _tendido_url(proyecto_i147, torre_i147)
    resp = authenticated_client.get(url)
    assert resp.status_code == 200, resp.content[:600]
    body = resp.content.decode()

    assert "Cuadrilla Alpha" in body, "el valor de cuadrilla_tendido debe aparecer en Circuito 1"
    assert "Cuadrilla tendido (informativo — desde Tiro)" in body
    # Solo 1 input editable (el de la sección Tiro); el de Circuito 1 es texto plano.
    assert body.count('name="cuadrilla_tendido"') == 1, (
        "debe existir un único input editable name=cuadrilla_tendido en todo el HTML"
    )


def _render_tendido_matriz(proyecto, filas):
    """Renderiza tendido_matriz.html directamente (bypass del queryset de la
    vista real, que usa ordenar_torres_construccion -> regexp_replace, función
    Postgres-only que no existe en sqlite). Mismo patrón ya usado en
    test_lista_muestra_link_editar_torre_no_marcada para aislar el fix del
    template del gap de infra de sqlite (ver docstring de ese test)."""
    from django.template.loader import render_to_string

    from apps.construccion.models import TendidoTorre

    return render_to_string(
        "construccion/tendido_matriz.html",
        {
            "proyecto": proyecto,
            "filas": filas,
            "pesos_conductor": {
                "riega_manila": 0, "riega_guaya": 0, "tendido": 0,
                "grapado": 0, "accesorios": 0, "balizas": 0,
            },
            "pesos_fibra": {
                "riega_manila_fibra": 0, "riega_guaya_opgw": 0, "tendido_opgw": 0,
                "grapado_fibra": 0, "empalmes_opgw": 0,
            },
            "suma_conductor": 0,
            "suma_fibra": 0,
            "suma_conductor_ok": False,
            "suma_fibra_ok": False,
            "columnas_conductor": TendidoTorre.COLUMNAS_CONDUCTOR,
            "columnas_fibra": TendidoTorre.COLUMNAS_FIBRA,
            "avance_general_conductor": 0,
            "avance_general_fibra": 0,
            "active_tab": "tendido",
        },
    )


@pytest.mark.django_db
def test_matriz_titulo_y_h1_dicen_tendido_no_cant_tendido(proyecto_i147):
    """Cambio 3: <title> y <h1> de la matriz dicen 'Tendido', no 'CANT TENDIDO'."""
    html = _render_tendido_matriz(proyecto_i147, filas=[])
    assert "<title>Tendido" in html
    assert "⚡ Tendido</h1>" in html
    assert "CANT TENDIDO" not in html, "el rename debe eliminar 'CANT TENDIDO' del título/h1"


@pytest.mark.django_db
def test_matriz_thead_sticky_top_sin_regresion_columna_torre(proyecto_i147, torre_i147):
    """Cambio 4: el <thead> completo lleva 'sticky top-0 z-20' (freeze-header
    vertical); el sticky left-0 ya existente de la columna Torre (header +
    celda de cuerpo) NO se toca — debe seguir intacto (esquina congelada)."""
    from apps.construccion.models import TendidoTorre

    fila = TendidoTorre.objects.create(proyecto=proyecto_i147, torre=torre_i147)
    html = _render_tendido_matriz(proyecto_i147, filas=[fila])

    assert '<thead class="bg-gray-50 dark:bg-gray-900 sticky top-0 z-20">' in html
    # sin regresión: la columna Torre conserva su sticky left-0 (header y celda)
    assert "sticky left-0 bg-gray-50 dark:bg-gray-900 z-10" in html, (
        "el header de la columna Torre debe conservar su sticky left-0 (sin regresión)"
    )
    assert "sticky left-0 bg-white dark:bg-gray-800 z-10" in html, (
        "la celda de la columna Torre debe conservar su sticky left-0 (sin regresión)"
    )
