"""
Tests for permission and access control.

These tests verify:
- Login required on all protected views
- Role-based access control (RoleRequiredMixin)
- API authentication requirements
"""

import pytest
from django.urls import reverse
from django.test import Client
from django.contrib.auth import get_user_model

from apps.core.models import RoleModuloPermiso
from apps.core.permissions import (
    MODULO_CONFIG,
    MODULO_MANTENIMIENTO,
    SUBMODULO_A_MODULO,
    SUBMODULO_CONFIG_ROLES_PERMISOS,
    SUBMODULO_FIN_NOMINA,
    SUBMODULO_MANTENIMIENTO_ACTIVIDADES,
    SUBMODULOS_CONFIG,
    SUBMODULOS_FINANCIERO,
    SUBMODULOS_MANTENIMIENTO,
    invalidate_role_cache,
    user_can_access_modulo,
    user_can_access_submodulo,
    user_submodulos,
)
from tests.factories import (
    AdminFactory,
    CoordinadorFactory,
    IngenieroResidenteFactory,
    SupervisorFactory,
    LinieroFactory,
    LineaFactory,
    TorreFactory,
    CuadrillaFactory,
    ActividadFactory,
    RegistroCampoFactory,
)

User = get_user_model()


# ==============================================================================
# Authentication Tests - Login Required
# ==============================================================================

@pytest.mark.django_db
class TestLoginRequired:
    """Tests that protected views redirect unauthenticated users to login."""

    def test_unauthenticated_user_redirected_from_lineas_list(self, client):
        """Test that lineas list redirects to login for unauthenticated users."""
        url = reverse('lineas:lista')
        response = client.get(url)

        assert response.status_code == 302
        assert 'login' in response.url

    def test_unauthenticated_user_redirected_from_lineas_detail(self, client):
        """Test that lineas detail redirects to login for unauthenticated users."""
        linea = LineaFactory()
        url = reverse('lineas:detalle', kwargs={'pk': linea.pk})
        response = client.get(url)

        assert response.status_code == 302
        assert 'login' in response.url

    def test_unauthenticated_user_redirected_from_torres(self, client):
        """Test that torres list redirects to login for unauthenticated users."""
        linea = LineaFactory()
        url = reverse('lineas:torres', kwargs={'pk': linea.pk})
        response = client.get(url)

        assert response.status_code == 302
        assert 'login' in response.url

    def test_unauthenticated_user_redirected_from_mapa_lineas(self, client):
        """Test that mapa lineas redirects to login for unauthenticated users."""
        url = reverse('lineas:mapa')
        response = client.get(url)

        assert response.status_code == 302
        assert 'login' in response.url

    def test_unauthenticated_user_redirected_from_cuadrillas_list(self, client):
        """Test that cuadrillas list redirects to login for unauthenticated users."""
        url = reverse('cuadrillas:lista')
        response = client.get(url)

        assert response.status_code == 302
        assert 'login' in response.url

    def test_unauthenticated_user_redirected_from_cuadrillas_detail(self, client):
        """Test that cuadrillas detail redirects to login for unauthenticated users."""
        cuadrilla = CuadrillaFactory()
        url = reverse('cuadrillas:detalle', kwargs={'pk': cuadrilla.pk})
        response = client.get(url)

        assert response.status_code == 302
        assert 'login' in response.url

    def test_unauthenticated_user_redirected_from_mapa_cuadrillas(self, client):
        """Test that mapa cuadrillas redirects to login for unauthenticated users."""
        url = reverse('cuadrillas:mapa')
        response = client.get(url)

        assert response.status_code == 302
        assert 'login' in response.url

    def test_unauthenticated_user_redirected_from_campo_list(self, client):
        """Test that campo list redirects to login for unauthenticated users."""
        url = reverse('campo:lista')
        response = client.get(url)

        assert response.status_code == 302
        assert 'login' in response.url

    def test_unauthenticated_user_redirected_from_campo_detail(self, client):
        """Test that campo detail redirects to login for unauthenticated users."""
        registro = RegistroCampoFactory()
        url = reverse('campo:detalle', kwargs={'pk': registro.pk})
        response = client.get(url)

        assert response.status_code == 302
        assert 'login' in response.url

    def test_unauthenticated_user_redirected_from_evidencias(self, client):
        """Test that evidencias view redirects to login for unauthenticated users."""
        registro = RegistroCampoFactory()
        url = reverse('campo:evidencias', kwargs={'pk': registro.pk})
        response = client.get(url)

        assert response.status_code == 302
        assert 'login' in response.url

    def test_unauthenticated_user_redirected_from_actividades_list(self, client):
        """Test that actividades list redirects to login for unauthenticated users."""
        url = reverse('actividades:lista')
        response = client.get(url)

        assert response.status_code == 302
        assert 'login' in response.url

    def test_unauthenticated_user_redirected_from_financiero(self, client):
        """Test that financiero dashboard redirects to login for unauthenticated users."""
        url = reverse('financiero:dashboard')
        response = client.get(url)

        assert response.status_code == 302
        assert 'login' in response.url

    def test_unauthenticated_user_redirected_from_indicadores(self, client):
        """Test that indicadores dashboard redirects to login for unauthenticated users."""
        url = reverse('indicadores:dashboard')
        response = client.get(url)

        assert response.status_code == 302
        assert 'login' in response.url


# ==============================================================================
# Role-Based Access Control Tests
# ==============================================================================

@pytest.mark.django_db
class TestRoleBasedAccessControl:
    """Tests that views with RoleRequiredMixin enforce proper role restrictions."""

    def test_wrong_role_denied_cuadrillas_list(self, client, user_password):
        """Test that users without required role get 403 for cuadrillas list."""
        # Liniero doesn't have access to cuadrillas list (needs supervisor or higher)
        liniero = LinieroFactory()
        client.login(username=liniero.email, password=user_password)

        url = reverse('cuadrillas:lista')
        response = client.get(url)

        assert response.status_code == 403

    def test_wrong_role_denied_cuadrillas_mapa(self, client, user_password):
        """`cuadrillas:mapa` está abierto a TODOS los roles autenticados;
        liniero ya puede acceder. Validamos que un anónimo SÍ es denegado."""
        url = reverse('cuadrillas:mapa')
        response = client.get(url)

        # Anónimo → redirige a login.
        assert response.status_code == 302
        assert 'login' in response.url

    def test_wrong_role_denied_mapa_lineas(self, client, user_password):
        """Test that users without required role get 403 for mapa lineas."""
        # Liniero doesn't have access to mapa lineas (needs supervisor or higher)
        liniero = LinieroFactory()
        client.login(username=liniero.email, password=user_password)

        url = reverse('lineas:mapa')
        response = client.get(url)

        assert response.status_code == 403

    def test_wrong_role_denied_programacion(self, client, user_password):
        """Test that liniero gets 403 for programacion view."""
        liniero = LinieroFactory()
        client.login(username=liniero.email, password=user_password)

        url = reverse('actividades:programacion')
        response = client.get(url)

        assert response.status_code == 403

    def test_wrong_role_denied_importar(self, client, user_password):
        """Test que un rol no-admin (liniero) recibe 403 en importar.
        (ing_residente pasó a admin-level en RBAC v2 #44; se usa liniero, NIVEL_OPERARIO.)"""
        liniero = LinieroFactory()
        client.login(username=liniero.email, password=user_password)

        url = reverse('actividades:importar')
        response = client.get(url)

        assert response.status_code == 403

    def test_wrong_role_denied_financiero(self, client, user_password):
        """liniero no tiene ninguna hoja FIN_* -- #186 A3: RBACModuloMiddleware
        ahora gatea /financiero/* por submódulo granular ANTES de que la
        vista corra, así que el denial llega como 302 (mismo patrón que el
        resto del middleware RBAC), no como el 403 legacy de RoleRequiredMixin."""
        liniero = LinieroFactory()
        client.login(username=liniero.email, password=user_password)

        url = reverse('financiero:dashboard')
        response = client.get(url)

        assert response.status_code == 302

    def test_wrong_role_denied_actas(self, client, user_password):
        """Test that liniero gets 403 for actas list."""
        liniero = LinieroFactory()
        client.login(username=liniero.email, password=user_password)

        url = reverse('indicadores:actas')
        response = client.get(url)

        assert response.status_code == 403


# ==============================================================================
# Correct Role Allowed Tests
# ==============================================================================

@pytest.mark.django_db
class TestCorrectRoleAllowed:
    """Tests that users with correct roles can access protected views."""

    def test_admin_can_access_all_views(self, client, user_password):
        """Test that admin users can access all protected views."""
        admin = AdminFactory()
        client.login(username=admin.email, password=user_password)

        # Test lineas
        response = client.get(reverse('lineas:lista'))
        assert response.status_code == 200

        response = client.get(reverse('lineas:mapa'))
        assert response.status_code == 200

        # Test cuadrillas
        response = client.get(reverse('cuadrillas:lista'))
        assert response.status_code == 200

        response = client.get(reverse('cuadrillas:mapa'))
        assert response.status_code == 200

        # Test campo
        response = client.get(reverse('campo:lista'))
        assert response.status_code == 200

        # Test programacion
        response = client.get(reverse('actividades:programacion'))
        assert response.status_code == 200

        # Test importar
        response = client.get(reverse('actividades:importar'))
        assert response.status_code == 200

        # Test financiero
        response = client.get(reverse('financiero:dashboard'))
        assert response.status_code == 200

        # Test indicadores
        response = client.get(reverse('indicadores:dashboard'))
        assert response.status_code == 200

        response = client.get(reverse('indicadores:actas'))
        assert response.status_code == 200

    def test_legacy_liniero_permission_is_evaluated_from_rbac_matrix(self, liniero_user):
        """The effective module permission, not only is_campo, controls access."""
        RoleModuloPermiso.objects.update_or_create(
            role_id=liniero_user.rol,
            modulo=MODULO_MANTENIMIENTO,
            submodulo='',
            defaults={'nivel_acceso': RoleModuloPermiso.SIN_ACCESO},
        )
        try:
            assert user_can_access_modulo(liniero_user, MODULO_MANTENIMIENTO) is False
        finally:
            # _get_role_permisos() cachea por role_id (permissions.py); el rollback de la
            # transacción del test borra la fila pero no dispara el post_delete que
            # invalidaría el cache, dejando "sin acceso" filtrado a los tests siguientes
            # que reusan el mismo rol de liniero.
            invalidate_role_cache(liniero_user.rol)

    def test_coordinador_can_access_cuadrillas(self, client, user_password):
        """Test that coordinador can access cuadrillas views."""
        coordinador = CoordinadorFactory()
        client.login(username=coordinador.email, password=user_password)

        response = client.get(reverse('cuadrillas:lista'))
        assert response.status_code == 200

        response = client.get(reverse('cuadrillas:mapa'))
        assert response.status_code == 200

    def test_coordinador_can_access_programacion(self, client, user_password):
        """Test that coordinador can access programacion."""
        coordinador = CoordinadorFactory()
        client.login(username=coordinador.email, password=user_password)

        response = client.get(reverse('actividades:programacion'))
        assert response.status_code == 200

    def test_coordinador_can_access_financiero(self, client, user_password):
        """Test that coordinador can access financiero."""
        coordinador = CoordinadorFactory()
        client.login(username=coordinador.email, password=user_password)

        response = client.get(reverse('financiero:dashboard'))
        assert response.status_code == 200

    def test_ingeniero_can_access_programacion(self, client, user_password):
        """Test that ingeniero residente can access programacion."""
        ingeniero = IngenieroResidenteFactory()
        client.login(username=ingeniero.email, password=user_password)

        response = client.get(reverse('actividades:programacion'))
        assert response.status_code == 200

    def test_ingeniero_can_access_actas(self, client, user_password):
        """Test that ingeniero residente can access actas."""
        ingeniero = IngenieroResidenteFactory()
        client.login(username=ingeniero.email, password=user_password)

        response = client.get(reverse('indicadores:actas'))
        assert response.status_code == 200

    def test_supervisor_can_access_cuadrillas(self, client, user_password):
        """Test that supervisor can access cuadrillas views."""
        supervisor = SupervisorFactory()
        client.login(username=supervisor.email, password=user_password)

        response = client.get(reverse('cuadrillas:lista'))
        assert response.status_code == 200

        response = client.get(reverse('cuadrillas:mapa'))
        assert response.status_code == 200

    def test_supervisor_can_access_campo(self, client, user_password):
        """Test that supervisor can access campo views."""
        supervisor = SupervisorFactory()
        client.login(username=supervisor.email, password=user_password)

        response = client.get(reverse('campo:lista'))
        assert response.status_code == 200

    def test_liniero_can_access_campo(self, client, user_password):
        """Test that liniero can access campo views."""
        liniero = LinieroFactory()
        client.login(username=liniero.email, password=user_password)

        response = client.get(reverse('campo:lista'))
        assert response.status_code == 200

    def test_liniero_can_access_lineas(self, client, user_password):
        """Test that liniero can access lineas list and detail."""
        liniero = LinieroFactory()
        linea = LineaFactory()
        client.login(username=liniero.email, password=user_password)

        response = client.get(reverse('lineas:lista'))
        assert response.status_code == 200

        response = client.get(reverse('lineas:detalle', kwargs={'pk': linea.pk}))
        assert response.status_code == 200


# ==============================================================================
# API Authentication Tests
# ==============================================================================

@pytest.mark.django_db
class TestAPIAuthentication:
    """Tests for API authentication requirements."""

    def test_api_lineas_requires_auth(self, client):
        """Test that lineas API requires authentication."""
        response = client.get('/api/lineas/')
        assert response.status_code in [401, 404]

    def test_api_cuadrillas_requires_auth(self, client):
        """Test that cuadrillas API requires authentication."""
        response = client.get('/api/cuadrillas/')
        assert response.status_code in [401, 404]

    def test_api_actividades_requires_auth(self, client):
        """Test that actividades API requires authentication."""
        response = client.get('/api/actividades/mis-actividades')
        assert response.status_code in [401, 404]

    def test_api_campo_requires_auth(self, client):
        """Test that campo API requires authentication."""
        response = client.get('/api/campo/registros')
        assert response.status_code in [401, 404]

    def test_api_auth_me_requires_token(self, client):
        """Test that /api/auth/me requires valid token."""
        response = client.get('/api/auth/me')
        assert response.status_code in [401, 404]

    def test_api_authenticated_access_lineas(self, client):
        """Test that authenticated users can access lineas API."""
        from rest_framework_simplejwt.tokens import RefreshToken

        user = LinieroFactory()
        LineaFactory.create_batch(2)

        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)

        response = client.get(
            '/api/lineas/',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
        )
        assert response.status_code in [200, 404]

    def test_api_authenticated_access_cuadrillas(self, client):
        """Test that authenticated users can access cuadrillas API."""
        from rest_framework_simplejwt.tokens import RefreshToken

        user = CoordinadorFactory()
        CuadrillaFactory.create_batch(2)

        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)

        response = client.get(
            '/api/cuadrillas/',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
        )
        assert response.status_code in [200, 404]

    def test_api_invalid_token_rejected(self, client):
        """Test that invalid tokens are rejected."""
        response = client.get(
            '/api/lineas/',
            HTTP_AUTHORIZATION='Bearer invalid_token_here',
        )
        assert response.status_code in [401, 404]

    def test_api_expired_token_rejected(self, client):
        """Test that expired tokens are rejected."""
        from rest_framework_simplejwt.tokens import RefreshToken
        from datetime import timedelta
        from django.utils import timezone

        user = LinieroFactory()
        refresh = RefreshToken.for_user(user)
        access_token = refresh.access_token

        # Manually expire the token by backdating it
        access_token.set_exp(from_time=timezone.now() - timedelta(hours=2), lifetime=timedelta(minutes=5))

        response = client.get(
            '/api/lineas/',
            HTTP_AUTHORIZATION=f'Bearer {str(access_token)}',
        )
        assert response.status_code in [401, 404]


# ==============================================================================
# Superuser Access Tests
# ==============================================================================

@pytest.mark.django_db
class TestSuperuserAccess:
    """Tests that superusers bypass role restrictions."""

    def test_superuser_bypasses_role_check(self, client, user_password):
        """Test that superusers can access any view regardless of role."""
        # Create a superuser with liniero role (which normally has limited access)
        superuser = User.objects.create_superuser(
            email='superuser@test.com',
            password=user_password,
            first_name='Super',
            last_name='User',
        )
        client.login(username=superuser.email, password=user_password)

        # Should be able to access all restricted views
        response = client.get(reverse('financiero:dashboard'))
        assert response.status_code == 200

        response = client.get(reverse('indicadores:actas'))
        assert response.status_code == 200

        response = client.get(reverse('actividades:importar'))
        assert response.status_code == 200


# ==============================================================================
# Edge Case Tests
# ==============================================================================

@pytest.mark.django_db
class TestAccessControlEdgeCases:
    """Tests for edge cases in access control."""

    def test_inactive_user_cannot_access(self, client, user_password):
        """Test that inactive users cannot access protected views."""
        user = AdminFactory(is_active=False)

        # Login should fail for inactive user
        logged_in = client.login(username=user.email, password=user_password)
        assert logged_in is False

    def test_detail_view_with_nonexistent_object(self, client, user_password):
        """Test that 404 is returned for nonexistent objects."""
        import uuid
        admin = AdminFactory()
        client.login(username=admin.email, password=user_password)

        url = reverse('lineas:detalle', kwargs={'pk': uuid.uuid4()})
        response = client.get(url)

        assert response.status_code == 404

    def test_post_request_on_get_only_view(self, client, user_password):
        """Test behavior of POST request on GET-only views."""
        admin = AdminFactory()
        client.login(username=admin.email, password=user_password)

        # List views typically don't accept POST
        url = reverse('lineas:lista')
        response = client.post(url)

        # Should be 405 Method Not Allowed or similar
        assert response.status_code in [200, 405]


# ==============================================================================
# Mantenimiento granular (#186 A1)
# ==============================================================================

@pytest.mark.django_db
class TestSubmodulosMantenimiento186:
    """La ampliación granular conserva acceso legacy y respeta el padre."""

    def test_legacy_liniero_conserva_las_cuatro_hojas_mantenimiento(self, liniero_user):
        """Dato legacy real del catálogo: liniero ya tenía Mantenimiento=Ver.

        El seed compatible debe replicar ese nivel en las hojas nuevas, no
        convertir a los usuarios operativos existentes en usuarios sin acceso.
        """
        invalidate_role_cache(liniero_user.rol)

        assert user_submodulos(liniero_user, MODULO_MANTENIMIENTO) == SUBMODULOS_MANTENIMIENTO
        for submodulo in SUBMODULOS_MANTENIMIENTO:
            assert user_can_access_submodulo(liniero_user, submodulo) is True

    def test_hoja_no_autoriza_si_el_modulo_padre_esta_denegado(self):
        """Edge case de seguridad: una fila hija no salta el permiso padre."""
        from apps.core.models import Role

        role = Role.objects.create(
            codigo="mantenimiento_padre_denegado",
            nombre="Mantenimiento padre denegado",
            nivel="operario",
        )
        RoleModuloPermiso.objects.create(
            role=role,
            modulo=MODULO_MANTENIMIENTO,
            submodulo="",
            nivel_acceso=RoleModuloPermiso.SIN_ACCESO,
        )
        RoleModuloPermiso.objects.create(
            role=role,
            modulo=MODULO_MANTENIMIENTO,
            submodulo=SUBMODULO_MANTENIMIENTO_ACTIVIDADES,
            nivel_acceso=RoleModuloPermiso.VER,
        )
        user = User.objects.create_user(
            email="padre-denegado@test.com",
            password="testpass123!",
            rol=role.codigo,
        )

        assert user_can_access_submodulo(
            user, SUBMODULO_MANTENIMIENTO_ACTIVIDADES
        ) is False

    def test_cambio_de_hoja_invalida_cache_inmediatamente(self, liniero_user):
        """Edge case: no se puede esperar el TTL tras revocar una hoja."""
        permiso = RoleModuloPermiso.objects.get(
            role_id=liniero_user.rol,
            modulo=MODULO_MANTENIMIENTO,
            submodulo=SUBMODULO_MANTENIMIENTO_ACTIVIDADES,
        )
        invalidate_role_cache(liniero_user.rol)
        assert user_can_access_submodulo(
            liniero_user, SUBMODULO_MANTENIMIENTO_ACTIVIDADES
        ) is True

        permiso.nivel_acceso = RoleModuloPermiso.SIN_ACCESO
        permiso.save(update_fields=["nivel_acceso", "updated_at"])

        assert user_can_access_submodulo(
            liniero_user, SUBMODULO_MANTENIMIENTO_ACTIVIDADES
        ) is False


class TestSubmodulosConfigFinanciero186:
    """A2: catálogo granular de Financiero (`apps/financiero/`, colgado de
    MODULO_MANTENIMIENTO) y Configuración/Parametrización (colgado de
    MODULO_CONFIG) -- ver decisión de diseño en
    `rbac_seed_data.SUBMODULOS_FINANCIERO_APP`."""

    def test_las_hojas_de_config_quedan_registradas_bajo_config(self):
        for submodulo in SUBMODULOS_CONFIG:
            assert SUBMODULO_A_MODULO[submodulo] == MODULO_CONFIG

    def test_las_hojas_de_financiero_quedan_registradas_bajo_mantenimiento(self):
        for submodulo in SUBMODULOS_FINANCIERO:
            assert SUBMODULO_A_MODULO[submodulo] == MODULO_MANTENIMIENTO

    @pytest.mark.django_db
    def test_fila_vacia_es_sin_acceso_por_defecto(self):
        """A diferencia de las hojas de Mantenimiento originales (A1),
        Financiero/Config NO tienen fila legacy previa de la cual derivar --
        la migración no siembra nada, así que un rol sin fila explícita debe
        quedar sin acceso."""
        from apps.core.models import Role

        role = Role.objects.create(
            codigo="config_sin_filas", nombre="Sin filas", nivel="operario",
        )
        user = User.objects.create_user(
            email="sin-filas@test.com", password="testpass123!", rol=role.codigo,
        )

        for submodulo in SUBMODULOS_CONFIG | SUBMODULOS_FINANCIERO:
            assert user_can_access_submodulo(user, submodulo) is False

    @pytest.mark.django_db
    def test_hoja_financiero_autoriza_con_permiso_propio_sin_modulo_completo(self):
        """Generaliza el fix de A1: una hoja de Financiero también autoriza
        sin el módulo (Mantenimiento) padre completo."""
        from apps.core.models import Role

        role = Role.objects.create(
            codigo="solo_nomina", nombre="Solo nómina", nivel="operario",
        )
        RoleModuloPermiso.objects.create(
            role=role, modulo=MODULO_MANTENIMIENTO, submodulo=SUBMODULO_FIN_NOMINA,
            nivel_acceso=RoleModuloPermiso.VER,
        )
        user = User.objects.create_user(
            email="solo-nomina@test.com", password="testpass123!", rol=role.codigo,
        )

        assert user_can_access_submodulo(user, SUBMODULO_FIN_NOMINA) is True
        assert user_can_access_modulo(user, MODULO_MANTENIMIENTO) is False
        assert user_can_access_submodulo(
            user, SUBMODULO_MANTENIMIENTO_ACTIVIDADES
        ) is False

    @pytest.mark.django_db
    def test_hoja_financiero_no_autoriza_si_el_modulo_padre_esta_denegado(self):
        """Mismo edge case de seguridad que A1, generalizado a Financiero."""
        from apps.core.models import Role

        role = Role.objects.create(
            codigo="financiero_padre_denegado", nombre="Financiero padre denegado",
            nivel="operario",
        )
        RoleModuloPermiso.objects.create(
            role=role, modulo=MODULO_MANTENIMIENTO, submodulo="",
            nivel_acceso=RoleModuloPermiso.SIN_ACCESO,
        )
        RoleModuloPermiso.objects.create(
            role=role, modulo=MODULO_MANTENIMIENTO, submodulo=SUBMODULO_FIN_NOMINA,
            nivel_acceso=RoleModuloPermiso.VER,
        )
        user = User.objects.create_user(
            email="financiero-padre-denegado@test.com", password="testpass123!",
            rol=role.codigo,
        )

        assert user_can_access_submodulo(user, SUBMODULO_FIN_NOMINA) is False

    @pytest.mark.django_db
    def test_hoja_config_no_autoriza_si_el_modulo_padre_esta_denegado(self):
        """Mismo edge case de seguridad que A1, generalizado a CONFIG (con una
        hoja que sí es propiamente de Configuración)."""
        from apps.core.models import Role

        role = Role.objects.create(
            codigo="config_padre_denegado", nombre="Config padre denegado",
            nivel="operario",
        )
        RoleModuloPermiso.objects.create(
            role=role, modulo=MODULO_CONFIG, submodulo="",
            nivel_acceso=RoleModuloPermiso.SIN_ACCESO,
        )
        RoleModuloPermiso.objects.create(
            role=role, modulo=MODULO_CONFIG, submodulo=SUBMODULO_CONFIG_ROLES_PERMISOS,
            nivel_acceso=RoleModuloPermiso.VER,
        )
        user = User.objects.create_user(
            email="config-padre-denegado@test.com", password="testpass123!",
            rol=role.codigo,
        )

        assert user_can_access_submodulo(user, SUBMODULO_CONFIG_ROLES_PERMISOS) is False


class TestMiddlewareGranularA3:
    """#186 A3: RBACModuloMiddleware gatea por submódulo (no solo módulo) y
    distingue Ver de Ver y editar en mutaciones."""

    def test_ver_permite_get_pero_bloquea_mutacion(self, client, liniero_user, user_password):
        """liniero tiene 'ver' (no 'ver_editar') en MANTENIMIENTO_CAMPO, vía
        el seed de A1 (nivel operario -> ver). Debe poder LISTAR pero no
        CREAR."""
        client.login(username=liniero_user.email, password=user_password)

        get_response = client.get(reverse('campo:lista'))
        assert get_response.status_code == 200

        post_response = client.post(reverse('campo:reportar_dano'), {})
        assert post_response.status_code == 302
        assert post_response.url == reverse('core:home')

    def test_sin_hoja_financiero_bloquea_get_y_post(self, client, liniero_user, user_password):
        """liniero no tiene ninguna hoja FIN_* -- bloqueado incluso para GET,
        antes de llegar a RoleRequiredMixin."""
        client.login(username=liniero_user.email, password=user_password)

        response = client.get(reverse('financiero:dashboard'))
        assert response.status_code == 302
        assert response.url == reverse('core:home')

    def test_hoja_mas_especifica_gana_sobre_la_generica(self, client, liniero_user, user_password):
        """`/campo/procedimientos/` debe gatearse por
        MANTENIMIENTO_PROCEDIMIENTOS, no por el MANTENIMIENTO_CAMPO más
        genérico -- liniero tiene 'ver' en ambos vía el seed de A1, así que
        esto en particular no distingue nivel, pero sí confirma que el
        prefijo específico matchea antes que el catch-all '/campo/'."""
        client.login(username=liniero_user.email, password=user_password)

        response = client.get(reverse('campo:procedimientos'))
        assert response.status_code == 200


class TestSidebarGranularA3:
    """#186 A3: el sidebar administrativo (rama `{% else %}` de
    `request.user.is_campo` en sidebar.html) muestra/oculta cada dropdown de
    Mantenimiento/Financiero según la hoja granular, no el módulo completo."""

    @staticmethod
    def _submenus(html):
        import re
        return set(re.findall(r'aria-label="Submenu ([^"]+)"', html))

    @pytest.mark.django_db
    def test_coordinador_ve_mantenimiento_y_financiero(self, client, user_password):
        """coordinador: nivel admin, con MANTENIMIENTO, y en la lista legacy
        de acceso a Financiero (ver rbac_seed_data) -- debe ver todo."""
        u = CoordinadorFactory()
        client.login(username=u.email, password=user_password)

        subs = self._submenus(client.get('/').content.decode())

        assert 'Actividades' in subs
        assert 'Campo' in subs
        assert 'Procedimientos' in subs
        assert 'Financiero' in subs

    @pytest.mark.django_db
    def test_admin_construccion_no_ve_mantenimiento_ni_financiero(self, client, user_password):
        """admin_construccion: nivel admin pero SOLO módulo CONSTRUCCION --
        no debe ver ninguna hoja de Mantenimiento ni Financiero (que cuelga
        de MANTENIMIENTO)."""
        u = User.objects.create_user(
            email='admin-construccion-sidebar@test.com', password=user_password,
            rol='admin_construccion',
        )
        client.login(username=u.email, password=user_password)

        subs = self._submenus(client.get('/').content.decode())

        assert 'Actividades' not in subs
        assert 'Campo' not in subs
        assert 'Procedimientos' not in subs
        assert 'Financiero' not in subs
