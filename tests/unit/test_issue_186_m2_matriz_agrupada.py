"""Issue #186 (186-M2) — la matriz de Roles agrupa visualmente sus columnas
por módulo.

Antes: `templates/core/roles_matriz.html` pintaba las 3 columnas de módulo
(Mantenimiento/Construcción/Configuración) y luego los N sub-módulos de
Construcción en una sola fila de `<th>` plana, sin indicar a qué módulo
pertenece cada sub-módulo.

Después: thead de 2 filas -- fila 1 agrupa cada módulo con
`colspan="{{ N hojas de ese módulo + 1 }}"`; fila 2 expone el leaf "General"
(acceso al módulo completo) más las hojas que pertenecen a ese módulo.

No se tocó `_columnas_matriz()`/el contexto de la vista (`columnas_modulo`/
`columnas_submodulo` siguen siendo las mismas tuplas que ya cubre
`tests/unit/test_issue_186_a5_ui_matriz.py::TestRoleModuloPermisoMatriz186`)
-- este es un cambio puramente de template.
"""

import pytest

from apps.core.models import Role
from tests.factories import AdminFactory


@pytest.fixture
def admin_client(client, user_password):
    admin = AdminFactory()
    client.login(username=admin.email, password=user_password)
    return client


@pytest.mark.django_db
class TestMatrizRolesAgrupadaPorModulo186M2:
    def test_thead_agrupa_cada_modulo_con_sus_hojas_y_general(self, admin_client):
        """Cada padre tiene colspan = sus hojas reales + la columna General."""
        response = admin_client.get("/parametrizacion/roles/matriz/")
        assert response.status_code == 200
        body = response.content.decode("utf-8")
        for modulo, hojas in response.context["columnas_por_modulo"].items():
            assert f'colspan="{len(hojas) + 1}"' in body, (
                f"Falta el colspan agrupado de {modulo} en el thead"
            )

    def test_thead_muestra_los_3_modulos_y_leaf_general(self, admin_client):
        response = admin_client.get("/parametrizacion/roles/matriz/")
        body = response.content.decode("utf-8")
        for label in ["Mantenimiento", "Construcción", "Configuración", "General"]:
            assert label in body, f"Falta el label {label!r} en el thead de la matriz"

    def test_thead_incluye_labels_de_submodulo_anidados(self, admin_client):
        """Los sub-módulos (ej. Obra Civil) siguen renderizando su columna, ahora
        anidada bajo Construcción."""
        response = admin_client.get("/parametrizacion/roles/matriz/")
        body = response.content.decode("utf-8")
        for _codigo, etiqueta in response.context["columnas_submodulo"]:
            assert etiqueta in body, f"Falta el label de sub-módulo {etiqueta!r}"

    def test_rol_sin_ningun_submodulo_asignado_no_rompe_el_render(self, admin_client):
        """Edge case: un rol activo sin ninguna fila de RoleModuloPermiso (ni
        módulo ni sub-módulo) sigue renderizando -- todas sus celdas caen al
        default `sin_acceso`, sin romper colspan ni lanzar excepción."""
        Role.objects.create(
            codigo="qa_e2e_186_m2_sin_permisos",
            nombre="QA_E2E_186 Rol Sin Permisos",
            nivel=Role.NIVEL_OPERARIO,
            activo=True,
        )
        response = admin_client.get("/parametrizacion/roles/matriz/")
        assert response.status_code == 200
        body = response.content.decode("utf-8")
        assert "qa_e2e_186_m2_sin_permisos" in body
        # Cada celda de ese rol debe seguir siendo un <select> renderizado con
        # "Sin acceso" seleccionado por default (no una excepción de template).
        assert "Sin acceso" in body

    def test_admin_mantenimiento_legacy_sin_construccion_renderiza(self, admin_client):
        """Contra un rol LEGACY real ya sembrado (admin_mantenimiento) que NO
        tiene ningún sub-módulo de Construcción asignado (ver
        rbac_seed_data.ROL_SUBMODULOS) -- confirma que el gate no rompe con
        datos reales del catálogo, no solo un fixture nuevo."""
        response = admin_client.get("/parametrizacion/roles/matriz/")
        assert response.status_code == 200
        codigos = [f["role"].codigo for f in response.context["filas"]]
        assert "admin_mantenimiento" in codigos
        body = response.content.decode("utf-8")
        assert "admin_mantenimiento" in body
        # El catálogo legacy sin permiso explícito conserva el estado accesible
        # de falta de acceso, en lugar de depender solo del color.
        assert 'data-access-level="sin_acceso"' in body
        assert "bg-gray-100" in body
