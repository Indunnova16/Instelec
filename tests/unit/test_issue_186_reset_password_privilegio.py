"""Límite de privilegio en el reset de contraseña (#186, revisión adversarial).

`_generar_password_campo` produce una clave DERIVABLE de datos visibles en el
listado de usuarios (`documento` + 3 primeras letras del nombre). Eso es
deliberado para onboarding de personal de campo, pero convierte el reset en
una entrega de credenciales si se aplica a una cuenta privilegiada.

Agravante que hace esto explotable: `RoleRequiredMixin` deja pasar a CUALQUIER
rol de `nivel='admin'` ANTES de mirar `allowed_roles` (apps/core/mixins.py), o
sea 9 de 15 roles del sistema — no solo `admin`.
"""
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

Usuario = get_user_model()
PWD = "testpass123!"


def _usuario(email, rol, **extra):
    u = Usuario.objects.create(
        email=email, rol=rol, documento=extra.pop("documento", email[:10]),
        first_name=extra.pop("first_name", "Nombre"), last_name="Apellido",
        is_active=True, **extra,
    )
    u.set_password(PWD)
    u.save()
    return u


@pytest.mark.django_db
def test_rol_admin_no_superuser_no_puede_resetear_la_clave_del_superadmin(client):
    """La cadena de escalada: admin_construccion resetea al Super Admin, deduce
    la clave (documento + nombre[:3]) y entra como él."""
    superadmin = _usuario(
        "super@test.com", "admin", documento="0000000000",
        first_name="Admin", is_superuser=True, is_staff=True,
    )
    clave_original = superadmin.password
    atacante = _usuario("atacante@test.com", "admin_construccion", is_staff=True)

    client.force_login(atacante)
    resp = client.post(
        reverse("usuarios:reset_password"), data={"usuario_id": str(superadmin.pk)}
    )

    # Defensa en profundidad: desde #235 el atacante ni siquiera pasa el gate
    # (403/302, `admin_bypass=False` hace autoritativo el `allowed_roles`);
    # antes llegaba al handler y lo frenaba el chequeo sobre el objetivo. Lo
    # que se fija acá es el invariante, no por cuál de las dos capas cayó.
    assert resp.status_code in (302, 200, 403)
    superadmin.refresh_from_db()
    assert superadmin.password == clave_original, (
        "Un rol no-superusuario reseteó la contraseña del Super Admin: "
        "escalada directa a control total."
    )
    assert not superadmin.check_password("0000000000adm")


@pytest.mark.django_db
def test_superuser_si_puede_resetear_a_otro_administrativo(client):
    """El fix no debe romper el caso legítimo."""
    superadmin = _usuario(
        "super2@test.com", "admin", is_superuser=True, is_staff=True
    )
    objetivo = _usuario(
        "coord@test.com", "coordinador", documento="1234567890", first_name="Carlos"
    )

    client.force_login(superadmin)
    client.post(reverse("usuarios:reset_password"), data={"usuario_id": str(objetivo.pk)})

    objetivo.refresh_from_db()
    assert objetivo.check_password("1234567890car")


@pytest.mark.django_db
def test_reset_de_usuario_de_campo_sigue_funcionando(client):
    """El flujo real de onboarding (personal operativo) no se toca."""
    actor = _usuario("admin3@test.com", "admin", is_staff=True)
    liniero = _usuario(
        "liniero@test.com", "liniero", documento="9876543210", first_name="Pedro"
    )

    client.force_login(actor)
    client.post(reverse("usuarios:reset_password"), data={"usuario_id": str(liniero.pk)})

    liniero.refresh_from_db()
    assert liniero.check_password("9876543210ped")
