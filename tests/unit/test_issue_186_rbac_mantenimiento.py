"""Instelec#186 A1 — Mantenimiento se autoriza por servidor y por menú.

El rol ``auxiliar`` es un registro legacy ya sembrado por la migración de
roles. El caso reproduce la matriz reportada por cliente: sin acceso general a
Mantenimiento, aunque conserve sus submódulos de Construcción.
"""

import pytest
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.test import RequestFactory

from apps.core.middleware import RBACModuloMiddleware


MANTENIMIENTO_URLS = (
    "/actividades/",
    "/lineas/",
    "/campo/",
    "/contratos/",
    "/ambiental/",
    "/financiero/",
    "/indicadores/",
    "/cuadrillas/mapa/",
)


@pytest.fixture
def auxiliar_sin_mantenimiento(db, user_password):
    """Usuario legacy contra su Role preexistente, no un fixture inventado."""
    from apps.core.models_roles import RoleModuloPermiso
    from apps.core.permissions import MODULO_MANTENIMIENTO, invalidate_role_cache
    from apps.usuarios.models import Usuario

    RoleModuloPermiso.objects.filter(
        role__codigo="auxiliar",
        modulo=MODULO_MANTENIMIENTO,
        submodulo="",
    ).update(nivel_acceso=RoleModuloPermiso.SIN_ACCESO)
    invalidate_role_cache("auxiliar")
    return Usuario.objects.create_user(
        email="auxiliar.sin.mantenimiento.186@test.com",
        password=user_password,
        first_name="Auxiliar",
        last_name="Sin Mantenimiento",
        rol="auxiliar",
    )


def _middleware_response(user, path):
    """Ejecuta el middleware real sin acoplar el test a vistas secundarias."""
    request = RequestFactory().get(path)
    request.user = user
    return RBACModuloMiddleware(lambda _request: HttpResponse(status=204))(request)


@pytest.mark.django_db
class TestRbacMantenimiento186:
    @pytest.mark.parametrize("path", MANTENIMIENTO_URLS)
    def test_auxiliar_sin_permiso_es_bloqueado_en_toda_ruta_mantenimiento(
        self, client, auxiliar_sin_mantenimiento, path
    ):
        """URL directa no debe saltarse el menú: middleware redirige al inicio."""
        client.force_login(auxiliar_sin_mantenimiento)
        response = client.get(path)
        assert response.status_code == 302
        assert response.url == "/"

    def test_auxiliar_sin_permiso_no_recibe_menu_de_mantenimiento(
        self, auxiliar_sin_mantenimiento
    ):
        request = RequestFactory().get("/")
        request.user = auxiliar_sin_mantenimiento
        request.session = {}
        html = render_to_string(
            "components/sidebar.html",
            request=request,
        )
        for label in (
            "Formato de Campo",
            "Actividades",
            "Lineas y Torres",
            "Campo",
            "Contratos",
            "Ambiental",
            "Financiero",
            "Indicadores",
            "Mapa en Vivo",
        ):
            assert label not in html

    def test_admin_general_conserva_acceso_a_mantenimiento_y_construccion(
        self, db, user_password
    ):
        from apps.usuarios.models import Usuario

        admin = Usuario.objects.create_user(
            email="admin.general.186a1@test.com",
            password=user_password,
            first_name="Admin",
            last_name="General",
            rol="admin_general",
        )
        assert _middleware_response(admin, "/actividades/").status_code == 204
        assert _middleware_response(admin, "/construccion/proyecto/").status_code == 204

    def test_operario_construccion_conserva_construccion_y_no_mantenimiento(
        self, client, db, user_password
    ):
        from apps.usuarios.models import Usuario

        operario = Usuario.objects.create_user(
            email="operario.construccion.186a1@test.com",
            password=user_password,
            first_name="Operario",
            last_name="Construccion",
            rol="operario_construccion",
        )
        assert _middleware_response(operario, "/construccion/proyecto/").status_code == 204
        client.force_login(operario)
        assert client.get("/actividades/").status_code == 302
