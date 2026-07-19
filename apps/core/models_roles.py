"""RBAC dinámico — catálogo editable de roles/permisos (issue #186).

NEW MODELS GO IN A NEW FILE (convención del repo, ver
apps/cuadrillas/models_cargo.py, precedente issue #176) — re-exportado en
apps/core/models.py.

`Role` reemplaza el `Usuario.Rol` TextChoices hardcodeado como fuente de
verdad para PERMISOS (el campo `Usuario.rol` en sí sigue siendo un
CharField, ver PLAN §1 — no se convierte a FK esta sesión, menor blast
radius con RBACModuloMiddleware, que corre en CADA request).

`codigo` debe coincidir EXACTAMENTE con los valores de `Usuario.rol`. NO
renombrar el `codigo` de un rol en uso sin coordinar con el dropdown de
asignación de usuarios (apps/usuarios/views.py, A4).
"""

from django.db import models
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.core.models import BaseModel


class Role(BaseModel):
    """Catálogo editable de roles/cargos (issue #186)."""

    NIVEL_ADMIN = "admin"
    NIVEL_OPERARIO = "operario"
    NIVEL_CHOICES = [
        (NIVEL_ADMIN, "Administrador"),
        (NIVEL_OPERARIO, "Operario"),
    ]

    codigo = models.CharField("Código", max_length=30, unique=True)
    nombre = models.CharField("Nombre", max_length=100)
    nivel = models.CharField("Nivel", max_length=10, choices=NIVEL_CHOICES)
    # 7 roles RBAC v2 (#44) vs 8 legacy — ver Usuario.Rol en apps/usuarios/models.py.
    legacy = models.BooleanField("Legacy", default=False)
    activo = models.BooleanField("Activo", default=True)

    class Meta:
        db_table = "roles"
        verbose_name = "Rol"
        verbose_name_plural = "Roles"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"


class RoleModuloPermiso(BaseModel):
    """Permiso de un `Role` sobre un módulo (y, opcionalmente, sub-módulo de
    CONSTRUCCION).

    Una fila con `submodulo=''` (string vacío, NO NULL -- ver nota abajo) =
    permiso a nivel de MÓDULO completo (MANTENIMIENTO/CONSTRUCCION/CONFIG).
    Una fila con `submodulo` no vacío afina el acceso dentro de CONSTRUCCION
    (obra civil, montaje, etc. — ver `TODOS_SUBMODULOS` en
    `apps.core.permissions`). La AUSENCIA de una fila para un
    módulo/submódulo dado equivale a `sin_acceso` (no se crean filas
    explícitas de `sin_acceso` en la migración de datos, ver 0002).

    Nota A6 (hallazgo de hardening): `submodulo` usa `default=''` en vez de
    `null=True` A PROPÓSITO -- Postgres trata cada NULL como distinto de
    cualquier otro NULL para efectos de `UNIQUE`/`unique_together`, así que
    con `null=True` dos filas (role, modulo, NULL) NO chocaban contra el
    constraint (confirmado con un test que falló: "DID NOT RAISE
    IntegrityError"). Con `''` como sentinel de "sin submódulo", el
    constraint sí protege la unicidad real. Los checks `if p.submodulo`/
    `if not p.submodulo` (permissions.py, views.py) no cambian: `''` es
    falsy igual que `None`.
    """

    SIN_ACCESO = "sin_acceso"
    VER = "ver"
    VER_EDITAR = "ver_editar"
    NIVEL_ACCESO_CHOICES = [
        (SIN_ACCESO, "Sin acceso"),
        (VER, "Ver"),
        (VER_EDITAR, "Ver y editar"),
    ]

    MODULO_MANTENIMIENTO = "MANTENIMIENTO"
    MODULO_CONSTRUCCION = "CONSTRUCCION"
    MODULO_CONFIG = "CONFIG"
    MODULO_CHOICES = [
        (MODULO_MANTENIMIENTO, "Mantenimiento"),
        (MODULO_CONSTRUCCION, "Construcción"),
        (MODULO_CONFIG, "Configuración"),
    ]

    role = models.ForeignKey(
        Role,
        to_field="codigo",
        db_column="role_codigo",
        on_delete=models.CASCADE,
        related_name="permisos",
    )
    modulo = models.CharField("Módulo", max_length=20, choices=MODULO_CHOICES)
    submodulo = models.CharField("Sub-módulo", max_length=40, blank=True, default="")
    nivel_acceso = models.CharField(
        "Nivel de acceso",
        max_length=12,
        choices=NIVEL_ACCESO_CHOICES,
        default=SIN_ACCESO,
    )

    class Meta:
        db_table = "role_modulo_permisos"
        unique_together = [("role", "modulo", "submodulo")]
        verbose_name = "Permiso de Rol"
        verbose_name_plural = "Permisos de Rol"
        ordering = ["role__nombre", "modulo", "submodulo"]

    def __str__(self):
        sub = f"/{self.submodulo}" if self.submodulo else ""
        return f"{self.role.codigo} → {self.modulo}{sub} ({self.nivel_acceso})"


# === Invalidación de cache (issue #186, A3) ===============================
# `apps.core.permissions._get_role_permisos` cachea por `Role.codigo`
# (RBACModuloMiddleware corre en CADA request -- ver PLAN §4). Estas señales
# garantizan que editar la matriz (A5) tenga efecto INMEDIATO, sin esperar
# el TTL de 1h. Import de `permissions` diferido (dentro del receiver) para
# evitar un ciclo de import a nivel de módulo con `permissions.py`.


@receiver(post_save, sender=Role)
@receiver(post_delete, sender=Role)
def _invalidar_cache_al_cambiar_role(sender, instance, **kwargs):
    from .permissions import invalidate_role_cache

    invalidate_role_cache(instance.codigo)


@receiver(post_save, sender=RoleModuloPermiso)
@receiver(post_delete, sender=RoleModuloPermiso)
def _invalidar_cache_al_cambiar_permiso(sender, instance, **kwargs):
    from .permissions import invalidate_role_cache

    # `instance.role_id` es el valor crudo de la columna FK -- con
    # to_field='codigo' eso ES el código del rol (no un UUID), ver
    # verificación manual en el commit de A1.
    invalidate_role_cache(instance.role_id)
