"""
Tests issue #176 (A1) — CRUD Tipos de Actividad en /actividades/tipos/.

Issue: Indunnova16/Instelec#176

Ejecutar con:
    python3 manage.py test apps.actividades.tests_issue_176 -v 2
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.actividades.models import TipoActividad

Usuario = get_user_model()


def _crear_admin():
    return Usuario.objects.create_user(
        email="admin_176_act@test.com",
        password="testpass123!",
        first_name="Admin",
        last_name="Actividades176",
        rol="admin",
        is_staff=True,
        is_superuser=True,
    )


class TestA1CRUDTiposActividad(TestCase):
    """A1: crear/editar/inactivar TipoActividad + filtro en dropdowns."""

    def setUp(self):
        self.admin = _crear_admin()
        self.client = Client()
        self.client.force_login(self.admin)

    def test_crear_tipo_actividad_via_form_valida_codigo_nombre_categoria(self):
        url = reverse("actividades:tipos_crear")
        resp = self.client.post(
            url,
            {
                "codigo": "TIPO-176-01",
                "nombre": "Inspeccion Especial 176",
                "categoria": TipoActividad.Categoria.INSPECCION,
                "descripcion": "Prueba issue 176",
                "requiere_fotos_antes": "on",
                "requiere_fotos_durante": "on",
                "requiere_fotos_despues": "on",
                "min_fotos": 3,
                "tiempo_estimado_horas": "2.5",
                "rendimiento_estandar_vanos": 4,
                "activo": "on",
            },
        )
        self.assertIn(resp.status_code, (200, 302))
        self.assertTrue(TipoActividad.objects.filter(codigo="TIPO-176-01").exists())
        tipo = TipoActividad.objects.get(codigo="TIPO-176-01")
        self.assertEqual(tipo.nombre, "Inspeccion Especial 176")
        self.assertEqual(tipo.categoria, TipoActividad.Categoria.INSPECCION)
        self.assertTrue(tipo.activo)

    def test_editar_tipo_actividad_existente_persiste_cambios(self):
        tipo = TipoActividad.objects.create(
            codigo="TIPO-176-02",
            nombre="Nombre Original",
            categoria=TipoActividad.Categoria.PODA,
        )
        url = reverse("actividades:tipos_editar", args=[tipo.pk])
        resp = self.client.post(
            url,
            {
                "codigo": "TIPO-176-02",
                "nombre": "Nombre Actualizado",
                "categoria": TipoActividad.Categoria.HERRAJES,
                "descripcion": "",
                "min_fotos": 5,
                "tiempo_estimado_horas": "3",
                "rendimiento_estandar_vanos": 2,
                "activo": "on",
            },
        )
        self.assertIn(resp.status_code, (200, 302))
        tipo.refresh_from_db()
        self.assertEqual(tipo.nombre, "Nombre Actualizado")
        self.assertEqual(tipo.categoria, TipoActividad.Categoria.HERRAJES)
        self.assertEqual(tipo.min_fotos, 5)

    def test_inactivar_tipo_actividad_no_lo_borra(self):
        tipo = TipoActividad.objects.create(
            codigo="TIPO-176-03",
            nombre="A Inactivar",
            categoria=TipoActividad.Categoria.LIMPIEZA,
            activo=True,
        )
        url = reverse("actividades:tipos_inactivar", args=[tipo.pk])
        resp = self.client.post(url)
        self.assertIn(resp.status_code, (200, 302))
        tipo.refresh_from_db()
        self.assertFalse(tipo.activo)
        # Sigue existiendo el registro (no se borra).
        self.assertTrue(TipoActividad.objects.filter(pk=tipo.pk).exists())

    def test_tipo_inactivo_no_aparece_en_dropdown_creacion_actividad(self):
        activo = TipoActividad.objects.create(
            codigo="TIPO-176-04A",
            nombre="Activo Dropdown",
            categoria=TipoActividad.Categoria.PODA,
            activo=True,
        )
        inactivo = TipoActividad.objects.create(
            codigo="TIPO-176-04B",
            nombre="Inactivo Dropdown",
            categoria=TipoActividad.Categoria.PODA,
            activo=False,
        )
        url = reverse("actividades:crear")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        tipos_ctx = list(resp.context["tipos"])
        self.assertIn(activo, tipos_ctx)
        self.assertNotIn(inactivo, tipos_ctx)

    def test_codigo_duplicado_rechazado_con_mensaje_de_dominio(self):
        TipoActividad.objects.create(
            codigo="TIPO-176-05",
            nombre="Original",
            categoria=TipoActividad.Categoria.OTRO,
        )
        url = reverse("actividades:tipos_crear")
        resp = self.client.post(
            url,
            {
                "codigo": "TIPO-176-05",
                "nombre": "Duplicado",
                "categoria": TipoActividad.Categoria.OTRO,
                "min_fotos": 3,
                "tiempo_estimado_horas": "2",
                "rendimiento_estandar_vanos": 3,
            },
        )
        # No debe lanzar IntegrityError (500); re-renderiza el form con error.
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(TipoActividad.objects.filter(codigo="TIPO-176-05").count(), 1)
        form = resp.context["form"]
        self.assertFalse(form.is_valid())
        self.assertIn("codigo", form.errors)
