"""Regression tests for the weekly-crew range and free-route changes in #223."""

from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import Client, TestCase
from django.urls import reverse

from apps.actividades.models import TipoActividad
from apps.cuadrillas.models import Cuadrilla, CuadrillaMiembro, PersonalCuadrilla
from apps.cuadrillas.views_semanal import _bloque_a_dict, _choices_form_bloque
from apps.lineas.models import Linea, Torre, Tramo


Usuario = get_user_model()


class TestProgramacionSemanalTramoLibreYRango(TestCase):
    """A1: free route text and both date boundaries survive all weekly views."""

    def setUp(self):
        self.admin = Usuario.objects.create_user(
            email="admin_223@test.local",
            password="testpass123!",
            first_name="Admin",
            last_name="223",
            rol="admin",
            is_staff=True,
            is_superuser=True,
        )
        self.client = Client()
        self.client.force_login(self.admin)
        self.crear_url = reverse("cuadrillas:semanal_bloque_crear", args=[2099, 1])

    def test_crear_y_editar_persisten_tramo_libre_y_rango_completo(self):
        response = self.client.post(
            self.crear_url,
            {
                "nombre": "Cuadrilla QA 223",
                "tramo_libre": "K12+345 a K13+000",
                "fecha_inicio": "2099-01-05",
                "fecha_fin": "2099-01-09",
            },
        )

        self.assertEqual(response.status_code, 200)
        cuadrilla = Cuadrilla.objects.get(nombre="Cuadrilla QA 223")
        self.assertEqual(cuadrilla.tramo_libre, "K12+345 a K13+000")
        self.assertEqual(cuadrilla.fecha, date(2099, 1, 5))
        self.assertEqual(cuadrilla.fecha_fin, date(2099, 1, 9))
        self.assertContains(response, "Fecha Inicio")
        self.assertContains(response, "Fecha Fin")
        self.assertContains(response, "K12+345 a K13+000")

        response = self.client.post(
            reverse("cuadrillas:semanal_bloque_editar", args=[cuadrilla.id]),
            {
                "nombre": "Cuadrilla QA 223 editada",
                "tramo_libre": "K13+000 a K13+500",
                "fecha_inicio": "2099-01-06",
                "fecha_fin": "2099-01-10",
            },
        )

        self.assertEqual(response.status_code, 200)
        cuadrilla.refresh_from_db()
        self.assertEqual(cuadrilla.tramo_libre, "K13+000 a K13+500")
        self.assertEqual(cuadrilla.fecha, date(2099, 1, 6))
        self.assertEqual(cuadrilla.fecha_fin, date(2099, 1, 10))

    def test_fecha_fin_anterior_no_guarda_y_mantiene_error_visible(self):
        response = self.client.post(
            self.crear_url,
            {
                "nombre": "Cuadrilla rango inválido",
                "tramo_libre": "Vano 25-50",
                "fecha_inicio": "2099-01-10",
                "fecha_fin": "2099-01-09",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "La fecha de fin no puede ser anterior", status_code=400)
        self.assertContains(response, 'value="Vano 25-50"', status_code=400)
        self.assertEqual(Cuadrilla.objects.filter(nombre="Cuadrilla rango inválido").count(), 0)

    def test_fecha_fin_malformada_no_guarda(self):
        response = self.client.post(
            self.crear_url,
            {
                "nombre": "Cuadrilla fecha inválida",
                "fecha_inicio": "2099-01-05",
                "fecha_fin": "09-01-2099",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "La fecha de fin ingresada no es válida", status_code=400)
        self.assertFalse(Cuadrilla.objects.filter(nombre="Cuadrilla fecha inválida").exists())

    def test_cuadrilla_legacy_con_tramo_fk_aun_renderiza_en_card_y_pdf(self):
        linea = Linea.objects.create(codigo="223-L", nombre="Línea legacy", cliente="TRANSELCA")
        inicio = Torre.objects.create(linea=linea, numero="1", latitud="7.0", longitud="-75.5")
        fin = Torre.objects.create(linea=linea, numero="2", latitud="7.1", longitud="-75.6")
        tramo = Tramo.objects.create(
            linea=linea,
            codigo="223-LEG",
            nombre="Tramo legado",
            torre_inicio=inicio,
            torre_fin=fin,
        )
        legacy = Cuadrilla.objects.create(
            codigo="01-2099-0002-LEG",
            nombre="Cuadrilla legacy 223",
            tramo=tramo,
            fecha=date(2099, 1, 5),
            fecha_fin=date(2099, 1, 9),
        )

        bloque = _bloque_a_dict(legacy)
        self.assertEqual(bloque["tramo_libre"], "")
        card = render_to_string("cuadrillas/partials/_bloque_card.html", {"b": bloque, "anio": 2099, "semana": 1})
        pdf = render_to_string(
            "cuadrillas/programacion_semanal_pdf.html",
            {
                "bloques": [bloque], "semana": 1, "anio": 2099, "tiene_datos": True,
                "lunes": None, "domingo": None, "total_bloques": 1, "total_miembros": 0,
                "total_novedades": 0, "novedades": [], "generado": None,
            },
        )
        self.assertIn("Tramo 223-LEG - Tramo legado", card)
        self.assertIn("Tramo 223-LEG", pdf)


class TestCatalogoSupervisorMantenimiento(TestCase):
    """A2: el responsable de una cuadrilla no se limita al rol legacy."""

    def _usuario(self, email, *, area, rol="operario_mantenimiento", documento=""):
        return Usuario.objects.create_user(
            email=email,
            password="testpass123!",
            first_name="Colaborador",
            last_name=email.split("@")[0],
            rol=rol,
            area=area,
            documento=documento,
            is_active=True,
        )

    def test_lista_dos_colaboradores_elegibles_y_legacy_no_supervisor(self):
        mantenimiento = self._usuario(
            "mant_223@test.local", area="MANTENIMIENTO", documento="223-1001"
        )
        legacy = self._usuario(
            "legacy_223@test.local", area="", rol="liniero", documento="223-1002"
        )

        choices = list(_choices_form_bloque()["supervisores_bloque"])

        self.assertIn(mantenimiento, choices)
        self.assertIn(legacy, choices)

    def test_excluye_colaborador_de_otra_area_e_inactivo(self):
        construccion = self._usuario("obra_223@test.local", area="CONSTRUCCION")
        inactivo = self._usuario("baja_223@test.local", area="MANTENIMIENTO")
        inactivo.is_active = False
        inactivo.save(update_fields=["is_active"])

        choices = list(_choices_form_bloque()["supervisores_bloque"])

        self.assertNotIn(construccion, choices)
        self.assertNotIn(inactivo, choices)

    def test_crear_y_editar_conservan_supervisor_y_etiqueta_buscable_por_documento(self):
        self.admin = Usuario.objects.create_user(
            email="admin_catalogo_223@test.local",
            password="testpass123!",
            first_name="Admin",
            last_name="223",
            rol="admin",
            is_staff=True,
            is_superuser=True,
        )
        supervisor = self._usuario(
            "responsable_223@test.local", area="MANTENIMIENTO", documento="CC-223-900"
        )
        client = Client()
        client.force_login(self.admin)
        crear_url = reverse("cuadrillas:semanal_bloque_crear", args=[2099, 2])

        response = client.post(
            crear_url, {"nombre": "Cuadrilla catálogo 223", "supervisor": supervisor.pk}
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("CC-223-900", response.content.decode())
        cuadrilla = Cuadrilla.objects.get(nombre="Cuadrilla catálogo 223")
        self.assertEqual(cuadrilla.supervisor, supervisor)

        response = client.post(
            reverse("cuadrillas:semanal_bloque_editar", args=[cuadrilla.pk]),
            {"nombre": "Cuadrilla catálogo 223 editada", "supervisor": supervisor.pk},
        )

        self.assertEqual(response.status_code, 200)
        cuadrilla.refresh_from_db()
        self.assertEqual(cuadrilla.supervisor, supervisor)

    def test_grid_expone_los_tres_catalogos_tomselect_con_opciones_buscables(self):
        """La pantalla entrega los selects que el navegador transforma en búsqueda."""
        admin = Usuario.objects.create_user(
            email="admin_catalogos_ui_223@test.local",
            password="testpass123!",
            first_name="Admin",
            last_name="Catálogos 223",
            rol="admin",
            is_staff=True,
            is_superuser=True,
        )
        tipo = TipoActividad.objects.create(
            codigo="223-CAT", nombre="Poda 223", categoria=TipoActividad.Categoria.PODA
        )
        linea = Linea.objects.create(codigo="223-CAT-L", nombre="Línea catálogo 223")
        supervisor = self._usuario(
            "catalogo_ui_223@test.local", area="MANTENIMIENTO", documento="CC-223-UI"
        )
        client = Client()
        client.force_login(admin)

        response = client.get(reverse("cuadrillas:semanal_grid", args=[2099, 1]))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('id="id_tipo_actividad"', html)
        self.assertIn('id="id_linea"', html)
        self.assertIn('id="id_supervisor"', html)
        self.assertRegex(
            html, r'<select name="tipo_actividad" id="id_tipo_actividad"\s+class="js-tomselect'
        )
        self.assertRegex(html, r'<select name="linea_asignada" id="id_linea"\s+class="js-tomselect')
        self.assertRegex(html, r'<select name="supervisor" id="id_supervisor"\s+class="js-tomselect')
        self.assertIn(tipo.nombre, html)
        self.assertIn(linea.codigo, html)
        self.assertIn(supervisor.documento, html)


class TestPersonalActivoAsignableSinArea(TestCase):
    """A2: legacy y grid semanal comparten la elegibilidad por estado activo."""

    def setUp(self):
        self.admin = Usuario.objects.create_user(
            email="admin_personal_223@test.local",
            password="testpass123!",
            first_name="Admin",
            last_name="Personal 223",
            rol="admin",
            is_staff=True,
            is_superuser=True,
        )
        self.client = Client()
        self.client.force_login(self.admin)

    def _personal(self, documento, *, area, activo=True):
        return PersonalCuadrilla.objects.create(
            nombre=f"Personal {documento}",
            documento=documento,
            rol_cuadrilla_id="LINIERO_I",
            salario_base=0,
            area=area,
            activo=activo,
        )

    def test_api_legacy_lista_personal_activo_de_todas_las_areas_y_legacy(self):
        construccion = self._personal("223-A2-CON", area="CONSTRUCCION")
        mantenimiento = self._personal("223-A2-MAN", area="MANTENIMIENTO")
        otra_area = self._personal("223-A2-FIN", area="FINANCIERO")
        legacy = self._personal("223-A2-LEG", area="")
        inactivo = self._personal("223-A2-BAJ", area="CONSTRUCCION", activo=False)

        response = self.client.get(reverse("cuadrillas:personal_list_api"))

        self.assertEqual(response.status_code, 200)
        documentos = {item["documento"] for item in response.json()}
        self.assertTrue(
            {construccion.documento, mantenimiento.documento, otra_area.documento, legacy.documento}
            .issubset(documentos)
        )
        self.assertNotIn(inactivo.documento, documentos)

    def test_post_semanal_acepta_todas_las_areas_activas_y_rechaza_duplicado_activo(self):
        personal_activo = [
            self._personal("223-A2-CON-POST", area="CONSTRUCCION"),
            self._personal("223-A2-MAN-POST", area="MANTENIMIENTO"),
            self._personal("223-A2-FIN-POST", area="FINANCIERO"),
            self._personal("223-A2-LEG-POST", area=""),
        ]
        cuadrilla = Cuadrilla.objects.create(
            codigo="02-2099-0223-A2", nombre="Bloque elegibilidad 223"
        )
        url = reverse("cuadrillas:semanal_miembro_agregar", args=[cuadrilla.pk])

        for personal in personal_activo:
            response = self.client.post(url, {"documento": personal.documento})
            self.assertEqual(response.status_code, 200)

        self.assertEqual(
            CuadrillaMiembro.objects.filter(cuadrilla=cuadrilla, activo=True).count(), 4
        )

        duplicado = self.client.post(url, {"documento": personal_activo[0].documento})

        self.assertEqual(duplicado.status_code, 400)
        self.assertContains(duplicado, "ya es miembro activo", status_code=400)
        self.assertEqual(
            CuadrillaMiembro.objects.filter(cuadrilla=cuadrilla, activo=True).count(), 4
        )

    def test_post_semanal_rechaza_inactivo_y_conserva_el_formulario_abierto(self):
        """La exclusión por activo también se aplica al POST, no solo al API.

        Es el guard que el journey de navegador no puede cubrir con un option
        inexistente: aun si llega un documento manipulado, no se crea la
        asignación y el operador recibe el error recuperable en el card.
        """
        inactivo = self._personal("223-A3-BAJ-POST", area="CONSTRUCCION", activo=False)
        cuadrilla = Cuadrilla.objects.create(
            codigo="02-2099-0223-A3", nombre="Bloque inactivo 223"
        )

        response = self.client.post(
            reverse("cuadrillas:semanal_miembro_agregar", args=[cuadrilla.pk]),
            {"documento": inactivo.documento},
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "No se encontró un colaborador activo", status_code=400)
        self.assertContains(response, 'id="form-agregar-personal"', status_code=400)
        self.assertFalse(CuadrillaMiembro.objects.filter(cuadrilla=cuadrilla).exists())


class TestListadoSemanasActualesOFuturas(TestCase):
    """A3: /cuadrillas/ es operativo; /semanal conserva el historial."""

    def setUp(self):
        self.admin = Usuario.objects.create_user(
            email="admin_lista_223@test.local",
            password="testpass123!",
            first_name="Admin",
            last_name="Listado 223",
            rol="admin",
            is_staff=True,
            is_superuser=True,
        )
        self.client = Client()
        self.client.force_login(self.admin)

        # Registro con la forma de un código legado real: debe seguir siendo
        # consultable en su semana histórica, pero no en el tablero operativo.
        self.pasada = Cuadrilla.objects.create(
            codigo="31-2026-LEGACY-223",
            nombre="Cuadrilla pasada legacy 223",
            fecha=date(2026, 7, 27),
            activa=True,
        )
        self.actual = Cuadrilla.objects.create(
            codigo="32-2026-ACTUAL-223",
            nombre="Cuadrilla actual 223",
            fecha=date(2026, 8, 3),
            activa=True,
        )
        self.futura = Cuadrilla.objects.create(
            codigo="01-2027-FUTURA-223",
            nombre="Cuadrilla futura 223",
            fecha=date(2027, 1, 4),
            activa=True,
        )

    @patch("apps.cuadrillas.views_b3.timezone.localdate", return_value=date(2026, 8, 3))
    def test_lista_excluye_semana_pasada_e_incluye_actual_y_futura(self, _localdate):
        response = self.client.get(reverse("cuadrillas:lista"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.pasada.nombre)
        self.assertContains(response, self.actual.nombre)
        self.assertContains(response, self.futura.nombre)
        self.assertContains(response, "Semanas actuales y futuras")
        self.assertContains(response, "Historial semanal")

    @patch("apps.cuadrillas.views_b3.timezone.localdate", return_value=date(2026, 8, 3))
    def test_historial_semanal_conserva_registro_legacy_pasado(self, _localdate):
        response = self.client.get(
            reverse("cuadrillas:semanal_grid", args=[2026, 31])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.pasada.nombre)

    @patch("apps.cuadrillas.views_b3.timezone.localdate", return_value=date(2026, 8, 3))
    def test_lista_no_revienta_con_codigo_legacy_sin_formato_semana(self, _localdate):
        """Regresión: códigos reales de prod ("28-Apoyo Sede-011", "28-Avisos
        SC-010") no siguen el formato WW-YYYY-... — castear su substring a
        INTEGER revienta la query completa con un 500 real (no un 0
        resultados). El filtro de A3 debe tratarlos como visibles por
        default, nunca tumbar la página."""
        Cuadrilla.objects.create(
            codigo="28-Apoyo Sede-011",
            nombre="Cuadrilla codigo legacy sin semana 223",
            fecha=date(2026, 8, 3),
            activa=True,
        )

        response = self.client.get(reverse("cuadrillas:lista"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cuadrilla codigo legacy sin semana 223")


class TestListadoOperativoSemanal(TestCase):
    """A1 del follow-up: tarjetas operativas visibles sin desplegarlas."""

    def setUp(self):
        self.admin = Usuario.objects.create_user(
            email="admin_listado_operativo_223@test.local",
            password="testpass123!",
            first_name="Admin",
            last_name="Operativo",
            rol="admin",
            is_staff=True,
            is_superuser=True,
        )
        self.client = Client()
        self.client.force_login(self.admin)
        self.actividad = TipoActividad.objects.create(
            codigo="223-OPERATIVA",
            nombre="Inspección semanal",
            categoria=TipoActividad.Categoria.INSPECCION,
            descripcion="Revisión programada de la línea.",
        )
        self.linea = Linea.objects.create(codigo="223-OP-L", nombre="Línea operativa")
        self.supervisor = Usuario.objects.create_user(
            email="supervisor_operativo_223@test.local",
            password="testpass123!",
            first_name="Sofía",
            last_name="Supervisora",
            rol="supervisor",
        )
        self.cuadrilla = Cuadrilla.objects.create(
            codigo="35-2026-OPERATIVA-223",
            nombre="Cuadrilla operativa 223",
            fecha=date(2026, 8, 24),
            activa=True,
            tipo_actividad=self.actividad,
            linea_asignada=self.linea,
            supervisor=self.supervisor,
        )

    @patch("apps.cuadrillas.views_b3.timezone.localdate", return_value=date(2026, 8, 24))
    def test_semana_actual_agrupa_y_destaca_el_resumen_visible(self, _localdate):
        response = self.client.get(reverse("cuadrillas:lista"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-semana="Semana 35 - 2026"')
        self.assertContains(response, "Inspección semanal")
        self.assertContains(response, "Revisión programada de la línea.")
        self.assertContains(response, "Sofía Supervisora")
        self.assertContains(response, "223-OP-L")
        self.assertContains(response, "Miembros / Estado")
        self.assertContains(response, "0 miembros")
        self.assertContains(response, "bg-blue-50")

    @patch("apps.cuadrillas.views_b3.timezone.localdate", return_value=date(2026, 8, 24))
    def test_registro_legacy_sin_relaciones_muestra_resumen_seguro(self, _localdate):
        legacy = Cuadrilla.objects.create(
            codigo="35-2026-LEGACY-OPERATIVA",
            nombre="Cuadrilla legacy operativa 223",
            fecha=date(2026, 8, 24),
            activa=True,
        )

        response = self.client.get(reverse("cuadrillas:lista"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, legacy.nombre)
        self.assertContains(response, "Sin actividad registrada")
        self.assertContains(response, "Sin descripción registrada")
        self.assertContains(response, "Sin supervisor asignado")
        self.assertContains(response, "Sin línea asignada")

    @patch("apps.cuadrillas.views_b3.timezone.localdate", return_value=date(2026, 8, 24))
    def test_acciones_conservan_destinos_y_no_activan_el_acordeon(self, _localdate):
        response = self.client.get(reverse("cuadrillas:lista"))
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn(f'@click.stop href="{reverse("cuadrillas:detalle", args=[self.cuadrilla.id])}"', html)
        self.assertIn(f'@click.stop href="{reverse("cuadrillas:editar", args=[self.cuadrilla.id])}"', html)
        self.assertIn("@click.stop=\"tab = 'mapa';", html)
        self.assertIn(f"focusCuadrilla('{self.cuadrilla.id}')", html)


class TestTerminologiaCuadrilla(TestCase):
    """A4: la programación semanal usa la terminología del cliente."""

    def setUp(self):
        self.admin = Usuario.objects.create_user(
            email="admin_terminologia_223@test.local",
            password="testpass123!",
            first_name="Admin",
            last_name="Terminologia",
            rol="admin",
            is_staff=True,
            is_superuser=True,
        )
        self.client = Client()
        self.client.force_login(self.admin)
        Cuadrilla.objects.create(
            codigo="01-2099-0001-TERM",
            nombre="Cuadrilla terminología 223",
            fecha=date(2099, 1, 5),
            activa=True,
        )

    def test_grid_y_formulario_dicen_cuadrilla_y_conservan_ids_tecnicos(self):
        response = self.client.get(reverse("cuadrillas:semanal_grid", args=[2099, 1]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1 cuadrilla(s)")
        self.assertContains(response, "+ Nueva cuadrilla")
        self.assertContains(response, 'id="btn-nuevo-bloque"')
        self.assertContains(response, 'data-bloque-codigo="01-2099-0001-TERM"')

        form = render_to_string("cuadrillas/partials/_bloque_form.html", {"b": {}})
        self.assertIn("Nombre de la cuadrilla", form)
        self.assertIn("Guardar cuadrilla", form)

    def test_pdf_generado_usa_cuadrillas(self):
        class FakeHTML:
            ultimo_html = ""

            def __init__(self, *, string, base_url):
                type(self).ultimo_html = string

            def write_pdf(self):
                return b"%PDF-1.4 terminologia"

        with patch.dict("sys.modules", {"weasyprint": SimpleNamespace(HTML=FakeHTML)}):
            response = self.client.get(reverse("cuadrillas:semanal_pdf", args=[2099, 1]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertIn("1 cuadrilla(s)", FakeHTML.ultimo_html)
        self.assertIn("Programación semanal de cuadrillas", FakeHTML.ultimo_html)
        self.assertIn("Cuadrilla: Cuadrilla terminología 223", FakeHTML.ultimo_html)

    def test_terminologia_de_macro_bloques_de_construccion_no_cambia(self):
        macro = Path(settings.BASE_DIR) / "templates/construccion/programacion_cuadrilla_lista.html"

        self.assertIn(">Bloque</th>", macro.read_text(encoding="utf-8"))
