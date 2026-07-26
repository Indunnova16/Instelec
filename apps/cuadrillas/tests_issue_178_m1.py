"""Tests #178 — Sprint (2026-07-25), sub-item M1: migraciones aditivas
consolidadas (apps/cuadrillas/migrations/0024_migraciones_aditivas_m1_178.py).

Issue: Indunnova16/Instelec#178

M1 agrega, todos nullable/blank y sin backfill destructivo:
  - Cuadrilla.fecha_fin (DateField)
  - Cuadrilla.reprogramado_desde (FK self, SET_NULL)
  - Cuadrilla.hora_inicio_planeada / hora_fin_planeada (TimeField)
  - TrackingUbicacion.origen (CharField choices auto|manual, default='auto')

M1 es la migración base de la que dependen A1, D1, C1 y F2 (sub-items
siguientes del mismo sprint) — el objetivo de esta suite es probar
EXCLUSIVAMENTE que la migración es aditiva y no rompe filas ya cargadas
(bloques/miembros/tracking pre-existentes). El comportamiento funcional de
cada campo (exportador A2, form D1, botón reprogramar C1, ubicación manual
F2) se cubre en su propio sub-item / en la suite consolidada T1
(tests_issue_178_demo0725.py).

Ejecutar:
  DJANGO_SETTINGS_MODULE=config.settings.local \
    venv/bin/python -m pytest apps/cuadrillas/tests_issue_178_m1.py -v \
    -o python_files="tests_*.py test_*.py"
"""
from datetime import date, time

import pytest
from django.core.exceptions import ValidationError

from apps.cuadrillas.models import Cuadrilla, CuadrillaMiembro, TrackingUbicacion
from apps.cuadrillas.tests_s18 import _crear_usuario


def _crear_cuadrilla(codigo, **extra):
    defaults = {'nombre': codigo, 'activa': True}
    defaults.update(extra)
    return Cuadrilla.objects.create(codigo=codigo, **defaults)


def _crear_tracking(cuadrilla, usuario, **extra):
    defaults = {
        'latitud': '10.00000000',
        'longitud': '-75.00000000',
    }
    defaults.update(extra)
    return TrackingUbicacion.objects.create(cuadrilla=cuadrilla, usuario=usuario, **defaults)


@pytest.mark.django_db
class TestM1MigracionesAditivas:
    """Sub-item M1 — migración aditiva consolidada, cero backfill destructivo."""

    def test_migraciones_aditivas_no_rompen_filas_existentes(self):
        """El requisito explícito del sub-item: una fila creada como si fuera
        LEGACY (sin tocar los campos nuevos, exactamente como quedaban las
        filas antes de esta migración) debe seguir leyéndose sin romper —
        campos nuevos en None / 'auto', ningún IntegrityError ni excepción al
        recargar desde BD."""
        usuario = _crear_usuario('1143246675', 'JHON JAIRO JIMENEZ')
        cuadrilla_legacy = _crear_cuadrilla('CUA-LEGACY-178')
        CuadrillaMiembro.objects.create(
            cuadrilla=cuadrilla_legacy,
            usuario=usuario,
            rol_cuadrilla_id='LINIERO_I',
            cargo='MIEMBRO',
            costo_dia=0,
            fecha_inicio=date.today(),
            activo=True,
        )
        tracking_legacy = _crear_tracking(cuadrilla_legacy, usuario)

        # Recargar EXPLÍCITAMENTE desde BD (no confiar en la instancia en
        # memoria) — es lo que garantiza que el esquema post-migración lee
        # bien filas que nunca tocaron los campos nuevos.
        cuadrilla_db = Cuadrilla.objects.get(pk=cuadrilla_legacy.pk)
        tracking_db = TrackingUbicacion.objects.get(pk=tracking_legacy.pk)

        assert cuadrilla_db.fecha_fin is None
        assert cuadrilla_db.reprogramado_desde is None
        assert cuadrilla_db.hora_inicio_planeada is None
        assert cuadrilla_db.hora_fin_planeada is None
        assert tracking_db.origen == 'auto'
        # El miembro y la cuadrilla siguen íntegros — la migración no tocó
        # ningún dato pre-existente.
        assert cuadrilla_db.miembros.count() == 1
        assert cuadrilla_db.miembros.filter(usuario__documento='1143246675').exists()

    def test_happy_nuevos_campos_se_persisten(self):
        """Happy path: los 4 campos nuevos de Cuadrilla + el nuevo campo de
        TrackingUbicacion se pueden setear explícitamente y se recuperan tal
        cual tras un reload."""
        usuario = _crear_usuario('1004487321', 'KEINER SERRANO')
        origen_cuadrilla = _crear_cuadrilla('CUA-ORIGEN-178')
        cuadrilla = _crear_cuadrilla(
            'CUA-NUEVA-178',
            fecha_fin=date(2026, 8, 1),
            hora_inicio_planeada=time(7, 0),
            hora_fin_planeada=time(15, 0),
            reprogramado_desde=origen_cuadrilla,
        )
        tracking = _crear_tracking(cuadrilla, usuario, origen=TrackingUbicacion.OrigenUbicacion.MANUAL)

        cuadrilla_db = Cuadrilla.objects.get(pk=cuadrilla.pk)
        tracking_db = TrackingUbicacion.objects.get(pk=tracking.pk)

        assert cuadrilla_db.fecha_fin == date(2026, 8, 1)
        assert cuadrilla_db.hora_inicio_planeada == time(7, 0)
        assert cuadrilla_db.hora_fin_planeada == time(15, 0)
        assert cuadrilla_db.reprogramado_desde_id == origen_cuadrilla.pk
        assert tracking_db.origen == 'manual'

    def test_edge_reprogramado_desde_set_null_al_borrar_origen(self):
        """FK self con on_delete=SET_NULL: si el bloque origen se elimina, la
        referencia del bloque reprogramado NO debe romper (ni el delete ni
        una lectura posterior) — queda en None."""
        origen = _crear_cuadrilla('CUA-ORIGEN-DEL-178')
        nueva = _crear_cuadrilla('CUA-REPROG-DEL-178', reprogramado_desde=origen)

        origen.delete()

        nueva.refresh_from_db()
        assert nueva.reprogramado_desde_id is None
        # El bloque reprogramado sigue existiendo — SET_NULL, no CASCADE.
        assert Cuadrilla.objects.filter(pk=nueva.pk).exists()

    def test_edge_origen_choices_invalido_no_pasa_full_clean(self):
        """El choices de TrackingUbicacion.origen es una validación real, no
        solo cosmética: un valor fuera de auto|manual debe fallar full_clean
        (defensa contra un futuro caller que escriba un string arbitrario)."""
        usuario = _crear_usuario('1093293706', 'SNEYDER JEREZ')
        cuadrilla = _crear_cuadrilla('CUA-CHOICES-178')
        tracking = TrackingUbicacion(
            cuadrilla=cuadrilla,
            usuario=usuario,
            latitud='10.00000000',
            longitud='-75.00000000',
            origen='satelite',
        )
        with pytest.raises(ValidationError):
            tracking.full_clean()
