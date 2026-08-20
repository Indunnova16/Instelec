"""Regresiones de UI para Instelec#224.

El E2E del RUN usa un vano legacy real de LN829; estas pruebas mantienen los
contratos de DOM y de sincronización que ese journey necesita.
"""

from pathlib import Path

import pytest
from django.urls import reverse

from apps.lineas.models import Vano
from apps.lineas.models_b21 import VanoSemestre

TEMPLATES = Path("templates/campo")


def test_dashboard_exposes_stable_live_stat_counter_ids():
    content = (TEMPLATES / "avance_registrar.html").read_text(encoding="utf-8")

    for estado in (
        "pendiente",
        "ejecutado",
        "sin_permiso",
        "en_espera",
        "seccionado",
        "especial",
    ):
        assert f'id="stat-count-{estado}"' in content


def test_successful_modal_save_notifies_page_and_teleports_out_of_scroll_container():
    modal = (TEMPLATES / "partials/_vano_estado_modal.html").read_text(encoding="utf-8")

    assert '<template x-teleport="body">' in modal
    assert "new CustomEvent('vano-actualizado'" in modal
    assert "document.body.dispatchEvent" in modal
    assert "vanoId: this.vanoId" in modal
    assert "estado: data.estado" in modal
    assert "semestre: data.semestre || ''" in modal
    assert "this.cerrar()" in modal


def test_dashboard_listener_updates_card_counts_and_chart_without_reload():
    content = (TEMPLATES / "avance_registrar.html").read_text(encoding="utf-8")

    assert "document.addEventListener('vano-actualizado'" in content
    assert "estadoData[anterior]" in content
    assert "estadoChart.update()" in content
    assert "document.getElementById(`vano-${vanoId}`)" in content
    assert "border-green-300" in content
    assert "const semestreActivo" in content
    assert "(semestre || '') !== semestreActivo" in content


def test_modal_uses_global_event_to_keep_only_one_open():
    modal = (TEMPLATES / "partials/_vano_estado_modal.html").read_text(encoding="utf-8")

    assert "vano-modal-abierto" in modal
    assert "event.detail.vanoId !== this.vanoId" in modal


@pytest.mark.django_db
def test_semester_post_updates_legacy_vano_and_its_active_semester(admin_client, linea):
    vano = Vano.objects.create(linea=linea, numero="224", estado=Vano.Estado.PENDIENTE)
    s1 = VanoSemestre.objects.create(vano=vano, semestre=VanoSemestre.Semestre.S1)
    s2 = VanoSemestre.objects.create(
        vano=vano,
        semestre=VanoSemestre.Semestre.S2,
        estado=VanoSemestre.Estado.SIN_PERMISO,
    )

    response = admin_client.post(
        reverse("campo:vano_historial_crear", kwargs={"pk": vano.pk}),
        {"estado": Vano.Estado.EJECUTADO, "semestre": "S1"},
    )

    assert response.status_code == 200
    assert response.json()["semestre"] == "S1"
    vano.refresh_from_db()
    s1.refresh_from_db()
    s2.refresh_from_db()
    assert vano.estado == Vano.Estado.EJECUTADO
    assert s1.estado == VanoSemestre.Estado.EJECUTADO
    assert s2.estado == VanoSemestre.Estado.SIN_PERMISO


@pytest.mark.django_db
def test_semester_grid_renders_card_from_vano_semestre_not_global_state(admin_client, linea):
    vano = Vano.objects.create(linea=linea, numero="225", estado=Vano.Estado.PENDIENTE)
    VanoSemestre.objects.create(
        vano=vano,
        semestre=VanoSemestre.Semestre.S1,
        estado=VanoSemestre.Estado.EJECUTADO,
    )

    response = admin_client.get(
        reverse("campo:avance_registrar"),
        {"linea_id": str(linea.id), "semestre": "S1"},
    )

    assert response.status_code == 200
    card = response.content.decode().split(f'id="vano-{vano.id}"', 1)[1][:1500]
    assert "bg-green-50" in card
    assert "Ejecutado" in card
