"""
Tests issue #188 — Rediseño Programación Semanal de Cuadrillas (Sprint A).

Cubre A1-A11 (implementación en curso, ver
Instelec/SPRINTS/PLAN_2026-07-19_188_rediseno_cuadrillas.md). Cada bloque de
clases corresponde a un sub-item del sprint. A12 (este mismo archivo) es la
consolidación final del set de tests.

Ejecutar con:
    pytest apps/cuadrillas/tests_issue_188.py -v
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.cuadrillas.models import (
    Cargo,
    Cuadrilla,
    CuadrillaMiembro,
    PersonalCuadrilla,
)

Usuario = get_user_model()


def _crear_admin():
    return Usuario.objects.create_user(
        email="admin_188@test.com",
        password="testpass123!",
        first_name="Admin",
        last_name="Test188",
        rol="admin",
        is_staff=True,
        is_superuser=True,
    )


def _crear_usuario_miembro(documento, nombre="Colaborador Test188"):
    partes = nombre.split(maxsplit=1)
    return Usuario.objects.create(
        email=f"{documento}@test188.local",
        documento=documento,
        first_name=partes[0],
        last_name=partes[1] if len(partes) > 1 else "",
        rol="liniero",
        is_active=True,
    )


# ---------------------------------------------------------------------------
# A1 — Migraciones aditivas: Cuadrilla.tipo_actividad/tramo,
# PersonalCuadrilla.celular, CuadrillaMiembro.placa_vehiculo
# ---------------------------------------------------------------------------
class TestA1MigracionesAditivas(TestCase):
    """Los campos nuevos son 100% opcionales — filas legacy (creadas sin
    ellos, simulando datos pre-existentes en prod) siguen leyendo bien."""

    def test_migraciones_aditivas_no_rompen_filas_existentes(self):
        # Cuadrilla legacy sin tipo_actividad/tramo.
        legacy_cuadrilla = Cuadrilla.objects.create(
            codigo="188-0001-LEG",
            nombre="Cuadrilla Legacy 188",
        )
        legacy_cuadrilla.refresh_from_db()
        self.assertIsNone(legacy_cuadrilla.tipo_actividad_id)
        self.assertIsNone(legacy_cuadrilla.tramo_id)

        # PersonalCuadrilla legacy sin celular.
        legacy_personal = PersonalCuadrilla.objects.create(
            nombre="Personal Legacy 188",
            documento="188-LEG-0001",
            rol_cuadrilla_id="LINIERO_I",
        )
        legacy_personal.refresh_from_db()
        self.assertEqual(legacy_personal.celular, "")

        # CuadrillaMiembro legacy sin placa_vehiculo.
        usuario = _crear_usuario_miembro("188-LEG-0002")
        legacy_miembro = CuadrillaMiembro.objects.create(
            cuadrilla=legacy_cuadrilla,
            usuario=usuario,
            rol_cuadrilla_id="LINIERO_I",
            fecha_inicio=date.today(),
        )
        legacy_miembro.refresh_from_db()
        self.assertEqual(legacy_miembro.placa_vehiculo, "")

    def test_puede_setear_campos_nuevos_sin_error(self):
        from apps.actividades.models import TipoActividad
        from apps.lineas.models import Linea, Tramo, Torre

        linea = Linea.objects.create(codigo="188-L1", nombre="Linea 188", cliente="TRANSELCA")
        t1 = Torre.objects.create(linea=linea, numero="1", latitud="7.00000000", longitud="-75.50000000")
        t2 = Torre.objects.create(linea=linea, numero="2", latitud="7.00100000", longitud="-75.50100000")
        tramo = Tramo.objects.create(
            linea=linea, codigo="188-TRM-1", nombre="Tramo 188", torre_inicio=t1, torre_fin=t2
        )
        tipo = TipoActividad.objects.create(
            codigo="188-TA1", nombre="Poda 188", categoria="PODA"
        )
        cuadrilla = Cuadrilla.objects.create(
            codigo="188-0002-NEW",
            nombre="Cuadrilla con campos nuevos",
            tipo_actividad=tipo,
            tramo=tramo,
        )
        cuadrilla.refresh_from_db()
        self.assertEqual(cuadrilla.tipo_actividad_id, tipo.id)
        self.assertEqual(cuadrilla.tramo_id, tramo.id)


# ---------------------------------------------------------------------------
# A2 — Shell interactivo del grid (partials HTMX/Alpine)
# ---------------------------------------------------------------------------
class TestA2ShellGridInteractivo(TestCase):
    """Render-only: el grid renderiza con 0/1/N bloques sin error, usando los
    nuevos partials _bloque_card.html/_bloque_form.html."""

    def setUp(self):
        self.admin = _crear_admin()
        self.client = Client()
        self.client.force_login(self.admin)

    def _url(self, anio=2026, semana=51):
        return reverse("cuadrillas:semanal_grid", args=[anio, semana])

    def test_grid_renderiza_sin_bloques(self):
        resp = self.client.get(self._url(anio=2099, semana=1))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id="bloques-lista"')
        self.assertContains(resp, 'id="btn-nuevo-bloque"')

    def test_grid_renderiza_con_un_bloque(self):
        Cuadrilla.objects.create(codigo="51-2026-0001-A2T", nombre="Bloque A2 Uno", activa=True)
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Bloque A2 Uno")
        self.assertContains(resp, 'data-bloque-codigo="51-2026-0001-A2T"')

    def test_grid_renderiza_con_n_bloques_y_miembros(self):
        usuario = _crear_usuario_miembro("188-A2-0001", "Trabajador A2 Dos")
        for i in range(3):
            c = Cuadrilla.objects.create(
                codigo=f"51-2026-000{i + 2}-A2T", nombre=f"Bloque A2 {i}", activa=True
            )
            if i == 0:
                CuadrillaMiembro.objects.create(
                    cuadrilla=c,
                    usuario=usuario,
                    rol_cuadrilla_id="LINIERO_I",
                    fecha_inicio=date.today(),
                )
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Trabajador A2 Dos")
        self.assertEqual(resp.content.decode().count('data-bloque-codigo='), 3)


# ---------------------------------------------------------------------------
# A3 — Endpoint crear bloque + cascada Línea→Tramo AJAX
# ---------------------------------------------------------------------------
class TestA3CrearBloqueCascadaTramo(TestCase):
    def setUp(self):
        self.admin = _crear_admin()
        self.client = Client()
        self.client.force_login(self.admin)

    def _crear_linea_con_tramo(self):
        from apps.lineas.models import Linea, Torre, Tramo

        linea = Linea.objects.create(codigo="188-A3-L1", nombre="Linea A3", cliente="TRANSELCA")
        t1 = Torre.objects.create(linea=linea, numero="1", latitud="7.0", longitud="-75.5")
        t2 = Torre.objects.create(linea=linea, numero="2", latitud="7.01", longitud="-75.51")
        tramo = Tramo.objects.create(
            linea=linea, codigo="188-A3-TRM1", nombre="Tramo A3 Uno", torre_inicio=t1, torre_fin=t2
        )
        return linea, tramo

    def test_happy_crear_bloque_con_tramo_real(self):
        linea, tramo = self._crear_linea_con_tramo()
        url = reverse("cuadrillas:semanal_bloque_crear", args=[2026, 40])
        resp = self.client.post(
            url,
            {
                "nombre": "Bloque A3 Feliz",
                "linea_asignada": str(linea.id),
                "tramo": str(tramo.id),
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Bloque A3 Feliz")
        self.assertContains(resp, "Tramo A3 Uno")
        creado = Cuadrilla.objects.get(nombre="Bloque A3 Feliz")
        self.assertEqual(creado.linea_asignada_id, linea.id)
        self.assertEqual(creado.tramo_id, tramo.id)
        self.assertTrue(creado.codigo.startswith("40-2026-"))

    def test_edge_linea_sin_tramos_combo_vacio_no_rompe(self):
        from apps.lineas.models import Linea

        linea = Linea.objects.create(codigo="188-A3-L2", nombre="Linea Sin Tramos", cliente="TRANSELCA")
        api_url = reverse("cuadrillas:tramos_por_linea_api")
        resp = self.client.get(api_url, {"linea_id": str(linea.id)})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("— Sin tramo —", resp.content.decode())

        url = reverse("cuadrillas:semanal_bloque_crear", args=[2026, 40])
        resp = self.client.post(url, {"nombre": "Bloque Linea Sin Tramos", "linea_asignada": str(linea.id)})
        self.assertEqual(resp.status_code, 200)
        creado = Cuadrilla.objects.get(nombre="Bloque Linea Sin Tramos")
        self.assertIsNone(creado.tramo_id)

    def test_edge_tipo_actividad_y_tramo_omitidos_bloque_se_crea_igual(self):
        url = reverse("cuadrillas:semanal_bloque_crear", args=[2026, 41])
        resp = self.client.post(url, {"nombre": "Bloque Minimo A3"})
        self.assertEqual(resp.status_code, 200)
        creado = Cuadrilla.objects.get(nombre="Bloque Minimo A3")
        self.assertIsNone(creado.tipo_actividad_id)
        self.assertIsNone(creado.tramo_id)
        self.assertIsNone(creado.linea_asignada_id)

    def test_edge_nombre_vacio_no_crea_bloque_y_muestra_error(self):
        url = reverse("cuadrillas:semanal_bloque_crear", args=[2026, 42])
        antes = Cuadrilla.objects.count()
        resp = self.client.post(url, {"nombre": ""})
        self.assertEqual(resp.status_code, 400)
        self.assertContains(resp, "obligatorio", status_code=400)
        self.assertEqual(Cuadrilla.objects.count(), antes)


# ---------------------------------------------------------------------------
# A4 — Endpoint editar bloque existente
# ---------------------------------------------------------------------------
class TestA4EditarBloqueExistente(TestCase):
    def setUp(self):
        self.admin = _crear_admin()
        self.client = Client()
        self.client.force_login(self.admin)
        self.cuadrilla = Cuadrilla.objects.create(
            codigo="43-2026-0001-A4T", nombre="Bloque A4 Original", activa=True
        )

    def test_happy_editar_nombre_y_tramo_persiste(self):
        from apps.lineas.models import Linea, Torre, Tramo

        linea = Linea.objects.create(codigo="188-A4-L1", nombre="Linea A4", cliente="TRANSELCA")
        t1 = Torre.objects.create(linea=linea, numero="1", latitud="7.0", longitud="-75.5")
        t2 = Torre.objects.create(linea=linea, numero="2", latitud="7.01", longitud="-75.51")
        tramo = Tramo.objects.create(
            linea=linea, codigo="188-A4-TRM1", nombre="Tramo A4 Uno", torre_inicio=t1, torre_fin=t2
        )
        url = reverse("cuadrillas:semanal_bloque_editar", args=[self.cuadrilla.id])
        resp = self.client.post(
            url,
            {
                "nombre": "Bloque A4 Editado",
                "linea_asignada": str(linea.id),
                "tramo": str(tramo.id),
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Bloque A4 Editado")
        self.cuadrilla.refresh_from_db()
        self.assertEqual(self.cuadrilla.nombre, "Bloque A4 Editado")
        self.assertEqual(self.cuadrilla.tramo_id, tramo.id)

    def test_edge_guardar_sin_cambios_no_rompe(self):
        url = reverse("cuadrillas:semanal_bloque_editar", args=[self.cuadrilla.id])
        resp = self.client.post(url, {"nombre": self.cuadrilla.nombre})
        self.assertEqual(resp.status_code, 200)
        self.cuadrilla.refresh_from_db()
        self.assertEqual(self.cuadrilla.nombre, "Bloque A4 Original")

    def test_edge_nombre_vacio_no_guarda_y_reabre_form(self):
        url = reverse("cuadrillas:semanal_bloque_editar", args=[self.cuadrilla.id])
        resp = self.client.post(url, {"nombre": ""})
        self.assertEqual(resp.status_code, 400)
        self.assertContains(resp, "obligatorio", status_code=400)
        self.assertContains(resp, 'id="form-editar-bloque"', status_code=400)
        self.cuadrilla.refresh_from_db()
        self.assertEqual(self.cuadrilla.nombre, "Bloque A4 Original")


# ---------------------------------------------------------------------------
# A5 — Endpoint agregar personal (reusa maestro Colaboradores) + placa
# condicional Conductor
# ---------------------------------------------------------------------------
class TestA5AgregarPersonalBloque(TestCase):
    def setUp(self):
        self.admin = _crear_admin()
        self.client = Client()
        self.client.force_login(self.admin)
        self.cuadrilla = Cuadrilla.objects.create(
            codigo="44-2026-0001-A5T", nombre="Bloque A5", activa=True
        )
        self.url = reverse("cuadrillas:semanal_miembro_agregar", args=[self.cuadrilla.id])

    def test_happy_agregar_colaborador_existente_con_celular_visible(self):
        personal = PersonalCuadrilla.objects.create(
            nombre="Colaborador A5 Feliz",
            documento="188-A5-0001",
            rol_cuadrilla_id="LINIERO_I",
            celular="3009998877",
            activo=True,
        )
        resp = self.client.post(self.url, {"documento": personal.documento})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Colaborador A5 Feliz")
        self.assertContains(resp, "3009998877")
        miembro = CuadrillaMiembro.objects.get(cuadrilla=self.cuadrilla)
        self.assertEqual(miembro.usuario.documento, "188-A5-0001")
        self.assertTrue(miembro.activo)

    def test_edge_documento_inexistente_muestra_error_inline(self):
        resp = self.client.post(self.url, {"documento": "NO-EXISTE-188"})
        self.assertEqual(resp.status_code, 400)
        self.assertContains(resp, "No se encontró", status_code=400)
        self.assertFalse(CuadrillaMiembro.objects.filter(cuadrilla=self.cuadrilla).exists())

    def test_edge_cargo_conductor_sin_placa_bloqueado(self):
        PersonalCuadrilla.objects.create(
            nombre="Conductor A5",
            documento="188-A5-0002",
            rol_cuadrilla_id="CONDUCTOR",
            activo=True,
        )
        resp = self.client.post(self.url, {"documento": "188-A5-0002"})
        self.assertEqual(resp.status_code, 400)
        self.assertContains(resp, "Debe ingresar la placa del vehículo", status_code=400)
        self.assertFalse(CuadrillaMiembro.objects.filter(cuadrilla=self.cuadrilla).exists())

        # Con placa sí se crea.
        resp2 = self.client.post(self.url, {"documento": "188-A5-0002", "placa_vehiculo": "XYZ987"})
        self.assertEqual(resp2.status_code, 200)
        miembro = CuadrillaMiembro.objects.get(cuadrilla=self.cuadrilla)
        self.assertEqual(miembro.placa_vehiculo, "XYZ987")

    def test_edge_colaborador_con_usuario_ya_resuelto_no_duplica_usuario(self):
        usuario_existente = _crear_usuario_miembro("188-A5-0003", "Ya Resuelto A5")
        PersonalCuadrilla.objects.create(
            nombre="Ya Resuelto A5",
            documento="188-A5-0003",
            rol_cuadrilla_id="LINIERO_I",
            activo=True,
        )
        antes = Usuario.objects.filter(documento="188-A5-0003").count()
        resp = self.client.post(self.url, {"documento": "188-A5-0003"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Usuario.objects.filter(documento="188-A5-0003").count(), antes)
        miembro = CuadrillaMiembro.objects.get(cuadrilla=self.cuadrilla)
        self.assertEqual(miembro.usuario_id, usuario_existente.id)


# ---------------------------------------------------------------------------
# A6 — Endpoint quitar/inactivar personal de un bloque
# ---------------------------------------------------------------------------
class TestA6QuitarPersonalBloque(TestCase):
    def setUp(self):
        self.admin = _crear_admin()
        self.client = Client()
        self.client.force_login(self.admin)
        self.cuadrilla = Cuadrilla.objects.create(
            codigo="45-2026-0001-A6T", nombre="Bloque A6", activa=True
        )
        self.usuario = _crear_usuario_miembro("188-A6-0001", "Miembro A6 Quitar")
        self.miembro = CuadrillaMiembro.objects.create(
            cuadrilla=self.cuadrilla,
            usuario=self.usuario,
            rol_cuadrilla_id="LINIERO_I",
            fecha_inicio=date.today(),
        )

    def test_happy_quitar_miembro_desaparece_de_la_card(self):
        url = reverse("cuadrillas:semanal_miembro_quitar", args=[self.cuadrilla.id, self.miembro.id])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Miembro A6 Quitar")
        self.miembro.refresh_from_db()
        self.assertFalse(self.miembro.activo)
        self.assertEqual(self.miembro.fecha_fin, date.today())

    def test_edge_quitar_miembro_ya_inactivo_es_idempotente(self):
        self.miembro.activo = False
        self.miembro.fecha_fin = date.today()
        self.miembro.save(update_fields=["activo", "fecha_fin"])

        url = reverse("cuadrillas:semanal_miembro_quitar", args=[self.cuadrilla.id, self.miembro.id])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        self.miembro.refresh_from_db()
        self.assertFalse(self.miembro.activo)


# ---------------------------------------------------------------------------
# A7 — Validación de duplicado inline
# ---------------------------------------------------------------------------
class TestA7ValidacionDuplicadoInline(TestCase):
    def setUp(self):
        self.admin = _crear_admin()
        self.client = Client()
        self.client.force_login(self.admin)
        self.personal = PersonalCuadrilla.objects.create(
            nombre="Colaborador A7 Duplicado",
            documento="188-A7-0001",
            rol_cuadrilla_id="LINIERO_I",
            activo=True,
        )

    def test_happy_agregar_misma_persona_2_veces_mismo_bloque_muestra_aviso_no_duplica(self):
        cuadrilla = Cuadrilla.objects.create(codigo="46-2026-0001-A7T", nombre="Bloque A7", activa=True)
        url = reverse("cuadrillas:semanal_miembro_agregar", args=[cuadrilla.id])

        resp1 = self.client.post(url, {"documento": self.personal.documento})
        self.assertEqual(resp1.status_code, 200)

        resp2 = self.client.post(url, {"documento": self.personal.documento})
        self.assertEqual(resp2.status_code, 400)
        self.assertContains(resp2, "ya es miembro activo", status_code=400)

        self.assertEqual(
            CuadrillaMiembro.objects.filter(cuadrilla=cuadrilla, activo=True).count(), 1
        )

    def test_edge_misma_persona_en_2_bloques_distintos_es_valido(self):
        bloque1 = Cuadrilla.objects.create(codigo="46-2026-0002-A7T", nombre="Bloque A7 Uno", activa=True)
        bloque2 = Cuadrilla.objects.create(codigo="46-2026-0003-A7T", nombre="Bloque A7 Dos", activa=True)

        resp1 = self.client.post(
            reverse("cuadrillas:semanal_miembro_agregar", args=[bloque1.id]),
            {"documento": self.personal.documento},
        )
        self.assertEqual(resp1.status_code, 200)

        resp2 = self.client.post(
            reverse("cuadrillas:semanal_miembro_agregar", args=[bloque2.id]),
            {"documento": self.personal.documento},
        )
        self.assertEqual(resp2.status_code, 200)

        self.assertEqual(
            CuadrillaMiembro.objects.filter(usuario__documento="188-A7-0001", activo=True).count(), 2
        )


# ---------------------------------------------------------------------------
# A8 — Duplicar semana → editar el duplicado → guardar sin perder datos
# ---------------------------------------------------------------------------
class TestA8DuplicarEditarSinPerderDatos(TestCase):
    """Integración: ProgramacionSemanalDuplicarView (#178, C2, ya validado en
    prod) + la edición in-place nueva (A2-A7) sobre el MISMO modelo Cuadrilla/
    CuadrillaMiembro deben convivir sin pérdida de datos."""

    def setUp(self):
        self.admin = _crear_admin()
        self.client = Client()
        self.client.force_login(self.admin)

    def test_happy_duplicar_editar_duplicado_origen_intacto(self):
        origen = Cuadrilla.objects.create(
            codigo="47-2026-0001-A8T", nombre="Bloque A8 Origen", activa=True
        )
        usuario = _crear_usuario_miembro("188-A8-0001", "Miembro A8 Origen")
        CuadrillaMiembro.objects.create(
            cuadrilla=origen, usuario=usuario, rol_cuadrilla_id="LINIERO_I", fecha_inicio=date.today()
        )

        dup_url = reverse("cuadrillas:semanal_duplicar", args=[2026, 48])
        resp = self.client.post(dup_url)
        self.assertEqual(resp.status_code, 302)

        duplicado = Cuadrilla.objects.get(codigo="48-2026-0001-A8T")
        self.assertEqual(duplicado.miembros.filter(activo=True).count(), 1)

        editar_url = reverse("cuadrillas:semanal_bloque_editar", args=[duplicado.id])
        resp2 = self.client.post(editar_url, {"nombre": "Bloque A8 Duplicado Editado"})
        self.assertEqual(resp2.status_code, 200)
        self.assertContains(resp2, "Bloque A8 Duplicado Editado")

        # El origen (semana 47) sigue intacto — ni el nombre ni el miembro cambiaron.
        origen.refresh_from_db()
        self.assertEqual(origen.nombre, "Bloque A8 Origen")
        self.assertEqual(origen.miembros.filter(activo=True).count(), 1)

        # El duplicado (semana 48) sí persistió el cambio.
        duplicado.refresh_from_db()
        self.assertEqual(duplicado.nombre, "Bloque A8 Duplicado Editado")
