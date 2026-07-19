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
        assert user.rol == "operario_general"  # Default role (Rol.OPERARIO_GENERAL)
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


@pytest.mark.django_db
class TestEsOperarioCampoRetrofit186:
    """Issue #186 (A4): `es_operario_campo` retrofit BD-backed.

    Antes importaba `ROL_NIVEL`/`NIVEL_OPERARIO` directo del dict eliminado
    en A3; ahora pasa por `apps.core.permissions.rol_nivel` (BD-backed,
    cacheado). Debe dar el MISMO resultado que antes para los 15 roles
    legacy -- reusa el snapshot congelado del Gate de Paridad (A2)."""

    def test_es_operario_campo_paridad_15_roles(self):
        from apps.core import rbac_seed_data as snap

        for codigo in snap.TODOS_LOS_CODIGOS:
            user = User(rol=codigo, is_superuser=False, is_staff=False)
            esperado = snap.ROL_NIVEL.get(codigo) == snap.NIVEL_OPERARIO
            assert user.es_operario_campo == esperado, (
                f"es_operario_campo roto para rol={codigo}: "
                f"esperado={esperado} real={user.es_operario_campo}"
            )

    def test_es_operario_campo_liniero_true(self):
        """Caso concreto (liniero es el rol legacy más usado en prod, 90
        usuarios reales confirmados 2026-07-18 vía proxy Cloud SQL)."""
        user = User(rol="liniero", is_superuser=False, is_staff=False)
        assert user.es_operario_campo is True

    def test_es_operario_campo_admin_false(self):
        user = User(rol="admin", is_superuser=False, is_staff=False)
        assert user.es_operario_campo is False


@pytest.mark.django_db
class TestDropdownRolesDinamicoRetrofit186:
    """Issue #186 (A4): el dropdown de asignación de rol en
    GestionUsuariosView/CrearUsuarioAdminView lee `Role.objects.filter(
    activo=True)` en vez de `Usuario.Rol.choices` -- así un rol creado desde
    la matriz (A5) queda disponible para asignar sin deploy."""

    def test_gestion_usuarios_dropdown_incluye_rol_nuevo(self, client, user_password):
        from apps.core.models import Role
        from tests.factories import AdminFactory

        Role.objects.create(
            codigo="qa_e2e_test_dropdown_a4",
            nombre="QA_E2E_186 Rol Dropdown",
            nivel=Role.NIVEL_OPERARIO,
            activo=True,
        )
        admin = AdminFactory()
        client.login(username=admin.email, password=user_password)

        response = client.get("/usuarios/gestion/")
        assert response.status_code == 200
        codigos = [codigo for codigo, _nombre in response.context["roles"]]
        assert "qa_e2e_test_dropdown_a4" in codigos

    def test_crear_usuario_dropdown_excluye_rol_inactivo(self, client, user_password):
        from apps.core.models import Role
        from tests.factories import AdminFactory

        Role.objects.create(
            codigo="qa_e2e_dropdown_inact_a4",
            nombre="QA_E2E_186 Rol Inactivo",
            nivel=Role.NIVEL_OPERARIO,
            activo=False,
        )
        admin = AdminFactory()
        client.login(username=admin.email, password=user_password)

        response = client.get("/usuarios/gestion/crear/")
        assert response.status_code == 200
        codigos = [codigo for codigo, _nombre in response.context["roles"]]
        assert "qa_e2e_dropdown_inact_a4" not in codigos
