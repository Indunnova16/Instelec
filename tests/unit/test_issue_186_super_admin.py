"""Security contract for Instelec#186 A3: the Super Admin toggle."""

import pytest
from django.urls import reverse

from apps.core.mixins import RoleRequiredMixin
from apps.usuarios.forms import UsuarioChangeForm
from tests.factories import AdminFactory, UsuarioFactory


def _edit_data(user, **overrides):
    data = {
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'rol': user.rol,
        'telefono': user.telefono or '',
        'documento': user.documento or '',
        'cargo': user.cargo or '',
        'is_active': 'true' if user.is_active else 'false',
        'area': user.area or '',
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
class TestSuperAdminToggle186:
    def test_super_admin_can_grant_and_revoke_another_user(self, client, user_password):
        actor = AdminFactory()
        target = UsuarioFactory(is_superuser=False)
        client.login(username=actor.email, password=user_password)
        url = reverse('usuarios:editar_usuario', kwargs={'pk': target.pk})

        response = client.get(url)
        assert response.status_code == 200
        assert b'Super Admin' in response.content

        response = client.post(url, _edit_data(target, is_superuser='true'))
        target.refresh_from_db()
        assert response.status_code == 302
        assert target.is_superuser is True

        response = client.post(url, _edit_data(target, is_superuser='false'))
        target.refresh_from_db()
        assert response.status_code == 302
        assert target.is_superuser is False

    def test_non_superuser_cannot_see_or_forge_the_toggle(self, client, user_password):
        actor = UsuarioFactory(rol='admin', is_superuser=False, is_staff=True)
        target = UsuarioFactory(is_superuser=False)
        client.login(username=actor.email, password=user_password)
        url = reverse('usuarios:editar_usuario', kwargs={'pk': target.pk})

        response = client.get(url)
        assert response.status_code == 200
        assert b'Super Admin' not in response.content

        response = client.post(url, _edit_data(target, is_superuser='true'))
        target.refresh_from_db()
        assert response.status_code == 302
        assert target.is_superuser is False

    def test_super_admin_cannot_elevate_themself(self, client, user_password):
        actor = AdminFactory()
        client.login(username=actor.email, password=user_password)
        url = reverse('usuarios:editar_usuario', kwargs={'pk': actor.pk})

        response = client.get(url)
        assert response.status_code == 200
        assert b'Super Admin' not in response.content

        response = client.post(url, _edit_data(actor, is_superuser='false'))
        actor.refresh_from_db()
        assert response.status_code == 302
        assert actor.is_superuser is True

    def test_cannot_revoke_the_last_super_admin(self, client, user_password):
        target = AdminFactory()
        # The UI never lets a Super Admin revoke themself, so this safety
        # branch is tested at the form boundary with an authenticated-style,
        # unsaved actor.  Target is the sole persisted Super Admin.
        actor = type('Actor', (), {'is_superuser': True})()
        form = UsuarioChangeForm(
            data=_edit_data(target, is_superuser='false'),
            instance=target,
            actor=actor,
        )

        assert form.is_valid() is False
        target.refresh_from_db()
        assert target.is_superuser is True
        assert 'No se puede retirar Super Admin al último Super Admin del sistema.' in form.errors['is_superuser']

    def test_granted_super_admin_bypasses_role_restrictions(self):
        user = UsuarioFactory(rol='operario_general', is_superuser=True)

        class RestrictedView(RoleRequiredMixin):
            allowed_roles = ['director']

        view = RestrictedView()
        view.request = type('Request', (), {'user': user})()
        assert view.test_func() is True
