"""Cobertura B1: registro diario con sus validaciones de dominio (#252)."""

from datetime import date, time
from decimal import Decimal

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
from apps.cuadrillas.models import Asistencia, Cuadrilla, PersonalCuadrilla
from apps.cuadrillas.models_pc import ProgramacionSemanalCuadrilla
from apps.cuadrillas.models_produccion_diaria import ProduccionDiaria
from apps.cuadrillas.services_produccion_diaria import importar_asistencias


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

    def test_importacion_es_idempotente_y_conserva_fuente_de_asistencia(self):
        trabajador = get_user_model().objects.create_user(
            email="operario-importado@test.local", password="testpass123!", documento="PD-IMPORT-1"
        )
        personal = PersonalCuadrilla.objects.create(
            nombre="Operario importado", documento="PD-IMPORT-1", salario_base=Decimal("2400000")
        )
        asistencia = Asistencia.objects.create(
            usuario=trabajador, cuadrilla=self.cuadrilla, fecha=date.today(),
            hora_entrada=time(7), hora_salida=time(15), horas_extra=Decimal("2"),
        )

        produccion, creada, omitidas = importar_asistencias(
            self.programacion, date.today(), self.usuario
        )
        repetir, creada_repetida, _ = importar_asistencias(self.programacion, date.today(), self.usuario)
        registro = produccion.registros_personal.get()

        self.assertTrue(creada)
        self.assertFalse(creada_repetida)
        self.assertEqual(produccion, repetir)
        self.assertEqual(omitidas, [])
        self.assertEqual(registro.personal, personal)
        self.assertEqual(registro.asistencia_origen, asistencia)
        self.assertEqual(registro.horas_trabajadas, Decimal("10"))
        self.assertEqual(produccion.registros_personal.count(), 1)

    def test_importacion_de_ausencia_y_fecha_fuera_de_semana_es_explicita(self):
        trabajador = get_user_model().objects.create_user(
            email="ausente-importado@test.local", password="testpass123!", documento="PD-IMPORT-2"
        )
        PersonalCuadrilla.objects.create(nombre="Operario ausente", documento="PD-IMPORT-2")
        Asistencia.objects.create(
            usuario=trabajador, cuadrilla=self.cuadrilla, fecha=date.today(),
            tipo_novedad=Asistencia.TipoNovedad.INCAPACIDAD,
        )
        produccion, _, _ = importar_asistencias(self.programacion, date.today(), self.usuario)
        registro = produccion.registros_personal.get()
        self.assertEqual(registro.horas_trabajadas, Decimal("0"))
        self.assertEqual(registro.motivo_ausencia, "ENFERMEDAD")
        with self.assertRaisesMessage(ValueError, "semana ISO"):
            importar_asistencias(self.programacion, date.fromordinal(date.today().toordinal() + 14))

    def test_listado_muestra_programacion_pendiente_y_enlace_de_importacion(self):
        self.programacion.actividades_programadas = "Preliminares y Obra Civil"
        self.programacion.save(update_fields=["actividades_programadas", "updated_at"])

        response = self.client.get(reverse("construccion:produccion_diaria_lista"))

        self.assertContains(response, "Pendiente")
        self.assertContains(response, "Preliminares y Obra Civil")
        self.assertContains(response, "+ Registrar")
        self.assertContains(response, f"programacion={self.programacion.pk}")
