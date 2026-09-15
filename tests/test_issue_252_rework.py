"""Regresiones del rework posterior al validador de cierre de #252."""

from datetime import time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.cuadrillas.models import Asistencia, Cuadrilla, PersonalCuadrilla
from apps.cuadrillas.models_pc import ProgramacionSemanalCuadrilla
from apps.cuadrillas.models_produccion_diaria import (
    ProduccionDiaria,
    RegistroPersonalProduccion,
)
from apps.cuadrillas.services_produccion_analisis import (
    ESTADO_DISPONIBLE,
    ESTADO_SIN_BASE,
    construir_analisis,
)


class TestIssue252Rework(TestCase):
    def setUp(self):
        Usuario = get_user_model()
        self.admin = Usuario.objects.create_user(
            email="issue-252-admin@test.local", password="testpass123!", rol="admin"
        )
        self.client.force_login(self.admin)
        self.fecha = timezone.localdate()
        iso = self.fecha.isocalendar()
        self.cuadrilla = Cuadrilla.objects.create(
            codigo="PD-252-REWORK", nombre="Cuadrilla regresión 252"
        )
        self.programacion = ProgramacionSemanalCuadrilla.objects.create(
            cuadrilla=self.cuadrilla,
            anio=iso.year,
            semana=iso.week,
            torres_programadas=2,
        )

    def test_link_registrar_importa_asistencia_real_y_redirige_a_edicion(self):
        trabajador = get_user_model().objects.create_user(
            email="issue-252-operario@test.local",
            password="testpass123!",
            documento="PD-252-OPERARIO",
        )
        personal = PersonalCuadrilla.objects.create(
            nombre="Operario de regresión", documento="PD-252-OPERARIO"
        )
        asistencia = Asistencia.objects.create(
            usuario=trabajador,
            cuadrilla=self.cuadrilla,
            fecha=self.fecha,
            hora_entrada=time(7),
            hora_salida=time(15),
        )

        response = self.client.get(
            reverse("construccion:produccion_diaria_registrar"),
            {"programacion": self.programacion.pk, "fecha": self.fecha.isoformat()},
        )

        produccion = ProduccionDiaria.objects.get(
            programacion=self.programacion, fecha=self.fecha
        )
        self.assertRedirects(
            response,
            reverse("construccion:produccion_diaria_editar", args=[produccion.pk]),
        )
        registro = RegistroPersonalProduccion.objects.get(produccion=produccion)
        self.assertEqual(registro.personal, personal)
        self.assertEqual(registro.asistencia_origen, asistencia)

    def test_varianza_horas_planeadas_se_calcula_y_se_renderiza(self):
        self.programacion.horas_planeadas = Decimal("10")
        self.programacion.save(update_fields=["horas_planeadas", "updated_at"])
        produccion = ProduccionDiaria.objects.create(
            programacion=self.programacion, fecha=self.fecha, registrado_por=self.admin
        )
        personal = PersonalCuadrilla.objects.create(
            nombre="Personal horas", documento="PD-252-HORAS"
        )
        RegistroPersonalProduccion.objects.create(
            produccion=produccion, personal=personal, horas_trabajadas=Decimal("8")
        )

        analisis = construir_analisis(self.programacion)
        response = self.client.get(
            reverse("construccion:produccion_diaria_analisis", args=[self.programacion.pk])
        )

        self.assertEqual(analisis["estado_horas"], ESTADO_DISPONIBLE)
        self.assertEqual(analisis["varianza_horas_pct"], Decimal("-20.00"))
        self.assertContains(response, "Horas planeadas")
        self.assertContains(response, "Varianza de horas")

    def test_varianza_horas_sin_base_es_explicita(self):
        analisis = construir_analisis(self.programacion)

        self.assertEqual(analisis["estado_horas"], ESTADO_SIN_BASE)
        self.assertIsNone(analisis["varianza_horas_pct"])

    def test_listado_solo_muestra_error_para_fecha_malformada(self):
        url = reverse("construccion:produccion_diaria_lista")

        sin_filtro = self.client.get(url)
        fecha_invalida = self.client.get(url, {"fecha": "basura"})

        self.assertNotIn("error_filtro", sin_filtro.context)
        self.assertEqual(
            fecha_invalida.context["error_filtro"],
            "La fecha indicada no es válida. Se muestra hoy.",
        )
