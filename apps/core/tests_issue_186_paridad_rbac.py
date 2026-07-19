"""Gate de Paridad de Acceso — issue #186 §3 (OBLIGATORIO, impuesto por Miguel).

Compara, para los roles legacy existentes, el resultado del sistema VIEJO
(dicts hardcodeados de `apps/core/permissions.py`, ANTES de que A3 los
elimine) contra el sistema NUEVO (funciones BD-backed post A3:
`user_can_access_modulo`, `user_es_admin`, `user_can_access_submodulo`
leyendo `Role`/`RoleModuloPermiso`). Cualquier diferencia = bug de mapeo de
la migración de datos (`0002_seed_roles_permisos.py`) = BLOQUEANTE — no se
puede deployar. Si algo falla, se corrige el `RunPython` de la migración,
NUNCA este test.

Snapshot congelado: `apps/core/rbac_seed_data.py` (`_LEGACY_ROL_*_SNAPSHOT`
abajo) es una copia VERBATIM de `ROL_MODULOS`/`ROL_NIVEL`/`ROL_SUBMODULOS`
tomada el 2026-07-18, ANTES de tocar `permissions.py`. Es también la fuente
de datos de la migración 0002 — centralizado en un único módulo (no
transcrito dos veces) para que migración y test NUNCA puedan divergir por
un error de copiado (ver docstring de `rbac_seed_data.py`).

Nota sobre el conteo de roles: el plan de F2 dice "14 roles x 3 módulos x 14
submódulos x nivel-admin (252 aserciones/rol)". El conteo REAL de
`Usuario.Rol.choices` es **15** (7 RBAC v2 + 8 legacy) — se testean los 15,
no 14 (dejar 1 rol legacy sin cubrir sería precisamente el tipo de bug de
paridad silenciosa que este gate busca atrapar). La aritmética correcta es
3 (módulo) + 14 (submódulo) + 1 (nivel/admin) = 18 aserciones POR rol × 15
roles = **270 aserciones totales** (no 252 — 252 sale de 18×14, el conteo
de roles equivocado de F2).

Verificación adicional contra BD prod real (requisito de A2, "≥1 usuario
legacy real de BD prod, no solo fixture"): confirmado 2026-07-18 vía proxy
Cloud SQL (127.0.0.1:5434, instelec_db) que los roles REALMENTE en uso en
prod son {liniero: 90, auxiliar: 30, operario_general: 18, admin: 8,
supervisor: 2, admin_general: 1} — los 6 están cubiertos 1:1 en
`rbac_seed_data.ROLES` con el mapeo correcto. El usuario QA
`qa_claude@instelec.com` tiene hoy `rol='admin_general'` en prod (RBAC v2,
NO 'admin' legacy como asume el CLAUDE.md del repo) — mismo nivel de acceso
resultante (MANTENIMIENTO+CONSTRUCCION+CONFIG), no afecta este gate pero se
documenta para A7 (journey de cierre).
"""

import pytest

from apps.core import rbac_seed_data as _snap
from apps.core.models import Role
from apps.core.permissions import (
    user_can_access_modulo,
    user_can_access_submodulo,
    user_es_admin,
)
from tests.factories.usuarios import UsuarioFactory

# === Snapshot congelado — NO actualizar aunque cambie el catálogo BD ===
# (copiado 1:1 desde apps/core/rbac_seed_data.py, que a su vez es una
# transcripción verbatim de apps/core/permissions.py líneas 15-33/36-53/124-145)
_LEGACY_ROL_MODULOS_SNAPSHOT = _snap.ROL_MODULOS
_LEGACY_ROL_NIVEL_SNAPSHOT = _snap.ROL_NIVEL
_LEGACY_ROL_SUBMODULOS_SNAPSHOT = _snap.ROL_SUBMODULOS

_MODULOS = [_snap.MODULO_MANTENIMIENTO, _snap.MODULO_CONSTRUCCION, _snap.MODULO_CONFIG]
_SUBMODULOS = sorted(_snap.TODOS_SUBMODULOS)
_TODOS_LOS_CODIGOS = _snap.TODOS_LOS_CODIGOS


@pytest.fixture(autouse=True)
def _roles_seeded_en_bd(db):
    """El seed real ya corre una vez por sesión (ver `conftest.py::
    django_db_setup`) -- este fixture es un no-op idempotente (get_or_create)
    que deja el test file auto-explicativo/self-contained si se corre en
    aislamiento; no duplica datos."""
    _snap.seed_roles_permisos_bd()


def _usuario_con_rol(codigo_rol):
    """Usuario NO guardado (build, no create) con el rol dado.

    `is_superuser=False`/`is_staff=False` explícitos: algunas factories
    (AdminFactory) fuerzan `is_superuser=True`, lo que activaría el bypass
    de superuser en ambos sistemas (viejo y nuevo) y dejaría de probar la
    resolución real por `codigo` — acá se instancia `Usuario` directo
    (vía UsuarioFactory.build) para los 15 códigos, no las subclases.
    """
    return UsuarioFactory.build(rol=codigo_rol, is_superuser=False, is_staff=False)


@pytest.mark.django_db
class TestGateDeParidadAccesoRBAC186:
    """270 aserciones (18/rol x 15 roles) — VIEJO (dicts) vs NUEVO (BD)."""

    @pytest.mark.parametrize("codigo_rol", _TODOS_LOS_CODIGOS)
    def test_paridad_modulos(self, codigo_rol):
        user = _usuario_con_rol(codigo_rol)
        for modulo in _MODULOS:
            viejo = modulo in _LEGACY_ROL_MODULOS_SNAPSHOT.get(codigo_rol, set())
            nuevo = user_can_access_modulo(user, modulo)
            assert viejo == nuevo, (
                f"PARIDAD ROTA -- rol={codigo_rol} modulo={modulo}: viejo={viejo} nuevo={nuevo}"
            )

    @pytest.mark.parametrize("codigo_rol", _TODOS_LOS_CODIGOS)
    def test_paridad_nivel_admin(self, codigo_rol):
        user = _usuario_con_rol(codigo_rol)
        viejo = _LEGACY_ROL_NIVEL_SNAPSHOT.get(codigo_rol) == _snap.NIVEL_ADMIN
        nuevo = user_es_admin(user)
        assert viejo == nuevo, (
            f"PARIDAD ROTA -- rol={codigo_rol} nivel/admin: viejo={viejo} nuevo={nuevo}"
        )

    @pytest.mark.parametrize("codigo_rol", _TODOS_LOS_CODIGOS)
    def test_paridad_submodulos(self, codigo_rol):
        user = _usuario_con_rol(codigo_rol)
        for submodulo in _SUBMODULOS:
            viejo = submodulo in _LEGACY_ROL_SUBMODULOS_SNAPSHOT.get(codigo_rol, set())
            nuevo = user_can_access_submodulo(user, submodulo)
            assert viejo == nuevo, (
                f"PARIDAD ROTA -- rol={codigo_rol} submodulo={submodulo}: "
                f"viejo={viejo} nuevo={nuevo}"
            )

    def test_role_objects_count_15(self):
        """Requisito A2: Role.objects.count() tras seed. F2 dijo 14 -- el
        conteo real de Usuario.Rol.choices es 15, ver docstring del módulo."""
        assert Role.objects.count() == len(_snap.ROLES) == 15
