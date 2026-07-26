"""Tests #178 — Sprint (2026-07-25), sub-item A1: persistir ``fecha_fin`` real
al importar S18.

Issue: Indunnova16/Instelec#178

``ProgramacionS18CuadrillaImporter._guardar_bloque`` ya parseaba
``bloque['fecha_fin']`` (columna FIN del Excel S18) pero la descartaba al
crear/actualizar la ``Cuadrilla`` — A1 la persiste en el campo nuevo
``Cuadrilla.fecha_fin`` (nullable, agregado por M1).

Ejecutar:
  DJANGO_SETTINGS_MODULE=config.settings.local \
    python3.12 -m pytest apps/cuadrillas/tests_issue_178_a1.py -v \
    -o python_files="tests_*.py test_*.py"
"""

from datetime import date

import pytest

from apps.cuadrillas.importers import ProgramacionS18CuadrillaImporter
from apps.cuadrillas.models import Cuadrilla
from apps.cuadrillas.tests_s18 import _act, _build_s18_excel, _crear_linea, _crear_usuario


@pytest.mark.django_db
class TestA1PersistirFechaFin:
    """Sub-item A1 — INICIO+FIN reales del Excel S18 se persisten en
    Cuadrilla.fecha_fin (antes se descartaban)."""

    def test_happy_fila_con_inicio_y_fin_persiste_fecha_fin(self):
        _crear_linea("LN817")
        _crear_usuario("1143246675", "JHON JAIRO JIMENEZ")

        excel = _build_s18_excel(
            [
                _act(
                    1,
                    "Servidumbre Completa",
                    "817",
                    date(2026, 4, 27),
                    date(2026, 5, 3),
                    "JHON JAIRO JIMENEZ",
                    "1143246675",
                    "LINIERO I",
                    "JT/CTA",
                ),
            ]
        )

        res = ProgramacionS18CuadrillaImporter().importar(excel)
        assert res["exito"] is True

        cuad = Cuadrilla.objects.get()
        assert cuad.fecha == date(2026, 4, 27)
        assert cuad.fecha_fin == date(2026, 5, 3)

    def test_edge_fila_sin_fin_deja_fecha_fin_none(self):
        """Columna FIN vacía en el Excel (bloques legacy o filas incompletas
        del cliente) — no debe romper el import, fecha_fin queda en None."""
        _crear_linea("LN817")
        _crear_usuario("1143246675", "JHON JAIRO JIMENEZ")

        excel = _build_s18_excel(
            [
                _act(
                    1,
                    "Servidumbre Completa",
                    "817",
                    date(2026, 4, 27),
                    None,
                    "JHON JAIRO JIMENEZ",
                    "1143246675",
                    "LINIERO I",
                    "JT/CTA",
                ),
            ]
        )

        res = ProgramacionS18CuadrillaImporter().importar(excel)
        assert res["exito"] is True

        cuad = Cuadrilla.objects.get()
        assert cuad.fecha == date(2026, 4, 27)
        assert cuad.fecha_fin is None

    def test_edge_reimport_con_actualizar_persiste_fecha_fin_nueva(self):
        """Re-import con actualizar_existentes=True (rerun idempotente, mismo
        patrón que test_rerun_idempotente_con_actualizar de tests_s18.py)
        también debe persistir/actualizar fecha_fin en la rama de UPDATE, no
        solo en CREATE."""
        _crear_linea("LN817")
        _crear_usuario("1143246675", "JHON JAIRO JIMENEZ")

        def _excel(fin):
            return _build_s18_excel(
                [
                    _act(
                        1,
                        "Servidumbre Completa",
                        "817",
                        date(2026, 4, 27),
                        fin,
                        "JHON JAIRO JIMENEZ",
                        "1143246675",
                        "LINIERO I",
                        "JT/CTA",
                    ),
                ]
            )

        ProgramacionS18CuadrillaImporter().importar(_excel(date(2026, 5, 3)))
        cuad = Cuadrilla.objects.get()
        assert cuad.fecha_fin == date(2026, 5, 3)

        res2 = ProgramacionS18CuadrillaImporter().importar(
            _excel(date(2026, 5, 10)), {"actualizar_existentes": True}
        )
        assert res2["cuadrillas_actualizadas"] == 1
        assert Cuadrilla.objects.count() == 1
        cuad.refresh_from_db()
        assert cuad.fecha_fin == date(2026, 5, 10)
