# E2E gate del bloque ERP-Financiero (post #264) detectó que el link
# "Facturas de Gastos" no aparecía en el sidebar para el usuario admin recién
# desplegado el código, pese a que `0008_seed_fin_facturas_gastos_y_roles_248`
# y `0009_seed_modulo_completo_contador_gerente_financiero` sembraron
# correctamente las filas `RoleModuloPermiso` en BD (verificado por psql).
#
# Causa raíz: `_get_role_permisos()` (apps/core/permissions.py) cachea en
# Redis por 1h (`CACHE_TTL_ROLE_PERMISOS`), y su invalidación depende de
# `@receiver(post_save, sender=Role)` / `sender=RoleModuloPermiso`
# (apps/core/models_roles.py). Esos receivers están conectados a las clases
# CONCRETAS del app registry -- pero `RunPython` en una migración usa
# `apps.get_model(...)`, que devuelve un modelo HISTÓRICO (una clase Python
# DISTINTA a la concreta). Django despacha señales por identidad de clase
# (`sender=`), así que el `post_save` del modelo histórico NUNCA dispara el
# receiver conectado al modelo real: la caché de cualquier rol con una
# entrada previa (ej. `admin`, ya consultado constantemente) queda
# desactualizada hasta que expire su TTL de 1h, aunque la BD ya esté
# correcta. Mismo gap latente en 0004/0007 (nunca se detectó porque el
# E2E de esos RUNs corrió después de que el TTL ya hubiera expirado).
#
# Fix: invalidar explícitamente, vía RunPython, la caché de los roles que
# 0008/0009 tocaron -- no depende de señales, corre siempre.

from django.db import migrations

ROLES_AFECTADOS = [
    "admin",
    "admin_general",
    "director",
    "coordinador",
    "coordinador_general",
    "contador",
    "gerente_financiero",
]


def invalidar_cache_roles(apps, schema_editor):
    from apps.core.permissions import invalidate_role_cache

    for codigo in ROLES_AFECTADOS:
        invalidate_role_cache(codigo)


def noop_reversa(apps, schema_editor):
    # Invalidar caché no tiene estado que revertir -- el próximo request
    # recalcula desde BD igual. No-op deliberado.
    pass


class Migration(migrations.Migration):
    dependencies = [("core", "0009_seed_modulo_completo_contador_gerente_financiero")]
    operations = [
        migrations.RunPython(invalidar_cache_roles, noop_reversa),
    ]
