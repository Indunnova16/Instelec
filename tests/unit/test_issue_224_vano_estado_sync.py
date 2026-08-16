"""Regresiones de UI para Instelec#224.

El E2E del RUN usa un vano legacy real de LN829; estas pruebas mantienen los
contratos de DOM y de sincronización que ese journey necesita.
"""

from pathlib import Path


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
    assert "this.cerrar()" in modal


def test_dashboard_listener_updates_card_counts_and_chart_without_reload():
    content = (TEMPLATES / "avance_registrar.html").read_text(encoding="utf-8")

    assert "document.addEventListener('vano-actualizado'" in content
    assert "estadoData[anterior]" in content
    assert "estadoChart.update()" in content
    assert "document.getElementById(`vano-${vanoId}`)" in content
    assert "border-green-300" in content
