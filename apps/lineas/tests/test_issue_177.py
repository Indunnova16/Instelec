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

from apps.lineas.models import Vano, VanoHistorialEstado, VanoHistorialFoto


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


@pytest.mark.django_db
class TestVanoHistorialModelsIssue177:
    """A2 — VanoHistorialEstado / VanoHistorialFoto."""

    def test_crear_historial_sin_fotos(self, linea, admin_user):
        vano = Vano.objects.create(linea=linea, numero='201')
        historial = VanoHistorialEstado.objects.create(
            vano=vano, usuario=admin_user, estado=Vano.Estado.EJECUTADO, nota='Listo.'
        )
        assert historial.pk is not None
        assert historial.fotos.count() == 0

    def test_crear_historial_con_n_fotos(self, linea, admin_user):
        vano = Vano.objects.create(linea=linea, numero='202')
        historial = VanoHistorialEstado.objects.create(
            vano=vano, usuario=admin_user, estado=Vano.Estado.SECCIONADO, nota='2 fotos.'
        )
        VanoHistorialFoto.objects.create(historial=historial, imagen='campo/vanos/historial/a.jpg')
        VanoHistorialFoto.objects.create(historial=historial, imagen='campo/vanos/historial/b.jpg')
        assert historial.fotos.count() == 2
        nombres = sorted(f.imagen.name for f in historial.fotos.all())
        assert nombres == ['campo/vanos/historial/a.jpg', 'campo/vanos/historial/b.jpg']

    def test_vano_historial_ordenado_desc_por_fecha(self, linea, admin_user):
        vano = Vano.objects.create(linea=linea, numero='203')
        h1 = VanoHistorialEstado.objects.create(
            vano=vano, usuario=admin_user, estado=Vano.Estado.PENDIENTE
        )
        h2 = VanoHistorialEstado.objects.create(
            vano=vano, usuario=admin_user, estado=Vano.Estado.EJECUTADO
        )
        ids = list(vano.historial.values_list('id', flat=True))
        assert ids == [h2.id, h1.id]

    def test_estado_no_ejecutado_valido_en_modelo_aunque_no_seleccionable(self, linea):
        """El value legacy 'no_ejecutado' sigue siendo válido a nivel de modelo
        (el backfill A3 lo necesita para el vano legacy), aunque no aparezca
        en seleccionables()."""
        vano = Vano.objects.create(linea=linea, numero='204', estado=Vano.Estado.NO_EJECUTADO)
        historial = VanoHistorialEstado.objects.create(
            vano=vano, estado=Vano.Estado.NO_EJECUTADO, nota=''
        )
        historial.full_clean()  # no debe lanzar ValidationError por choices
        assert historial.estado == 'no_ejecutado'
