"""Regression coverage for Instelec#240 — selector combined activity/type."""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.actividades.models import Actividad
from apps.cuadrillas.models import Cuadrilla
from apps.cuadrillas.views_semanal import (
    _bloque_a_dict,
    _choices_form_bloque,
    _resolver_seleccion_tipo_actividad,
)
from tests.factories.actividades import ActividadFactory, TipoActividadFactory


class TestSelectorActividadReal(TestCase):
    """The server contract must not trust values sent by the combined select."""

    def test_actividad_elegible_se_resuelve_y_el_bloque_puede_conservarla(self):
        actividad = ActividadFactory(estado=Actividad.Estado.PROGRAMADA)

        tipo, actividad_resuelta, error = _resolver_seleccion_tipo_actividad(
            f"actividad:{actividad.pk}"
        )

        self.assertIsNone(tipo)
        self.assertEqual(actividad_resuelta, actividad)
        self.assertIsNone(error)
        bloque = Cuadrilla.objects.create(
            codigo="240-0001-ACT",
            nombre="Bloque actividad real",
            actividad=actividad_resuelta,
        )
        bloque.refresh_from_db()
        self.assertEqual(bloque.actividad_id, actividad.pk)

    def test_lista_excluye_actividades_completadas_y_canceladas(self):
        pendiente = ActividadFactory(estado=Actividad.Estado.PENDIENTE)
        completada = ActividadFactory(estado=Actividad.Estado.COMPLETADA)
        cancelada = ActividadFactory(estado=Actividad.Estado.CANCELADA)

        opciones = _choices_form_bloque()["actividades_elegibles_bloque"]

        self.assertIn(pendiente, opciones)
        self.assertNotIn(completada, opciones)
        self.assertNotIn(cancelada, opciones)

    def test_rechaza_actividad_no_elegible_y_valor_malformado(self):
        completada = ActividadFactory(estado=Actividad.Estado.COMPLETADA)

        tipo, actividad, error = _resolver_seleccion_tipo_actividad(f"actividad:{completada.pk}")
        self.assertIsNone(tipo)
        self.assertIsNone(actividad)
        self.assertEqual(error, "La actividad seleccionada ya fue completada o cancelada.")

        tipo, actividad, error = _resolver_seleccion_tipo_actividad("actividad:no-es-un-uuid")
        self.assertIsNone(tipo)
        self.assertIsNone(actividad)
        self.assertEqual(error, "La actividad seleccionada no es válida.")

    def test_categoria_codificada_y_legacy_siguen_siendolo(self):
        tipo_actividad = TipoActividadFactory()

        tipo, actividad, error = _resolver_seleccion_tipo_actividad(f"tipo:{tipo_actividad.pk}")
        self.assertEqual(tipo, tipo_actividad)
        self.assertIsNone(actividad)
        self.assertIsNone(error)


class TestProgramacionSemanalActividadReal(TestCase):
    """HTTP contract: a concrete activity wins over manual location values."""

    def setUp(self):
        Usuario = get_user_model()
        self.usuario = Usuario.objects.create_user(
            email="admin_240@test.local",
            password="testpass123!",
            first_name="Admin",
            last_name="240",
            rol="admin",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.usuario)
        self.tipo = TipoActividadFactory(codigo="240-TIPO", nombre="Tipo 240")
        self.linea, self.torre, self.tramo = self._ubicacion("240-A")
        self.actividad = Actividad.objects.create(
            linea=self.linea,
            torre=self.torre,
            tramo=self.tramo,
            tipo_actividad=self.tipo,
            fecha_programada=date.today(),
            estado=Actividad.Estado.PROGRAMADA,
        )

    def _ubicacion(self, prefijo):
        from apps.lineas.models import Linea, Torre, Tramo

        linea = Linea.objects.create(
            codigo=f"{prefijo}-LINEA", nombre=f"Línea {prefijo}", cliente="TRANSELCA"
        )
        inicio = Torre.objects.create(
            linea=linea, numero=f"{prefijo}-1", latitud="7.00000000", longitud="-75.50000000"
        )
        fin = Torre.objects.create(
            linea=linea, numero=f"{prefijo}-2", latitud="7.01000000", longitud="-75.51000000"
        )
        tramo = Tramo.objects.create(
            linea=linea,
            codigo=f"{prefijo}-TRAMO",
            nombre=f"Tramo {prefijo}",
            torre_inicio=inicio,
            torre_fin=fin,
        )
        return linea, inicio, tramo

    def test_crear_con_actividad_precarga_tipo_linea_y_tramo(self):
        linea_manual, _, _ = self._ubicacion("240-MANUAL")
        response = self.client.post(
            reverse("cuadrillas:semanal_bloque_crear", args=[2026, 33]),
            {
                "nombre": "Bloque desde actividad 240",
                "tipo_actividad": f"actividad:{self.actividad.pk}",
                "linea_asignada": str(linea_manual.pk),
                "tramo_libre": "No debe persistir",
            },
        )

        self.assertEqual(response.status_code, 200)
        bloque = Cuadrilla.objects.get(nombre="Bloque desde actividad 240")
        self.assertEqual(bloque.actividad_id, self.actividad.pk)
        self.assertEqual(bloque.tipo_actividad_id, self.tipo.pk)
        self.assertEqual(bloque.linea_asignada_id, self.linea.pk)
        self.assertEqual(bloque.tramo_id, self.tramo.pk)
        self.assertEqual(bloque.tramo_libre, "")

    def test_editar_bloque_legacy_con_actividad_reemplaza_ubicacion_manual(self):
        linea_manual, _, _ = self._ubicacion("240-EDIT")
        bloque = Cuadrilla.objects.create(
            codigo="33-2026-0001-LEG",
            nombre="Bloque legacy 240",
            linea_asignada=linea_manual,
            tramo_libre="Tramo histórico",
        )

        response = self.client.post(
            reverse("cuadrillas:semanal_bloque_editar", args=[bloque.pk]),
            {"nombre": bloque.nombre, "tipo_actividad": f"actividad:{self.actividad.pk}"},
        )

        self.assertEqual(response.status_code, 200)
        bloque.refresh_from_db()
        self.assertEqual(bloque.actividad_id, self.actividad.pk)
        self.assertEqual(bloque.linea_asignada_id, self.linea.pk)
        self.assertEqual(bloque.tramo_id, self.tramo.pk)
        self.assertEqual(bloque.tramo_libre, "")

    def test_tipo_generico_conserva_flujo_manual_y_no_vincula_actividad(self):
        response = self.client.post(
            reverse("cuadrillas:semanal_bloque_crear", args=[2026, 34]),
            {
                "nombre": "Bloque manual 240",
                "tipo_actividad": f"tipo:{self.tipo.pk}",
                "linea_asignada": str(self.linea.pk),
                "tramo": str(self.tramo.pk),
                "tramo_libre": "Valor manual permitido",
            },
        )

        self.assertEqual(response.status_code, 200)
        bloque = Cuadrilla.objects.get(nombre="Bloque manual 240")
        self.assertIsNone(bloque.actividad_id)
        self.assertEqual(bloque.tipo_actividad_id, self.tipo.pk)
        self.assertEqual(bloque.linea_asignada_id, self.linea.pk)
        self.assertEqual(bloque.tramo_id, self.tramo.pk)
        self.assertEqual(bloque.tramo_libre, "Valor manual permitido")

    def test_actividad_cancelada_muestra_error_inline_y_no_modifica_legacy(self):
        actividad_cancelada = Actividad.objects.create(
            linea=self.linea,
            torre=self.torre,
            tipo_actividad=self.tipo,
            fecha_programada=date.today(),
            estado=Actividad.Estado.CANCELADA,
        )
        bloque = Cuadrilla.objects.create(
            codigo="35-2026-0001-LEG",
            nombre="Bloque legado protegido",
            tipo_actividad=self.tipo,
            linea_asignada=self.linea,
            tramo_libre="Conservar",
        )

        response = self.client.post(
            reverse("cuadrillas:semanal_bloque_editar", args=[bloque.pk]),
            {
                "nombre": "Nombre que no debe aplicar",
                "tipo_actividad": f"actividad:{actividad_cancelada.pk}",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "completada o cancelada", status_code=400)
        bloque.refresh_from_db()
        self.assertEqual(bloque.nombre, "Bloque legado protegido")
        self.assertIsNone(bloque.actividad_id)
        self.assertEqual(bloque.tramo_libre, "Conservar")

    def test_bloque_historico_sin_actividad_sigue_renderizando_su_tipo(self):
        bloque = Cuadrilla.objects.create(
            codigo="36-2026-0001-HIS",
            nombre="Bloque histórico",
            tipo_actividad=self.tipo,
            linea_asignada=self.linea,
            tramo_libre="Legado",
        )

        datos = _bloque_a_dict(bloque)

        self.assertEqual(datos["tipo_actividad"], self.tipo.nombre)
        self.assertEqual(datos["actividad_id"], "")
        self.assertEqual(datos["seleccion_tipo_actividad"], f"tipo:{self.tipo.pk}")

        tipo, actividad, error = _resolver_seleccion_tipo_actividad(str(tipo_actividad.pk))
        self.assertEqual(tipo, tipo_actividad)
        self.assertIsNone(actividad)
        self.assertIsNone(error)
