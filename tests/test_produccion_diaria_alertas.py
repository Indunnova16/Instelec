"""Cobertura B3: alertas, destinatarios y consulta de Producción Diaria (#252)."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.cuadrillas.models import Cuadrilla
from apps.cuadrillas.models_pc import EjecucionSemanalCuadrilla, ProgramacionSemanalCuadrilla
from apps.cuadrillas.models_produccion_diaria import AlertaProduccion, ProduccionDiaria


class TestProduccionDiariaAlertas(TestCase):
    def setUp(self):
        Usuario = get_user_model()
        self.admin = Usuario.objects.create_user(
            email="alertas-admin@test.local", password="testpass123!", rol="admin"
        )
        self.director = Usuario.objects.create_user(
            email="director@test.local", password="testpass123!", rol="director"
        )
        self.client.force_login(self.admin)
        self.cuadrilla = Cuadrilla.objects.create(codigo="PD-ALERTA", nombre="Cuadrilla alertas")
        hoy = timezone.localdate()
        iso = hoy.isocalendar()
        self.programacion = ProgramacionSemanalCuadrilla.objects.create(
            cuadrilla=self.cuadrilla, anio=iso.year, semana=iso.week, torres_programadas=10
        )

    def crear_produccion(self, fecha=None):
        return ProduccionDiaria.objects.create(
            programacion=self.programacion,
            fecha=fecha or timezone.localdate(),
            registrado_por=self.admin,
        )

    def test_badge_e_historial_de_alerta(self):
        produccion = self.crear_produccion()
        EjecucionSemanalCuadrilla.objects.create(
            programacion=self.programacion, torres_ejecutadas=7
        )

        response = self.client.get(reverse("construccion:produccion_diaria_lista"))
        # Locale es-CO: Django renderiza Decimal con coma decimal, no punto.
        self.assertContains(response, "Alerta: -30,00%")
        alerta = AlertaProduccion.objects.get(produccion=produccion)
        self.assertIsNotNone(alerta.notificada_en)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.director.email])

        historial = self.client.get(reverse("construccion:produccion_diaria_historial"))
        self.assertContains(historial, "Alerta persistente: -30,00%")

    def test_desviacion_en_umbral_y_sin_ejecucion_no_crean_alerta(self):
        produccion = self.crear_produccion()
        EjecucionSemanalCuadrilla.objects.create(
            programacion=self.programacion, torres_ejecutadas=8
        )
        self.client.get(reverse("construccion:produccion_diaria_lista"))
        self.assertFalse(AlertaProduccion.objects.filter(produccion=produccion).exists())

        EjecucionSemanalCuadrilla.objects.all().delete()
        self.client.get(reverse("construccion:produccion_diaria_lista"))
        self.assertFalse(AlertaProduccion.objects.filter(produccion=produccion).exists())

    def test_historial_excluye_legacy_y_conserva_registro_sin_alerta(self):
        reciente = self.crear_produccion()
        legacy = self.crear_produccion(fecha=timezone.localdate() - timedelta(days=30))
        response = self.client.get(reverse("construccion:produccion_diaria_historial"))
        self.assertContains(response, str(reciente.fecha))
        self.assertNotContains(response, str(legacy.fecha))
        self.assertContains(response, "Sin alerta")

    def test_rol_no_permitido_recibe_403(self):
        Usuario = get_user_model()
        operario = Usuario.objects.create_user(
            email="operario-alertas@test.local", password="testpass123!", rol="operario_general"
        )
        self.client.force_login(operario)
        self.assertEqual(
            self.client.get(reverse("construccion:produccion_diaria_lista")).status_code, 403
        )
