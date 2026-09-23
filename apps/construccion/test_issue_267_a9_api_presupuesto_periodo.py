"""Instelec#267 — A9: API GET /api/presupuesto/{proyecto_id}/periodo/{mes}/{año}
(Django Ninja, consumo de #246 Indicadores Financieros — issue Fase 6.2).

Cobertura:
- Happy path: response shape EXACTO del ejemplo del issue (5 claves, valores
  del caso Fase 4/6.2), restringido al mes/año pedidos.
- Filtrado por mes: filas de OTRO mes en el mismo año NO se mezclan en la
  respuesta (el A5/KPI cards agrega el año completo; A9 debe filtrar antes).
- 404 (nunca 200 con ceros — #246 no puede distinguir "cero real" de "sin
  dato"): proyecto inexistente, mes fuera de 1..12, año sin presupuesto
  PLANEADO cargado, presupuesto legacy sin ``finv2_bd``/``filas_detalle``, y
  mes/año sin ninguna fila.
- Seguridad (gotcha real del portafolio — Consof tuvo toda una API django-ninja
  abierta por falta de ``auth=`` explícito en el router): sin Bearer token
  → 401, NUNCA 200. Token inválido → 401 también.
"""
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.construccion.models import ProyectoConstruccion
from apps.construccion.models_fin import PresupuestoDetalladoConstruccion
from apps.contratos.models import Contrato

Usuario = get_user_model()


def _crear_proyecto(nombre='Proyecto A9 API test #267'):
    contrato = Contrato.objects.create(
        codigo=f"CONS-{uuid.uuid4().hex[:10]}",
        nombre='Contrato test construcción #267 A9',
        unidad_negocio='CONSTRUCCION',
    )
    return ProyectoConstruccion.objects.create(contrato=contrato, nombre=nombre)


def _crear_usuario(email=None):
    email = email or f'qa_267a9_{uuid.uuid4().hex[:8]}@instelec.com'
    return Usuario.objects.create_user(
        email=email, password='testpass123!',
        first_name='A9', last_name='Api', rol='admin',
        documento=f'267a9-{uuid.uuid4().hex[:8]}',
    )


def _bearer_header(usuario):
    token = str(RefreshToken.for_user(usuario).access_token)
    return {'HTTP_AUTHORIZATION': f'Bearer {token}'}


def _filas_caso_issue_mes9():
    """Caso EXACTO del issue (Fase 4/6.2), mes=9/2026."""
    return [
        {'rubro': 'Ingresos Operacionales', 'clasificacion': 'Ingresos',
         'valor': -23_511_292_673.0, 'mes': 9, 'anio': 2026, 'ciudad': 'Barranquilla'},
        {'rubro': 'Gastos de Personal', 'clasificacion': 'Fijo',
         'valor': 4_243_284_093.0, 'mes': 9, 'anio': 2026, 'ciudad': 'Barranquilla'},
        {'rubro': 'Materiales', 'clasificacion': 'Variable',
         'valor': 2_813_662_061.0, 'mes': 9, 'anio': 2026, 'ciudad': 'Barranquilla'},
    ]


class PresupuestoPeriodoApiTests(TestCase):
    def setUp(self):
        self.proyecto = _crear_proyecto()
        self.usuario = _crear_usuario()
        self.client = Client()
        self.url = (
            f'/api/presupuesto/{self.proyecto.pk}/periodo/9/2026'
        )

    # -----------------------------------------------------------------
    # Happy path — response shape exacto
    # -----------------------------------------------------------------
    def test_response_shape_exacto_caso_del_issue(self):
        PresupuestoDetalladoConstruccion.objects.create(
            proyecto=self.proyecto, anio=2026,
            tipo=PresupuestoDetalladoConstruccion.Tipo.PLANEADO,
            datos={'finv2_bd': {'filas_detalle': _filas_caso_issue_mes9()}},
        )
        resp = self.client.get(self.url, **_bearer_header(self.usuario))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Mismas 5 claves EXACTAS del ejemplo del issue, ni una de más/menos.
        self.assertEqual(
            set(data.keys()),
            {'periodo', 'proyecto', 'costos_fijos', 'costos_variables', 'ingresos', 'total_año'},
        )
        self.assertEqual(data['periodo'], '09/2026')
        self.assertEqual(data['proyecto'], self.proyecto.nombre)
        self.assertEqual(data['costos_fijos'], 4_243_284_093.0)
        self.assertEqual(data['costos_variables'], 2_813_662_061.0)
        self.assertEqual(data['ingresos'], -23_511_292_673.0)
        # total_año (Fase 3, "Total Año") = suma cruda de TODAS las filas del
        # período, sin filtrar por Clasificación.
        total_esperado = -23_511_292_673.0 + 4_243_284_093.0 + 2_813_662_061.0
        self.assertEqual(data['total_año'], total_esperado)

    def test_agrega_multiples_filas_de_la_misma_clasificacion_en_el_mes(self):
        """≥2 filas 'Fijo' del MISMO mes se suman en costos_fijos (mismo
        criterio de agregación que A5, aplicado ya filtrado por período)."""
        PresupuestoDetalladoConstruccion.objects.create(
            proyecto=self.proyecto, anio=2026,
            tipo=PresupuestoDetalladoConstruccion.Tipo.PLANEADO,
            datos={'finv2_bd': {'filas_detalle': [
                {'rubro': 'Gastos de Personal', 'clasificacion': 'Fijo',
                 'valor': 1000.0, 'mes': 9, 'anio': 2026, 'ciudad': 'Bogota'},
                {'rubro': 'Servicios Publicos', 'clasificacion': 'Fijo',
                 'valor': 500.0, 'mes': 9, 'anio': 2026, 'ciudad': 'Bogota'},
                {'rubro': 'Arriendos', 'clasificacion': 'Variable',
                 'valor': 200.0, 'mes': 9, 'anio': 2026, 'ciudad': 'Bogota'},
            ]}},
        )
        resp = self.client.get(self.url, **_bearer_header(self.usuario))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['costos_fijos'], 1500.0)
        self.assertEqual(data['costos_variables'], 200.0)
        self.assertEqual(data['ingresos'], 0.0)

    # -----------------------------------------------------------------
    # Filtrado por mes — no mezclar otros meses del mismo año
    # -----------------------------------------------------------------
    def test_filas_de_otro_mes_no_se_mezclan(self):
        PresupuestoDetalladoConstruccion.objects.create(
            proyecto=self.proyecto, anio=2026,
            tipo=PresupuestoDetalladoConstruccion.Tipo.PLANEADO,
            datos={'finv2_bd': {'filas_detalle': [
                *_filas_caso_issue_mes9(),
                # Agosto: NO debe entrar en la respuesta de septiembre.
                {'rubro': 'Otro rubro agosto', 'clasificacion': 'Fijo',
                 'valor': 999_999.0, 'mes': 8, 'anio': 2026, 'ciudad': 'Bogota'},
            ]}},
        )
        resp = self.client.get(self.url, **_bearer_header(self.usuario))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # costos_fijos sigue siendo SOLO el de septiembre (4.243.284.093),
        # no +999999 de agosto.
        self.assertEqual(data['costos_fijos'], 4_243_284_093.0)

    # -----------------------------------------------------------------
    # 404 — nunca 200 con ceros
    # -----------------------------------------------------------------
    def test_404_mes_fuera_de_rango(self):
        resp = self.client.get(
            f'/api/presupuesto/{self.proyecto.pk}/periodo/13/2026',
            **_bearer_header(self.usuario),
        )
        self.assertEqual(resp.status_code, 404)

    def test_404_proyecto_inexistente(self):
        resp = self.client.get(
            f'/api/presupuesto/{uuid.uuid4()}/periodo/9/2026',
            **_bearer_header(self.usuario),
        )
        self.assertEqual(resp.status_code, 404)

    def test_404_anio_sin_presupuesto_planeado_cargado(self):
        # Ningún PresupuestoDetalladoConstruccion para este proyecto/año.
        resp = self.client.get(self.url, **_bearer_header(self.usuario))
        self.assertEqual(resp.status_code, 404)

    def test_404_mes_sin_ninguna_fila(self):
        PresupuestoDetalladoConstruccion.objects.create(
            proyecto=self.proyecto, anio=2026,
            tipo=PresupuestoDetalladoConstruccion.Tipo.PLANEADO,
            # Solo agosto cargado; se pide septiembre.
            datos={'finv2_bd': {'filas_detalle': [
                {'rubro': 'X', 'clasificacion': 'Fijo',
                 'valor': 100.0, 'mes': 8, 'anio': 2026, 'ciudad': 'Bogota'},
            ]}},
        )
        resp = self.client.get(self.url, **_bearer_header(self.usuario))
        self.assertEqual(resp.status_code, 404)

    def test_404_dato_legacy_sin_finv2_bd(self):
        """Presupuesto legacy (formato columnas-por-mes, sin finv2_bd ni
        filas_detalle) → 404, no un 200 con ceros."""
        PresupuestoDetalladoConstruccion.objects.create(
            proyecto=self.proyecto, anio=2026,
            tipo=PresupuestoDetalladoConstruccion.Tipo.PLANEADO,
            datos={'ingreso': {'Ventas': {'enero': 100}}, 'variables': {}, 'fijos': {}},
        )
        resp = self.client.get(self.url, **_bearer_header(self.usuario))
        self.assertEqual(resp.status_code, 404)

    def test_404_ignora_presupuesto_tipo_real(self):
        """Solo el tipo PLANEADO alimenta este endpoint — un REAL cargado
        para el mismo proyecto/año NO debe satisfacer la consulta."""
        PresupuestoDetalladoConstruccion.objects.create(
            proyecto=self.proyecto, anio=2026,
            tipo=PresupuestoDetalladoConstruccion.Tipo.REAL,
            datos={'finv2_bd': {'filas_detalle': _filas_caso_issue_mes9()}},
        )
        resp = self.client.get(self.url, **_bearer_header(self.usuario))
        self.assertEqual(resp.status_code, 404)

    # -----------------------------------------------------------------
    # Seguridad — gate de auth (gotcha del portafolio: NinjaAPI/Router sin
    # auth= explícito queda abierta por defecto, ya pasó en Consof).
    # -----------------------------------------------------------------
    def test_401_sin_token_de_autenticacion(self):
        PresupuestoDetalladoConstruccion.objects.create(
            proyecto=self.proyecto, anio=2026,
            tipo=PresupuestoDetalladoConstruccion.Tipo.PLANEADO,
            datos={'finv2_bd': {'filas_detalle': _filas_caso_issue_mes9()}},
        )
        # Sin header Authorization — un cliente sin sesión/token.
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 401)
        self.assertNotEqual(resp.status_code, 200)

    def test_401_token_invalido(self):
        PresupuestoDetalladoConstruccion.objects.create(
            proyecto=self.proyecto, anio=2026,
            tipo=PresupuestoDetalladoConstruccion.Tipo.PLANEADO,
            datos={'finv2_bd': {'filas_detalle': _filas_caso_issue_mes9()}},
        )
        resp = self.client.get(self.url, HTTP_AUTHORIZATION='Bearer token-basura-invalido')
        self.assertEqual(resp.status_code, 401)
