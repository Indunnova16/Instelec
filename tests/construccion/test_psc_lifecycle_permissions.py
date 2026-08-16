"""Ciclo de vida y RBAC de la Programación Semanal de Construcción (#225, B5)."""
from datetime import date, time

from django.contrib.auth import get_user_model
from django.conf import settings
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse

from apps.construccion.models import (
    ProgramacionSemanalConstruccion,
    ProgramacionSemanalConstruccionPersonal,
    ProgramacionSemanalConstruccionVehiculo,
    ProyectoConstruccion,
)
from apps.contratos.models import Contrato
from apps.cuadrillas.models import PersonalCuadrilla, Vehiculo


Usuario = get_user_model()


def _usuario(email, rol, documento=''):
    return Usuario.objects.create_user(
        email=email, password='testpass123!', first_name='PSC', last_name=rol,
        rol=rol, documento=documento,
    )


@override_settings(MIDDLEWARE=[
    middleware for middleware in settings.MIDDLEWARE
    if middleware != 'apps.core.middleware.RBACModuloMiddleware'
])
class TestPSCLifecyclePermissions(TestCase):
    """Aísla el filtro de fila PSC de la matriz RBAC global, ya cubierta en core."""
    def setUp(self):
        self.admin = _usuario('admin-psc-b5@test.local', 'admin')
        self.supervisor = _usuario('supervisor-psc-b5@test.local', 'supervisor', 'PSC-SUP-5')
        self.otro_supervisor = _usuario('otro-psc-b5@test.local', 'supervisor', 'PSC-OTRO-5')
        contrato = Contrato.objects.create(codigo='PSC-B5-001', nombre='Contrato PSC B5', unidad_negocio='CONSTRUCCION')
        self.proyecto = ProyectoConstruccion.objects.create(contrato=contrato, nombre='Proyecto PSC B5')
        self.personal = PersonalCuadrilla.objects.create(nombre='Supervisor PSC B5', documento='PSC-SUP-5')
        self.vehiculo = Vehiculo.objects.create(placa='PSC-B5-01', marca='Toyota')
        self.programacion = ProgramacionSemanalConstruccion.objects.create(
            proyecto=self.proyecto, tipo_actividad='TENDIDO', subactividad='Tendido conductor',
            fecha_inicio=date(2026, 8, 17), fecha_fin=date(2026, 8, 21),
            hora_inicio=time(7), hora_fin=time(16), supervisor=self.otro_supervisor,
        )
        ProgramacionSemanalConstruccionPersonal.objects.create(programacion=self.programacion, personal=self.personal)
        ProgramacionSemanalConstruccionVehiculo.objects.create(programacion=self.programacion, vehiculo=self.vehiculo, conductor=self.personal)

    def test_semana_supervisor_solo_ve_programacion_propia_o_integrada(self):
        ajena = ProgramacionSemanalConstruccion.objects.create(
            proyecto=self.proyecto, tipo_actividad='MONTAJE', subactividad='Montaje ajeno',
            fecha_inicio=date(2026, 8, 24), fecha_fin=date(2026, 8, 28), supervisor=self.otro_supervisor,
        )
        self.client.force_login(self.supervisor)
        response = self.client.get(reverse('construccion:psc_programacion_lista'))
        self.assertContains(response, 'Tendido conductor')
        self.assertNotContains(response, 'Montaje ajeno')
        self.assertNotContains(response, 'data-psc-action="duplicar"')
        self.assertNotContains(response, 'data-psc-action="eliminar"')
        self.assertTrue(ProgramacionSemanalConstruccion.objects.filter(pk=ajena.pk).exists())

    def test_duplicar_copia_asignaciones_y_preserva_origen(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('construccion:psc_programacion_duplicar', args=[self.programacion.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ProgramacionSemanalConstruccion.objects.count(), 2)
        copia = ProgramacionSemanalConstruccion.objects.exclude(pk=self.programacion.pk).get()
        self.assertEqual(copia.fecha_inicio, self.programacion.fecha_inicio)
        self.assertEqual(copia.asignaciones_personal.count(), 1)
        self.assertEqual(copia.asignaciones_vehiculo.count(), 1)
        self.assertEqual(self.programacion.asignaciones_personal.count(), 1)

    def test_roles_supervisor_no_puede_duplicar_ni_eliminar(self):
        self.client.force_login(self.supervisor)
        duplicate = self.client.post(reverse('construccion:psc_programacion_duplicar', args=[self.programacion.pk]))
        delete = self.client.post(reverse('construccion:psc_programacion_eliminar', args=[self.programacion.pk]))
        self.assertEqual(duplicate.status_code, 403)
        self.assertEqual(delete.status_code, 403)
        self.assertTrue(ProgramacionSemanalConstruccion.objects.filter(pk=self.programacion.pk).exists())

    def test_eliminar_cascadea_asignaciones_y_get_no_muta(self):
        self.client.force_login(self.admin)
        get_response = self.client.get(reverse('construccion:psc_programacion_eliminar', args=[self.programacion.pk]))
        self.assertEqual(get_response.status_code, 405)
        response = self.client.post(reverse('construccion:psc_programacion_eliminar', args=[self.programacion.pk]))
        self.assertRedirects(response, reverse('construccion:psc_programacion_lista'))
        self.assertFalse(ProgramacionSemanalConstruccion.objects.filter(pk=self.programacion.pk).exists())
        self.assertFalse(ProgramacionSemanalConstruccionPersonal.objects.exists())
        self.assertFalse(ProgramacionSemanalConstruccionVehiculo.objects.exists())
