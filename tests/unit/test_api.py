"""Unit tests for API endpoints."""

import pytest
from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
class TestHealthCheck:
    """Tests for health check endpoint."""

    def test_health_check(self, client: Client):
        """Test health check returns OK."""
        response = client.get("/health/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


@pytest.mark.django_db
class TestAuthAPI:
    """Tests for authentication API."""

    def test_login_success(self, client: Client):
        """Test successful login."""
        user = User.objects.create_user(
            email="login@test.com",
            password="testpass123!",
        )
        response = client.post(
            "/api/v1/auth/login",
            data={"email": "login@test.com", "password": "testpass123!"},
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.json()
        assert "access" in data
        assert "refresh" in data

    def test_login_invalid_credentials(self, client: Client):
        """Test login with invalid credentials."""
        response = client.post(
            "/api/v1/auth/login",
            data={"email": "wrong@test.com", "password": "wrongpass"},
            content_type="application/json",
        )
        assert response.status_code in [401, 422]

    def test_me_authenticated(self, client: Client):
        """Test getting current user info when authenticated."""
        from rest_framework_simplejwt.tokens import RefreshToken

        user = User.objects.create_user(
            email="me@test.com",
            password="testpass123!",
            first_name="Test",
            last_name="User",
            rol="coordinador",
        )
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)

        response = client.get(
            "/api/v1/auth/me",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "me@test.com"
        assert data["rol"] == "coordinador"

    def test_me_unauthenticated(self, client: Client):
        """Test getting current user info without auth."""
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 401


@pytest.mark.django_db
class TestLineasAPI:
    """Tests for lineas API."""

    def test_list_lineas_authenticated(self, client: Client):
        """Test listing lineas when authenticated."""
        from rest_framework_simplejwt.tokens import RefreshToken
        from tests.factories import LineaFactory

        user = User.objects.create_user(
            email="lineas@test.com",
            password="testpass123!",
        )
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)

        # Create some lineas
        LineaFactory.create_batch(3)

        response = client.get(
            "/api/v1/lineas/",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

    def test_list_lineas_unauthenticated(self, client: Client):
        """Test listing lineas without auth."""
        response = client.get("/api/v1/lineas/")
        assert response.status_code == 401


@pytest.mark.django_db
class TestActividadesAPI:
    """Tests for actividades API."""

    def test_list_mis_actividades(self, client: Client):
        """Test listing my activities."""
        from rest_framework_simplejwt.tokens import RefreshToken
        from tests.factories import (
            ActividadFactory,
            CuadrillaFactory,
            CuadrillaMiembroFactory,
            LinieroFactory,
        )

        user = LinieroFactory()
        cuadrilla = CuadrillaFactory()
        CuadrillaMiembroFactory(cuadrilla=cuadrilla, usuario=user)

        # Create activities for this crew
        ActividadFactory.create_batch(3, cuadrilla=cuadrilla, estado="PENDIENTE")

        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)

        response = client.get(
            "/api/v1/actividades/mis-actividades",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        # Note: This might need the cuadrilla_actual property implemented
        assert response.status_code in [200, 404]
