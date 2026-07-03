"""Issue #177 (sub-items A1, A2, A3) — Vano.Estado ampliado + historial de trazabilidad.

Cobertura:
- A1: Vano.Estado 7 choices (aditivo, retiene 'no_ejecutado') + seleccionables()
  (6 valores, sin 'no_ejecutado').
- A2: Modelos VanoHistorialEstado / VanoHistorialFoto — creación, FK inversas,
  orden, valor legacy 'no_ejecutado' válido en el modelo aunque no seleccionable.
- A3: Backfill de historial (migración 0016, RunPython) — SOLO INSERT, cero
  UPDATE/DELETE sobre `vanos`, idempotente.

Los tests de los endpoints (A4/A5), el modal (A6/A7) y el journey E2E viven en
apps/campo/tests_issue_177.py (sub-item A11) — ese archivo ya es dedicado a
este issue y no colisiona con Instelec#179/#182 del mismo RUN.
"""
from __future__ import annotations

import pytest

from apps.lineas.models import Vano


@pytest.mark.django_db
class TestVanoEstadoEnumIssue177:
    """A1 — Vano.Estado ampliado a 7 choices, seleccionables() = 6 sin 'no_ejecutado'."""

    def test_estado_choices_tiene_7_tuplas(self):
        assert len(Vano.Estado.choices) == 7
        labels = dict(Vano.Estado.choices)
        assert labels['no_ejecutado'] == 'No Ejecutado'
        assert labels['seccionado'] == 'Seccionado'
        assert labels['especial'] == 'Especial'

    def test_seleccionables_tiene_6_sin_no_ejecutado(self):
        seleccionables = Vano.Estado.seleccionables()
        assert len(seleccionables) == 6
        valores = [v for v, _ in seleccionables]
        assert 'no_ejecutado' not in valores
        assert 'seccionado' in valores
        assert 'especial' in valores
        assert 'pendiente' in valores

    def test_regresion_en_espera_label_parcial(self):
        """Regresión del rename anterior (En Espera -> Parcial, mismo value)."""
        assert Vano.Estado.EN_ESPERA.label == 'Parcial'
        assert Vano.Estado.EN_ESPERA.value == 'en_espera'
