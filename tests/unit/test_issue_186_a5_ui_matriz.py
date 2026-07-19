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

from apps.core.models import Role, RoleModuloPermiso
from apps.core.permissions import (
    MODULO_CONSTRUCCION,
    user_can_access_modulo,
    user_can_access_submodulo,
)
from tests.factories import AdminFactory


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
        assert len(columnas_sub) == 14

    def test_matriz_no_incluye_roles_inactivos(self, admin_client):
        Role.objects.create(
            codigo="qa_e2e_a5_matriz_inact", nombre="Inactivo", nivel=Role.NIVEL_OPERARIO,
            activo=False,
        )
        response = admin_client.get("/parametrizacion/roles/matriz/")
        codigos_en_matriz = [f["role"].codigo for f in response.context["filas"]]
        assert "qa_e2e_a5_matriz_inact" not in codigos_en_matriz

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
            role=role, modulo="CONSTRUCCION", submodulo=None
        )
        assert permiso.nivel_acceso == "ver"

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
