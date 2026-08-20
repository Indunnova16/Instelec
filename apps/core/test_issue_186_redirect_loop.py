"""Instelec#186 (bounce 3) — recursión infinita del widget "Mis Actividades de
Hoy" para roles sin acceso al módulo Mantenimiento.

Causa raíz confirmada por F2 (reproducida en vivo con Playwright, usuario real
`qa_claude_auxiliar@instelec.com`): el widget en `templates/core/home.html`
dispara SIEMPRE `hx-get="/actividades/?fecha=hoy&partial=true"` con
`hx-trigger="load"`. Cuando el rol del usuario NO tiene acceso al módulo
MANTENIMIENTO (auxiliar/liniero en prod, 120 usuarios reales),
`RBACModuloMiddleware` interceptaba ese `hx-get` y respondía con un
`redirect()` plano (302 + Location) que NO es HTMX-aware: htmx sigue ese 302
como un GET normal, recibe la página `home.html` COMPLETA, la swapea como
innerHTML del div chico que originó la request -- y esa página completa
contiene el MISMO widget `hx-trigger="load"`, que se re-dispara -> recursión
infinita real (60-78 redirects 302 encadenados, confirmado con Playwright).

Fix (2 piezas, ver apps/core/middleware.py y templates/core/home.html):
  1. RBACModuloMiddleware responde con header `HX-Redirect` (no 302 plano)
     cuando la request es HTMX -- fuerza navegación TOP-LEVEL del browser,
     rompe la recursión estructuralmente para cualquier widget futuro.
  2. El widget de home.html se envuelve en un guard `{% if %}` que no intenta
     cargar un recurso que se sabe bloqueado (defensa en profundidad).

Reproceso (bounce 3): la ronda 2026-08-16 cerró el síntoma en
HomeView.dispatch pero nunca tocó el widget HTMX ni el middleware -- el
síntoma cambió de forma (de "sin acceso silencioso" a "recursión infinita
visible") sin que la causa de fondo se corrigiera. Estos tests reproducen el
escenario EXACTO (rol legacy real `auxiliar`, dato de permisos igual al de
prod: MANTENIMIENTO=sin_acceso) contra el middleware Y el template juntos,
no solo un mock aislado.
"""

import pytest
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import reverse

from apps.core.middleware import RBACModuloMiddleware


WIDGET_HX_GET_FRAGMENT = "actividades/?fecha=hoy&partial=true"


@pytest.fixture
def auxiliar_sin_mantenimiento(db, user_password):
    """Usuario con rol legacy REAL (`auxiliar`, no un mock), con el permiso de
    MANTENIMIENTO puesto en `sin_acceso` -- exactamente el dato observado en
    BD prod por F2 (SELECT directo, ver Instelec_186_f2.json)."""
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
        email="auxiliar.sin.mantenimiento.186.redirectloop@test.com",
        password=user_password,
        first_name="Auxiliar",
        last_name="SinMantenimiento",
        rol="auxiliar",
    )


def _middleware_response(user, path, htmx=False):
    """Ejecuta el middleware real de forma aislada (sin acoplar a vistas).

    `RBACModuloMiddleware` llama `messages.error(...)` en el camino de
    denegación -- `RequestFactory` no instala `MessageMiddleware`, así que
    hay que darle un storage de mensajes manualmente (mismo patrón que usa
    Django internamente en sus propios tests de `contrib.messages`)."""
    from django.contrib.messages.storage.fallback import FallbackStorage

    kwargs = {"HTTP_HX_REQUEST": "true"} if htmx else {}
    request = RequestFactory().get(path, **kwargs)
    request.user = user
    request.session = {}
    request._messages = FallbackStorage(request)
    return RBACModuloMiddleware(lambda _request: HttpResponse(status=204))(request)


@pytest.mark.django_db
class TestMiddlewareHXRedirectRompeRecursion186:
    """Caso 1: el middleware, aislado, debe distinguir HTMX de navegación normal."""

    def test_request_htmx_denegada_recibe_hx_redirect_no_302_plano(
        self, auxiliar_sin_mantenimiento
    ):
        response = _middleware_response(
            auxiliar_sin_mantenimiento, "/actividades/", htmx=True
        )
        # Pieza central del fix: NO puede ser un 302 -- eso es exactamente lo
        # que htmx sigue con un GET normal y dispara el swap anidado que causa
        # la recursión. Debe ser una respuesta 2xx con el header HX-Redirect,
        # que hace que htmx navegue top-level en vez de swapear.
        assert response.status_code != 302
        assert response.get("HX-Redirect") == reverse("core:home")

    def test_request_normal_denegada_sigue_siendo_302_plano(
        self, auxiliar_sin_mantenimiento
    ):
        """Comportamiento viejo preservado para navegación NO-HTMX (browser
        bar, links normales, etc.) -- no romper ese caso."""
        response = _middleware_response(
            auxiliar_sin_mantenimiento, "/actividades/", htmx=False
        )
        assert response.status_code == 302
        assert response.url == reverse("core:home")
        assert "HX-Redirect" not in response

    def test_usuario_con_acceso_no_se_ve_afectado(self, db, user_password):
        """Un usuario CON acceso al módulo sigue pasando derecho, con o sin
        header HTMX -- el fix no debe interferir en el camino feliz."""
        from apps.usuarios.models import Usuario

        admin = Usuario.objects.create_user(
            email="admin.general.186.redirectloop@test.com",
            password=user_password,
            first_name="Admin",
            last_name="General",
            rol="admin_general",
        )
        assert _middleware_response(admin, "/actividades/", htmx=True).status_code == 204
        assert _middleware_response(admin, "/actividades/", htmx=False).status_code == 204


@pytest.mark.django_db
class TestClientEndToEndHXRedirect186:
    """Caso 2: contra el Client real (URL dispatch + middleware stack completo),
    con el usuario legacy real (`auxiliar`) logueado -- no un RequestFactory
    aislado."""

    def test_client_htmx_get_actividades_recibe_hx_redirect(
        self, client, auxiliar_sin_mantenimiento, user_password
    ):
        client.force_login(auxiliar_sin_mantenimiento)
        response = client.get(
            "/actividades/?fecha=hoy&partial=true", HTTP_HX_REQUEST="true"
        )
        assert response.status_code != 302
        assert response.get("HX-Redirect") == "/"

    def test_client_get_normal_actividades_sigue_302(
        self, client, auxiliar_sin_mantenimiento
    ):
        client.force_login(auxiliar_sin_mantenimiento)
        response = client.get("/actividades/?fecha=hoy&partial=true")
        assert response.status_code == 302
        assert response.url == "/"


@pytest.mark.django_db
class TestHomeTemplateGuard186:
    """Caso 3: defensa en profundidad -- el widget de home.html no debe ni
    intentar cargar un recurso que se sabe bloqueado para el rol actual."""

    def test_home_no_incluye_hx_get_del_widget_para_rol_sin_acceso(
        self, auxiliar_sin_mantenimiento
    ):
        request = RequestFactory().get("/")
        request.user = auxiliar_sin_mantenimiento
        request.session = {}
        html = render_to_string(
            "core/home.html",
            {"show_full_dashboard": False, "puede_ver_actividades_hoy": False},
            request=request,
        )
        assert WIDGET_HX_GET_FRAGMENT not in html
        assert "no tiene acceso al módulo de Mantenimiento" in html

    def test_home_incluye_hx_get_del_widget_para_rol_con_acceso(
        self, liniero_user
    ):
        """`liniero_user` (fixture de conftest.py) usa el seed RBAC por
        defecto -- MANTENIMIENTO=ver para `liniero` -- confirmando que el
        guard NO rompe el camino feliz para roles que sí deben ver el widget."""
        request = RequestFactory().get("/")
        request.user = liniero_user
        request.session = {}
        html = render_to_string(
            "core/home.html",
            {"show_full_dashboard": False, "puede_ver_actividades_hoy": True},
            request=request,
        )
        assert WIDGET_HX_GET_FRAGMENT in html


@pytest.mark.django_db
class TestHomeViewContextFlag186:
    """Caso 4: `HomeView.get_context_data` calcula el flag correctamente
    contra la vista real (no solo el template en aislado)."""

    def test_context_flag_false_para_auxiliar_sin_acceso(
        self, client, auxiliar_sin_mantenimiento
    ):
        client.force_login(auxiliar_sin_mantenimiento)
        response = client.get("/")
        assert response.status_code == 200
        assert response.context["puede_ver_actividades_hoy"] is False
        assert WIDGET_HX_GET_FRAGMENT not in response.content.decode()

    def test_context_flag_true_para_rol_no_campo_con_acceso_seed_default(
        self, client, ingeniero_user
    ):
        """`ingeniero_user` (fixture de conftest.py, rol=`ing_residente`) NO
        es personal de campo (`Usuario.is_campo` sólo cubre liniero/auxiliar/
        supervisor) y SÍ tiene acceso a MANTENIMIENTO por el seed RBAC
        default -- por eso llega a la rama `{% else %}` de home.html
        (show_full_dashboard=False) sin que `HomeView.dispatch` lo redirija
        antes, a diferencia de liniero/auxiliar con acceso (ver
        `Usuario.is_campo` + `HomeView.dispatch`, que los manda directo a
        `campo:lista`)."""
        client.force_login(ingeniero_user)
        response = client.get("/")
        assert response.status_code == 200
        assert response.context["show_full_dashboard"] is False
        assert response.context["puede_ver_actividades_hoy"] is True
        assert WIDGET_HX_GET_FRAGMENT in response.content.decode()
