"""Regresiones para Instelec#238 — Actividades preliminares (predial/ambiental).

Bug 1: los 5 <input type="date"> de la hoja socio-predial no tenían
name="valor", así que htmx nunca mandaba el valor en el POST y el backend
limpiaba el campo. Fix: agregar name="valor" (templates/preliminares/predial.html).

Bug 2: el partial `_campo_ambiental.html` usaba
hx-target="closest .campo-flex" + hx-swap="outerHTML", pero el wrapper
`.campo-flex` vivía solo en `ambiental_editable.html`, no en el partial. La
primera edición exitosa (outerHTML) reemplazaba el wrapper por contenido sin
la clase `campo-flex` — la SIGUIENTE edición sobre esa misma celda perdía su
target y htmx fallaba en silencio (afecta guardado en general y el toggle de
N/A, que es justamente una segunda edición sobre la misma celda). Fix: mover
`class="campo-flex"` DENTRO de `_campo_ambiental.html` como su único elemento
raíz, y quitar el wrapper duplicado en `ambiental_editable.html`.
"""
from pathlib import Path

import pytest
from django.urls import reverse

from apps.contratos.models import Contrato
from apps.ingenieria.models import TorreContrato
from apps.preliminares.models import AmbientalTorre, PredialTorre

TEMPLATES = Path("templates/preliminares")


# ── Regresión de template (contrato estático, sin BD) ───────────────────────

def test_predial_date_inputs_have_name_valor():
    """Los 5 inputs de fecha de la hoja socio-predial deben tener name="valor"
    (sin esto htmx no manda el valor y el backend limpia el campo)."""
    content = (TEMPLATES / "predial.html").read_text(encoding="utf-8")

    campos_fecha = [
        "socializacion",
        "acta_vecindad",
        "acta_acceso_com",
        "autorizacion_prop",
        "acta_acceso_priv",
    ]
    for campo in campos_fecha:
        # Aislar el bloque del input de fecha correspondiente a este campo
        marker = f'"campo": "{campo}"'
        idx = content.index(marker)
        # El input abre antes del hx-vals y cierra en el primer '>' tras el marker
        bloque_inicio = content.rindex("<input", 0, idx)
        bloque_fin = content.index(">", idx)
        bloque = content[bloque_inicio:bloque_fin]
        assert 'name="valor"' in bloque, (
            f"input de fecha para '{campo}' no tiene name=\"valor\" — "
            "htmx no mandará el valor en el POST"
        )


def test_campo_ambiental_partial_is_self_contained_campo_flex():
    """El partial _campo_ambiental.html debe tener class="campo-flex" en su
    ÚNICO elemento raíz para cada tipo de campo — si el wrapper vive afuera
    (en ambiental_editable.html) el hx-swap="outerHTML" se lo come en la
    primera edición y la segunda edición pierde su hx-target."""
    partial = (TEMPLATES / "partials/_campo_ambiental.html").read_text(encoding="utf-8")

    # Debe aparecer una vez por cada rama {% if/elif/else %} (5 tipos)
    assert partial.count('class="campo-flex') >= 5

    # ambiental_editable.html YA NO debe envolver el include con su propio
    # <div class="campo-flex"> — eso duplicaría el wrapper.
    editable = (TEMPLATES / "ambiental_editable.html").read_text(encoding="utf-8")
    assert '<div class="campo-flex">{% include' not in editable


# ── Regresión funcional (POST real contra la BD) ────────────────────────────

@pytest.fixture
def contrato_construccion(db):
    return Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo="TEST-238",
        nombre="Contrato de prueba Instelec#238",
    )


@pytest.fixture
def torre_contrato(contrato_construccion):
    return TorreContrato.objects.create(contrato=contrato_construccion, nombre="T-1")


@pytest.mark.django_db
def test_post_fecha_nueva_a_hoja_predial_persiste(authenticated_client, contrato_construccion, torre_contrato):
    """(a) POST con fecha nueva a una hoja predial persiste el valor."""
    url = reverse("preliminares:campo", kwargs={"contrato_id": contrato_construccion.id})

    response = authenticated_client.post(url, {
        "torre_id": str(torre_contrato.id),
        "campo": "socializacion",
        "valor": "2026-08-15",
    })

    assert response.status_code == 204
    pred = PredialTorre.objects.get(torre=torre_contrato)
    assert pred.socializacion is not None
    assert pred.socializacion.isoformat() == "2026-08-15"


@pytest.mark.django_db
def test_post_fecha_predial_sobre_registro_existente_actualiza(authenticated_client, contrato_construccion, torre_contrato):
    """Reproduce el reporte del cliente: la hoja "dice que se guarda
    automáticamente" pero al recargar sigue vacía. Simulamos edición sobre un
    registro que ya existe (no solo creación) — TorreContrato.save() ya crea
    un PredialTorre vacío vía signal (apps/ingenieria/signals.py)."""
    pred_previo, _ = PredialTorre.objects.get_or_create(torre=torre_contrato)
    assert pred_previo.acta_vecindad is None
    url = reverse("preliminares:campo", kwargs={"contrato_id": contrato_construccion.id})

    response = authenticated_client.post(url, {
        "torre_id": str(torre_contrato.id),
        "campo": "acta_vecindad",
        "valor": "2026-07-01",
    })

    assert response.status_code == 204
    pred = PredialTorre.objects.get(torre=torre_contrato)
    assert pred.acta_vecindad.isoformat() == "2026-07-01"


@pytest.mark.django_db
def test_dos_ediciones_consecutivas_ambiental_marcar_y_desmarcar_na(authenticated_client, contrato_construccion, torre_contrato):
    """(b) dos ediciones consecutivas sobre el mismo campo ambiental (marcar
    N/A, luego desmarcar) ambas persisten. Antes del fix, la SEGUNDA edición
    fallaba en silencio en el navegador porque htmx perdía su hx-target — a
    nivel de backend cada POST es independiente, así que este test valida el
    contrato del backend; el fix de template es lo que hace que el navegador
    realmente dispare la segunda request (cubierto arriba por
    test_campo_ambiental_partial_is_self_contained_campo_flex)."""
    url = reverse("preliminares:campo_ambiental", kwargs={"contrato_id": contrato_construccion.id})

    # 1ra edición: marcar N/A
    resp1 = authenticated_client.post(url, {
        "torre_id": str(torre_contrato.id),
        "campo": "ahuyentamiento",
        "valor": "NA",
    })
    assert resp1.status_code == 200
    amb = AmbientalTorre.objects.get(torre=torre_contrato)
    assert amb.ahuyentamiento == "NA"
    # La respuesta debe traer el wrapper campo-flex para que la SIGUIENTE
    # edición tenga un target válido en el navegador real.
    assert 'class="campo-flex' in resp1.content.decode()

    # 2da edición: desmarcar N/A (volver a vacío)
    resp2 = authenticated_client.post(url, {
        "torre_id": str(torre_contrato.id),
        "campo": "ahuyentamiento",
        "valor": "",
    })
    assert resp2.status_code == 200
    amb.refresh_from_db()
    assert amb.ahuyentamiento == ""
    assert 'class="campo-flex' in resp2.content.decode()


@pytest.mark.django_db
def test_edicion_ambiental_choice_conserva_wrapper_para_siguiente_swap(authenticated_client, contrato_construccion, torre_contrato):
    """Cualquier tipo de campo ambiental (no solo date_or_na) debe devolver
    un wrapper .campo-flex, porque hx-target="closest .campo-flex" aplica a
    todos los tipos."""
    url = reverse("preliminares:campo_ambiental", kwargs={"contrato_id": contrato_construccion.id})

    resp = authenticated_client.post(url, {
        "torre_id": str(torre_contrato.id),
        "campo": "arqueologia_poligonos",
        "valor": "OK",
    })
    assert resp.status_code == 200
    assert 'class="campo-flex' in resp.content.decode()

    amb = AmbientalTorre.objects.get(torre=torre_contrato)
    assert amb.arqueologia_poligonos == "OK"
