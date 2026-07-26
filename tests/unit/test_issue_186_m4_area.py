"""Issue #186 (186-M4) — campo Área en la persona + filtro en el listado de
Usuarios.

Pedido de Gabriel Valencia (reunión, documentada en el issue): al estar
"parado en la parte azul... de construcción" y buscar usuarios, no quiere
ver "todo ese listado de mantenimiento". Andrea confirmó que TODOS los
usuarios deben seguir existiendo en un único listado base (Financiero los
necesita a todos también) -- el filtro es SOLO de vista, no segmenta la BD.

Decisión de diseño del revisor (no se re-discute acá): el campo Área vive
en la PERSONA (`Usuario` para login, `PersonalCuadrilla` para colaboradores
de campo), NO en el Cargo -- cargos como "Liniero I"/"Conductor"/
"Supervisor" existen en ambas áreas. Catálogo compartido en
`apps.core.permissions.AREA_CHOICES` (Construcción/Mantenimiento/
Financiero), blank/null-friendly para no romper usuarios legacy.
"""

import pytest

from apps.core.permissions import AREA_CONSTRUCCION, AREA_FINANCIERO, AREA_MANTENIMIENTO
from tests.factories import AdminFactory


@pytest.fixture
def admin_client(client, user_password):
    admin = AdminFactory()
    client.login(username=admin.email, password=user_password)
    return client


@pytest.mark.django_db
class TestAreaModeloUsuario186M4:
    """El campo `area` existe en `Usuario`, es opcional y no rompe legacy."""

    def test_usuario_legacy_sin_area_default_vacio(self):
        """Edge case central del issue: un usuario legacy (creado antes de
        186-M4, sin área asignada) no debe fallar ni requerir el campo."""
        from apps.usuarios.models import Usuario

        user = Usuario.objects.create_user(
            email="legacy.sin.area.186m4@test.com",
            password="testpass123!",
            first_name="Legacy",
            last_name="SinArea",
            rol="liniero",
        )
        assert user.area == ""
        assert user.get_area_display() == ""

    def test_usuario_con_area_construccion(self):
        from apps.usuarios.models import Usuario

        user = Usuario.objects.create_user(
            email="con.area.186m4@test.com",
            password="testpass123!",
            first_name="Con",
            last_name="Area",
            rol="operario_construccion",
            area=AREA_CONSTRUCCION,
        )
        assert user.area == AREA_CONSTRUCCION
        assert user.get_area_display() == "Construcción"


@pytest.mark.django_db
class TestFiltroAreaListadoUsuarios186M4:
    """El listado de Usuarios (Parametrización) filtra DE VISTA por área."""

    def _crear(self, email, area, rol="operario_general"):
        from apps.usuarios.models import Usuario

        return Usuario.objects.create_user(
            email=email,
            password="testpass123!",
            first_name=email.split("@")[0],
            last_name="Test186M4",
            rol=rol,
            area=area,
        )

    def test_happy_filtrar_por_construccion_muestra_el_usuario(self, admin_client):
        self._crear("m4.construccion@test.com", AREA_CONSTRUCCION)
        self._crear("m4.mantenimiento@test.com", AREA_MANTENIMIENTO)

        response = admin_client.get("/usuarios/gestion/", {"area": AREA_CONSTRUCCION})
        assert response.status_code == 200
        emails = [u.email for u in response.context["usuarios"]]
        assert "m4.construccion@test.com" in emails

    def test_edge_filtrar_por_mantenimiento_no_muestra_construccion(self, admin_client):
        self._crear("m4.construccion2@test.com", AREA_CONSTRUCCION)
        self._crear("m4.mantenimiento2@test.com", AREA_MANTENIMIENTO)

        response = admin_client.get("/usuarios/gestion/", {"area": AREA_MANTENIMIENTO})
        assert response.status_code == 200
        emails = [u.email for u in response.context["usuarios"]]
        assert "m4.mantenimiento2@test.com" in emails
        assert "m4.construccion2@test.com" not in emails

    def test_edge_usuario_legacy_sin_area_aparece_sin_filtro(self, admin_client, liniero_user):
        """Requisito explícito del issue: probar contra >=1 usuario legacy
        real ya existente (fixture `liniero_user` de conftest.py, rol
        'liniero', SIN área asignada) -- debe seguir apareciendo en el
        listado completo sin filtro."""
        assert liniero_user.area == ""
        response = admin_client.get("/usuarios/gestion/")
        assert response.status_code == 200
        emails = [u.email for u in response.context["usuarios"]]
        assert liniero_user.email in emails

    def test_area_actual_vacio_por_default(self, admin_client):
        response = admin_client.get("/usuarios/gestion/")
        assert response.context["area_actual"] == ""

    def test_context_areas_incluye_las_3(self, admin_client):
        response = admin_client.get("/usuarios/gestion/")
        valores = [value for value, _label in response.context["areas"]]
        assert set(valores) == {AREA_CONSTRUCCION, AREA_MANTENIMIENTO, AREA_FINANCIERO}


@pytest.mark.django_db
class TestCrearYEditarUsuarioConArea186M4:
    def test_crear_usuario_admin_con_area(self, admin_client):
        from apps.usuarios.models import Usuario

        response = admin_client.post(
            "/usuarios/gestion/crear/",
            {
                "email": "creado.con.area.186m4@test.com",
                "first_name": "Creado",
                "last_name": "ConArea",
                "password": "clavesegura123",
                "rol": "coordinador",
                "area": AREA_FINANCIERO,
            },
        )
        assert response.status_code == 302
        user = Usuario.objects.get(email="creado.con.area.186m4@test.com")
        assert user.area == AREA_FINANCIERO

    def test_crear_usuario_admin_sin_area_no_rompe(self, admin_client):
        """Edge case: área es opcional al crear -- omitirla no debe fallar."""
        from apps.usuarios.models import Usuario

        response = admin_client.post(
            "/usuarios/gestion/crear/",
            {
                "email": "creado.sin.area.186m4@test.com",
                "first_name": "Creado",
                "last_name": "SinArea",
                "password": "clavesegura123",
                "rol": "coordinador",
            },
        )
        assert response.status_code == 302
        user = Usuario.objects.get(email="creado.sin.area.186m4@test.com")
        assert user.area == ""

    def test_editar_usuario_actualiza_area(self, admin_client):
        from apps.usuarios.models import Usuario

        user = Usuario.objects.create_user(
            email="editar.area.186m4@test.com",
            password="testpass123!",
            first_name="Editar",
            last_name="Area",
            rol="coordinador",
        )
        response = admin_client.post(
            f"/usuarios/gestion/{user.pk}/editar/",
            {
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "rol": user.rol,
                "telefono": "",
                "documento": "",
                "cargo": "",
                "is_active": "true",
                "area": AREA_CONSTRUCCION,
            },
        )
        assert response.status_code == 302
        user.refresh_from_db()
        assert user.area == AREA_CONSTRUCCION


@pytest.mark.django_db
class TestAreaModeloPersonalCuadrilla186M4:
    """Mismo campo `area`, migración aparte, en PersonalCuadrilla (issue #186 M4)."""

    @pytest.fixture(autouse=True)
    def _cargo_liniero_i(self):
        """`rol_cuadrilla` es FK(Cargo, to_field='codigo') PROTECT -- el
        default 'LINIERO_I' del modelo exige que la fila exista (no hay
        seed global de Cargo en tests, ver tests/factories/cuadrillas.py)."""
        from apps.cuadrillas.models import Cargo

        Cargo.objects.get_or_create(
            codigo="LINIERO_I", defaults={"nombre": "Liniero I", "activo": True}
        )

    def test_personal_cuadrilla_legacy_sin_area(self):
        from apps.cuadrillas.models_base import PersonalCuadrilla

        colaborador = PersonalCuadrilla.objects.create(
            nombre="Colaborador Legacy 186M4",
            documento="qa-e2e-186m4-legacy",
        )
        assert colaborador.area == ""

    def test_personal_cuadrilla_con_area(self):
        from apps.cuadrillas.models_base import PersonalCuadrilla

        colaborador = PersonalCuadrilla.objects.create(
            nombre="Colaborador Con Area 186M4",
            documento="qa-e2e-186m4-con-area",
            area=AREA_MANTENIMIENTO,
        )
        assert colaborador.area == AREA_MANTENIMIENTO
        assert colaborador.get_area_display() == "Mantenimiento"

    def test_form_personal_cuadrilla_acepta_area(self):
        from apps.cuadrillas.forms_personal import PersonalCuadrillaForm

        form = PersonalCuadrillaForm(
            data={
                "nombre": "Colaborador Form 186M4",
                "documento": "qa-e2e-186m4-form",
                "rol_cuadrilla": "LINIERO_I",
                "area": AREA_CONSTRUCCION,
                "salario_base": "0",
            }
        )
        assert form.is_valid(), form.errors
        colaborador = form.save()
        assert colaborador.area == AREA_CONSTRUCCION
