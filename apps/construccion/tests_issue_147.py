"""Tests #147 — Tendido items 9/10/11 (feature).

- Item 9: protecciones con "No aplica" (protecciones_no_aplica gana sobre
  protecciones_ok en form_valid).
- Item 10: fecha_riega_manila (cabecera) + modelo hijo RiegaManilaTiro por tiros
  (F.T = flecha de tendido).
- Item 11: regulación/flechado por circuito (c1/c2/guarda); regulacion_flechado_ok
  legacy se conserva; si C2 no aplica se limpia regulacion_flechado_c2.
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


def _base_post():
    """POST mínimo con el management_form vacío del formset de tiros."""
    return {
        "circuito_2_aplica": "on",
        "tiros_manila-TOTAL_FORMS": "0",
        "tiros_manila-INITIAL_FORMS": "0",
        "tiros_manila-MIN_NUM_FORMS": "0",
        "tiros_manila-MAX_NUM_FORMS": "1000",
    }


# ===========================================================================
# 1. Modelo: campos nuevos + RiegaManilaTiro
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


@pytest.mark.django_db
def test_riega_manila_tiro_ordering_y_unique(torre_i147):
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


# ===========================================================================
# 2. View POST: protecciones N/A + tiros
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
def test_post_crea_dos_tiros(authenticated_client, proyecto_i147, torre_i147):
    """POST con 2 filas de tiros crea 2 RiegaManilaTiro en DB."""
    from apps.construccion.models import FaseTorre, RiegaManilaTiro

    url = _tendido_url(proyecto_i147, torre_i147)
    data = _base_post()
    data.update(
        {
            "tiros_manila-TOTAL_FORMS": "2",
            "tiros_manila-0-numero_tiro": "1",
            "tiros_manila-0-fecha": "2026-06-10",
            "tiros_manila-0-flecha_tendido_m": "10.5",
            "tiros_manila-0-observaciones": "tiro uno",
            "tiros_manila-1-numero_tiro": "2",
            "tiros_manila-1-fecha": "2026-06-11",
            "tiros_manila-1-flecha_tendido_m": "11.0",
            "tiros_manila-1-observaciones": "tiro dos",
        }
    )
    resp = authenticated_client.post(url, data)
    assert resp.status_code in (200, 302), resp.content[:600]

    fase = FaseTorre.objects.get(torre=torre_i147)
    tiros = list(fase.tiros_manila.all())
    assert len(tiros) == 2, [t.numero_tiro for t in tiros]
    assert {t.numero_tiro for t in tiros} == {1, 2}
    assert RiegaManilaTiro.objects.filter(fase=fase, flecha_tendido_m=10.5).exists()


@pytest.mark.django_db
def test_post_tiro_sin_numero_autoasigna(authenticated_client, proyecto_i147, torre_i147):
    """numero_tiro vacío → autoasigna max+1 (empieza en 1)."""
    from apps.construccion.models import FaseTorre

    url = _tendido_url(proyecto_i147, torre_i147)
    data = _base_post()
    data.update(
        {
            "tiros_manila-TOTAL_FORMS": "1",
            "tiros_manila-0-numero_tiro": "",  # vacío
            "tiros_manila-0-flecha_tendido_m": "7.0",
        }
    )
    resp = authenticated_client.post(url, data)
    assert resp.status_code in (200, 302), resp.content[:600]
    fase = FaseTorre.objects.get(torre=torre_i147)
    nums = list(fase.tiros_manila.values_list("numero_tiro", flat=True))
    assert nums == [1], f"autoasignar a 1, fue {nums}"


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
# 3. Render del detalle muestra los campos nuevos
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
        "data-tiros-manila",
        'name="regulacion_flechado_c1_ok"',
        'name="regulacion_flechado_c2_ok"',
        'name="regulacion_flechado_guarda_ok"',
    ):
        assert needle in body, f"falta {needle} en el render"
    # textos que el journey espera
    assert "riega de manila" in body.lower()
    assert "F.T" in body


@pytest.mark.django_db
def test_render_incluye_boton_agregar_tiro(authenticated_client, proyecto_i147, torre_i147):
    """#147 UI: el detalle de tendido renderiza el botón dinámico
    [data-add-tiro] + la plantilla empty_form (placeholder __prefix__) para
    que el cliente pueda agregar tiros (síntoma original: solo 'Quitar')."""
    url = _tendido_url(proyecto_i147, torre_i147)
    resp = authenticated_client.get(url)
    assert resp.status_code == 200, resp.content[:600]
    body = resp.content.decode()
    # botón con selector contractual del E2E
    assert "data-add-tiro" in body, "falta el botón '+ Agregar tiro'"
    assert "Agregar tiro" in body
    # plantilla oculta con el empty_form (placeholder __prefix__)
    assert "__prefix__" in body, "falta la plantilla empty_form clonable"
    assert 'name="tiros_manila-__prefix__-flecha_tendido_m"' in body
    # componente Alpine registrado + management_form presente
    assert "Alpine.data('tirosManila'" in body
    assert "id_tiros_manila-TOTAL_FORMS" in body


@pytest.mark.django_db
def test_render_total_forms_cuenta_la_fila_extra(authenticated_client, proyecto_i147, torre_i147):
    """Con 0 tiros guardados, el formset (extra=1) rinde 1 fila editable y
    TOTAL_FORMS=1 → tras 1 click de 'Agregar tiro' el JS añade el índice 1
    (tiros_manila-1-*) y deja TOTAL_FORMS=2, como espera el journey."""
    url = _tendido_url(proyecto_i147, torre_i147)
    resp = authenticated_client.get(url)
    body = resp.content.decode()
    # management_form TOTAL_FORMS = INITIAL(0) + extra(1) = 1
    assert 'name="tiros_manila-TOTAL_FORMS" value="1"' in body, (
        "TOTAL_FORMS inicial debe contar la fila extra editable"
    )
    # la fila extra (índice 0) es editable de entrada
    assert 'name="tiros_manila-0-flecha_tendido_m"' in body


# ===========================================================================
# 4. UI: consistencia visual del control "Quitar" (fix vigente del bounce #147)
# ===========================================================================


@pytest.mark.django_db
def test_quitar_ui_consistente_fila_guardada(authenticated_client, proyecto_i147, torre_i147):
    """#147 (fix visual): una fila YA guardada NO debe mostrar el checkbox DELETE
    crudo + label 'Quitar'; debe mostrar el MISMO botón rojo 'Quitar' que las
    filas nuevas, con el checkbox DELETE oculto que ese botón togglea.

    Síntoma (oráculo att_07): fila guardada = checkbox + 'Quitar' gris; fila
    nueva = botón texto rojo. El fix unifica ambos al botón rojo."""
    from apps.construccion.models import FaseTorre, RiegaManilaTiro

    # crear una fila guardada (legacy) para que se renderice como INITIAL_FORMS=1
    fase = FaseTorre.objects.create(torre=torre_i147, proyecto=torre_i147.proyecto)
    RiegaManilaTiro.objects.create(fase=fase, numero_tiro=1, flecha_tendido_m=9.5)

    url = _tendido_url(proyecto_i147, torre_i147)
    resp = authenticated_client.get(url)
    assert resp.status_code == 200, resp.content[:600]
    body = resp.content.decode()

    # el checkbox DELETE de la fila guardada existe pero va OCULTO (envuelto en
    # un contenedor .hidden con data-tiro-delete-saved)
    assert "data-tiro-delete-saved" in body, "falta el wrapper del DELETE oculto"
    assert 'name="tiros_manila-0-DELETE"' in body, (
        "el checkbox DELETE del formset debe seguir presente (semántica can_delete)"
    )
    # el control visible de la fila guardada es el MISMO botón rojo de las nuevas
    assert "quitarFilaGuardada($event)" in body, (
        "la fila guardada debe usar el botón rojo que togglea el DELETE oculto"
    )
    # el wrapper oculto envuelve el checkbox (clase hidden + el DELETE adentro)
    assert '<span class="hidden" data-tiro-delete-saved>' in body, (
        "el checkbox DELETE de la fila guardada debe ir oculto"
    )
    # botón rojo presente con el mismo styling text-red-600 que las filas nuevas
    assert "data-remove-tiro" in body
    assert "text-red-600" in body


# ===========================================================================
# 5. BLINDAJE de persistencia (directiva Miguel, bounce x4 — red de seguridad)
#    Si la persistencia se rompiera, este test debe atraparlo en el gate.
# ===========================================================================


@pytest.mark.django_db
def test_persistencia_blindaje_dos_tiros_recarga(authenticated_client, proyecto_i147, torre_i147):
    """RED DE SEGURIDAD: POST de ≥2 tiros via formset -> guardar -> re-query a
    construccion_riega_manila_tiro -> assert COUNT == esperado. Recargar el GET
    (simula el reload del cliente) y verificar que las filas siguen renderizando.

    Blinda el flujo que el cliente reportó como roto ('si actualizo se borran
    los datos'); la persistencia YA funciona en prod (rev 00173-cax), este test
    evita que un cambio futuro la rompa sin ser detectado."""
    from django.db import connection

    from apps.construccion.models import FaseTorre, RiegaManilaTiro

    url = _tendido_url(proyecto_i147, torre_i147)
    data = _base_post()
    data.update(
        {
            "tiros_manila-TOTAL_FORMS": "2",
            "tiros_manila-0-numero_tiro": "1",
            "tiros_manila-0-fecha": "2026-06-10",
            "tiros_manila-0-flecha_tendido_m": "10.5",
            "tiros_manila-0-observaciones": "tiro uno",
            "tiros_manila-1-numero_tiro": "2",
            "tiros_manila-1-fecha": "2026-06-11",
            "tiros_manila-1-flecha_tendido_m": "11.0",
            "tiros_manila-1-observaciones": "tiro dos",
        }
    )
    resp = authenticated_client.post(url, data)
    assert resp.status_code in (200, 302), resp.content[:600]

    fase = FaseTorre.objects.get(torre=torre_i147)

    # (a) COUNT via ORM re-query
    assert RiegaManilaTiro.objects.filter(fase=fase).count() == 2, (
        "los 2 tiros deben persistir tras guardar"
    )

    # (b) COUNT directo contra la TABLA física (nombre que cita Miguel).
    #     Se prepara el valor del PK con el MISMO conversor del UUIDField del
    #     backend (NO str(pk)): en Postgres queda uuid nativo y en sqlite el hex
    #     sin guiones, de modo que el binding del raw SQL es robusto en ambos.
    fase_id_param = FaseTorre._meta.pk.get_db_prep_value(fase.pk, connection)
    with connection.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM construccion_riega_manila_tiro WHERE fase_id = %s",
            [fase_id_param],
        )
        count_tabla = cur.fetchone()[0]
    assert count_tabla == 2, (
        f"construccion_riega_manila_tiro debe tener 2 filas, tiene {count_tabla}"
    )

    # (c) recarga del GET (el reload del cliente) sigue mostrando las filas
    resp2 = authenticated_client.get(url)
    body = resp2.content.decode()
    assert 'value="10.5"' in body, "tiro 1 sobrevive a la recarga"
    assert 'value="11.0"' in body, "tiro 2 sobrevive a la recarga"


@pytest.mark.django_db
def test_persistencia_blindaje_agrega_a_legacy_existente(
    authenticated_client, proyecto_i147, torre_i147
):
    """RED DE SEGURIDAD + dato LEGACY: con 1 tiro pre-existente (INITIAL_FORMS=1),
    agregar 2 nuevos -> COUNT debe ser 3 (el legacy sobrevive + 2 nuevos). Atrapa
    una regresión que perdiera los tiros guardados al editar."""
    from apps.construccion.models import FaseTorre, RiegaManilaTiro

    # registro LEGACY pre-existente (no fixture del POST)
    fase = FaseTorre.objects.create(torre=torre_i147, proyecto=torre_i147.proyecto)
    legacy = RiegaManilaTiro.objects.create(
        fase=fase, numero_tiro=1, flecha_tendido_m=5.5, observaciones="legacy"
    )

    url = _tendido_url(proyecto_i147, torre_i147)
    data = _base_post()
    # INITIAL_FORMS=1 (la fila legacy) + 2 nuevas
    data.update(
        {
            "tiros_manila-INITIAL_FORMS": "1",
            "tiros_manila-TOTAL_FORMS": "3",
            # fila 0 = el registro legacy (se reenvía con su pk + datos actuales)
            "tiros_manila-0-id": str(legacy.pk),
            "tiros_manila-0-numero_tiro": "1",
            "tiros_manila-0-flecha_tendido_m": "5.5",
            "tiros_manila-0-observaciones": "legacy",
            # filas nuevas
            "tiros_manila-1-numero_tiro": "2",
            "tiros_manila-1-flecha_tendido_m": "7.0",
            "tiros_manila-2-numero_tiro": "3",
            "tiros_manila-2-flecha_tendido_m": "8.0",
        }
    )
    resp = authenticated_client.post(url, data)
    assert resp.status_code in (200, 302), resp.content[:600]

    assert RiegaManilaTiro.objects.filter(fase=fase).count() == 3, (
        "el legacy debe sobrevivir + 2 nuevos = 3"
    )
    # el legacy específico sigue ahí
    assert RiegaManilaTiro.objects.filter(pk=legacy.pk).exists(), (
        "el tiro legacy pre-existente NO debe borrarse al editar"
    )


@pytest.mark.django_db
def test_delete_oculto_borra_fila_guardada(authenticated_client, proyecto_i147, torre_i147):
    """El checkbox DELETE oculto que togglea el botón rojo SIGUE borrando la fila
    al guardar (la semántica can_delete=True no se rompe con el fix visual)."""
    from apps.construccion.models import FaseTorre, RiegaManilaTiro

    fase = FaseTorre.objects.create(torre=torre_i147, proyecto=torre_i147.proyecto)
    t1 = RiegaManilaTiro.objects.create(fase=fase, numero_tiro=1, flecha_tendido_m=9.0)
    t2 = RiegaManilaTiro.objects.create(fase=fase, numero_tiro=2, flecha_tendido_m=9.5)

    url = _tendido_url(proyecto_i147, torre_i147)
    data = _base_post()
    data.update(
        {
            "tiros_manila-INITIAL_FORMS": "2",
            "tiros_manila-TOTAL_FORMS": "2",
            "tiros_manila-0-id": str(t1.pk),
            "tiros_manila-0-numero_tiro": "1",
            "tiros_manila-0-flecha_tendido_m": "9.0",
            "tiros_manila-0-DELETE": "on",  # marcado por el botón rojo (toggle)
            "tiros_manila-1-id": str(t2.pk),
            "tiros_manila-1-numero_tiro": "2",
            "tiros_manila-1-flecha_tendido_m": "9.5",
        }
    )
    resp = authenticated_client.post(url, data)
    assert resp.status_code in (200, 302), resp.content[:600]

    assert not RiegaManilaTiro.objects.filter(pk=t1.pk).exists(), (
        "el tiro con DELETE marcado debe borrarse"
    )
    assert RiegaManilaTiro.objects.filter(pk=t2.pk).exists(), "el tiro sin DELETE sobrevive"
    assert RiegaManilaTiro.objects.filter(fase=fase).count() == 1


# ===========================================================================
# 6. #147 (rebote x5) — Tendido editable AUNQUE Montaje no marque "entrega
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
