"""Instelec#267 — A8: Filtros Clasificación + Ciudad (issue Fase 2).

``PresupuestoPlaneadoConstruccionView`` (Construcción) lee ``?clasificacion=``
y ``?ciudad=`` del querystring y filtra ``filas_detalle`` (fuente de verdad
de A2) ANTES de reconstruir la matriz (Fase 2, ``_bimodal_context``) y la
tabla de Rubros (Fase 3, ``build_rubro_display_rows``). Reusa el MISMO
agregador rubro×mes que el importador (``_construir_finv2_bd_desde_filas_planas``)
para no duplicar la lógica de suma — el filtro solo cambia qué subconjunto de
filas entra.

KPI cards (A5, Fase 4) y el gate ``tiene_datos_bd`` NO se filtran a propósito:
el issue no pide filtrar la Fase 4, y un filtro sin resultados no puede
colapsar la pestaña completa a "sin datos cargados" (esos son estados
distintos — ver ``matrix_vacia_por_filtro``).

Cobertura:
- Unit (sin BD): ``_filtrar_filas_detalle``, ``_opciones_ciudad``,
  ``_datos_filtrados_por_clasificacion_ciudad`` — happy path, normalización
  de texto (acentos/mayúsculas), combinación de ambos filtros, sin
  filas_detalle (legacy) no rompe.
- Integración (GET real): tests_requeridos EXACTOS de F2 —
  "filtro Clasificacion=Fijo excluye Ingresos/Variable" y
  "filtro Ciudad=Barranquilla excluye otras ciudades" — más edge cases:
  ambos filtros combinados, filtro sin resultados (mensaje dedicado, no
  rompe), dato legacy sin filas_detalle (el filtro no se pinta), KPI cards
  siguen SIN filtrar.
"""
import re
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from apps.construccion.models import ProyectoConstruccion
from apps.construccion.models_fin import PresupuestoDetalladoConstruccion
from apps.construccion.views_fin import (
    _datos_filtrados_por_clasificacion_ciudad,
    _filtrar_filas_detalle,
    _opciones_ciudad,
)
from apps.contratos.models import Contrato

User = get_user_model()


def _filas_multi_ciudad_clasificacion():
    """3 rubros × 2 ciudades × 3 clasificaciones — fixture propia para A8,
    NO un catálogo de prod (regla del prompt del subagente)."""
    return [
        {'rubro': 'Ingresos Operacionales', 'clasificacion': 'Ingresos',
         'ciudad': 'Barranquilla', 'valor': -1000.0, 'mes': 9, 'anio': 2026,
         'codigo_contable': '4001'},
        {'rubro': 'Gastos de Personal', 'clasificacion': 'Fijo',
         'ciudad': 'Barranquilla', 'valor': 400.0, 'mes': 9, 'anio': 2026,
         'codigo_contable': '5101'},
        {'rubro': 'Materiales', 'clasificacion': 'Variable',
         'ciudad': 'Barranquilla', 'valor': 150.0, 'mes': 9, 'anio': 2026,
         'codigo_contable': '5201'},
        {'rubro': 'Ingresos Operacionales', 'clasificacion': 'Ingresos',
         'ciudad': 'Bogota', 'valor': -600.0, 'mes': 9, 'anio': 2026,
         'codigo_contable': '4001'},
        {'rubro': 'Gastos de Personal', 'clasificacion': 'Fijo',
         'ciudad': 'Bogota', 'valor': 250.0, 'mes': 9, 'anio': 2026,
         'codigo_contable': '5101'},
        {'rubro': 'Materiales', 'clasificacion': 'Variable',
         'ciudad': 'Bogota', 'valor': 90.0, 'mes': 9, 'anio': 2026,
         'codigo_contable': '5201'},
    ]


# ===========================================================================
# Unit — helpers de filtrado (sin BD)
# ===========================================================================
class FiltrarFilasDetalleTests(SimpleTestCase):
    def test_sin_filtro_devuelve_todo(self):
        filas = _filas_multi_ciudad_clasificacion()
        resultado = _filtrar_filas_detalle(filas, 'todos', 'todos')
        self.assertEqual(len(resultado), 6)

    def test_filtro_clasificacion_fijo_excluye_ingresos_variable(self):
        """tests_requeridos F2: 'filtro Clasificacion=Fijo excluye
        Ingresos/Variable'."""
        filas = _filas_multi_ciudad_clasificacion()
        resultado = _filtrar_filas_detalle(filas, 'fijo', 'todos')
        self.assertEqual(len(resultado), 2)
        self.assertTrue(all(f['clasificacion'] == 'Fijo' for f in resultado))

    def test_filtro_ciudad_barranquilla_excluye_otras_ciudades(self):
        """tests_requeridos F2: 'filtro Ciudad=Barranquilla excluye otras
        ciudades'."""
        filas = _filas_multi_ciudad_clasificacion()
        resultado = _filtrar_filas_detalle(filas, 'todos', 'Barranquilla')
        self.assertEqual(len(resultado), 3)
        self.assertTrue(all(f['ciudad'] == 'Barranquilla' for f in resultado))

    def test_combina_clasificacion_y_ciudad(self):
        """Ambos filtros activos a la vez — AND, no OR."""
        filas = _filas_multi_ciudad_clasificacion()
        resultado = _filtrar_filas_detalle(filas, 'fijo', 'Bogota')
        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]['rubro'], 'Gastos de Personal')
        self.assertEqual(resultado[0]['ciudad'], 'Bogota')

    def test_normaliza_mayusculas_acentos_espacios(self):
        """Comparación normalizada — mismo criterio que _kpi_cards_finv2_bd,
        no frágil ante cómo el cliente tipeó Clasificación/Ciudad."""
        filas = [
            {'rubro': 'R1', 'clasificacion': '  FIJO  ', 'ciudad': 'BOGOTÁ', 'valor': 1.0},
            {'rubro': 'R2', 'clasificacion': 'Variable', 'ciudad': 'Bogota', 'valor': 2.0},
        ]
        resultado = _filtrar_filas_detalle(filas, 'fijo', 'bogota')
        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]['rubro'], 'R1')

    def test_filtro_sin_matches_devuelve_lista_vacia_no_rompe(self):
        filas = _filas_multi_ciudad_clasificacion()
        resultado = _filtrar_filas_detalle(filas, 'fijo', 'Medellin')
        self.assertEqual(resultado, [])


class OpcionesCiudadTests(SimpleTestCase):
    def test_dedup_normalizado_conserva_primer_tipeo(self):
        filas = [
            {'ciudad': 'Barranquilla'},
            {'ciudad': 'barranquilla '},
            {'ciudad': 'Bogota'},
            {'ciudad': ''},
            {'ciudad': None},
        ]
        opciones = _opciones_ciudad(filas)
        self.assertEqual(opciones, ['Barranquilla', 'Bogota'])

    def test_filas_vacias_devuelve_lista_vacia(self):
        self.assertEqual(_opciones_ciudad([]), [])


class DatosFiltradosPorClasificacionCiudadTests(SimpleTestCase):
    def test_reconstruye_finv2_bd_solo_con_filas_filtradas(self):
        datos = {'finv2_bd': {
            'rubros': {'x': {'total': 1}}, 'total': 1,
            'filas_detalle': _filas_multi_ciudad_clasificacion(),
        }}
        filtrado = _datos_filtrados_por_clasificacion_ciudad(datos, 'fijo', 'todos')
        rubros = filtrado['finv2_bd']['rubros']
        self.assertEqual(set(rubros.keys()), {'Gastos de Personal'})
        # 400 (Barranquilla) + 250 (Bogota) = 650 — el agregador reusado
        # (_construir_finv2_bd_desde_filas_planas) suma ambas ciudades juntas
        # cuando solo se filtra por Clasificación.
        self.assertEqual(rubros['Gastos de Personal']['total'], 650.0)

    def test_sin_filas_detalle_legacy_devuelve_datos_intacto(self):
        datos = {'ingreso': {'Ventas': {'enero': 100}}, 'variables': {}, 'fijos': {}}
        filtrado = _datos_filtrados_por_clasificacion_ciudad(datos, 'fijo', 'todos')
        self.assertEqual(filtrado, datos)

    def test_sin_filtro_activo_devuelve_mismo_objeto_datos(self):
        datos = {'finv2_bd': {
            'rubros': {}, 'total': 0,
            'filas_detalle': _filas_multi_ciudad_clasificacion(),
        }}
        filtrado = _datos_filtrados_por_clasificacion_ciudad(datos, 'todos', 'todos')
        self.assertIs(filtrado, datos)


# ===========================================================================
# Integración — GET real (Construcción, Presupuesto Planeado)
# ===========================================================================
def _crear_proyecto(nombre='Proyecto A8 test #267'):
    contrato = Contrato.objects.create(
        codigo=f"CONS-{uuid.uuid4().hex[:10]}",
        nombre='Contrato test construcción #267 A8',
        unidad_negocio='CONSTRUCCION',
    )
    return ProyectoConstruccion.objects.create(contrato=contrato, nombre=nombre)


def _crear_usuario_admin():
    try:
        return User.objects.create_superuser(
            username=f'qa_267a8_{uuid.uuid4().hex[:6]}',
            email=f'qa_267a8_{uuid.uuid4().hex[:6]}@instelec.com', password='x',
        )
    except TypeError:
        user = User(is_superuser=True, is_staff=True)
        if hasattr(user, 'email'):
            user.email = f'qa_267a8_{uuid.uuid4().hex[:6]}@instelec.com'
        user.set_password('x')
        user.save()
        return user


class PresupuestoPlaneadoFiltrosRenderTests(TestCase):
    def setUp(self):
        self.proyecto = _crear_proyecto()
        self.user = _crear_usuario_admin()
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse('construccion:fin_presupuesto_planeado',
                            kwargs={'proyecto_id': self.proyecto.pk})
        filas = _filas_multi_ciudad_clasificacion()
        PresupuestoDetalladoConstruccion.objects.create(
            proyecto=self.proyecto, anio=2026,
            tipo=PresupuestoDetalladoConstruccion.Tipo.PLANEADO,
            datos={'finv2_bd': {
                'rubros': {
                    'Ingresos Operacionales': {'total': -1600.0, 'meses': {}, 'cuentas': []},
                    'Gastos de Personal': {'total': 650.0, 'meses': {}, 'cuentas': []},
                    'Materiales': {'total': 240.0, 'meses': {}, 'cuentas': []},
                },
                'total': -710.0,
                'filas_detalle': filas,
            }},
        )

    def test_sin_filtro_muestra_los_3_rubros(self):
        resp = self.client.get(self.url, {'anio': 2026, 'tab': 'tabla'})
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn('Ingresos Operacionales', content)
        self.assertIn('Gastos de Personal', content)
        self.assertIn('Materiales', content)

    def test_filtro_clasificacion_fijo_excluye_ingresos_variable(self):
        """tests_requeridos F2, vía GET real: la tabla de Rubros SOLO muestra
        'Gastos de Personal' (Fijo) y NO los rubros de Ingresos/Variable.

        Comparación anclada a ``data-rubro="..."`` (no substring suelto del
        nombre) — la página trae nav/sidebar globales que pueden mencionar
        palabras sueltas del dominio ("Materiales", etc.) sin relación con
        esta tabla; un assertNotIn de texto libre da falso rojo."""
        resp = self.client.get(self.url, {'anio': 2026, 'clasificacion': 'fijo'})
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn('data-rubro="Gastos de Personal"', content)
        self.assertNotIn('data-rubro="Ingresos Operacionales"', content)
        self.assertNotIn('data-rubro="Materiales"', content)
        # El select refleja la selección
        self.assertIn('value="fijo" selected', content)

    def test_filtro_ciudad_barranquilla_excluye_otras_ciudades(self):
        """tests_requeridos F2, vía GET real: con ?ciudad=Barranquilla los 3
        rubros siguen apareciendo (cada uno tiene fila en Barranquilla) pero
        el TOTAL de cada uno baja (ya no suma Bogotá) — verificado contra el
        agregado de Barranquilla-only calculado en el helper unit, anclado a
        la fila exacta (``data-rubro="..."``) para no colisionar con otro
        número "650"/"400" que pueda aparecer en el resto de la página."""
        resp = self.client.get(self.url, {'anio': 2026, 'ciudad': 'Barranquilla'})
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        fila = re.search(
            r'<tr[^>]*data-rubro="Gastos de Personal".*?</tr>', content, re.S)
        self.assertIsNotNone(fila, 'fila de Gastos de Personal no encontrada')
        self.assertIn('400', fila.group())
        self.assertNotIn('650', fila.group())

    def test_filtro_sin_resultados_no_rompe_y_muestra_mensaje(self):
        """Clasificación + Ciudad que no matchean ninguna fila → 200, mensajes
        dedicados en matriz y tabla de rubros, NO el error de datos degradados."""
        resp = self.client.get(
            self.url, {'anio': 2026, 'clasificacion': 'fijo', 'ciudad': 'Medellin'})
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn('No hay rubros para el filtro seleccionado', content)
        self.assertIn('No hay datos para el filtro seleccionado', content)
        self.assertNotIn('No se pudo construir la matriz mensual', content)

    def test_tiene_datos_bd_no_colapsa_con_filtro_sin_resultados(self):
        """El gate tiene_datos_bd usa el dato SIN filtrar — un filtro sin
        matches no debe ocultar la sección/tabs completos."""
        resp = self.client.get(
            self.url, {'anio': 2026, 'clasificacion': 'fijo', 'ciudad': 'Medellin'})
        content = resp.content.decode()
        # La sección "Rubros (Base de Datos contable)" se sigue pintando
        # (aunque con 0 filas) — solo el <thead>/mensaje de vacío.
        self.assertIn('Rubros (Base de Datos contable)', content)

    def test_kpi_cards_no_se_filtran(self):
        """A5 (Fase 4) sigue mostrando el TOTAL sin filtrar aunque haya un
        filtro Clasificación/Ciudad activo — el issue no pide filtrar ahí.
        Anclado a ``data-kpi="ingreso"`` (mismo patrón que A5) para no
        colisionar con otro "1.600" suelto en el resto de la página."""
        resp = self.client.get(self.url, {'anio': 2026, 'clasificacion': 'fijo'})
        content = resp.content.decode()
        bloque = re.search(r'data-kpi="ingreso".*?</div>', content, re.S)
        self.assertIsNotNone(bloque, 'bloque KPI ingreso no encontrado')
        # Ingreso total sin filtrar es -1600 (Barranquilla -1000 + Bogota -600),
        # NO -1000 (que sería el resultado si se hubiese filtrado por Fijo).
        self.assertIn('1.600', bloque.group())

    def test_dropdowns_ofrecen_las_ciudades_reales_cargadas(self):
        resp = self.client.get(self.url, {'anio': 2026})
        content = resp.content.decode()
        self.assertIn('Barranquilla', content)
        self.assertIn('Bogota', content)
        self.assertIn('name="clasificacion"', content)
        self.assertIn('name="ciudad"', content)

    def test_limpiar_filtros_visible_solo_con_filtro_activo(self):
        resp_sin_filtro = self.client.get(self.url, {'anio': 2026})
        self.assertNotIn('Limpiar filtros', resp_sin_filtro.content.decode())
        resp_con_filtro = self.client.get(self.url, {'anio': 2026, 'clasificacion': 'fijo'})
        self.assertIn('Limpiar filtros', resp_con_filtro.content.decode())

    def test_dato_legacy_sin_filas_detalle_no_pinta_filtro_y_responde_200(self):
        """Presupuesto legacy (sin finv2_bd/filas_detalle) → el <select> de
        filtros no se pinta (no hay Clasificación/Ciudad por fila), pero la
        vista sigue respondiendo 200 sin romper."""
        PresupuestoDetalladoConstruccion.objects.filter(
            proyecto=self.proyecto, anio=2026,
        ).update(datos={'ingreso': {'Ventas': {'enero': 100}}, 'variables': {}, 'fijos': {}})
        resp = self.client.get(self.url, {'anio': 2026, 'clasificacion': 'fijo'})
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertNotIn('name="clasificacion"', content)
        self.assertNotIn('name="ciudad"', content)
