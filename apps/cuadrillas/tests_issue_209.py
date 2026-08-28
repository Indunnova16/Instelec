"""
Tests issue #209 — Formularios de bloque y personal: select2 (TomSelect)
buscable en los 6 campos + filtros reales en cascada (Línea→Tramo, Supervisor
y Personal activo+búsqueda).

Separado de #178 (ver SPRINTS/ANALISIS_2026-08-03_issue178_particion.md,
partición N3). Depende de #178 Sprint BC (grid editable, YA en producción,
ver tests_issue_178_bc.py) y del maestro de Colaboradores #176 (YA en
producción, ver tests_issue_176.py) — ambos verificados en código antes de
construir este issue.

Cubre:
- A1: los 6 campos (tipo_actividad, línea, tramo, vehículo, supervisor,
  personal/documento) llevan la clase `js-tomselect` en el HTML renderizado.
- A2: cascada Línea→Tramo real con 2 líneas (la línea A no debe traer los
  tramos de la línea B) — el test único preexistente (tests_issue_188.py,
  TestA3CrearBloqueCascadaTramo) solo cubre el caso de una línea sin tramos.
- A3: Supervisor solo lista `rol='supervisor'` + área compatible (MANTENIMIENTO
  o legacy sin área) — excluye explícitamente área=CONSTRUCCION/FINANCIERO.
- A4: Personal lista todo `PersonalCuadrilla` activo, independientemente de
  área, y excluye inactivos; el <option> incluye nombre Y documento para que
  TomSelect pueda buscar por cualquiera de los dos (cédula incluida).

Ejecutar con:
    pytest apps/cuadrillas/tests_issue_209.py -v
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.cuadrillas.models import PersonalCuadrilla
from apps.cuadrillas.views_semanal import _choices_form_bloque, _personal_visible_para_usuario

Usuario = get_user_model()


def _crear_admin():
    return Usuario.objects.create_user(
        email="admin_209@test.com",
        password="testpass123!",
        first_name="Admin",
        last_name="Test209",
        rol="admin",
        is_staff=True,
        is_superuser=True,
    )


def _crear_linea_con_tramo(codigo_sufijo, nombre_tramo):
    from apps.lineas.models import Linea, Torre, Tramo

    linea = Linea.objects.create(
        codigo=f"209-{codigo_sufijo}", nombre=f"Linea {codigo_sufijo}", cliente="TRANSELCA"
    )
    t1 = Torre.objects.create(linea=linea, numero="1", latitud="7.0", longitud="-75.5")
    t2 = Torre.objects.create(linea=linea, numero="2", latitud="7.01", longitud="-75.51")
    tramo = Tramo.objects.create(
        linea=linea,
        codigo=f"209-{codigo_sufijo}-TRM",
        nombre=nombre_tramo,
        torre_inicio=t1,
        torre_fin=t2,
    )
    return linea, tramo


# ---------------------------------------------------------------------------
# A1 — select2 (TomSelect) buscable en los 6 campos
# ---------------------------------------------------------------------------
class TestA1Select2EnLosSeisCampos(TestCase):
    def setUp(self):
        self.admin = _crear_admin()
        self.client = Client()
        self.client.force_login(self.admin)

    def test_form_bloque_los_cinco_selects_estaticos_tienen_js_tomselect(self):
        url = reverse("cuadrillas:semanal_bloque_crear", args=[2026, 40])
        resp = self.client.post(url, {"nombre": "Bloque select2 A1"})
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        for field_id in (
            "id_tipo_actividad",
            "id_linea",
            "id_tramo",
            "id_vehiculo",
            "id_supervisor",
        ):
            idx = html.index(f'id="{field_id}"')
            # La clase va en el atributo `class` del MISMO <select>, que en
            # este template aparece DESPUÉS del `id` (multilínea) -- ventana
            # amplia hacia adelante hasta el cierre `>` de la etiqueta.
            ventana = html[idx : idx + 400]
            self.assertIn("js-tomselect", ventana, f"{field_id} no tiene js-tomselect")

    def test_card_personal_select_documento_tiene_js_tomselect_y_es_buscable_por_nombre_y_documento(
        self,
    ):
        PersonalCuadrilla.objects.create(
            nombre="Pedro Martinez",
            documento="209-0001",
            rol_cuadrilla_id="LINIERO_I",
            salario_base=Decimal("1500000"),
            activo=True,
            area="MANTENIMIENTO",
        )
        url = reverse("cuadrillas:semanal_bloque_crear", args=[2026, 40])
        resp = self.client.post(url, {"nombre": "Bloque select2 A1 personal"})
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        idx = html.index('id="id_documento"')
        ventana = html[idx : idx + 400]
        self.assertIn("js-tomselect", ventana)
        # El texto visible de la opción trae nombre Y documento -- TomSelect
        # busca sobre el texto visible, así que ambos son buscables.
        self.assertIn('value="209-0001"', html)
        self.assertIn("Pedro Martinez", html)
        self.assertIn("Pedro Martinez — 209-0001", html)


# ---------------------------------------------------------------------------
# A2 — cascada Línea→Tramo real con 2 líneas (bug reportado por el cliente)
# ---------------------------------------------------------------------------
class TestA2CascadaTramoConDosLineasReales(TestCase):
    def setUp(self):
        self.admin = _crear_admin()
        self.client = Client()
        self.client.force_login(self.admin)

    def test_elegir_linea_a_no_trae_tramos_de_la_linea_b(self):
        linea_a, tramo_a = _crear_linea_con_tramo("A2A", "Tramo Solo De A")
        linea_b, tramo_b = _crear_linea_con_tramo("A2B", "Tramo Solo De B")

        api_url = reverse("cuadrillas:tramos_por_linea_api")

        resp_a = self.client.get(api_url, {"linea_id": str(linea_a.id)})
        self.assertEqual(resp_a.status_code, 200)
        html_a = resp_a.content.decode()
        self.assertIn("Tramo Solo De A", html_a)
        self.assertNotIn("Tramo Solo De B", html_a)

        resp_b = self.client.get(api_url, {"linea_id": str(linea_b.id)})
        self.assertEqual(resp_b.status_code, 200)
        html_b = resp_b.content.decode()
        self.assertIn("Tramo Solo De B", html_b)
        self.assertNotIn("Tramo Solo De A", html_b)

    def test_form_bloque_creacion_solo_precarga_catalogos_no_filtra_tramo_por_get(self):
        """El <select> de Tramo del form estático arranca vacío/placeholder --
        el filtrado real ocurre por el hx-get de A2 al elegir Línea, no en el
        GET inicial del form. Confirma que no quedó ningún tramo de OTRA
        línea precargado por accidente al crear un bloque nuevo."""
        _linea_a, _tramo_a = _crear_linea_con_tramo("A2C", "Tramo No Debe Precargar")
        url = reverse("cuadrillas:semanal_bloque_crear", args=[2026, 41])
        resp = self.client.post(url, {"nombre": "Bloque sin linea"})
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("Tramo No Debe Precargar", resp.content.decode())


# ---------------------------------------------------------------------------
# A3 — Supervisor: rol=supervisor + área compatible con Mantenimiento
# ---------------------------------------------------------------------------
class TestA3SupervisorFiltradoPorArea(TestCase):
    def setUp(self):
        self.admin = _crear_admin()

    def _crear_supervisor(self, email, area=""):
        return Usuario.objects.create_user(
            email=email,
            password="testpass123!",
            first_name="Sup",
            last_name=email.split("@")[0],
            rol="supervisor",
            area=area,
            is_active=True,
        )

    def test_supervisor_sin_area_legacy_aparece(self):
        sup = self._crear_supervisor("sup_sin_area_209@test.com", area="")
        choices = _choices_form_bloque()
        self.assertIn(sup, list(choices["supervisores_bloque"]))

    def test_supervisor_area_mantenimiento_aparece(self):
        sup = self._crear_supervisor("sup_mant_209@test.com", area="MANTENIMIENTO")
        choices = _choices_form_bloque()
        self.assertIn(sup, list(choices["supervisores_bloque"]))

    def test_supervisor_area_construccion_no_aparece(self):
        sup = self._crear_supervisor("sup_constr_209@test.com", area="CONSTRUCCION")
        choices = _choices_form_bloque()
        self.assertNotIn(sup, list(choices["supervisores_bloque"]))

    def test_usuario_rol_no_supervisor_no_aparece_aunque_area_mantenimiento(self):
        liniero = Usuario.objects.create_user(
            email="liniero_209@test.com",
            password="testpass123!",
            first_name="Liniero",
            last_name="Test",
            rol="liniero",
            area="MANTENIMIENTO",
            is_active=True,
        )
        choices = _choices_form_bloque()
        self.assertNotIn(liniero, list(choices["supervisores_bloque"]))


# ---------------------------------------------------------------------------
# A4 — Personal activo sin restricción por área, buscable
# ---------------------------------------------------------------------------
class TestA4PersonalFiltradoPorAreaYActivo(TestCase):
    def _crear_personal(self, documento, nombre, area="", activo=True):
        return PersonalCuadrilla.objects.create(
            nombre=nombre,
            documento=documento,
            rol_cuadrilla_id="LINIERO_I",
            salario_base=Decimal("1500000"),
            activo=activo,
            area=area,
        )

    def test_personal_sin_area_legacy_visible(self):
        p = self._crear_personal("209-A4-01", "Legacy Sin Area", area="")
        visibles = list(_personal_visible_para_usuario(None))
        self.assertIn(p, visibles)

    def test_personal_area_mantenimiento_visible(self):
        p = self._crear_personal("209-A4-02", "De Mantenimiento", area="MANTENIMIENTO")
        visibles = list(_personal_visible_para_usuario(None))
        self.assertIn(p, visibles)

    def test_personal_area_construccion_visible(self):
        p = self._crear_personal("209-A4-03", "De Construccion", area="CONSTRUCCION")
        visibles = list(_personal_visible_para_usuario(None))
        self.assertIn(p, visibles)

    def test_personal_inactivo_no_visible(self):
        p = self._crear_personal("209-A4-04", "Inactivo Mant", area="MANTENIMIENTO", activo=False)
        visibles = list(_personal_visible_para_usuario(None))
        self.assertNotIn(p, visibles)

    def test_buscable_por_documento_cedula_ademas_de_nombre(self):
        """El <option> del select trae 'Nombre — Documento' -- una búsqueda
        por cédula (ej. últimos dígitos del documento) matchea el texto
        visible igual que una búsqueda por nombre o apellido (nombre es un
        único campo de texto libre en PersonalCuadrilla, sin apellido
        separado -- confirma la limitación real del modelo)."""
        self._crear_personal("209-CEDULA-9988", "Ana Restrepo Gomez", area="MANTENIMIENTO")
        admin = _crear_admin()
        client = Client()
        client.force_login(admin)
        url = reverse("cuadrillas:semanal_bloque_crear", args=[2026, 42])
        resp = client.post(url, {"nombre": "Bloque A4 buscar"})
        html = resp.content.decode()
        self.assertIn("Ana Restrepo Gomez — 209-CEDULA-9988", html)
