"""Instelec#186 A1 — la matriz granular es autoridad en Campo."""

import pytest

from apps.core.models import RoleModuloPermiso
from apps.core.permissions import (
    MODULO_MANTENIMIENTO,
    SUBMODULO_MANTENIMIENTO_CAMPO,
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
