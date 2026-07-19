"""Unit tests CRUD Role/RoleModuloPermiso -- issue #186, A6.

Complementa A1 (verificado manualmente vía shell en su momento) y A5 (CRUD
vía las vistas HTTP) con tests directos sobre el ORM: constraints, cascade
delete, y la invalidación de cache por señal (A3) disparada por
`Role.save()`/`.delete()` y `RoleModuloPermiso.save()`/`.delete()`
directos -- no solo a través del endpoint HTTP de la matriz (A5).
"""

import pytest
from django.db import IntegrityError

from apps.core.models import Role, RoleModuloPermiso
from apps.core.permissions import (
    MODULO_CONSTRUCCION,
    _get_role_permisos,
    user_can_access_modulo,
    user_es_admin,
)
from apps.usuarios.models import Usuario


@pytest.mark.django_db
class TestRoleModelCRUD:
    def test_crear_role_basico(self):
        role = Role.objects.create(
            codigo="qa_e2e_a6_basico", nombre="QA A6", nivel=Role.NIVEL_OPERARIO
        )
        assert role.activo is True  # default
        assert role.legacy is False  # default
        assert str(role) == "qa_e2e_a6_basico - QA A6"

    def test_codigo_unique(self):
        Role.objects.create(codigo="qa_e2e_a6_unique", nombre="A", nivel=Role.NIVEL_OPERARIO)
        with pytest.raises(IntegrityError):
            Role.objects.create(codigo="qa_e2e_a6_unique", nombre="B", nivel=Role.NIVEL_ADMIN)

    def test_update_role(self):
        role = Role.objects.create(
            codigo="qa_e2e_a6_update", nombre="Antes", nivel=Role.NIVEL_OPERARIO
        )
        role.nombre = "Despues"
        role.nivel = Role.NIVEL_ADMIN
        role.save()
        role.refresh_from_db()
        assert role.nombre == "Despues"
        assert role.nivel == Role.NIVEL_ADMIN

    def test_delete_role(self):
        role = Role.objects.create(codigo="qa_e2e_a6_delete", nombre="X", nivel=Role.NIVEL_OPERARIO)
        pk = role.pk
        role.delete()
        assert not Role.objects.filter(pk=pk).exists()


@pytest.mark.django_db
class TestRoleModuloPermisoModelCRUD:
    def test_crear_permiso_modulo(self):
        role = Role.objects.create(codigo="qa_e2e_a6_perm1", nombre="X", nivel=Role.NIVEL_OPERARIO)
        permiso = RoleModuloPermiso.objects.create(
            role=role, modulo=MODULO_CONSTRUCCION, nivel_acceso=RoleModuloPermiso.VER
        )
        assert permiso.submodulo == ""
        assert str(permiso) == f"qa_e2e_a6_perm1 → {MODULO_CONSTRUCCION} (ver)"

    def test_fk_to_field_codigo_guarda_el_codigo_no_uuid(self):
        """A1: FK to_field='codigo' -- la columna cruda (role_id, el nombre
        que Django genera para el campo `role`) debe contener el CÓDIGO del
        rol (string), NO el UUID pk de Role."""
        role = Role.objects.create(codigo="qa_e2e_a6_fk", nombre="X", nivel=Role.NIVEL_OPERARIO)
        permiso = RoleModuloPermiso.objects.create(role=role, modulo=MODULO_CONSTRUCCION)
        assert permiso.role_id == "qa_e2e_a6_fk"
        assert permiso.role_id != str(role.pk)

    def test_unique_together_role_modulo_submodulo(self):
        role = Role.objects.create(codigo="qa_e2e_a6_perm2", nombre="X", nivel=Role.NIVEL_OPERARIO)
        RoleModuloPermiso.objects.create(role=role, modulo=MODULO_CONSTRUCCION, submodulo="")
        with pytest.raises(IntegrityError):
            RoleModuloPermiso.objects.create(role=role, modulo=MODULO_CONSTRUCCION, submodulo="")

    def test_mismo_modulo_distinto_submodulo_no_choca(self):
        role = Role.objects.create(codigo="qa_e2e_a6_perm3", nombre="X", nivel=Role.NIVEL_OPERARIO)
        RoleModuloPermiso.objects.create(role=role, modulo=MODULO_CONSTRUCCION, submodulo="")
        # No debe lanzar -- mismo modulo, submodulo distinto (uno '', otro 'OBRA_CIVIL')
        RoleModuloPermiso.objects.create(
            role=role, modulo=MODULO_CONSTRUCCION, submodulo="OBRA_CIVIL"
        )
        assert role.permisos.count() == 2

    def test_cascade_delete_role_borra_sus_permisos(self):
        role = Role.objects.create(codigo="qa_e2e_a6_cascade", nombre="X", nivel=Role.NIVEL_OPERARIO)
        RoleModuloPermiso.objects.create(role=role, modulo=MODULO_CONSTRUCCION)
        RoleModuloPermiso.objects.create(role=role, modulo=MODULO_CONSTRUCCION, submodulo="OBRA_CIVIL")
        assert RoleModuloPermiso.objects.filter(role=role).count() == 2

        role.delete()
        assert RoleModuloPermiso.objects.filter(role_id="qa_e2e_a6_cascade").count() == 0

    def test_default_nivel_acceso_es_sin_acceso(self):
        role = Role.objects.create(codigo="qa_e2e_a6_default", nombre="X", nivel=Role.NIVEL_OPERARIO)
        permiso = RoleModuloPermiso.objects.create(role=role, modulo=MODULO_CONSTRUCCION)
        assert permiso.nivel_acceso == RoleModuloPermiso.SIN_ACCESO


@pytest.mark.django_db
class TestInvalidacionCachePorSenalDirecta:
    """A3+A6: la invalidación de cache debe dispararse aunque el cambio NO
    pase por la vista HTTP de la matriz (A5) -- p.ej. Django admin, shell,
    o un futuro script de carga masiva."""

    def test_save_directo_de_permiso_invalida_cache(self):
        role = Role.objects.create(
            codigo="qa_e2e_a6_signal1", nombre="X", nivel=Role.NIVEL_OPERARIO
        )
        user = Usuario(rol="qa_e2e_a6_signal1", is_superuser=False, is_staff=False)

        assert user_can_access_modulo(user, MODULO_CONSTRUCCION) is False  # prime cache

        RoleModuloPermiso.objects.create(
            role=role, modulo=MODULO_CONSTRUCCION, nivel_acceso=RoleModuloPermiso.VER
        )
        assert user_can_access_modulo(user, MODULO_CONSTRUCCION) is True  # sin esperar TTL

    def test_delete_directo_de_permiso_invalida_cache(self):
        role = Role.objects.create(
            codigo="qa_e2e_a6_signal2", nombre="X", nivel=Role.NIVEL_OPERARIO
        )
        permiso = RoleModuloPermiso.objects.create(
            role=role, modulo=MODULO_CONSTRUCCION, nivel_acceso=RoleModuloPermiso.VER
        )
        user = Usuario(rol="qa_e2e_a6_signal2", is_superuser=False, is_staff=False)
        assert user_can_access_modulo(user, MODULO_CONSTRUCCION) is True  # prime cache

        permiso.delete()
        assert user_can_access_modulo(user, MODULO_CONSTRUCCION) is False

    def test_save_directo_de_role_invalida_cache_nivel(self):
        role = Role.objects.create(
            codigo="qa_e2e_a6_signal3", nombre="X", nivel=Role.NIVEL_OPERARIO
        )
        user = Usuario(rol="qa_e2e_a6_signal3", is_superuser=False, is_staff=False)
        assert user_es_admin(user) is False  # prime cache

        role.nivel = Role.NIVEL_ADMIN
        role.save()
        assert user_es_admin(user) is True

    def test_role_inactivo_no_es_leido_por_get_role_permisos(self):
        """activo=False -- _get_role_permisos debe tratarlo como inexistente
        (Role.objects.get(codigo=..., activo=True) filtra por eso)."""
        role = Role.objects.create(
            codigo="qa_e2e_a6_inactivo", nombre="X", nivel=Role.NIVEL_ADMIN, activo=True
        )
        RoleModuloPermiso.objects.create(role=role, modulo=MODULO_CONSTRUCCION, nivel_acceso="ver")

        role.activo = False
        role.save()  # dispara invalidación

        resultado = _get_role_permisos("qa_e2e_a6_inactivo")
        assert resultado == {"modulos": set(), "submodulos": set(), "nivel": None}

    def test_get_role_permisos_codigo_inexistente(self):
        resultado = _get_role_permisos("qa_e2e_a6_no_existe_nunca")
        assert resultado == {"modulos": set(), "submodulos": set(), "nivel": None}

    def test_get_role_permisos_codigo_vacio(self):
        assert _get_role_permisos("") == {"modulos": set(), "submodulos": set(), "nivel": None}
        assert _get_role_permisos(None) == {"modulos": set(), "submodulos": set(), "nivel": None}
