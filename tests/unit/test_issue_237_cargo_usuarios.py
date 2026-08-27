"""#237 — Gestión de Usuarios muestra el Cargo del maestro de Colaboradores."""

import pytest

from apps.cuadrillas.models import Cargo, PersonalCuadrilla
from apps.usuarios.models import Usuario
from tests.factories import AdminFactory


@pytest.fixture
def admin_client(client, user_password):
    admin = AdminFactory()
    client.login(username=admin.email, password=user_password)
    return client


def _usuario(documento, **kwargs):
    kwargs.setdefault("rol", "liniero")
    return Usuario.objects.create_user(
        email=f"{documento.lower()}@issue237.test",
        password="testpass123!",
        first_name="Usuario",
        last_name=documento,
        documento=documento,
        **kwargs,
    )


@pytest.mark.django_db
class TestCargoColaboradorEnGestionUsuarios:
    def test_usuario_asociado_muestra_nombre_del_cargo_del_maestro(self, admin_client):
        usuario = _usuario("LEGACY-237-001", cargo="Cargo legacy desactualizado")
        cargo = Cargo.objects.create(
            codigo="QA-237-SUP", nombre="Supervisor de Obras", activo=True
        )
        PersonalCuadrilla.objects.create(
            nombre="Colaborador asociado", documento=usuario.documento, rol_cuadrilla=cargo
        )

        response = admin_client.get("/usuarios/gestion/")

        assert response.status_code == 200
        usuarios = {usuario.email: usuario for usuario in response.context["usuarios"]}
        assert usuarios[usuario.email].cargo_colaborador == "Supervisor de Obras"
        assert "Supervisor de Obras" in response.content.decode()
        assert "Cargo legacy desactualizado" not in response.content.decode()

    def test_usuario_legacy_sin_colaborador_muestra_marcador_explicito(self, admin_client):
        usuario = _usuario("LEGACY-237-002", cargo="Cargo sin maestro")

        response = admin_client.get("/usuarios/gestion/")

        assert response.status_code == 200
        usuarios = {usuario.email: usuario for usuario in response.context["usuarios"]}
        assert usuarios[usuario.email].cargo_colaborador is None
        content = response.content.decode()
        assert "Sin colaborador asociado" in content
        assert "Cargo sin maestro" not in content

    def test_busqueda_y_filtro_rol_conservan_cargo_resuelto(self, admin_client):
        usuario_encontrado = _usuario("FILTRO-237-OK")
        usuario_excluido = _usuario("FILTRO-237-EXCLUIDO", rol="coordinador")
        cargo = Cargo.objects.create(codigo="QA-237-LIN", nombre="Liniero QA", activo=True)
        PersonalCuadrilla.objects.create(
            nombre="Colaborador filtrado",
            documento=usuario_encontrado.documento,
            rol_cuadrilla=cargo,
        )

        response = admin_client.get(
            "/usuarios/gestion/", {"buscar": "FILTRO-237", "rol": "liniero"}
        )

        assert response.status_code == 200
        usuarios = list(response.context["usuarios"])
        assert [usuario.email for usuario in usuarios] == [usuario_encontrado.email]
        assert usuarios[0].cargo_colaborador == "Liniero QA"
        assert usuario_excluido.email not in response.content.decode()
