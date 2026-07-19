"""Pytest configuration and fixtures for TransMaint."""

import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


# ==============================================================================
# RBAC (issue #186, A3) — seed de Role/RoleModuloPermiso para TODA la suite
# ==============================================================================

@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    """Extiende el setup de BD de pytest-django sembrando Role/
    RoleModuloPermiso UNA VEZ por sesión.

    `apps/core/permissions.py` (A3) ahora lee RBAC desde `Role`/
    `RoleModuloPermiso` (BD) en vez de dicts hardcodeados. Pero `pytest`
    corre con `--nomigrations` (ver `pyproject.toml`) — la migración de
    datos real (`0002_seed_roles_permisos.py`) NUNCA se ejecuta en la suite
    de tests. Sin este fixture, CUALQUIER test que dependa de acceso por
    rol (RBAC, `RoleRequiredMixin`, `RBACModuloMiddleware`, que corre en
    CADA request) fallaría con 403/redirect porque no habría filas de
    `Role` que leer — confirmado con 6 regresiones reales en
    `tests/unit/test_permissions.py` antes de agregar este fixture.

    Sembrado a nivel de SESIÓN (no por-test) y con commit real (vía
    `django_db_blocker.unblock()`) para que sea visible como datos
    "ya existentes" en la transacción de cada test individual — igual que
    una migración de datos real ya aplicada. Misma fuente que la migración
    real y el Gate de Paridad (`apps/core/rbac_seed_data.py`).
    """
    with django_db_blocker.unblock():
        from apps.core.rbac_seed_data import seed_roles_permisos_bd

        seed_roles_permisos_bd()


# ==============================================================================
# User Fixtures
# ==============================================================================

@pytest.fixture
def user_password():
    """Return a common password for test users."""
    return "testpass123!"


@pytest.fixture
def admin_user(db, user_password):
    """Create and return an admin user."""
    return User.objects.create_user(
        email="admin@test.com",
        password=user_password,
        first_name="Admin",
        last_name="User",
        rol="admin",
        is_staff=True,
        is_superuser=True,
    )


@pytest.fixture
def coordinador_user(db, user_password):
    """Create and return a coordinator user."""
    return User.objects.create_user(
        email="coordinador@test.com",
        password=user_password,
        first_name="Coordinador",
        last_name="Test",
        rol="coordinador",
    )


@pytest.fixture
def ingeniero_user(db, user_password):
    """Create and return an engineer user."""
    return User.objects.create_user(
        email="ingeniero@test.com",
        password=user_password,
        first_name="Ingeniero",
        last_name="Residente",
        rol="ing_residente",
    )


@pytest.fixture
def liniero_user(db, user_password):
    """Create and return a lineman user."""
    return User.objects.create_user(
        email="liniero@test.com",
        password=user_password,
        first_name="Liniero",
        last_name="Campo",
        rol="liniero",
    )


# ==============================================================================
# API Client Fixtures
# ==============================================================================

@pytest.fixture
def api_client():
    """Return a Django Ninja test client."""
    from ninja.testing import TestClient

    from apps.api.router import api

    return TestClient(api)


@pytest.fixture
def authenticated_client(client, admin_user, user_password):
    """Return an authenticated Django test client."""
    client.login(username=admin_user.email, password=user_password)
    return client


@pytest.fixture
def jwt_token(liniero_user):
    """Return a JWT token for the liniero user."""
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(liniero_user)
    return str(refresh.access_token)


@pytest.fixture
def authenticated_api_client(client, liniero_user):
    """Return an authenticated API client with JWT token."""
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(liniero_user)
    client.defaults['HTTP_AUTHORIZATION'] = f"Bearer {str(refresh.access_token)}"
    return client


# ==============================================================================
# Domain Object Fixtures
# ==============================================================================

@pytest.fixture
def linea(db):
    """Create and return a transmission line."""
    from tests.factories import LineaFactory
    return LineaFactory()


@pytest.fixture
def torre(linea):
    """Create and return a tower for the line."""
    from tests.factories import TorreFactory
    return TorreFactory(linea=linea)


@pytest.fixture
def cuadrilla(db, liniero_user):
    """Create and return a crew with the liniero user."""
    from tests.factories import CuadrillaFactory, CuadrillaMiembroFactory
    cuadrilla = CuadrillaFactory()
    CuadrillaMiembroFactory(cuadrilla=cuadrilla, usuario=liniero_user, activo=True)
    return cuadrilla


@pytest.fixture
def tipo_actividad(db):
    """Create and return an activity type."""
    from tests.factories import TipoActividadFactory
    return TipoActividadFactory()


@pytest.fixture
def actividad_pendiente(linea, torre, tipo_actividad, cuadrilla):
    """Create and return a pending activity."""
    from tests.factories import ActividadFactory
    return ActividadFactory(
        linea=linea,
        torre=torre,
        tipo_actividad=tipo_actividad,
        cuadrilla=cuadrilla,
        estado='PENDIENTE',
    )


@pytest.fixture
def actividad_en_curso(linea, torre, tipo_actividad, cuadrilla):
    """Create and return an in-progress activity."""
    from tests.factories import ActividadEnCursoFactory
    return ActividadEnCursoFactory(
        linea=linea,
        torre=torre,
        tipo_actividad=tipo_actividad,
        cuadrilla=cuadrilla,
    )


@pytest.fixture
def actividad_completada(linea, torre, tipo_actividad, cuadrilla):
    """Create and return a completed activity."""
    from tests.factories import ActividadCompletadaFactory
    return ActividadCompletadaFactory(
        linea=linea,
        torre=torre,
        tipo_actividad=tipo_actividad,
        cuadrilla=cuadrilla,
    )


@pytest.fixture
def registro_campo(actividad_en_curso, liniero_user):
    """Create and return a field record."""
    from tests.factories import RegistroCampoFactory
    return RegistroCampoFactory(
        actividad=actividad_en_curso,
        usuario=liniero_user,
    )


@pytest.fixture
def registro_campo_completo(actividad_completada, liniero_user):
    """Create and return a completed field record with evidence."""
    from tests.factories import (
        RegistroCampoCompletadoFactory,
        EvidenciaAntesFactory,
        EvidenciaDuranteFactory,
        EvidenciaDespuesFactory,
    )
    registro = RegistroCampoCompletadoFactory(
        actividad=actividad_completada,
        usuario=liniero_user,
    )
    EvidenciaAntesFactory(registro_campo=registro)
    EvidenciaDuranteFactory(registro_campo=registro)
    EvidenciaDespuesFactory(registro_campo=registro)
    return registro


# ==============================================================================
# Financial Fixtures
# ==============================================================================

@pytest.fixture
def presupuesto(linea):
    """Create and return a budget for the line."""
    from tests.factories import PresupuestoFactory
    return PresupuestoFactory(linea=linea)


@pytest.fixture
def presupuesto_en_ejecucion(linea):
    """Create and return a budget in execution."""
    from tests.factories import PresupuestoEnEjecucionFactory
    return PresupuestoEnEjecucionFactory(linea=linea)


# ==============================================================================
# Indicator Fixtures
# ==============================================================================

@pytest.fixture
def indicadores_base(db):
    """Create base set of indicators."""
    from tests.factories import (
        IndicadorGestionFactory,
        IndicadorEjecucionFactory,
        IndicadorSeguridadFactory,
    )
    return {
        'gestion': IndicadorGestionFactory(),
        'ejecucion': IndicadorEjecucionFactory(),
        'seguridad': IndicadorSeguridadFactory(),
    }


# ==============================================================================
# Test Helpers
# ==============================================================================

@pytest.fixture
def current_period():
    """Return current year and month."""
    now = timezone.now()
    return {'anio': now.year, 'mes': now.month}


@pytest.fixture
def sample_gps_coords():
    """Return sample GPS coordinates in Colombia."""
    return {
        'latitud': Decimal("10.12345678"),
        'longitud': Decimal("-74.87654321"),
    }
