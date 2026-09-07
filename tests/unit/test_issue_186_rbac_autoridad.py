"""Instelec#186 A1 — la matriz granular es autoridad en Campo."""

import pytest

from apps.core.models import RoleModuloPermiso
from apps.core.permissions import (
    MODULO_MANTENIMIENTO,
    SUBMODULO_MANTENIMIENTO_CAMPO,
    SUBMODULO_MANTENIMIENTO_PROCEDIMIENTOS,
    invalidate_role_cache,
)
from apps.usuarios.models import Usuario


@pytest.fixture
def auxiliar_campo(db, user_password):
    """El ``auxiliar`` es un rol legacy ya sembrado, no un rol ad-hoc."""
    RoleModuloPermiso.objects.update_or_create(
        role_id="auxiliar",
        modulo=MODULO_MANTENIMIENTO,
        submodulo=SUBMODULO_MANTENIMIENTO_CAMPO,
        defaults={"nivel_acceso": RoleModuloPermiso.VER_EDITAR},
    )
    invalidate_role_cache("auxiliar")
    return Usuario.objects.create_user(
        email="auxiliar.campo.186@test.com",
        password=user_password,
        first_name="Auxiliar",
        last_name="Campo",
        rol="auxiliar",
    )


@pytest.fixture
def auxiliar_campo_solo_lectura(auxiliar_campo):
    RoleModuloPermiso.objects.filter(
        role_id="auxiliar",
        modulo=MODULO_MANTENIMIENTO,
        submodulo=SUBMODULO_MANTENIMIENTO_CAMPO,
    ).update(nivel_acceso=RoleModuloPermiso.VER)
    invalidate_role_cache("auxiliar")
    return auxiliar_campo


@pytest.fixture
def auxiliar_procedimientos_solo_lectura(auxiliar_campo):
    """Un rol legacy puede tener una hoja distinta sin el módulo completo."""
    RoleModuloPermiso.objects.update_or_create(
        role_id=auxiliar_campo.rol,
        modulo=MODULO_MANTENIMIENTO,
        submodulo=SUBMODULO_MANTENIMIENTO_PROCEDIMIENTOS,
        defaults={"nivel_acceso": RoleModuloPermiso.VER},
    )
    invalidate_role_cache(auxiliar_campo.rol)
    return auxiliar_campo


@pytest.mark.django_db
class TestCampoRbacAutoridad186:
    def test_auxiliar_legacy_con_ver_editar_obtiene_lista_campo(self, client, auxiliar_campo, user_password):
        client.login(username=auxiliar_campo.email, password=user_password)

        response = client.get("/campo/")

        assert response.status_code == 200

    def test_rol_con_ver_obtiene_lista_campo(self, client, auxiliar_campo_solo_lectura, user_password):
        client.login(username=auxiliar_campo_solo_lectura.email, password=user_password)

        response = client.get("/campo/")

        assert response.status_code == 200

    def test_rol_con_ver_no_puede_postear_creacion_campo(self, client, auxiliar_campo_solo_lectura, user_password):
        client.login(username=auxiliar_campo_solo_lectura.email, password=user_password)

        response = client.post("/campo/crear/", {})

        assert response.status_code == 302
        assert response.url == "/"

    def test_auxiliar_legacy_con_hoja_procedimientos_ve_url_mas_especifica(
        self, client, auxiliar_procedimientos_solo_lectura, user_password
    ):
        """El prefijo de procedimientos no puede caer en la hoja Campo."""
        client.login(
            username=auxiliar_procedimientos_solo_lectura.email,
            password=user_password,
        )

        response = client.get("/campo/procedimientos/")

        assert response.status_code == 200

    def test_admin_construccion_no_salta_mantenimiento_por_url_directa(
        self, client, user_password
    ):
        """Ser admin de Construcción no autoriza ninguna hoja de Mantenimiento."""
        usuario = Usuario.objects.create_user(
            email="admin-construccion-directo.186@test.com",
            password=user_password,
            first_name="Admin",
            last_name="Construccion",
            rol="admin_construccion",
        )
        client.login(username=usuario.email, password=user_password)

        for url in ("/campo/", "/campo/procedimientos/"):
            response = client.get(url)
            assert response.status_code == 302
            assert response.url == "/"

    def test_superusuario_legacy_conserva_acceso_a_ambas_superficies(
        self, client, user_password
    ):
        """El bypass explícito de superusuario sigue atravesando ambos gates."""
        superusuario = Usuario.objects.create_user(
            email="superusuario-legacy.186@test.com",
            password=user_password,
            first_name="Super",
            last_name="Legacy",
            rol="auxiliar",
            is_superuser=True,
            is_staff=True,
        )
        client.login(username=superusuario.email, password=user_password)

        for url in ("/campo/", "/campo/procedimientos/"):
            assert client.get(url).status_code == 200
