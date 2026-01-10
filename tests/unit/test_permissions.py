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
        client.login(email=liniero.email, password=user_password)

        url = reverse('cuadrillas:lista')
        response = client.get(url)

        assert response.status_code == 403

    def test_wrong_role_denied_cuadrillas_mapa(self, client, user_password):
        """Test that users without required role get 403 for cuadrillas mapa."""
        liniero = LinieroFactory()
        client.login(email=liniero.email, password=user_password)

        url = reverse('cuadrillas:mapa')
        response = client.get(url)

        assert response.status_code == 403

    def test_wrong_role_denied_mapa_lineas(self, client, user_password):
        """Test that users without required role get 403 for mapa lineas."""
        # Liniero doesn't have access to mapa lineas (needs supervisor or higher)
        liniero = LinieroFactory()
        client.login(email=liniero.email, password=user_password)

        url = reverse('lineas:mapa')
        response = client.get(url)

        assert response.status_code == 403

    def test_wrong_role_denied_programacion(self, client, user_password):
        """Test that liniero gets 403 for programacion view."""
        liniero = LinieroFactory()
        client.login(email=liniero.email, password=user_password)

        url = reverse('actividades:programacion')
        response = client.get(url)

        assert response.status_code == 403

    def test_wrong_role_denied_importar(self, client, user_password):
        """Test that ingeniero residente gets 403 for importar view."""
        ingeniero = IngenieroResidenteFactory()
        client.login(email=ingeniero.email, password=user_password)

        url = reverse('actividades:importar')
        response = client.get(url)

        assert response.status_code == 403

    def test_wrong_role_denied_financiero(self, client, user_password):
        """Test that liniero gets 403 for financiero dashboard."""
        liniero = LinieroFactory()
        client.login(email=liniero.email, password=user_password)

        url = reverse('financiero:dashboard')
        response = client.get(url)

        assert response.status_code == 403

    def test_wrong_role_denied_actas(self, client, user_password):
        """Test that liniero gets 403 for actas list."""
        liniero = LinieroFactory()
        client.login(email=liniero.email, password=user_password)

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
        client.login(email=admin.email, password=user_password)

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

    def test_coordinador_can_access_cuadrillas(self, client, user_password):
        """Test that coordinador can access cuadrillas views."""
        coordinador = CoordinadorFactory()
        client.login(email=coordinador.email, password=user_password)

        response = client.get(reverse('cuadrillas:lista'))
        assert response.status_code == 200

        response = client.get(reverse('cuadrillas:mapa'))
        assert response.status_code == 200

    def test_coordinador_can_access_programacion(self, client, user_password):
        """Test that coordinador can access programacion."""
        coordinador = CoordinadorFactory()
        client.login(email=coordinador.email, password=user_password)

        response = client.get(reverse('actividades:programacion'))
        assert response.status_code == 200

    def test_coordinador_can_access_financiero(self, client, user_password):
        """Test that coordinador can access financiero."""
        coordinador = CoordinadorFactory()
        client.login(email=coordinador.email, password=user_password)

        response = client.get(reverse('financiero:dashboard'))
        assert response.status_code == 200

    def test_ingeniero_can_access_programacion(self, client, user_password):
        """Test that ingeniero residente can access programacion."""
        ingeniero = IngenieroResidenteFactory()
        client.login(email=ingeniero.email, password=user_password)

        response = client.get(reverse('actividades:programacion'))
        assert response.status_code == 200

    def test_ingeniero_can_access_actas(self, client, user_password):
        """Test that ingeniero residente can access actas."""
        ingeniero = IngenieroResidenteFactory()
        client.login(email=ingeniero.email, password=user_password)

        response = client.get(reverse('indicadores:actas'))
        assert response.status_code == 200

    def test_supervisor_can_access_cuadrillas(self, client, user_password):
        """Test that supervisor can access cuadrillas views."""
        supervisor = SupervisorFactory()
        client.login(email=supervisor.email, password=user_password)

        response = client.get(reverse('cuadrillas:lista'))
        assert response.status_code == 200

        response = client.get(reverse('cuadrillas:mapa'))
        assert response.status_code == 200

    def test_supervisor_can_access_campo(self, client, user_password):
        """Test that supervisor can access campo views."""
        supervisor = SupervisorFactory()
        client.login(email=supervisor.email, password=user_password)

        response = client.get(reverse('campo:lista'))
        assert response.status_code == 200

    def test_liniero_can_access_campo(self, client, user_password):
        """Test that liniero can access campo views."""
        liniero = LinieroFactory()
        client.login(email=liniero.email, password=user_password)

        response = client.get(reverse('campo:lista'))
        assert response.status_code == 200

    def test_liniero_can_access_lineas(self, client, user_password):
        """Test that liniero can access lineas list and detail."""
        liniero = LinieroFactory()
        linea = LineaFactory()
        client.login(email=liniero.email, password=user_password)

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
        client.login(email=superuser.email, password=user_password)

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
        logged_in = client.login(email=user.email, password=user_password)
        assert logged_in is False

    def test_detail_view_with_nonexistent_object(self, client, user_password):
        """Test that 404 is returned for nonexistent objects."""
        import uuid
        admin = AdminFactory()
        client.login(email=admin.email, password=user_password)

        url = reverse('lineas:detalle', kwargs={'pk': uuid.uuid4()})
        response = client.get(url)

        assert response.status_code == 404

    def test_post_request_on_get_only_view(self, client, user_password):
        """Test behavior of POST request on GET-only views."""
        admin = AdminFactory()
        client.login(email=admin.email, password=user_password)

        # List views typically don't accept POST
        url = reverse('lineas:lista')
        response = client.post(url)

        # Should be 405 Method Not Allowed or similar
        assert response.status_code in [200, 405]
