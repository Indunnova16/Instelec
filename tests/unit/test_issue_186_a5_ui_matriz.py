"""Tests UI matriz roles x módulos (issue #186, A5).

CRUD `Role` + grid HTMX bajo Parametrización. Cubre:
- Crear/editar/inactivar `Role` vía las vistas nuevas.
- La matriz renderiza roles activos con sus permisos actuales.
- Guardar una celda (módulo o sub-módulo) vía HTMX invalida el cache de
  `apps.core.permissions` de inmediato (A3) -- no espera el TTL.
- El rol nuevo creado + con permiso asignado aparece en el dropdown de
  asignación de usuario (A4), cerrando el círculo "crear rol sin deploy".
"""

import pytest
from django.contrib.messages.storage.fallback import FallbackStorage
from django.http import HttpResponse
from django.test import RequestFactory

from apps.core.middleware import RBACModuloMiddleware
from apps.core.models import Role, RoleModuloPermiso
from apps.core.permissions import (
    MODULO_MANTENIMIENTO,
    MODULO_CONSTRUCCION,
    user_can_access_modulo,
    user_can_access_submodulo,
)
from tests.factories import AdminFactory


def _rbac_response(user, path, method="GET", htmx=False):
    """Pasa una URL real por el middleware que protege requests directos.

    La vista final devuelve 204: así un 302/HX-Redirect solo puede provenir
    del control RBAC y no de una validación de formulario ajena al permiso.
    """
    request = getattr(RequestFactory(), method.lower())(
        path, HTTP_HX_REQUEST="true" if htmx else None
    )
    request.user = user
    request.session = {}
    request._messages = FallbackStorage(request)
    return RBACModuloMiddleware(lambda _request: HttpResponse(status=204))(request)


@pytest.fixture
def admin_client(client, user_password):
    admin = AdminFactory()
    client.login(username=admin.email, password=user_password)
    return client


@pytest.mark.django_db
class TestRoleCRUD186:
    def test_roles_lista_status_200(self, admin_client):
        response = admin_client.get("/parametrizacion/roles/")
        assert response.status_code == 200

    def test_roles_lista_incluye_los_15_seeded(self, admin_client):
        response = admin_client.get("/parametrizacion/roles/")
        assert response.status_code == 200
        assert len(response.context["roles"]) == 15

    def test_crear_rol_nuevo(self, admin_client):
        response = admin_client.post(
            "/parametrizacion/roles/crear/",
            {
                "codigo": "qa_e2e_a5_crear",
                "nombre": "QA_E2E_186 Rol Creado A5",
                "nivel": Role.NIVEL_OPERARIO,
                "activo": "on",
            },
        )
        assert response.status_code == 302
        assert Role.objects.filter(codigo="qa_e2e_a5_crear").exists()

    def test_crear_rol_codigo_duplicado_falla(self, admin_client):
        Role.objects.create(codigo="qa_e2e_a5_dup", nombre="X", nivel=Role.NIVEL_OPERARIO)
        response = admin_client.post(
            "/parametrizacion/roles/crear/",
            {
                "codigo": "qa_e2e_a5_dup",
                "nombre": "Y",
                "nivel": Role.NIVEL_OPERARIO,
                "activo": "on",
            },
        )
        assert response.status_code == 200  # re-renderiza el form con error
        assert Role.objects.filter(codigo="qa_e2e_a5_dup").count() == 1

    def test_editar_rol_codigo_readonly(self, admin_client):
        role = Role.objects.create(
            codigo="qa_e2e_a5_edit", nombre="Antes", nivel=Role.NIVEL_OPERARIO
        )
        response = admin_client.post(
            f"/parametrizacion/roles/{role.pk}/editar/",
            {
                "codigo": "qa_e2e_a5_edit_HACKEADO",  # form.codigo está disabled -- se ignora
                "nombre": "Despues",
                "nivel": Role.NIVEL_ADMIN,
                "activo": "on",
            },
        )
        assert response.status_code == 302
        role.refresh_from_db()
        assert role.codigo == "qa_e2e_a5_edit"  # no cambió
        assert role.nombre == "Despues"
        assert role.nivel == Role.NIVEL_ADMIN

    def test_inactivar_rol_toggle(self, admin_client):
        role = Role.objects.create(
            codigo="qa_e2e_a5_inact", nombre="X", nivel=Role.NIVEL_OPERARIO, activo=True
        )
        response = admin_client.post(f"/parametrizacion/roles/{role.pk}/inactivar/")
        assert response.status_code == 302
        role.refresh_from_db()
        assert role.activo is False

        # Segundo toggle reactiva
        response2 = admin_client.post(f"/parametrizacion/roles/{role.pk}/inactivar/")
        assert response2.status_code == 302
        role.refresh_from_db()
        assert role.activo is True


@pytest.mark.django_db
class TestRoleModuloPermisoMatriz186:
    def test_matriz_status_200(self, admin_client):
        response = admin_client.get("/parametrizacion/roles/matriz/")
        assert response.status_code == 200

    def test_matriz_incluye_columnas_modulo_y_submodulo(self, admin_client):
        response = admin_client.get("/parametrizacion/roles/matriz/")
        assert response.status_code == 200
        columnas_modulo = dict(response.context["columnas_modulo"])
        assert set(columnas_modulo.keys()) == {"MANTENIMIENTO", "CONSTRUCCION", "CONFIG"}
        columnas_sub = dict(response.context["columnas_submodulo"])
        assert "OBRA_CIVIL" in columnas_sub
        # A1 (id:instelec-186-submodulos-mantenimiento) suma las 4 hojas nuevas
        # de Mantenimiento a las 14 de Construccion ya existentes: 14 + 4 = 18.
        assert "MANTENIMIENTO_ACTIVIDADES" in columnas_sub
        # A2 (id:instelec-186-financiero-parent-modulo) suma 6 hojas de
        # Financiero + 5 de Configuracion, ambas bajo CONFIG: 18 + 11 = 29.
        assert "FIN_NOMINA" in columnas_sub
        assert "CONFIG_ROLES_PERMISOS" in columnas_sub
        assert len(columnas_sub) == 29

    def test_matriz_no_incluye_roles_inactivos(self, admin_client):
        Role.objects.create(
            codigo="qa_e2e_a5_matriz_inact", nombre="Inactivo", nivel=Role.NIVEL_OPERARIO,
            activo=False,
        )
        response = admin_client.get("/parametrizacion/roles/matriz/")
        codigos_en_matriz = [f["role"].codigo for f in response.context["filas"]]
        assert "qa_e2e_a5_matriz_inact" not in codigos_en_matriz

    @pytest.mark.parametrize(
        ("nivel", "clase_esperada"),
        [
            (RoleModuloPermiso.SIN_ACCESO, "bg-gray-100"),
            (RoleModuloPermiso.VER, "bg-blue-50"),
            (RoleModuloPermiso.VER_EDITAR, "bg-emerald-50"),
        ],
    )
    def test_matriz_distingue_visual_y_semanticamente_cada_nivel(
        self, admin_client, nivel, clase_esperada
    ):
        """Cada nivel usa un estado visual propio y expone el valor a lectores de pantalla."""
        role = Role.objects.create(
            codigo=f"qa_e2e_a2_{nivel}", nombre="Rol de prueba A2", nivel=Role.NIVEL_OPERARIO
        )
        RoleModuloPermiso.objects.create(
            role=role, modulo="MANTENIMIENTO", nivel_acceso=nivel
        )

        response = admin_client.get("/parametrizacion/roles/matriz/")
        body = response.content.decode("utf-8")

        assert f'data-access-level="{nivel}"' in body
        assert clase_esperada in body
        assert "aria-label=\"Nivel de acceso de Rol de prueba A2 para MANTENIMIENTO\"" in body

    def test_guardar_celda_modulo_crea_permiso(self, admin_client):
        role = Role.objects.create(
            codigo="qa_e2e_a5_celda_mod", nombre="X", nivel=Role.NIVEL_OPERARIO
        )
        response = admin_client.post(
            "/parametrizacion/roles/matriz/qa_e2e_a5_celda_mod/CONSTRUCCION/celda/",
            {"celda_qa_e2e_a5_celda_mod_CONSTRUCCION": "ver"},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200
        permiso = RoleModuloPermiso.objects.get(
            role=role, modulo="CONSTRUCCION", submodulo=""
        )
        assert permiso.nivel_acceso == "ver"

    def test_guardar_celda_htmx_devuelve_estilo_del_nivel_persistido(self, admin_client):
        """El reemplazo outerHTML conserva el estado visual tras cambiar a Ver y editar."""
        role = Role.objects.create(
            codigo="qa_e2e_a2_htmx", nombre="Rol HTMX A2", nivel=Role.NIVEL_OPERARIO
        )

        response = admin_client.post(
            "/parametrizacion/roles/matriz/qa_e2e_a2_htmx/CONSTRUCCION/celda/",
            {"celda_qa_e2e_a2_htmx_CONSTRUCCION": "ver_editar"},
            HTTP_HX_REQUEST="true",
        )

        body = response.content.decode("utf-8")
        assert response.status_code == 200
        assert 'data-access-level="ver_editar"' in body
        assert "bg-emerald-50" in body
        assert 'value="ver_editar" selected' in body

    def test_guardar_celda_submodulo_implica_modulo_construccion(self, admin_client):
        role = Role.objects.create(
            codigo="qa_e2e_a5_celda_sub", nombre="X", nivel=Role.NIVEL_OPERARIO
        )
        response = admin_client.post(
            "/parametrizacion/roles/matriz/qa_e2e_a5_celda_sub/OBRA_CIVIL/celda/",
            {"celda_qa_e2e_a5_celda_sub_OBRA_CIVIL": "ver_editar"},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200
        permiso = RoleModuloPermiso.objects.get(
            role=role, modulo=MODULO_CONSTRUCCION, submodulo="OBRA_CIVIL"
        )
        assert permiso.nivel_acceso == "ver_editar"

    def test_guardar_celda_invalida_cache_de_inmediato(self, admin_client):
        """Issue #186 (A3+A5): editar una celda debe reflejarse en la
        siguiente lectura de permissions.py SIN esperar el TTL de 1h --
        la señal post_save de RoleModuloPermiso invalida el cache."""
        from apps.usuarios.models import Usuario

        role = Role.objects.create(
            codigo="qa_e2e_a5_cache", nombre="X", nivel=Role.NIVEL_OPERARIO
        )
        user = Usuario(rol="qa_e2e_a5_cache", is_superuser=False, is_staff=False)

        # Antes de asignar permiso: sin acceso a CONSTRUCCION
        assert user_can_access_modulo(user, MODULO_CONSTRUCCION) is False

        # Prime el cache leyendo ANTES de guardar (para probar que sí invalida,
        # no que simplemente nunca se llenó)
        _ = user_can_access_modulo(user, MODULO_CONSTRUCCION)

        admin_client.post(
            f"/parametrizacion/roles/matriz/{role.codigo}/CONSTRUCCION/celda/",
            {f"celda_{role.codigo}_CONSTRUCCION": "ver"},
            HTTP_HX_REQUEST="true",
        )

        assert user_can_access_modulo(user, MODULO_CONSTRUCCION) is True

    def test_rol_nuevo_con_permiso_aparece_en_dropdown_usuarios(self, admin_client):
        """Cierra el círculo A5→A4: crear rol + asignar permiso vía matriz →
        aparece disponible para asignar a un usuario, sin deploy."""
        admin_client.post(
            "/parametrizacion/roles/crear/",
            {
                "codigo": "qa_e2e_a5_dropdown_final",
                "nombre": "QA_E2E_186 Encargado de Obra Civil",
                "nivel": Role.NIVEL_OPERARIO,
                "activo": "on",
            },
        )
        admin_client.post(
            "/parametrizacion/roles/matriz/qa_e2e_a5_dropdown_final/OBRA_CIVIL/celda/",
            {"celda_qa_e2e_a5_dropdown_final_OBRA_CIVIL": "ver"},
            HTTP_HX_REQUEST="true",
        )

        response = admin_client.get("/usuarios/gestion/crear/")
        assert response.status_code == 200
        codigos = [codigo for codigo, _nombre in response.context["roles"]]
        assert "qa_e2e_a5_dropdown_final" in codigos

        # Y el permiso quedó bien asignado
        role = Role.objects.get(codigo="qa_e2e_a5_dropdown_final")
        from apps.usuarios.models import Usuario

        user = Usuario(rol=role.codigo, is_superuser=False, is_staff=False)
        assert user_can_access_submodulo(user, "OBRA_CIVIL") is True
        assert user_can_access_modulo(user, MODULO_CONSTRUCCION) is False  # solo submodulo, no modulo completo


@pytest.mark.django_db
class TestEnforcementGranularA5:
    """Regresión A5 de rutas directas, incluidos GET y mutaciones HTMX.

    El rol ``admin`` es legacy y está sembrado por la migración real. El
    segundo rol es deliberadamente no-superuser: evita que el bypass global
    oculte una regresión de nivel ``ver`` frente a ``ver_editar``.
    """

    @pytest.fixture
    def legacy_admin(self, user_password):
        from apps.usuarios.models import Usuario

        assert Role.objects.get(codigo="admin").legacy is True
        return Usuario.objects.create_user(
            email="admin.legacy.186.a5@test.com",
            password=user_password,
            first_name="Admin",
            last_name="Legacy",
            rol="admin",
            is_superuser=False,
        )

    @pytest.fixture
    def restricted_user(self, user_password):
        from apps.usuarios.models import Usuario

        role = Role.objects.create(
            codigo="qa_186_a5_restringido",
            nombre="QA #186 restringido",
            nivel=Role.NIVEL_OPERARIO,
        )
        user = Usuario.objects.create_user(
            email="restringido.186.a5@test.com",
            password=user_password,
            first_name="QA",
            last_name="Restringido",
            rol=role.codigo,
            is_superuser=False,
        )
        return user, role

    @pytest.mark.parametrize(
        "path",
        ["/construccion/proyecto/", "/construccion/obra-civil/"],
    )
    def test_rol_legacy_real_conserva_get_y_post_de_construccion(self, legacy_admin, path):
        """Construcción mantiene el guard legacy previo a #186 para un rol real."""
        assert _rbac_response(legacy_admin, path).status_code == 204
        assert _rbac_response(legacy_admin, path, method="POST").status_code == 204

    @pytest.mark.parametrize(
        ("path", "submodulo"),
        [
            ("/actividades/programacion/", "MANTENIMIENTO_ACTIVIDADES"),
            ("/campo/procedimientos/", "MANTENIMIENTO_PROCEDIMIENTOS"),
            ("/financiero/nomina/", "FIN_NOMINA"),
            ("/financiero/presupuesto-real/", "FIN_PRESUPUESTO_REAL"),
        ],
    )
    def test_ver_permite_get_y_deniega_mutacion_directa_htmx(
        self, restricted_user, path, submodulo
    ):
        user, role = restricted_user
        RoleModuloPermiso.objects.create(
            role=role,
            modulo=MODULO_MANTENIMIENTO,
            submodulo=submodulo,
            nivel_acceso=RoleModuloPermiso.VER,
        )

        assert _rbac_response(user, path).status_code == 204
        # La navegación normal conserva redirect; HTMX usa HX-Redirect para
        # no reintroducir el loop que cubre test_issue_186_redirect_loop.py.
        assert _rbac_response(user, path, method="POST").status_code == 302
        htmx_response = _rbac_response(user, path, method="POST", htmx=True)
        assert htmx_response.status_code == 200
        assert htmx_response["HX-Redirect"] == "/"

    @pytest.mark.parametrize(
        ("path", "submodulo"),
        [
            ("/actividades/programacion/", "MANTENIMIENTO_ACTIVIDADES"),
            ("/campo/procedimientos/", "MANTENIMIENTO_PROCEDIMIENTOS"),
            ("/financiero/nomina/", "FIN_NOMINA"),
            ("/financiero/presupuesto-real/", "FIN_PRESUPUESTO_REAL"),
        ],
    )
    def test_ver_editar_permite_get_y_mutacion_directa(self, restricted_user, path, submodulo):
        user, role = restricted_user
        RoleModuloPermiso.objects.create(
            role=role,
            modulo=MODULO_MANTENIMIENTO,
            submodulo=submodulo,
            nivel_acceso=RoleModuloPermiso.VER_EDITAR,
        )

        assert _rbac_response(user, path).status_code == 204
        assert _rbac_response(user, path, method="POST").status_code == 204
        assert _rbac_response(user, path, method="POST", htmx=True).status_code == 204
