"""E2E tests del módulo de Proyectos (apps.construccion).

Cubre las 22 rutas registradas en `apps/construccion/urls.py` mediante el
test client de Django. Valida:
- Auth: rutas requieren login.
- Permisos por rol: solo `admin/director/coordinador` acceden.
- Render: cada vista responde 200 con un proyecto válido.
- CRUD de torres: crear → editar → eliminar, con creación automática de PataObra.
- Filtros globales: contratos CONSTRUCCION listan en sidebar.

Ejecutar:
    DJANGO_SETTINGS_MODULE=config.settings.dev_lite \\
    .venv-test/bin/pytest tests/e2e/test_modulo_proyectos.py -v
"""
from datetime import date
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from apps.contratos.models import Contrato
from apps.construccion.models import PataObra, ProyectoConstruccion, TorreConstruccion
from tests.factories import AdminFactory, LinieroFactory


@pytest.fixture
def admin_user(db):
    return AdminFactory(email='admin-proyectos@test.com')


@pytest.fixture
def liniero_user(db):
    return LinieroFactory(email='liniero-proyectos@test.com')


@pytest.fixture
def admin_client(client: Client, admin_user) -> Client:
    client.force_login(admin_user)
    return client


@pytest.fixture
def liniero_client(client: Client, liniero_user) -> Client:
    client.force_login(liniero_user)
    return client


@pytest.fixture
def contrato_construccion(db) -> Contrato:
    return Contrato.objects.create(
        codigo='CTR-E2E-001',
        nombre='Proyecto E2E Construcción',
        unidad_negocio='CONSTRUCCION',
        estado='ACTIVO',
        cliente='Transelca',
        valor=Decimal('100000000'),
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
        numero_torres=3,
    )


@pytest.fixture
def proyecto(contrato_construccion) -> ProyectoConstruccion:
    return ProyectoConstruccion.objects.create(
        contrato=contrato_construccion,
        nombre='Proyecto Construcción E2E',
        descripcion='Proyecto creado por test E2E',
        estado='EJECUCION',
        fecha_inicio=date(2026, 1, 15),
        fecha_fin_estimada=date(2026, 11, 30),
    )


# Tabs que reciben `<uuid:proyecto_id>`.
TABS_GET = [
    'construccion:contrato',
    'construccion:ingenieria',
    'construccion:preliminares',
    'construccion:torres_lista',
    'construccion:torre_crear',
    'construccion:seguimiento_diario',
    'construccion:social_predial',
    'construccion:ambiental',
    'construccion:control_lluvia',
    'construccion:replanteo',
    'construccion:sst',
    'construccion:entrega',
    'construccion:pendientes',
    'construccion:programacion',
    'construccion:rs_data',
    'construccion:hochimin',
    'construccion:lectura',
    'construccion:entrega_flechas',
    'construccion:electromecanica',
]


@pytest.mark.django_db
class TestAuthYPermisos:
    """Auth + role-based access control."""

    def test_lista_proyectos_requiere_login(self, client):
        url = reverse('construccion:lista')
        resp = client.get(url)
        assert resp.status_code == 302
        assert '/usuarios/login/' in resp.url

    def test_dashboard_requiere_login(self, client, proyecto):
        url = reverse('construccion:dashboard', kwargs={'pk': proyecto.id})
        resp = client.get(url)
        assert resp.status_code == 302
        assert '/usuarios/login/' in resp.url

    def test_liniero_no_puede_acceder_lista_proyectos(self, liniero_client):
        """RoleRequiredMixin debe rechazar al liniero (allowed_roles=admin/director/coordinador)."""
        url = reverse('construccion:lista')
        resp = liniero_client.get(url, follow=False)
        # Puede redirigir a campo:lista (vía HomeView dispatch) o devolver 403 según mixin.
        assert resp.status_code in (302, 403)

    def test_admin_accede_lista_proyectos(self, admin_client):
        url = reverse('construccion:lista')
        resp = admin_client.get(url)
        assert resp.status_code == 200


@pytest.mark.django_db
class TestRutasProyectoExisten:
    """Cada tab del proyecto debe responder 200 con un proyecto válido."""

    @pytest.mark.parametrize('url_name', TABS_GET)
    def test_tab_responde_200(self, admin_client, proyecto, url_name):
        url = reverse(url_name, kwargs={'proyecto_id': proyecto.id})
        resp = admin_client.get(url)
        assert resp.status_code == 200, (
            f"{url_name} devolvió {resp.status_code} — "
            f"{resp.content[:200].decode('utf-8', 'replace')}"
        )

    def test_dashboard_proyecto_responde_200(self, admin_client, proyecto):
        url = reverse('construccion:dashboard', kwargs={'pk': proyecto.id})
        resp = admin_client.get(url)
        assert resp.status_code == 200


@pytest.mark.django_db
class TestCRUDTorre:
    """CRUD básico del modelo TorreConstruccion."""

    def test_crear_torre_genera_4_patas(self, admin_client, proyecto):
        url = reverse('construccion:torre_crear', kwargs={'proyecto_id': proyecto.id})
        data = {
            'numero': 'T-001',
            # #171 Fase 1 (2026-07-12): 'D6' era del dominio legacy (help_text
            # aspiracional, nunca usado en prod). choices real ahora: A/AE/B/C/D/TAE.
            'tipo': 'D',
            'tipo_cimentacion': 'ZAPATA',
            'peso_kg': 1500.0,
            'tramo_tendido': 'TEND 1',
            'latitud': 10.5,
            'longitud': -74.5,
            'cuadrilla_civil': '',
            'cuadrilla_montaje': '',
            'cuadrilla_tendido': '',
            'observaciones': 'Torre creada por test E2E',
        }
        resp = admin_client.post(url, data=data)
        assert resp.status_code in (302, 200), resp.content[:300]

        torre = TorreConstruccion.objects.get(proyecto=proyecto, numero='T-001')
        assert torre.tipo == 'D'
        # form_valid crea PataObra para A,B,C,D
        patas = PataObra.objects.filter(torre=torre).values_list('pata', flat=True)
        assert set(patas) == {'A', 'B', 'C', 'D'}

    def test_listar_torres_incluye_creada(self, admin_client, proyecto):
        TorreConstruccion.objects.create(proyecto=proyecto, numero='T-X1')
        url = reverse('construccion:torres_lista', kwargs={'proyecto_id': proyecto.id})
        resp = admin_client.get(url)
        assert resp.status_code == 200
        assert b'T-X1' in resp.content

    def test_eliminar_torre(self, admin_client, proyecto):
        torre = TorreConstruccion.objects.create(proyecto=proyecto, numero='T-DEL')
        url = reverse(
            'construccion:torre_eliminar',
            kwargs={'proyecto_id': proyecto.id, 'pk': torre.id},
        )
        resp = admin_client.post(url)
        assert resp.status_code in (302, 200)
        assert not TorreConstruccion.objects.filter(id=torre.id).exists()


@pytest.mark.django_db
class TestIntegracionConFiltroGlobal:
    """El filtro de #42 debe respetarse en el listado de proyectos cuando aplica."""

    def test_set_unidad_negocio_persiste(self, admin_client):
        # Cambia a CONSTRUCCION.
        url = reverse('core:set_unidad_negocio')
        resp = admin_client.post(url, data={'unidad_negocio': 'CONSTRUCCION'})
        assert resp.status_code == 200
        assert resp.json()['unidad_negocio'] == 'CONSTRUCCION'

        # Confirma que la siguiente request mantiene la sesión.
        from apps.core.utils import get_unidad_negocio
        session = admin_client.session
        # Reusar la utilidad con una request simulada vía session backend.
        assert session.get('unidad_negocio') == 'CONSTRUCCION'

    def test_contratos_lista_filtra_construccion(self, admin_client, contrato_construccion):
        # Contrato MANTENIMIENTO de control.
        Contrato.objects.create(
            codigo='CTR-MTTO-001',
            nombre='Contrato MTTO',
            unidad_negocio='MANTENIMIENTO',
            estado='ACTIVO',
        )
        url = reverse('contratos:lista') + '?unidad=CONSTRUCCION'
        resp = admin_client.get(url)
        assert resp.status_code == 200
        # El queryset filtrado pasa por `contratos` (context_object_name).
        # Verificar en el queryset del contexto, NO en el HTML completo (el sidebar
        # inyecta ambas listas via modulo_context).
        codigos_listados = {c.codigo for c in resp.context['contratos']}
        assert 'CTR-E2E-001' in codigos_listados
        assert 'CTR-MTTO-001' not in codigos_listados
