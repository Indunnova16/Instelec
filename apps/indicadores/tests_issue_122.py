"""
Tests #122 — Indicadores: comentario Django multilínea fugado en el dashboard.

Bug (reproceso QG#107): `templates/indicadores/dashboard.html` tenía un
comentario `{# ... #}` de DOS líneas. En Django el tag `{# #}` es de UNA sola
línea: la 2ª línea se renderizaba como TEXTO VISIBLE en la página
(`#122: ... reutilizan los partials ...`). El fix lo convierte a
`{% comment %}...{% endcomment %}`, que sí es multilínea.

Estrategia: renderizar el bloque `content` de `dashboard.html` a través del
motor de plantillas de Django con un `base.html` stub temporal (sin DB ni auth),
de modo que el test reproduce el render real del template fuente del bug y los
`{% include %}` de los partials técnico-financieros / ANS (que renderizan su
estructura completa con context vacío gracias a sus `{% empty %}`).
"""
import tempfile
from pathlib import Path

import pytest
from django.conf import settings
from django.template.loader import render_to_string
from django.test import override_settings


def _render_dashboard():
    """Renderiza dashboard.html con un base.html stub que solo expone `content`."""
    stub_dir = Path(tempfile.mkdtemp())
    # base.html stub: renderiza únicamente el bloque content del dashboard.
    (stub_dir / "base.html").write_text(
        "{% block title %}{% endblock %}"
        "{% block extra_head %}{% endblock %}"
        "{% block content %}{% endblock %}"
        "{% block extra_scripts %}{% endblock %}"
        "{% block extra_js %}{% endblock %}",
        encoding="utf-8",
    )

    templates = [dict(t) for t in settings.TEMPLATES]
    # El stub_dir va PRIMERO para que sombree el base.html real.
    templates[0]["DIRS"] = [str(stub_dir)] + list(templates[0]["DIRS"])

    with override_settings(TEMPLATES=templates):
        from django.template import engines
        engines._engines = {}  # forzar recarga con los DIRS nuevos
        return render_to_string(
            "indicadores/dashboard.html",
            {
                "indicadores_tecnico_financieros": [],
                "indicadores_ans": [],
                "ans_total_ponderado": None,
            },
        )


@pytest.fixture
def dashboard_html():
    html = _render_dashboard()
    # restaurar el cache de engines tras el override_settings
    from django.template import engines
    engines._engines = {}
    return html


def test_comentario_122_no_se_fuga_como_texto(dashboard_html):
    """La 2ª línea del comentario ya NO debe aparecer como texto visible."""
    assert "#122:" not in dashboard_html
    assert "reutilizan los partials" not in dashboard_html
    # tokens del comentario fugado (cualquier variante de la 2ª línea)
    assert "misma fuente de verdad" not in dashboard_html


def test_dashboard_sigue_renderizando_indicadores_tecnico_financieros(dashboard_html):
    """El partial técnico-financiero sigue incluido y renderiza su encabezado."""
    assert "Indicadores Técnico-Financieros" in dashboard_html
