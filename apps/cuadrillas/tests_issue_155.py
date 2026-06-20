"""
Tests del issue #155 — Programación de Cuadrillas:
  - Sprint A (FIX): el listado expone los botones "Nueva cuadrilla" y
    "Nueva programación" (cliente: "no permite agregar nueva cuadrilla como en
    Mantenimiento").
  - Sprint B (FEATURE item 12): campo `bloque` (obra_civil / montaje / tendido)
    en `ProgramacionSemanalCuadrilla` — form lo acepta con/sin valor, el filtro
    `?bloque=` funciona y `?bloque=basura` no rompe el listado, el badge se
    muestra en listado y detalle.

Cubre el contrato del journey:
  - listado: texto "Nueva cuadrilla" + link /cuadrillas/crear/ + "Nueva programación"
  - form crear: name="bloque" con opciones "Obra civil"/"Montaje"/"Tendido"
  - listado ?bloque=obra_civil → 200 + name="bloque"
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.cuadrillas.forms_pc import ProgramacionSemanalCuadrillaForm
from apps.cuadrillas.models import Cuadrilla
from apps.cuadrillas.models_pc import ProgramacionSemanalCuadrilla

User = get_user_model()


def _make_admin(email='qa155@test.local'):
    """Usuario rol admin (RBAC v2) — pasa el RoleRequiredMixin de las vistas.

    El user model usa USERNAME_FIELD='email' y un `rol` (no username); espeja el
    helper de tests_pc.py.
    """
    return User.objects.create_user(
        email=email,
        password='ClaudeQA2026!',
        first_name='QA',
        last_name='155',
        rol=User.Rol.ADMIN_CONSTRUCCION,
        is_active=True,
    )


class Issue155ListadoBotonesTests(TestCase):
    """Sprint A — botones de creación visibles en el listado."""

    def setUp(self):
        self.user = _make_admin()
        self.client.force_login(self.user)
        self.url = reverse('construccion:programacion_cuadrillas_index')

    def test_listado_expone_boton_nueva_cuadrilla(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Nueva cuadrilla')
        # El link apunta a la vista de Mantenimiento reusada.
        self.assertContains(resp, reverse('cuadrillas:crear'))
        self.assertContains(resp, '/cuadrillas/crear/')

    def test_listado_expone_boton_nueva_programacion(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Nueva programación')
        self.assertContains(
            resp, reverse('construccion:programacion_cuadrilla_crear')
        )


class Issue155FormBloqueTests(TestCase):
    """Sprint B — el form acepta `bloque` con y sin valor."""

    def setUp(self):
        self.cuadrilla = Cuadrilla.objects.create(
            codigo='C155', nombre='Cuadrilla 155', activa=True,
        )

    def _base_data(self, **extra):
        data = {
            'cuadrilla': str(self.cuadrilla.pk),
            'anio': 2026,
            'semana': 10,
            'torres_programadas': 3,
            'actividades_programadas': '',
            'observaciones': '',
        }
        data.update(extra)
        return data

    def test_bloque_en_fields_del_form(self):
        self.assertIn('bloque', ProgramacionSemanalCuadrillaForm.base_fields)

    def test_form_valido_sin_bloque(self):
        form = ProgramacionSemanalCuadrillaForm(data=self._base_data())
        self.assertTrue(form.is_valid(), form.errors)
        obj = form.save()
        self.assertIsNone(obj.bloque)

    def test_form_valido_con_bloque(self):
        form = ProgramacionSemanalCuadrillaForm(
            data=self._base_data(bloque='montaje')
        )
        self.assertTrue(form.is_valid(), form.errors)
        obj = form.save()
        self.assertEqual(obj.bloque, 'montaje')
        self.assertEqual(obj.get_bloque_display(), 'Montaje')

    def test_form_rechaza_bloque_invalido(self):
        form = ProgramacionSemanalCuadrillaForm(
            data=self._base_data(bloque='no_existe')
        )
        self.assertFalse(form.is_valid())
        self.assertIn('bloque', form.errors)

    def test_form_render_tiene_las_3_opciones(self):
        form = ProgramacionSemanalCuadrillaForm()
        html = str(form['bloque'])
        self.assertIn('name="bloque"', html)
        self.assertIn('Obra civil', html)
        self.assertIn('Montaje', html)
        self.assertIn('Tendido', html)


class Issue155FiltroBloqueTests(TestCase):
    """Sprint B — filtro `?bloque=` en el listado."""

    def setUp(self):
        self.user = _make_admin()
        self.client.force_login(self.user)
        self.url = reverse('construccion:programacion_cuadrillas_index')
        self.cuadrilla = Cuadrilla.objects.create(
            codigo='CF155', nombre='Cuadrilla filtro', activa=True,
        )
        self.p_obra = ProgramacionSemanalCuadrilla.objects.create(
            cuadrilla=self.cuadrilla, anio=2026, semana=5,
            torres_programadas=2, bloque='obra_civil',
        )
        self.cuadrilla2 = Cuadrilla.objects.create(
            codigo='CF155B', nombre='Cuadrilla filtro 2', activa=True,
        )
        self.p_montaje = ProgramacionSemanalCuadrilla.objects.create(
            cuadrilla=self.cuadrilla2, anio=2026, semana=5,
            torres_programadas=4, bloque='montaje',
        )
        # Una fila legacy sin bloque (no debe romper nada).
        self.cuadrilla3 = Cuadrilla.objects.create(
            codigo='CF155C', nombre='Cuadrilla legacy', activa=True,
        )
        self.p_legacy = ProgramacionSemanalCuadrilla.objects.create(
            cuadrilla=self.cuadrilla3, anio=2026, semana=5,
            torres_programadas=1, bloque=None,
        )

    def test_filtro_bloque_obra_civil(self):
        resp = self.client.get(self.url, {'bloque': 'obra_civil'})
        self.assertEqual(resp.status_code, 200)
        # El selector de filtro está presente.
        self.assertContains(resp, 'name="bloque"')
        progs = list(resp.context['programaciones'])
        self.assertIn(self.p_obra, progs)
        self.assertNotIn(self.p_montaje, progs)
        self.assertNotIn(self.p_legacy, progs)

    def test_filtro_bloque_basura_no_rompe(self):
        resp = self.client.get(self.url, {'bloque': 'no-es-un-bloque'})
        self.assertEqual(resp.status_code, 200)
        # Filtro inválido se ignora → muestra todo (sin filtrar por bloque).
        progs = list(resp.context['programaciones'])
        self.assertIn(self.p_obra, progs)
        self.assertIn(self.p_montaje, progs)
        self.assertIn(self.p_legacy, progs)

    def test_listado_muestra_badge_bloque(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Obra civil')
        self.assertContains(resp, 'Montaje')

    def test_detalle_muestra_bloque(self):
        url = reverse(
            'construccion:programacion_cuadrilla_detalle',
            kwargs={'pk': self.p_obra.pk},
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Obra civil')


# ===========================================================================
# Sprint UI #155 (RUN_2026-06-20) — 5 mejoras UI + mapa por proyecto (lat/lng).
# Tests de los sub-items con deploy: prefill semana ISO (sub1), dashboard de
# cumplimiento inline en el detalle (sub2) y coordenadas de proyecto para el
# mapa (sub5). TomSelect (sub1/3/4) es JS de cliente → cubierto por el journey
# E2E; aquí se valida que el contexto/servidor entrega los datos correctos.
# ===========================================================================
from datetime import date

from apps.cuadrillas.views import CuadrillaListView
from apps.cuadrillas.views_pc_programacion import (
    ProgramacionCuadrillaCreateView,
)


class Issue155PrefillSemanaTests(TestCase):
    """sub1 — el CreateView prefilla anio/semana con la semana ISO actual."""

    def test_get_initial_prefilla_anio_y_semana_iso(self):
        view = ProgramacionCuadrillaCreateView()
        view.request = None
        initial = view.get_initial()
        iso = date.today().isocalendar()
        # AÑO ISO (no date.today().year) por coherencia en bordes de año.
        self.assertEqual(initial['anio'], iso[0])
        self.assertEqual(initial['semana'], iso[1])

    def test_get_initial_no_pisa_valores_existentes(self):
        """Si ya viene un initial, respetarlo (editable)."""
        view = ProgramacionCuadrillaCreateView()
        view.request = None
        view.initial = {'anio': 2020, 'semana': 1}
        initial = view.get_initial()
        self.assertEqual(initial['anio'], 2020)
        self.assertEqual(initial['semana'], 1)


class Issue155DashboardCumplimientoInlineTests(TestCase):
    """sub2 — el DetailView pasa datos de cumplimiento (no el placeholder)."""

    def setUp(self):
        self.user = _make_admin(email='qa155dash@test.local')
        self.client.force_login(self.user)
        self.cuadrilla = Cuadrilla.objects.create(
            codigo='C155DASH', nombre='Cuadrilla dash', activa=True,
        )
        # Dos programaciones de la misma cuadrilla/año → filas de cumplimiento.
        self.p1 = ProgramacionSemanalCuadrilla.objects.create(
            cuadrilla=self.cuadrilla, anio=2026, semana=10,
            torres_programadas=5,
        )
        self.p2 = ProgramacionSemanalCuadrilla.objects.create(
            cuadrilla=self.cuadrilla, anio=2026, semana=11,
            torres_programadas=4,
        )
        self.url = reverse(
            'construccion:programacion_cuadrilla_detalle',
            kwargs={'pk': self.p1.pk},
        )

    def test_detalle_pasa_datos_cumplimiento_al_contexto(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        ctx = resp.context
        # El contexto trae las filas/chart_data del inline (no solo rendimiento_pct).
        self.assertIn('cumplimiento_filas', ctx)
        self.assertIn('cumplimiento_chart_data', ctx)
        # Ambas programaciones de la cuadrilla aparecen como filas.
        periodos = {f['periodo'] for f in ctx['cumplimiento_filas']}
        self.assertEqual(periodos, {'2026-S10', '2026-S11'})
        self.assertEqual(ctx['cumplimiento_total_programadas'], 9)

    def test_detalle_ya_no_muestra_el_placeholder(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'se mostrará aquí')
        # El payload del chart va por json_script (objeto crudo, sin doble-encoding).
        self.assertContains(resp, 'cumplimiento-chart-data')


class Issue155MapaPorProyectoTests(TestCase):
    """sub5 — el modelo proyecto acepta lat/lng y el mapa serializa los puntos."""

    @staticmethod
    def _make_proyecto(lat, lng, codigo='CT-155'):
        from apps.contratos.models import Contrato
        from apps.construccion.models import ProyectoConstruccion

        contrato = Contrato.objects.create(
            unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
            codigo=codigo,
            nombre=f'Contrato {codigo}',
        )
        return ProyectoConstruccion.objects.create(
            contrato=contrato,
            nombre=f'Proyecto {codigo}',
            latitud=lat,
            longitud=lng,
        )

    def test_modelo_proyecto_acepta_lat_lng(self):
        from decimal import Decimal
        from apps.construccion.models import ProyectoConstruccion

        proyecto = self._make_proyecto(Decimal('7.1193'), Decimal('-73.1227'))
        proyecto.refresh_from_db()
        self.assertEqual(proyecto.latitud, Decimal('7.1193000'))
        self.assertEqual(proyecto.longitud, Decimal('-73.1227000'))
        # lat/lng son opcionales (un proyecto sin coords es válido).
        sin_coords = self._make_proyecto(None, None, codigo='CT-155B')
        sin_coords.refresh_from_db()
        self.assertIsNone(sin_coords.latitud)

    def test_mapa_serializa_punto_del_proyecto_asignado(self):
        from decimal import Decimal

        proyecto = self._make_proyecto(Decimal('7.1193'), Decimal('-73.1227'))
        cuadrilla = Cuadrilla.objects.create(
            codigo='C155MAP', nombre='Cuadrilla map', activa=True,
        )
        ProgramacionSemanalCuadrilla.objects.create(
            cuadrilla=cuadrilla, anio=2026, semana=12,
            torres_programadas=3, proyecto=proyecto,
        )
        puntos = CuadrillaListView._build_ubicaciones_proyecto([cuadrilla])
        self.assertEqual(len(puntos), 1)
        self.assertAlmostEqual(puntos[0]['lat'], 7.1193, places=4)
        self.assertAlmostEqual(puntos[0]['lng'], -73.1227, places=4)
        self.assertEqual(puntos[0]['cuadrilla_codigo'], 'C155MAP')
        self.assertEqual(puntos[0]['proyecto_nombre'], proyecto.nombre)

    def test_mapa_robusto_a_cuadrilla_sin_proyecto_geo(self):
        """Sin proyecto/coords → la cuadrilla se omite (no rompe el mapa)."""
        cuadrilla = Cuadrilla.objects.create(
            codigo='C155NOGEO', nombre='Sin geo', activa=True,
        )
        # Programación sin proyecto.
        ProgramacionSemanalCuadrilla.objects.create(
            cuadrilla=cuadrilla, anio=2026, semana=13, torres_programadas=1,
        )
        puntos = CuadrillaListView._build_ubicaciones_proyecto([cuadrilla])
        self.assertEqual(puntos, [])
