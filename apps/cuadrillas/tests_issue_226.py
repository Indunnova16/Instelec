"""Regression tests for the shared vehicle catalogue in issue #226."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from apps.cuadrillas.models import Vehiculo


class TestVehiculoCatalogoEstado(TestCase):
    def test_persiste_descripcion_y_estado_mantenimiento(self):
        vehiculo = Vehiculo.objects.create(
            placa='226-MOTO-01',
            marca='Honda',
            tipo=Vehiculo.TipoVehiculo.MOTO,
            descripcion='Moto de apoyo para inspecciones',
            estado=Vehiculo.Estado.EN_MANTENIMIENTO,
            observaciones='Pendiente cambio de llanta',
        )

        vehiculo.refresh_from_db()

        self.assertEqual(vehiculo.descripcion, 'Moto de apoyo para inspecciones')
        self.assertEqual(vehiculo.estado, Vehiculo.Estado.EN_MANTENIMIENTO)
        self.assertFalse(vehiculo.activo)

    def test_actualizacion_legacy_de_activo_actualiza_estado(self):
        vehiculo = Vehiculo.objects.create(placa='226-LEGACY-01', marca='Toyota')

        vehiculo.activo = False
        vehiculo.save(update_fields=['activo'])
        vehiculo.refresh_from_db()

        self.assertEqual(vehiculo.estado, Vehiculo.Estado.INACTIVO)
        self.assertFalse(vehiculo.activo)

    def test_placa_sigue_siendo_unica(self):
        Vehiculo.objects.create(placa='226-UNICA-01', marca='Nissan')

        with self.assertRaises(Exception):
            Vehiculo.objects.create(placa='226-UNICA-01', marca='Toyota')


class TestVehiculoMigrationLegacy(TransactionTestCase):
    """The additive migration maps legacy ``activo=False`` rows to INACTIVO."""

    reset_sequences = True

    def test_registros_legacy_conservan_estado_operativo(self):
        executor = MigrationExecutor(connection)
        previous = [('cuadrillas', '0027_issue_223_tramo_libre')]
        latest = [('cuadrillas', '0028_vehiculo_catalogo_estado')]

        executor.migrate(previous)
        legacy_apps = executor.loader.project_state(previous).apps
        LegacyVehiculo = legacy_apps.get_model('cuadrillas', 'Vehiculo')
        LegacyVehiculo.objects.create(placa='226-ANTES-01', marca='Legacy activo', activo=True)
        LegacyVehiculo.objects.create(placa='226-ANTES-02', marca='Legacy inactivo', activo=False)

        executor.migrate(latest)
        migrated_apps = executor.loader.project_state(latest).apps
        VehiculoMigrado = migrated_apps.get_model('cuadrillas', 'Vehiculo')

        self.assertEqual(
            VehiculoMigrado.objects.get(placa='226-ANTES-01').estado,
            Vehiculo.Estado.ACTIVO,
        )
        self.assertEqual(
            VehiculoMigrado.objects.get(placa='226-ANTES-02').estado,
            Vehiculo.Estado.INACTIVO,
        )
