"""Unit tests for usuarios app."""

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
class TestUsuarioModel:
    """Tests for Usuario model."""

    def test_create_user(self):
        """Test creating a basic user."""
        user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
        )
        assert user.email == "test@example.com"
        assert user.check_password("testpass123")
        assert user.rol == "liniero"  # Default role
        assert user.is_active
        assert not user.is_staff
        assert not user.is_superuser

    def test_create_superuser(self):
        """Test creating a superuser."""
        user = User.objects.create_superuser(
            email="admin@example.com",
            password="adminpass123",
        )
        assert user.is_staff
        assert user.is_superuser
        assert user.is_active

    def test_user_str(self):
        """Test user string representation."""
        user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
        )
        # __str__ returns full name if available, otherwise email
        assert str(user) == "Test User"

    def test_user_str_no_name(self):
        """Test user string representation when no name set."""
        user = User.objects.create_user(
            email="noname@example.com",
            password="testpass123",
        )
        # Falls back to email when no name
        assert str(user) == "noname@example.com"

    def test_user_roles(self):
        """Test different user roles."""
        roles = [
            "admin", "director", "coordinador", "ing_residente",
            "ing_ambiental", "supervisor", "liniero", "auxiliar"
        ]
        for role in roles:
            user = User.objects.create_user(
                email=f"{role}@example.com",
                password="testpass123",
                rol=role,
            )
            assert user.rol == role

    def test_user_uuid_primary_key(self):
        """Test that user has UUID primary key."""
        import uuid
        user = User.objects.create_user(
            email="uuid@example.com",
            password="testpass123",
        )
        assert isinstance(user.id, uuid.UUID)

    def test_user_timestamps(self):
        """Test that user has timestamps."""
        user = User.objects.create_user(
            email="timestamps@example.com",
            password="testpass123",
        )
        assert user.created_at is not None
        assert user.updated_at is not None


@pytest.mark.django_db
class TestUsuarioFactory:
    """Tests for Usuario factory."""

    def test_usuario_factory(self):
        """Test UsuarioFactory creates valid users."""
        from tests.factories import UsuarioFactory

        user = UsuarioFactory()
        assert user.email
        assert user.first_name
        assert user.last_name
        assert user.check_password("testpass123!")

    def test_admin_factory(self):
        """Test AdminFactory creates admin users."""
        from tests.factories import AdminFactory

        user = AdminFactory()
        assert user.rol == "admin"
        assert user.is_staff
        assert user.is_superuser

    def test_coordinador_factory(self):
        """Test CoordinadorFactory creates coordinador users."""
        from tests.factories import CoordinadorFactory

        user = CoordinadorFactory()
        assert user.rol == "coordinador"
