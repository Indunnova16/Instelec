"""Regresiones A4: la matriz conserva el padre real de cada hoja RBAC."""

import pytest

from apps.core.models import Role, RoleModuloPermiso
from apps.core.permissions import MODULO_CONFIG, MODULO_MANTENIMIENTO
from tests.factories import AdminFactory


@pytest.fixture
def admin_client(client, user_password):
    admin = AdminFactory()
    client.login(username=admin.email, password=user_password)
    return client


@pytest.mark.django_db
class TestMatrizPadresA4:
    def test_agrupa_hojas_bajo_su_modulo_real_y_congela_panes(self, admin_client):
        response = admin_client.get("/parametrizacion/roles/matriz/")
        assert response.status_code == 200
        grupos = response.context["columnas_por_modulo"]
        assert ("MANTENIMIENTO_ACTIVIDADES", "Mantenimiento Actividades") in grupos[MODULO_MANTENIMIENTO]
        assert ("CONFIG_ROLES_PERMISOS", "Config Roles Permisos") in grupos[MODULO_CONFIG]
        body = response.content.decode()
        assert f'colspan="{len(grupos[MODULO_MANTENIMIENTO]) + 1}"' in body
        assert "sticky top-0 left-0 z-30" in body
        assert "sticky left-0 z-10" in body

    @pytest.mark.parametrize(
        ("submodulo", "modulo"),
        [
            ("MANTENIMIENTO_ACTIVIDADES", MODULO_MANTENIMIENTO),
            ("CONFIG_ROLES_PERMISOS", MODULO_CONFIG),
        ],
    )
    def test_guardar_hoja_usa_su_padre_real(self, admin_client, submodulo, modulo):
        role = Role.objects.create(
            codigo=f"qa_186_a4_{submodulo.lower()}", nombre="QA A4", nivel=Role.NIVEL_OPERARIO
        )
        response = admin_client.post(
            f"/parametrizacion/roles/matriz/{role.codigo}/{submodulo}/celda/",
            {f"celda_{role.codigo}_{submodulo}": "ver"}, HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200
        assert RoleModuloPermiso.objects.filter(role=role, modulo=modulo, submodulo=submodulo).exists()
        assert not RoleModuloPermiso.objects.filter(
            role=role, modulo="CONSTRUCCION", submodulo=submodulo
        ).exists()

    def test_columna_desconocida_no_crea_permiso_bajo_construccion(self, admin_client):
        role = Role.objects.create(codigo="qa_186_a4_invalida", nombre="QA A4", nivel=Role.NIVEL_OPERARIO)
        response = admin_client.post(
            f"/parametrizacion/roles/matriz/{role.codigo}/NO_EXISTE/celda/",
            {f"celda_{role.codigo}_NO_EXISTE": "ver"}, HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 404
        assert not RoleModuloPermiso.objects.filter(role=role).exists()
