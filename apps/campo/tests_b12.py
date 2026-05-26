"""
Tests B1.2 — Fix bug "vanos no cargan en RegistroAvanceCreateView con linea_id".

Refs: Indunnova16/Instelec#101

Cobertura:
- ``b12_vanos_cargan_con_admin``: usuario admin con ``?linea_id=<uuid>`` ve
  la grilla de vanos (happy path original del bug).
- ``b12_vanos_negados_con_liniero_ajeno``: liniero que NO pertenece a la
  cuadrilla de la línea recibe mensaje claro "no tienes permiso", no
  "no hay vanos" (raíz del bug — confundir denial con empty state).
- Edge: UUID inválido → ``error`` poblado y NO crash silencioso.
- Edge: línea no existe → ``error`` poblado, no 500.
- Legacy: línea con cero vanos pre-fix sigue mostrando empty state real
  (con ``linea`` en contexto y vanos vacíos), no se confunde con error.
"""
from datetime import date

import pytest
from django.contrib.auth.models import AnonymousUser  # noqa: F401 — disponible si se requiere
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.campo.views import RegistroAvanceCreateView
from apps.cuadrillas.models import Cuadrilla, CuadrillaMiembro, Vehiculo
from apps.lineas.models import Linea, Vano
from apps.usuarios.models import Usuario


def _invoke_get_context(user, linea_id=None):
    """
    Llama directamente ``get_context_data`` sin renderizar el template.

    El template real depende de ``lineas/_filtro_semestre.html`` (stub de B2.1)
    y carga base.html con menús — irrelevante para validar el contrato de
    contexto del fix B1.2. Usamos ``RequestFactory`` para aislar.
    """
    rf = RequestFactory()
    query = {'linea_id': linea_id} if linea_id is not None else {}
    request = rf.get(reverse('campo:avance_registrar'), query)
    request.user = user

    view = RegistroAvanceCreateView()
    view.setup(request)
    return view.get_context_data()


@pytest.mark.django_db
class RegistroAvanceCreateViewB12Tests(TestCase):
    """Tests del fix B1.2 sobre ``RegistroAvanceCreateView``."""

    @classmethod
    def setUpTestData(cls):
        cls.url = reverse('campo:avance_registrar')

        # Línea CON vanos
        cls.linea = Linea.objects.create(
            codigo='LT-B12',
            nombre='Línea de prueba B1.2',
            cliente=Linea.Cliente.TRANSELCA,
            activa=True,
        )
        for i in range(1, 4):
            Vano.objects.create(
                linea=cls.linea,
                numero=f'V-{i:03d}',
                estado=Vano.Estado.PENDIENTE,
            )

        # Línea sin vanos (para test legacy empty state)
        cls.linea_vacia = Linea.objects.create(
            codigo='LT-B12-EMPTY',
            nombre='Línea sin vanos',
            cliente=Linea.Cliente.TRANSELCA,
            activa=True,
        )

        # Línea NO asignada al liniero (para denial test)
        cls.linea_ajena = Linea.objects.create(
            codigo='LT-B12-AJENA',
            nombre='Línea ajena',
            cliente=Linea.Cliente.TRANSELCA,
            activa=True,
        )
        Vano.objects.create(
            linea=cls.linea_ajena,
            numero='V-XYZ',
            estado=Vano.Estado.EJECUTADO,
        )

        # Usuario admin
        cls.admin = Usuario.objects.create_user(
            email='admin_b12@test.com',
            password='testpass123!',
            first_name='Admin',
            last_name='B12',
            rol='admin',
            is_staff=True,
            is_superuser=True,
        )

        # Usuario liniero asignado a la línea CON vanos (autoselección)
        cls.liniero_asignado = Usuario.objects.create_user(
            email='liniero_asig_b12@test.com',
            password='testpass123!',
            first_name='Liniero',
            last_name='Asignado',
            rol='liniero',
        )
        cls.supervisor = Usuario.objects.create_user(
            email='supervisor_b12@test.com',
            password='testpass123!',
            first_name='Sup',
            last_name='B12',
            rol='supervisor',
        )
        cls.vehiculo = Vehiculo.objects.create(
            placa='B12001',
            tipo='CAMIONETA',
            marca='Toyota',
            modelo='2020',
            capacidad_personas=5,
            activo=True,
        )
        cls.cuadrilla_propia = Cuadrilla.objects.create(
            codigo='CUA-B12',
            nombre='Cuadrilla B12',
            supervisor=cls.supervisor,
            vehiculo=cls.vehiculo,
            linea_asignada=cls.linea,
            activa=True,
        )
        CuadrillaMiembro.objects.create(
            cuadrilla=cls.cuadrilla_propia,
            usuario=cls.liniero_asignado,
            rol_cuadrilla='LINIERO',
            fecha_inicio=date.today(),
            activo=True,
        )

        # Liniero ajeno: existe en una cuadrilla DISTINTA, no la de la línea
        cls.liniero_ajeno = Usuario.objects.create_user(
            email='liniero_ajeno_b12@test.com',
            password='testpass123!',
            first_name='Liniero',
            last_name='Ajeno',
            rol='liniero',
        )
        cls.cuadrilla_ajena = Cuadrilla.objects.create(
            codigo='CUA-B12-AJENA',
            nombre='Cuadrilla ajena',
            supervisor=cls.supervisor,
            vehiculo=cls.vehiculo,
            linea_asignada=cls.linea_ajena,
            activa=True,
        )
        CuadrillaMiembro.objects.create(
            cuadrilla=cls.cuadrilla_ajena,
            usuario=cls.liniero_ajeno,
            rol_cuadrilla='LINIERO',
            fecha_inicio=date.today(),
            activo=True,
        )

    # ------------------------------------------------------------------
    # Happy paths
    # ------------------------------------------------------------------
    def test_b12_vanos_cargan_con_admin(self):
        """
        Admin con ``?linea_id=<uuid>`` recibe los 3 vanos de la línea
        y los stats calculados. Era exactamente el caso reportado en #101.
        """
        ctx = _invoke_get_context(self.admin, linea_id=str(self.linea.id))

        self.assertEqual(ctx['linea'], self.linea)
        self.assertEqual(len(ctx['vanos']), 3)
        self.assertEqual(ctx['total_vanos'], 3)
        self.assertEqual(ctx['vanos_pendientes'], 3)
        self.assertFalse(ctx.get('error'))
        self.assertFalse(ctx.get('permission_denied'))

    def test_b12_liniero_asignado_autoselecciona_su_linea(self):
        """Liniero sin linea_id en la URL ve su línea asignada automáticamente."""
        ctx = _invoke_get_context(self.liniero_asignado)

        self.assertEqual(ctx['linea'], self.linea)
        self.assertEqual(len(ctx['vanos']), 3)
        self.assertFalse(ctx.get('permission_denied'))

    # ------------------------------------------------------------------
    # Denial — la raíz del bug: NO confundir con "sin vanos"
    # ------------------------------------------------------------------
    def test_b12_vanos_negados_con_liniero_ajeno(self):
        """
        Liniero que NO pertenece a la cuadrilla de la línea solicitada
        debe ver mensaje claro de permiso denegado.
        Antes del fix: caía en el silencioso "No hay vanos registrados".
        """
        ctx = _invoke_get_context(self.liniero_ajeno, linea_id=str(self.linea.id))

        self.assertTrue(ctx.get('permission_denied'))
        self.assertIn('permiso', ctx.get('error', '').lower())
        # Cuando hay denial NO debemos exponer datos de la línea
        self.assertNotIn('linea', ctx)
        self.assertNotIn('vanos', ctx)

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------
    def test_b12_uuid_invalido_no_revienta(self):
        """UUID malformado en la URL → error explícito, no ValueError 500."""
        ctx = _invoke_get_context(self.admin, linea_id='no-soy-uuid')

        self.assertIn('válido', ctx.get('error', '').lower())
        self.assertNotIn('linea', ctx)

    def test_b12_linea_no_existe(self):
        """UUID válido pero línea inexistente → error claro, no 500."""
        ctx = _invoke_get_context(
            self.admin,
            linea_id='00000000-0000-0000-0000-000000000000',
        )

        self.assertIn('no encontrada', ctx.get('error', '').lower())
        self.assertNotIn('linea', ctx)

    def test_b12_linea_existente_sin_vanos_muestra_empty_state(self):
        """
        Test contra dato legacy: una línea válida con cero vanos
        debe mostrar empty state (linea presente, vanos vacíos),
        NO un error. El fix debe DIFERENCIAR error de empty state.
        """
        ctx = _invoke_get_context(self.admin, linea_id=str(self.linea_vacia.id))

        self.assertEqual(ctx['linea'], self.linea_vacia)
        self.assertEqual(len(ctx['vanos']), 0)
        self.assertEqual(ctx['total_vanos'], 0)
        self.assertEqual(ctx['porcentaje'], 0)
        self.assertFalse(ctx.get('error'))
        self.assertFalse(ctx.get('permission_denied'))
