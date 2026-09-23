"""Matriz de roles — Módulo Financiero de Construcción (Instelec#267 A7).

Contrato con A10 (#267, "4 Reportes: PDF ejecutivo, Excel 4 hojas, CSV
contable, PPT 7 diapositivas" — dag_dependencias: A10 depende de A7): "Todo
gateado por A7 (rol→formato permitido)". Cada endpoint de descarga que A10
construya DEBE llamar a ``user_puede_descargar_reporte``/
``formatos_reporte_permitidos`` de acá, server-side, ANTES de generar el
archivo — ocultar el botón en el template NO es suficiente (instrucción
explícita de F2).

Fuente: respuesta del cliente en el issue #267 (comentario @Indunnova, tabla
Rol×Cargar×Ver×Reportes) + roles reales verificados en BD prod (tabla
``roles``, RBAC #186):

    | Rol cliente          | Rol BD (codigo)               | Cargar | Ver | Reportes           |
    |-----------------------|---------------------------------|--------|-----|---------------------|
    | Admin Instelec         admin* (nivel=admin genérico)      ✅      ✅    PDF/Excel/PPT/CSV   |
    | Gerente Financiero     gerente_financiero                 ✅      ✅    PDF/Excel/PPT/CSV   |
    | Contador (Claudia)     contador                            ❌      ✅    Solo Excel          |
    | Gerente Proyecto       director + admin_construccion       ✅      ✅    PDF/Excel           |
    | Supervisor             supervisor                          ❌      ✅    Solo lectura (nada) |

⚠️ **'Gerente Proyecto' NO existe como rol literal en BD** (verificado por
F2, 2026-09-22) — se mapeó a ``director`` ('Director de Proyecto (legacy)')
+ ``admin_construccion`` ('Administrador de Construcción'). Es una decisión
YA TOMADA por F2 (no se reabre acá) — queda PENDIENTE de confirmación
explícita del cliente, señalado en el comentario de cierre de A7.

⚠️ **CSV ("CSV para Contabilidad", Fase 5.4 del issue) no aparece en la
tabla Rol×Reportes literal del cliente.** Se asume el mismo tier que
PDF/PPT para admin*/gerente_financiero (formato ejecutivo/detallado) y se
EXCLUYE de ``contador`` pese a ser nominalmente "para Contabilidad", porque
la fila literal de Contador dice "Solo Excel" sin excepción. Asunción a
confirmar con el cliente cuando A10 construya el endpoint CSV — señalado en
el mismo comentario de cierre.

'Cargar' y 'Ver' NO se gatean acá con una lista hardcodeada: ya los resuelve
``ProyectoFinMixin``/``RoleRequiredMixin`` (``apps/core/mixins.py``) contra
la matriz RBAC real (``RoleModuloPermiso``, submódulo ``FINANCIERO`` del
módulo ``CONSTRUCCION``), sembrada para estos 5 roles por la migración
``core.0011_seed_construccion_financiero_matriz_roles_267``. Duplicar esa
decisión acá con una lista propia contradiría el patrón ya establecido en
el repo (#247/#248/#249 reemplazaron listas ``allowed_roles`` hardcodeadas
POR la matriz RBAC genérica) y arriesgaría que las dos fuentes diverjan. Los
dos helpers ``user_puede_ver_financiero_construccion``/
``user_puede_cargar_financiero_construccion`` de acá son solo un espejo
nombrado de esa MISMA matriz (útil para tests/documentación/futuros
consumidores que no hereden de ``ProyectoFinMixin``) — no una fuente nueva
de verdad.
"""
from apps.core.models_roles import RoleModuloPermiso
from apps.core.permissions import (
    MODULO_CONSTRUCCION,
    SUBMODULO_FINANCIERO,
    user_es_admin,
    user_nivel_acceso_submodulo,
)

FORMATO_PDF = 'pdf'
FORMATO_EXCEL = 'excel'
FORMATO_PPT = 'ppt'
FORMATO_CSV = 'csv'

_TODOS_LOS_FORMATOS = frozenset({FORMATO_PDF, FORMATO_EXCEL, FORMATO_PPT, FORMATO_CSV})
_FORMATOS_DIRECTOR_ADMIN_CONSTRUCCION = frozenset({FORMATO_PDF, FORMATO_EXCEL})
_FORMATOS_CONTADOR = frozenset({FORMATO_EXCEL})
_FORMATOS_SUPERVISOR = frozenset()  # solo lectura -- sin descargas de ningún formato

# Roles con carve-out EXPLÍCITO por fuera del bypass admin* genérico.
# 'admin_construccion' y 'director' SON nivel=admin en BD (ver tabla
# `roles`), pero el issue les da un tier MENOR que "Admin Instelec" real
# (PDF/Excel, no PPT/CSV) -- por eso se resuelven ANTES de consultar
# `user_es_admin`, que de otro modo los clasificaría en `_TODOS_LOS_FORMATOS`.
_ROL_A_FORMATOS_EXPLICITO = {
    'admin_construccion': _FORMATOS_DIRECTOR_ADMIN_CONSTRUCCION,
    'director': _FORMATOS_DIRECTOR_ADMIN_CONSTRUCCION,
    'contador': _FORMATOS_CONTADOR,
    'supervisor': _FORMATOS_SUPERVISOR,
    'gerente_financiero': _TODOS_LOS_FORMATOS,
}


def formatos_reporte_permitidos(user) -> set:
    """Set de formatos (``FORMATO_*``) que ``user`` puede descargar de los
    reportes financieros de Construcción (A10).

    Orden de resolución:
    1. Anónimo/no autenticado → ``set()`` (nunca lanza).
    2. Rol con carve-out explícito (tabla del módulo) — incluye
       ``admin_construccion``/``director``, que SON nivel=admin en BD pero
       el issue les asigna un tier distinto al de "Admin Instelec" genérico.
    3. Cualquier otro rol nivel=admin (``user_es_admin``, incluye
       superuser) — "Admin Instelec" del issue: todos los formatos.
    4. Rol sin matriz conocida (p.ej. roles operativos de campo que nunca
       deberían llegar a esta vista) — ningún formato.
    """
    if not getattr(user, 'is_authenticated', False):
        return set()
    rol = getattr(user, 'rol', None)
    if rol in _ROL_A_FORMATOS_EXPLICITO:
        return set(_ROL_A_FORMATOS_EXPLICITO[rol])
    try:
        if user_es_admin(user):
            return set(_TODOS_LOS_FORMATOS)
    except Exception:
        # Defensivo (espejo del resto del módulo: apps.core.permissions
        # puede lanzar si el usuario no tiene `rol`/no está autenticado de
        # una forma inesperada) -- nunca debe romper el render de la vista.
        pass
    return set()


def user_puede_descargar_reporte(user, formato) -> bool:
    """True si ``user`` puede descargar el reporte financiero en
    ``formato`` (``FORMATO_PDF``/``FORMATO_EXCEL``/``FORMATO_PPT``/
    ``FORMATO_CSV``).

    Usalo SIEMPRE server-side en cada endpoint de descarga (A10) antes de
    generar el archivo.
    """
    return formato in formatos_reporte_permitidos(user)


def user_puede_ver_financiero_construccion(user) -> bool:
    """Espejo de negocio de ``ProyectoFinMixin`` (GET) — delega en la
    matriz RBAC real (``RoleModuloPermiso``) para no duplicar la decisión.
    """
    nivel = user_nivel_acceso_submodulo(
        user, SUBMODULO_FINANCIERO, modulo=MODULO_CONSTRUCCION)
    return nivel in {RoleModuloPermiso.VER, RoleModuloPermiso.VER_EDITAR}


def user_puede_cargar_financiero_construccion(user) -> bool:
    """Espejo de negocio de ``ProyectoFinMixin`` (POST — carga de
    presupuesto) — delega en la matriz RBAC real (``RoleModuloPermiso``).
    """
    nivel = user_nivel_acceso_submodulo(
        user, SUBMODULO_FINANCIERO, modulo=MODULO_CONSTRUCCION)
    return nivel == RoleModuloPermiso.VER_EDITAR
