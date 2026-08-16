"""Regression tests for the shared vehicle catalogue in issue #226."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from apps.cuadrillas.models import Cuadrilla, Vehiculo


Usuario = get_user_model()


def _usuario_226(email, rol='admin'):
    return Usuario.objects.create_user(
        email=email,
        password='testpass123!',
        first_name='Usuario',
        last_name='226',
        rol=rol,
        is_staff=rol == 'admin',
        is_superuser=rol == 'admin',
    )


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


class TestVehiculoCRUDParametrizacion(TestCase):
    """A2: creación, detalle, edición y cambio de estado del catálogo."""

    def setUp(self):
        self.client = Client()
        self.client.force_login(_usuario_226('admin_226@test.com'))

    def _datos(self, **overrides):
        datos = {
            'placa': 'abc226',
            'marca': 'Toyota',
            'tipo': Vehiculo.TipoVehiculo.CAMIONETA,
            'descripcion': 'Vehículo de operación',
            'estado': Vehiculo.Estado.ACTIVO,
            'observaciones': 'Revisión vigente',
            'modelo': 'Hilux',
            'ano': '2024',
            'capacidad_personas': '5',
            'costo_dia': '120000.00',
        }
        datos.update(overrides)
        return datos

    def test_crear_muestra_detalle_y_normaliza_placa(self):
        respuesta = self.client.post(reverse('core:vehiculos_crear'), self._datos())
        self.assertEqual(respuesta.status_code, 302)
        vehiculo = Vehiculo.objects.get(placa='ABC226')
        detalle = self.client.get(reverse('core:vehiculos_detalle', args=[vehiculo.pk]))
        self.assertContains(detalle, 'Vehículo de operación')
        self.assertContains(detalle, 'Cambiar estado')

    def test_editar_y_cambiar_estado_actualizan_activo_legacy(self):
        vehiculo = Vehiculo.objects.create(placa='226-EDIT', marca='Chevrolet')
        editar = self.client.post(
            reverse('core:vehiculos_editar', args=[vehiculo.pk]),
            self._datos(placa='226-EDIT', marca='Chevrolet Actualizada', estado=Vehiculo.Estado.ACTIVO),
        )
        self.assertEqual(editar.status_code, 302)
        estado = self.client.post(
            reverse('core:vehiculos_estado', args=[vehiculo.pk]),
            {'estado': Vehiculo.Estado.EN_MANTENIMIENTO},
        )
        self.assertEqual(estado.status_code, 302)
        vehiculo.refresh_from_db()
        self.assertEqual(vehiculo.marca, 'Chevrolet Actualizada')
        self.assertEqual(vehiculo.estado, Vehiculo.Estado.EN_MANTENIMIENTO)
        self.assertFalse(vehiculo.activo)

    def test_requeridos_y_placa_duplicada_re_renderizan_con_error_de_dominio(self):
        vacio = self.client.post(reverse('core:vehiculos_crear'), self._datos(placa='', marca=''))
        self.assertEqual(vacio.status_code, 200)
        self.assertIn('placa', vacio.context['form'].errors)
        self.assertIn('marca', vacio.context['form'].errors)

        Vehiculo.objects.create(placa='DUP-226', marca='Nissan')
        duplicado = self.client.post(reverse('core:vehiculos_crear'), self._datos(placa='dup-226'))
        self.assertEqual(duplicado.status_code, 200)
        self.assertIn('Ya existe un vehículo', duplicado.context['form'].errors['placa'][0])
        self.assertEqual(Vehiculo.objects.filter(placa__iexact='DUP-226').count(), 1)

    def test_usuario_sin_rol_autorizado_no_puede_crear_ni_cambiar_estado(self):
        vehiculo = Vehiculo.objects.create(placa='DEN-226', marca='Mazda')
        self.client.force_login(_usuario_226('supervisor_226@test.com', rol='supervisor'))
        with self.assertRaises(PermissionDenied):
            self.client.get(reverse('core:vehiculos_crear'))
        with self.assertRaises(PermissionDenied):
            self.client.post(
                reverse('core:vehiculos_estado', args=[vehiculo.pk]),
                {'estado': Vehiculo.Estado.INACTIVO},
            )


class TestVehiculoListadoYEliminacion(TestCase):
    """A3: listado filtrable y eliminación segura del maestro."""

    def setUp(self):
        self.client = Client()
        self.client.force_login(_usuario_226('listado_admin_226@test.com'))
        self.activo = Vehiculo.objects.create(placa='ABC-226', marca='Toyota', tipo=Vehiculo.TipoVehiculo.CAMIONETA)
        self.mantenimiento = Vehiculo.objects.create(placa='MOTO-226', marca='Honda', tipo=Vehiculo.TipoVehiculo.MOTO, estado=Vehiculo.Estado.EN_MANTENIMIENTO)

    def test_listado_combina_filtros_y_muestra_acciones(self):
        respuesta = self.client.get(reverse('core:vehiculos_lista'), {'placa': 'moto', 'marca': 'hon', 'tipo': Vehiculo.TipoVehiculo.MOTO, 'estado': Vehiculo.Estado.EN_MANTENIMIENTO})
        self.assertContains(respuesta, 'MOTO-226')
        self.assertNotContains(respuesta, 'ABC-226')
        self.assertContains(respuesta, 'Ver detalle')
        self.assertContains(respuesta, 'Editar')
        self.assertContains(respuesta, 'Eliminar')

    def test_filtro_invalido_no_falla(self):
        respuesta = self.client.get(reverse('core:vehiculos_lista'), {'tipo': 'NO_EXISTE'})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(list(respuesta.context['vehiculos']), [self.activo, self.mantenimiento])

    def test_eliminar_bloquea_vehiculo_asignado_a_cuadrilla_activa(self):
        Cuadrilla.objects.create(codigo='CUA-226-A', nombre='Activa 226', vehiculo=self.activo, activa=True)
        respuesta = self.client.post(reverse('core:vehiculos_eliminar', args=[self.activo.pk]), follow=True)
        self.assertContains(respuesta, 'está asignado a una cuadrilla activa')
        self.assertContains(respuesta, 'Inactivar vehículo')
        self.assertContains(respuesta, 'No se eliminó para preservar la operación')
        self.assertTrue(Vehiculo.objects.filter(pk=self.activo.pk).exists())

    def test_inactivar_desde_advertencia_retiro_de_nuevas_asignaciones(self):
        Cuadrilla.objects.create(codigo='CUA-226-I', nombre='Activa para inactivar', vehiculo=self.activo, activa=True)
        bloqueo = self.client.post(reverse('core:vehiculos_eliminar', args=[self.activo.pk]), follow=True)
        self.assertContains(bloqueo, 'Inactivar vehículo')

        respuesta = self.client.post(
            reverse('core:vehiculos_estado', args=[self.activo.pk]),
            {'estado': Vehiculo.Estado.INACTIVO},
            follow=True,
        )

        self.assertContains(respuesta, 'actualizado a Inactivo')
        self.activo.refresh_from_db()
        self.assertEqual(self.activo.estado, Vehiculo.Estado.INACTIVO)
        self.assertFalse(self.activo.activo)

    def test_eliminar_vehiculo_sin_asignacion_activa(self):
        respuesta = self.client.post(reverse('core:vehiculos_eliminar', args=[self.mantenimiento.pk]), follow=True)
        self.assertContains(respuesta, 'eliminado exitosamente')
        self.assertFalse(Vehiculo.objects.filter(pk=self.mantenimiento.pk).exists())

    def test_eliminar_acepta_referencia_historica_inactiva(self):
        Cuadrilla.objects.create(codigo='CUA-226-H', nombre='Histórica 226', vehiculo=self.mantenimiento, activa=False)

        respuesta = self.client.post(reverse('core:vehiculos_eliminar', args=[self.mantenimiento.pk]), follow=True)

        self.assertContains(respuesta, 'eliminado exitosamente')
        self.assertFalse(Vehiculo.objects.filter(pk=self.mantenimiento.pk).exists())
        self.assertIsNone(Cuadrilla.objects.get(codigo='CUA-226-H').vehiculo)

    def test_supervisor_no_puede_eliminar(self):
        self.client.force_login(_usuario_226('listado_supervisor_226@test.com', rol='supervisor'))
        with self.assertRaises(PermissionDenied):
            self.client.post(reverse('core:vehiculos_eliminar', args=[self.activo.pk]))


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
