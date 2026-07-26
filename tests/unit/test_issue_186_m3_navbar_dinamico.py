"""Issue #186 (186-M3) — navbar dinámico según la matriz de permisos.

Regla acordada con el cliente: si un rol tiene 'Ver'/'Ver y editar' en un
sub-módulo de Construcción, su link aparece en el sidebar; si tiene 'Sin
acceso' (o no tiene fila -- ausencia = sin acceso), el link NO debe
aparecer. Antes, `templates/components/sidebar.html` mostraba Ingeniería/
Montaje/Obra Civil/etc. con lógica estática (solo gateados por el módulo
CONSTRUCCION completo), sin conectar a `user_can_access_submodulo()`
(`apps/core/permissions.py:175`).

Fix: cada item de la sección Construcción del sidebar ahora se envuelve en
`{% if %}` sobre el tag `puede_submodulo` (ya existía en `core_tags.py`
desde #62 pero nunca se había cableado en el sidebar).

Roles usados (BD-backed reales, NO superuser -- ver
`feedback_validar_role_gated_con_rol_real_no_superuser`, un superuser pasa
todo el gate y produciría un falso positivo):

  - `operario_construccion` (rbac_seed_data.ROL_SUBMODULOS): tiene
    OBRA_CIVIL/MONTAJE/SPT/TENDIDO/PROTECCIONES, pero NO INGENIERIA/
    PRELIMINARES/FINANCIERO/PROGRAMACION/ACTIVIDADES_FINALES/
    INDICADORES_CONSTRUCCION.
  - `admin_general` (nivel admin, TODOS_SUBMODULOS): regresión -- debe
    seguir viendo el menú completo de Construcción, exactamente como antes.
"""

import pytest
from django.urls import reverse


@pytest.fixture
def proyecto_construccion_186m3(db):
    from apps.construccion.models import ProyectoConstruccion
    from apps.contratos.models import Contrato

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo="CT-TEST-186M3",
        nombre="Contrato Navbar 186-M3",
        cliente="Cliente Test",
        estado=Contrato.Estado.ACTIVO,
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre="Proyecto Navbar 186-M3",
        estado="EJECUCION",
    )


@pytest.fixture
def operario_construccion_client(client, user_password):
    from apps.usuarios.models import Usuario

    user = Usuario.objects.create_user(
        email="operario.construccion.186m3@test.com",
        password=user_password,
        first_name="Operario",
        last_name="Construccion186M3",
        rol="operario_construccion",
    )
    assert user.is_superuser is False
    client.login(username=user.email, password=user_password)
    return client


@pytest.fixture
def admin_general_client(client, user_password):
    """Rol admin_general BD-backed, NO superuser -- ejercita el camino real
    de `_get_role_permisos()`/`Role.objects` (no el bypass de superuser)."""
    from apps.usuarios.models import Usuario

    user = Usuario.objects.create_user(
        email="admin.general.186m3@test.com",
        password=user_password,
        first_name="Admin",
        last_name="General186M3",
        rol="admin_general",
    )
    assert user.is_superuser is False
    client.login(username=user.email, password=user_password)
    return user, client


def _render_sidebar(test_client, proyecto):
    url = reverse("construccion:dashboard_obra_civil", kwargs={"proyecto_id": proyecto.id})
    resp = test_client.get(url)
    assert resp.status_code == 200, f"render falló: {resp.status_code}"
    return resp.content.decode("utf-8")


@pytest.mark.django_db
class TestNavbarDinamicoOperarioConstruccion186M3:
    """happy: operario_construccion ve los links de los sub-módulos que SÍ tiene."""

    @pytest.mark.parametrize(
        "label",
        [
            "Obra Civil",
            "Dashboard Obra Civil",
            "Obras de Protección",
            "Montaje",
            "Dashboard Montaje",
            "SPT y Pintura",
            "Tendido",
            "Dashboard Tendido",
        ],
    )
    def test_ve_los_submodulos_con_acceso(
        self, label, operario_construccion_client, proyecto_construccion_186m3
    ):
        body = _render_sidebar(operario_construccion_client, proyecto_construccion_186m3)
        assert label in body, f"operario_construccion debería ver {label!r} y no aparece"


@pytest.mark.django_db
class TestNavbarDinamicoOcultaSinAcceso186M3:
    """edge: operario_construccion NO ve los links de sub-módulos en 'Sin acceso'."""

    @pytest.mark.parametrize(
        "label",
        [
            "Ingeniería",
            "Actividades Preliminares",
            "Financiero",
            "Actividades Finales",
            "Indicadores en General",
            "Programación de Cuadrillas",
        ],
    )
    def test_no_ve_los_submodulos_sin_acceso(
        self, label, operario_construccion_client, proyecto_construccion_186m3
    ):
        body = _render_sidebar(operario_construccion_client, proyecto_construccion_186m3)
        assert label not in body, (
            f"operario_construccion NO debería ver {label!r} (Sin acceso) pero aparece en el sidebar"
        )


@pytest.mark.django_db
class TestNavbarDinamicoAdminGeneralSinRegresion186M3:
    """edge (no regresión): admin_general (nivel admin, TODOS_SUBMODULOS) sigue
    viendo el menú completo de Construcción, igual que antes del gate."""

    @pytest.mark.parametrize(
        "label",
        [
            "Ingeniería",
            "Actividades Preliminares",
            "Obra Civil",
            "Obras de Protección",
            "Montaje",
            "SPT y Pintura",
            "Tendido",
            "Financiero",
            "Actividades Finales",
            "Indicadores en General",
            "Programación de Cuadrillas",
        ],
    )
    def test_admin_general_ve_todo_el_menu(
        self, label, admin_general_client, proyecto_construccion_186m3
    ):
        _user, test_client = admin_general_client
        body = _render_sidebar(test_client, proyecto_construccion_186m3)
        assert label in body, (
            f"REGRESION: admin_general ya no ve {label!r} en el sidebar de Construcción"
        )
