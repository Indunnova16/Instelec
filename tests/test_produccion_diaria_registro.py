"""Cobertura B1: registro diario con sus validaciones de dominio (#252)."""

from datetime import date

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.cuadrillas.forms_produccion_diaria import (
    ActividadProduccionForm,
    MaterialProduccionForm,
    NovedadProduccionForm,
    RegistroPersonalProduccionForm,
)
from apps.cuadrillas.models import Cuadrilla
from apps.cuadrillas.models_pc import ProgramacionSemanalCuadrilla
from apps.cuadrillas.models_produccion_diaria import ProduccionDiaria


class TestProduccionDiariaRegistro(TestCase):
    def setUp(self):
        Usuario = get_user_model()
        self.usuario = Usuario.objects.create_user(
            email="registro_diario@test.local", password="testpass123!", rol="admin"
        )
        self.client.force_login(self.usuario)
        self.cuadrilla = Cuadrilla.objects.create(codigo="PD-001", nombre="Cuadrilla diaria")
        hoy = date.today()
        iso = hoy.isocalendar()
        self.programacion = ProgramacionSemanalCuadrilla.objects.create(
            cuadrilla=self.cuadrilla, anio=iso.year, semana=iso.week, torres_programadas=2
        )

    def _post_base(self, **extra):
        data = {
            "programacion": str(self.programacion.pk),
            "fecha": date.today().isoformat(),
            "calidad_trabajo": "BUENA",
            "observaciones": "Jornada completa",
            "personal-TOTAL_FORMS": "0",
            "personal-INITIAL_FORMS": "0",
            "personal-MIN_NUM_FORMS": "0",
            "personal-MAX_NUM_FORMS": "1000",
            "actividad-TOTAL_FORMS": "0",
            "actividad-INITIAL_FORMS": "0",
            "actividad-MIN_NUM_FORMS": "0",
            "actividad-MAX_NUM_FORMS": "1000",
            "novedad-TOTAL_FORMS": "0",
            "novedad-INITIAL_FORMS": "0",
            "novedad-MIN_NUM_FORMS": "0",
            "novedad-MAX_NUM_FORMS": "1000",
            "material-TOTAL_FORMS": "0",
            "material-INITIAL_FORMS": "0",
            "material-MIN_NUM_FORMS": "0",
            "material-MAX_NUM_FORMS": "1000",
        }
        data.update(extra)
        return self.client.post(reverse("construccion:produccion_diaria_registrar"), data)

    def test_registro_con_foto_y_limites_de_horas_avance(self):
        response = self._post_base()
        self.assertRedirects(
            response,
            reverse(
                "construccion:produccion_diaria_detalle", args=[ProduccionDiaria.objects.get().pk]
            ),
        )
        produccion = ProduccionDiaria.objects.get()
        self.assertEqual(produccion.registrado_por, self.usuario)
        self.assertEqual(produccion.calidad_trabajo, ProduccionDiaria.Calidad.BUENA)

        actividad = ActividadProduccionForm(
            data={"descripcion": "Tendido", "avance_pct": "100", "observacion": "OK"}
        )
        self.assertTrue(actividad.is_valid(), actividad.errors)
        self.assertFalse(
            ActividadProduccionForm(
                data={"descripcion": "Exceso", "avance_pct": "100.01"}
            ).is_valid()
        )

    def test_edge_cases_horas_ausencia_material_y_archivo_invalido(self):
        personal = RegistroPersonalProduccionForm(
            data={"horas_trabajadas": "25", "motivo_ausencia": ""}
        )
        self.assertFalse(personal.is_valid())
        self.assertIn("horas_trabajadas", personal.errors)

        material = MaterialProduccionForm(
            data={"descripcion": "Cable", "cantidad": "0", "costo_unitario_estimado": "10"}
        )
        self.assertFalse(material.is_valid())
        self.assertIn("cantidad", material.errors)

        archivo = SimpleUploadedFile(
            "evidencia.pdf", b"no es imagen", content_type="application/pdf"
        )
        novedad = NovedadProduccionForm(
            data={"tipo": "LLUVIA", "descripcion": "Lluvia fuerte"}, files={"foto": archivo}
        )
        self.assertFalse(novedad.is_valid())
        self.assertIn("foto", novedad.errors)

    def test_fecha_fuera_de_semana_programada_no_persiste(self):
        otra_fecha = date.fromordinal(date.today().toordinal() + 14)
        response = self._post_base(fecha=otra_fecha.isoformat())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ProduccionDiaria.objects.count(), 0)
