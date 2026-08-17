"""#235 — `admin_bypass=False` vuelve `allowed_roles` autoritativo.

El bypass de `nivel=admin` hace que `allowed_roles` sea decorativo para 9 de
los 15 roles. Eso es aceptable en superficies operativas, pero no donde se
otorga privilegio. Estos tests fijan el límite en ambos sentidos: que el
opt-out realmente cierre, y que NO se haya cerrado de más.
"""
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.core.mixins import RoleRequiredMixin

Usuario = get_user_model()
PWD = "testpass123!"

SENSIBLES = [
    ("usuarios:gestion", {}),
    ("usuarios:reset_password", {}),
    ("core:roles_matriz", {}),
]


def _u(email, rol, **extra):
    u = Usuario.objects.create(
        email=email, rol=rol, documento=email[:10], first_name="N", last_name="A",
        is_active=True, **extra,
    )
    u.set_password(PWD)
    u.save()
    return u


@pytest.mark.django_db
@pytest.mark.parametrize("url_name,kwargs", SENSIBLES)
def test_rol_admin_de_area_no_entra_a_superficies_de_privilegio(client, url_name, kwargs):
    """`admin_mantenimiento` es nivel=admin: antes entraba por el bypass pese a
    no estar en ninguna de las listas declaradas."""
    client.force_login(_u("adminmant@test.com", "admin_mantenimiento", is_staff=True))
    resp = client.get(reverse(url_name, kwargs=kwargs))
    assert resp.status_code in (302, 403), (
        f"{url_name}: un rol admin de área NO declarado sigue entrando"
    )


@pytest.mark.django_db
@pytest.mark.parametrize("url_name,kwargs", SENSIBLES)
def test_rol_admin_declarado_conserva_el_acceso(client, url_name, kwargs):
    """El rol `admin` SÍ está declarado en las 3: no debe perder nada.
    (En prod son 9 usuarios activos — este es el caso que no se puede romper.)"""
    client.force_login(_u("admin235@test.com", "admin", is_staff=True))
    resp = client.get(reverse(url_name, kwargs=kwargs))
    assert resp.status_code == 200, f"{url_name}: se cerró de más, `admin` quedó afuera"


@pytest.mark.django_db
def test_superusuario_nunca_queda_afuera(client):
    client.force_login(_u("su235@test.com", "admin", is_superuser=True, is_staff=True))
    assert client.get(reverse("usuarios:gestion")).status_code == 200


@pytest.mark.django_db
def test_superficie_operativa_conserva_el_bypass():
    """El opt-out es puntual: una vista que NO lo declara sigue con el bypass
    intacto. Es lo que evita romper las otras 283 vistas del portafolio.

    Se prueba contra el mixin directamente y no vía URL: cualquier ruta real
    pasa además por `RBACModuloMiddleware`, cuyo veredicto (módulo del rol)
    es independiente de lo que se está midiendo acá.
    """
    class VistaOperativa(RoleRequiredMixin):
        allowed_roles = ['admin', 'director']   # admin_mantenimiento NO está

    v = VistaOperativa()

    class _U:
        is_authenticated = True
        is_superuser = False
        is_admin = False
        rol = "admin_mantenimiento"

    class _R:
        user = _U()

    v.request = _R()
    assert v.test_func() is True, "el bypass se desactivó donde no correspondía"


def test_bypass_desactivado_con_lista_vacia_falla_cerrado():
    """Guardarraíl: `admin_bypass=False` + `allowed_roles=[]` no debe abrir la
    vista a cualquier autenticado (sería el peor de los dos mundos)."""
    class VistaMalConfigurada(RoleRequiredMixin):
        admin_bypass = False
        allowed_roles = []

    v = VistaMalConfigurada()

    class _U:
        is_authenticated = True
        is_superuser = False
        is_admin = False
        rol = "liniero"

    class _R:
        user = _U()

    v.request = _R()
    assert v.test_func() is False
