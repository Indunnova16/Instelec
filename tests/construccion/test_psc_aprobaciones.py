"""Cobertura de B1: aprobación de personal por proyecto (#225)."""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.contratos.models import Contrato
from apps.construccion.models import (
    AsignacionPersonalProyectoConstruccion,
    ProyectoConstruccion,
)
from apps.cuadrillas.models import Cargo, PersonalCuadrilla


class TestAprobacionPersonalProyecto(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            email='psc-admin@test.local', password='testpass123!',
            first_name='PSC', last_name='Admin',
        )
        self.client.force_login(self.user)
        contrato = Contrato.objects.create(
            codigo='PSC-225', nombre='Contrato PSC', unidad_negocio='CONSTRUCCION',
        )
        self.proyecto = ProyectoConstruccion.objects.create(
            contrato=contrato, nombre='Proyecto PSC',
        )
        cargo = Cargo.objects.create(codigo='PSC-ROL', nombre='Rol PSC')
        self.personal = PersonalCuadrilla.objects.create(
            nombre='Ana Personal', documento='PSC-ANA-001', rol_cuadrilla=cargo,
            fecha_ingreso=date(2025, 1, 1),
        )
        self.url = reverse('construccion:psc_aprobaciones_personal')

    def _payload(self, **changes):
        payload = {
            'proyecto_id': str(self.proyecto.id),
            'personal_id': str(self.personal.id),
            'fecha_inicio': '2026-08-17',
            'fecha_fin': '2026-08-23',
        }
        payload.update(changes)
        return payload

    def test_aprobacion_valida_por_intervalo(self):
        response = self.client.post(self.url, self._payload())
        self.assertEqual(response.status_code, 200)
        aprobacion = AsignacionPersonalProyectoConstruccion.objects.get()
        self.assertEqual(aprobacion.proyecto, self.proyecto)
        self.assertEqual(aprobacion.personal, self.personal)
        self.assertEqual(aprobacion.fecha_inicio, date(2026, 8, 17))
        self.assertEqual(aprobacion.fecha_fin, date(2026, 8, 23))
        self.assertContains(response, 'quedó habilitado')

    def test_rechaza_intervalo_invertido(self):
        response = self.client.post(self.url, self._payload(
            fecha_inicio='2026-08-23', fecha_fin='2026-08-17',
        ))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(AsignacionPersonalProyectoConstruccion.objects.count(), 0)
        self.assertContains(response, 'no puede ser anterior', status_code=400)

    def test_rechaza_personal_inactivo(self):
        self.personal.activo = False
        self.personal.save(update_fields=['activo'])
        response = self.client.post(self.url, self._payload())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(AsignacionPersonalProyectoConstruccion.objects.count(), 0)
        self.assertContains(response, 'personal inactivo', status_code=400)

    def test_rechaza_solapamiento_y_conserva_aprobacion_previa(self):
        AsignacionPersonalProyectoConstruccion.objects.create(
            proyecto=self.proyecto, personal=self.personal,
            fecha_inicio=date(2026, 8, 17), fecha_fin=date(2026, 8, 23),
        )
        response = self.client.post(self.url, self._payload(
            fecha_inicio='2026-08-20', fecha_fin='2026-08-27',
        ))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(AsignacionPersonalProyectoConstruccion.objects.count(), 1)
        self.assertContains(response, 'se cruza con el intervalo', status_code=400)

    def test_dato_legacy_sin_fecha_fin_permanece_vigente(self):
        legacy = AsignacionPersonalProyectoConstruccion.objects.create(
            proyecto=self.proyecto, personal=self.personal,
            fecha_inicio=date(2025, 1, 1), fecha_fin=None,
        )
        response = self.client.get(self.url)
        legacy.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(legacy.fecha_fin)
        self.assertContains(response, 'Vigente')
