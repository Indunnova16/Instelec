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

import importlib.util
from pathlib import Path

import pytest
from django.apps import apps as django_apps

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


def _cargar_modulo_migracion(nombre_archivo: str):
    """Carga un módulo de migración por nombre de archivo (no son paquetes
    importables normalmente por empezar con dígitos)."""
    ruta = Path(__file__).resolve().parent.parent / 'migrations' / nombre_archivo
    spec = importlib.util.spec_from_file_location(f'lineas_migration_{ruta.stem}', ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.mark.django_db
class TestVanoHistorialBackfillMigration:
    """A3 — backfill de historial (migración 0016, RunPython).

    ``--nomigrations`` está activo en pytest (pyproject.toml) así que el
    RunPython nunca se ejecuta solo por aplicar migraciones en tests: se
    invoca la función directamente contra el registro de apps real (mismo
    approach que ``apps.get_model`` usaría dentro de una migración real,
    con el mismo esquema porque no hubo drift de campos desde 0016).
    """

    @pytest.fixture
    def migracion(self):
        return _cargar_modulo_migracion('0016_vano_historial_backfill.py')

    def test_vano_legacy_no_ejecutado_genera_historial_sin_remapear(self, linea, migracion):
        vano = Vano.objects.create(
            linea=linea, numero='300', estado=Vano.Estado.NO_EJECUTADO, observaciones=''
        )

        migracion.backfill_historial(django_apps, None)

        vano.refresh_from_db()
        historial = list(vano.historial.all())
        assert len(historial) == 1
        assert historial[0].estado == 'no_ejecutado'  # AS-IS, sin remapear

    def test_backfill_no_muta_vano(self, linea, admin_user, migracion):
        vano = Vano.objects.create(
            linea=linea,
            numero='301',
            estado=Vano.Estado.SIN_PERMISO,
            observaciones='Predio cerrado.',
            marcado_por=admin_user,
        )
        antes = (vano.estado, vano.observaciones, bool(vano.foto))

        migracion.backfill_historial(django_apps, None)

        vano.refresh_from_db()
        despues = (vano.estado, vano.observaciones, bool(vano.foto))
        assert antes == despues

    def test_backfill_es_idempotente(self, linea, migracion):
        vano = Vano.objects.create(linea=linea, numero='302', estado=Vano.Estado.EJECUTADO)

        migracion.backfill_historial(django_apps, None)
        migracion.backfill_historial(django_apps, None)  # correr 2 veces

        assert vano.historial.count() == 1

    def test_vano_limpio_no_genera_historial_basura(self, linea, migracion):
        vano = Vano.objects.create(linea=linea, numero='303')  # pendiente, sin señales

        migracion.backfill_historial(django_apps, None)

        assert vano.historial.count() == 0
