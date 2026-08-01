# PLAN — Roles y Permisos editables (RBAC dinámico) (issue #186)

**Fecha:** 2026-07-18
**Issue:** [Indunnova16/Instelec#186](https://github.com/Indunnova16/Instelec/issues/186)
**Estado:** Planning F2 completado, listo para F3 sprint_exec
**Riesgo:** 🔴 ALTO (middleware global + retrofit transversal + migración de datos de acceso) — autorizado por Miguel con gate de paridad OBLIGATORIO (ver §3)

## Contexto

Instelec pide reemplazar el RBAC hardcodeado (`Usuario.Rol` TextChoices de 14
valores + dicts `ROL_MODULOS`/`ROL_NIVEL`/`ROL_SUBMODULOS` en
`apps/core/permissions.py`) por un modelo `Role`/`RoleModuloPermiso` en BD,
editable desde una pantalla de matriz bajo "Parametrización", para que el
cliente gestione accesos por CARGO sin depender de un deploy. La matriz Excel
real de Gabriel con 3 cargos nuevos (Construcción/Mantenimiento/Financiero)
**no está adjunta** — este sprint migra 1:1 los 14 roles existentes
preservando comportamiento y deja la UI lista para que Gabriel/Sebastián
carguen los cargos nuevos ellos mismos (sub-item E, scope ya decidido por
Miguel, no se fabrica matriz ficticia).

## Precedente arquitectónico: `PLAN_2026-07-10_maestro_cargos.md` (issue #176)

Ese plan resolvió el mismo problema de fondo (`TextChoices` hardcodeado →
catálogo BD editable) para `RolCuadrilla`. La decisión de diseño reusable:
**FK con `to_field='codigo'` + `db_column` igual al nombre físico actual**
para minimizar blast radius — la columna NO cambia de tipo/nombre, solo se le
agrega una constraint. Aplicamos el mismo patrón aquí, con una diferencia
importante explicada en §1.

## 1. Decisión de diseño: `Usuario.rol` se mantiene `CharField` (NO se convierte a FK esta sesión)

A diferencia de `RolCuadrilla` (donde SÍ convertimos a FK porque había 2
modelos duplicados que unificar), aquí **NO convertimos `Usuario.rol` a FK**
por menor blast radius con el mismo resultado funcional:

- `Usuario.rol` sigue siendo `CharField(max_length=30)`. Django no impone
  constraint de integridad sobre `choices=` a nivel de BD — solo valida en
  `clean()`/formularios. Esto significa que **podemos crear roles nuevos sin
  tocar el modelo `Usuario`**: basta con que el `codigo` del `Role` nuevo
  coincida con el string que se guarda en `Usuario.rol`.
- Lo único que había que cambiar para permitir "crear rol nuevo y asignarlo
  sin deploy" es el **origen del dropdown** en `apps/usuarios/views.py:78,91`
  (`context['roles'] = Usuario.Rol.choices` → `Role.objects.filter(activo=True).values_list('codigo', 'nombre')`).
  Con eso el cliente ya puede: crear cargo "Encargado de Obra Civil" en la
  matriz → aparece inmediato en el dropdown de asignar rol a un usuario.
- Las propiedades legacy de `Usuario` (`is_admin`/`is_director`/
  `is_coordinador`/`is_supervisor`, líneas 157/161/165/169) comparan contra
  constantes específicas del `TextChoices` (`self.rol == self.Rol.ADMIN`).
  Como esas constantes siguen siendo strings idénticos a los `codigo` de
  `Role`, **no requieren cambio** — se mantienen intactas.
- `Usuario.es_operario_campo` (línea 174/197-201) SÍ requiere retrofit: hoy
  importa `ROL_NIVEL`/`NIVEL_OPERARIO` directo del dict de `permissions.py`
  (que se elimina). Pasa a usar el nuevo helper BD-backed (`user_es_admin`
  invertido, o una función `rol_nivel(codigo)` nueva — ver §4).
- **Trade-off aceptado:** sin FK real, no hay integridad referencial dura
  (se podría, en teoría, guardar un `Usuario.rol` con un `codigo` que no
  exista en `Role`). Mitigado por: el dropdown de asignación siempre lee de
  `Role.objects.filter(activo=True)` (nunca texto libre), y el gate de
  paridad (§3) verifica los 14 códigos legacy exhaustivamente.

## 2. Esquema

Nuevo archivo `apps/core/models_roles.py` (convención "modelos nuevos van en
archivo nuevo", igual que `apps/cuadrillas/models_cargo.py` en el
precedente), heredando `BaseModel` (`apps/core/models.py`, ya provee UUID pk +
timestamps):

```python
class Role(BaseModel):
    """Catálogo editable de roles/cargos (issue #186).

    codigo debe coincidir EXACTAMENTE con los valores de Usuario.rol
    (CharField, sin FK real — ver PLAN §1). NO renombrar codigo de un
    rol en uso sin coordinar con el dropdown de asignación de usuarios.
    """
    NIVEL_ADMIN = 'admin'
    NIVEL_OPERARIO = 'operario'
    NIVEL_CHOICES = [(NIVEL_ADMIN, 'Administrador'), (NIVEL_OPERARIO, 'Operario')]

    codigo = models.CharField('Código', max_length=30, unique=True)
    nombre = models.CharField('Nombre', max_length=100)
    nivel = models.CharField('Nivel', max_length=10, choices=NIVEL_CHOICES)
    legacy = models.BooleanField('Legacy', default=False)  # 7 roles RBAC v2 vs 7 legacy (F1 sub-item a)
    activo = models.BooleanField('Activo', default=True)

    class Meta:
        db_table = 'roles'
        verbose_name = 'Rol'
        verbose_name_plural = 'Roles'
        ordering = ['nombre']

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"


class RoleModuloPermiso(BaseModel):
    """Permiso de un Role sobre un módulo (y, opcionalmente, sub-módulo de CONSTRUCCION).

    Una fila con submodulo=None = permiso a nivel de MÓDULO completo
    (MANTENIMIENTO/CONSTRUCCION/CONFIG). Una fila con submodulo != None
    afina el acceso dentro de CONSTRUCCION (obra civil, montaje, etc. —
    ver TODOS_SUBMODULOS). nivel_acceso reemplaza el binario actual
    (tiene/no tiene) por 3 estados que YA pide el Excel de Gabriel,
    aunque este sprint solo puebla ver_editar/ver preservando el mapeo
    binario legacy (ver Gate de Paridad, §3).
    """
    SIN_ACCESO = 'sin_acceso'
    VER = 'ver'
    VER_EDITAR = 'ver_editar'
    NIVEL_ACCESO_CHOICES = [
        (SIN_ACCESO, 'Sin acceso'), (VER, 'Ver'), (VER_EDITAR, 'Ver y editar'),
    ]
    MODULO_CHOICES = [
        ('MANTENIMIENTO', 'Mantenimiento'), ('CONSTRUCCION', 'Construcción'), ('CONFIG', 'Configuración'),
    ]
    # SUBMODULO_CHOICES = TODOS_SUBMODULOS de permissions.py (14 valores), importado, no reescrito a mano

    role = models.ForeignKey(Role, to_field='codigo', db_column='role_codigo',
                              on_delete=models.CASCADE, related_name='permisos')
    modulo = models.CharField('Módulo', max_length=20, choices=MODULO_CHOICES)
    submodulo = models.CharField('Sub-módulo', max_length=40, blank=True, null=True)
    nivel_acceso = models.CharField('Nivel de acceso', max_length=12,
                                     choices=NIVEL_ACCESO_CHOICES, default=SIN_ACCESO)

    class Meta:
        db_table = 'role_modulo_permisos'
        unique_together = [('role', 'modulo', 'submodulo')]
        verbose_name = 'Permiso de Rol'
        verbose_name_plural = 'Permisos de Rol'
```

Re-exportar en `apps/core/models.py` con `from .models_roles import *` (mismo
patrón del precedente).

## 3. Gate de paridad de acceso (OBLIGATORIO — requisito de aceptación del sub-item B, no opcional)

**Impuesto por Miguel: cualquier diferencia entre el sistema VIEJO (dicts) y
el NUEVO (BD) para los 14 roles × todos los módulos/submódulos es
BLOQUEANTE — no se puede deployar.** Este test es parte de los
`tests_requeridos` de B2 (no un nice-to-have posterior).

**Mecánica:**
1. Antes de eliminar los dicts de `permissions.py`, congelar una copia
   **verbatim** de `ROL_MODULOS` (líneas 15-33), `ROL_NIVEL` (líneas 36-53) y
   `ROL_SUBMODULOS` (líneas 124-145) dentro del propio archivo de test —
   `apps/core/tests_issue_186_paridad_rbac.py` — como
   `_LEGACY_ROL_MODULOS_SNAPSHOT` / `_LEGACY_ROL_NIVEL_SNAPSHOT` /
   `_LEGACY_ROL_SUBMODULOS_SNAPSHOT`, con comentario explícito "snapshot
   congelado para el gate de paridad — NO actualizar aunque cambie el
   catálogo BD en el futuro".
2. Para los 14 códigos de rol (`admin_general`, `coordinador_general`,
   `admin_mantenimiento`, `admin_construccion`, `operario_mantenimiento`,
   `operario_construccion`, `operario_general`, `admin`, `director`,
   `coordinador`, `ing_residente`, `ing_ambiental`, `supervisor`, `liniero`,
   `auxiliar`):
   - Instanciar (o usar factory) un `Usuario` con ese `rol`.
   - **VIEJO**: calcular `modulo in _LEGACY_ROL_MODULOS_SNAPSHOT.get(rol, set())`
     para cada uno de los 3 módulos; `_LEGACY_ROL_NIVEL_SNAPSHOT.get(rol) == 'admin'`
     para `user_es_admin`; `submodulo in _LEGACY_ROL_SUBMODULOS_SNAPSHOT.get(rol, set())`
     para cada uno de los 14 sub-módulos.
   - **NUEVO**: llamar a las funciones reales post-retrofit —
     `user_can_access_modulo(user, modulo)`, `user_es_admin(user)`,
     `user_can_access_submodulo(user, submodulo)` — que ahora leen
     `RoleModuloPermiso` desde BD (post-migración de datos de B1).
   - `assertEqual` VIEJO == NUEVO para las **3 × 14 = 42** combinaciones de
     módulo, las **14** de nivel/admin, y las **14 × 14 = 196** de
     sub-módulo. Total 252 aserciones por rol × módulo/submódulo/nivel.
3. Cualquier `assertEqual` que falle = el mapeo de la migración de datos
   (B1) está mal — se corrige el `RunPython` de la migración, NO el test.
4. Este test corre en `make test` (recolectado por pytest automáticamente,
   sin configuración extra) y es parte del gate de CI existente del repo.
5. **Closeout (`closeout.py`) debe verificar que este archivo de test existe
   y está en verde antes de permitir 🟢** — si no puede confirmarlo, el
   veredicto cae a 🟡 con este pendiente explícito (mismo criterio que
   cualquier sub-ítem de la tabla de entregables sin ✅).

## 4. Estrategia de caching (OBLIGATORIA — middleware corre en CADA request)

`RBACModuloMiddleware` (`apps/core/middleware.py`) intercepta TODO request no
exento. Hoy resuelve `user_can_access_modulo` contra un dict en memoria
(costo ~0). Post-migración, cada llamada implicaría una query a
`RoleModuloPermiso` — inaceptable en cada request.

**Decisión: cache framework de Django, keyed por `Role.codigo` (NO por
sesión de usuario).** Razón de diseño explícita:
- Los roles son un catálogo pequeño (14-20 filas) compartido por TODOS los
  usuarios de ese rol — cachear por `codigo` significa como máximo ~20
  entradas de cache en memoria/Redis, vs. cachear por sesión que multiplica
  por el número de usuarios activos concurrentes.
- Cache por sesión además queda **stale** si el cliente edita la matriz
  mientras un usuario tiene sesión abierta (el cambio no se refleja hasta que
  expira o re-loguea) — inaceptable para una UI que se vende como "editable
  sin deploy, con efecto inmediato".
- El repo YA tiene Redis configurado (`config/settings/base.py:108-110`,
  `django_redis.cache.RedisCache`) y un patrón reusable en
  `apps/core/cache.py` (`get_cached_queryset` + `CACHE_KEYS` + funciones
  `invalidate_*`). Reusamos ESE patrón, no inventamos uno nuevo.

**Implementación concreta** (`apps/core/permissions.py`, nueva función
`_get_role_permisos(codigo)`):
```python
from apps.core.cache import cache  # reusar import existente
CACHE_KEY_ROLE_PERMISOS = 'instelec:rbac:role:{codigo}'

def _get_role_permisos(codigo):
    key = CACHE_KEY_ROLE_PERMISOS.format(codigo=codigo)
    cached = cache.get(key)
    if cached is not None:
        return cached
    from .models_roles import Role
    try:
        role = Role.objects.prefetch_related('permisos').get(codigo=codigo, activo=True)
    except Role.DoesNotExist:
        cached = {'modulos': set(), 'submodulos': set(), 'nivel': None}
        cache.set(key, cached, 3600)
        return cached
    modulos = {p.modulo for p in role.permisos.all() if p.nivel_acceso != 'sin_acceso' and not p.submodulo}
    submodulos = {p.submodulo for p in role.permisos.all() if p.nivel_acceso != 'sin_acceso' and p.submodulo}
    cached = {'modulos': modulos, 'submodulos': submodulos, 'nivel': role.nivel}
    cache.set(key, cached, 3600)  # 1h, invalidado explícitamente abajo
    return cached
```
- **Invalidación explícita** (no solo TTL): señal `post_save`/`post_delete`
  sobre `RoleModuloPermiso` y `Role` en `apps/core/models_roles.py` (o
  `apps/core/apps.py::ready()`) que llama `cache.delete(CACHE_KEY_ROLE_PERMISOS.format(codigo=...))`
  — así una edición en la matriz (§5) tiene efecto inmediato en el próximo
  request, sin esperar el TTL de 1h.
- `user_modulos`/`user_can_access_modulo`/`user_es_admin`/`user_submodulos`/
  `user_can_access_submodulo` (`permissions.py`) mantienen su **firma
  exacta** (`user_can_access_modulo(user, modulo)` etc.) — solo cambia el
  cuerpo para llamar `_get_role_permisos(user_rol(user))` en vez de indexar
  los dicts. Esto es lo que hace que el retrofit de call sites (§6) sea
  case-por-caso casi nulo: middleware/mixins/templatetags/views ya llaman
  estas funciones, no los dicts directamente.

## 5. UI de administración (matriz roles × módulos)

Bajo "Parametrización" (`templates/components/sidebar.html:504-511`, mismo
patrón que Usuarios/Tipos de Actividad/Cargos):
- `RoleListView` / `RoleCreateView` / `RoleEditView` / `RoleInactivarView`
  (`apps/core/views.py`, nueva sección, análoga a
  `TipoActividadListView`/`CargoListView` del precedente). `codigo`
  read-only en edición (mismo trade-off que `Cargo.codigo`, aunque acá NO
  hay FK constraint que lo fuerce — se documenta como convención, no como
  restricción de BD, porque el dropdown de asignación de usuario referencia
  el `codigo` textualmente).
- `RoleModuloPermisoMatrizView`: grid roles (filas) × módulos/submódulos
  (columnas), celda = `<select>` `sin_acceso`/`ver`/`ver_editar`. Guardado
  por celda vía HTMX (`hx-post` al cambiar el select, sin reload completo —
  coherente con el stack HTMX/Alpine del repo). Cada guardado dispara la
  invalidación de cache de §4 para ese `role.codigo`.
- URLs (`apps/core/urls.py`): `roles/` → lista, `roles/crear/`, `roles/<uuid:pk>/editar/`,
  `roles/matriz/` → la matriz completa, `roles/matriz/<str:role_codigo>/<str:modulo_key>/celda/`
  (POST HTMX de una celda).
- Navbar: `<li role="none"><a href="{% url 'core:roles_matriz' %}" ...>Roles y Permisos</a></li>`
  después de "Cargos" (línea ~510).

## 6. Retrofit de call sites (blast radius acotado por §4 — firmas preservadas)

| Archivo | Patrón actual | Acción |
|---|---|---|
| `apps/core/middleware.py:18,68` | `user_can_access_modulo(request.user, modulo)` | Ninguna — firma preservada |
| `apps/core/mixins.py:52-53,107-110,126-127,148-151` | `user_es_admin`/`user_can_access_modulo`/`user_can_access_submodulo` | Ninguna — firma preservada |
| `apps/core/templatetags/core_tags.py:14-17,23-26,32-35` | ídem, usado por `sidebar.html` (`puede_acceder`/`es_admin_rbac`/`puede_submodulo`) | Ninguna |
| `apps/core/views.py:39-44` (`HomeView.dispatch`) | `user_modulos(request.user)` | Ninguna |
| `apps/lineas/views_b21.py:60-61` | `user_es_admin(user)` | Ninguna |
| `apps/usuarios/models.py:200-201` (`es_operario_campo`) | `from apps.core.permissions import ROL_NIVEL, NIVEL_OPERARIO` (import directo al dict, NO pasa por una función) | **Retrofit real**: cambiar a una función nueva `rol_nivel(codigo)` en `permissions.py` que usa `_get_role_permisos` (§4), o simplemente `user_es_admin(self)` invertido si el semantic exacto coincide (`NIVEL_OPERARIO` == "no admin") — confirmar en F3 que no hay un tercer nivel implícito |
| `apps/usuarios/models.py:157,161,165,169` (`is_admin`/`is_director`/`is_coordinador`/`is_supervisor`) | `self.rol == self.Rol.ADMIN` etc. | Ninguna (ver §1 — siguen siendo comparaciones string-a-string válidas) |
| `apps/usuarios/models.py:39` (`create_superuser`) | `extra_fields.setdefault('rol', Usuario.Rol.ADMIN)` | Ninguna — sigue siendo un string válido mientras `Role(codigo='admin')` exista tras la migración de datos |
| `apps/usuarios/views.py:78,91` (`GestionUsuariosView`/`CrearUsuarioAdminView`) | `context['roles'] = Usuario.Rol.choices` | **Retrofit real**: `Role.objects.filter(activo=True).values_list('codigo', 'nombre')` — esto es lo que habilita "crear rol nuevo → asignable sin deploy" |
| `apps/core/permissions.py` completo | Dicts `ROL_MODULOS`/`ROL_NIVEL`/`ROL_SUBMODULOS` | Se ELIMINAN tras B1 (snapshot ya congelado en el test de paridad, §3) — las funciones públicas (`user_modulos`, `user_can_access_modulo`, `user_es_admin`, `user_submodulos`, `user_can_access_submodulo`, `url_inicio_para_usuario`) se reescriben para usar `_get_role_permisos` pero mantienen firma |

**Nota importante:** a diferencia del precedente de Cargo (20 archivos, FK
real, muchos `== 'STRING'` rotos), acá el blast radius de retrofit es
**pequeño** porque `permissions.py` YA actuaba como capa de indirección
(todo el resto del código llama a sus funciones, no a los dicts
directamente) — excepto los 2 puntos marcados "Retrofit real" arriba. Esto
reduce significativamente el riesgo de A5/A6 vs. lo que estimó F1 ("36 usos
en 5 archivos" es cierto en superficie de grep, pero la mayoría no requiere
cambio de código, solo confirmación de que la firma no cambió).

## 7. Sub-items ejecutables — Sprint A (worktree único, ver §9)

| # | Sub-item | Archivos | Tests requeridos | Dependencias | Complexity | Deployable solo | Estado |
|---|---|---|---|---|---|---|---|
| A1 | Modelos `Role`+`RoleModuloPermiso` + migración de esquema (aditiva) | `apps/core/models_roles.py` (nuevo), `apps/core/models.py` (re-export), `apps/core/migrations/0001_role_rolemodulopermiso.py` (primera migración real de `apps.core`) | Migración aplica limpio; `Role`/`RoleModuloPermiso` CRUD básico vía shell | - | medium | sí (aditivo puro) | ❌ |
| A2 | Data migration (seed 14 `Role` desde `Usuario.Rol.choices` + `RoleModuloPermiso` replicando `ROL_MODULOS`/`ROL_NIVEL`/`ROL_SUBMODULOS` exactos) **+ Gate de Paridad de Acceso (§3, OBLIGATORIO)** | `apps/core/migrations/0002_seed_roles_permisos.py`, `apps/core/tests_issue_186_paridad_rbac.py` (nuevo) | Gate de paridad completo (252 aserciones/rol, §3) en verde; `Role.objects.count() == 14`; verificación contra ≥1 usuario legacy real en BD (no solo fixture) | A1 | **high** | no (requiere A1) | ❌ |
| A3 | Reescribir `apps/core/permissions.py` para leer BD vía `_get_role_permisos` + caching por-rol + invalidación por señal (§4) | `apps/core/permissions.py`, `apps/core/models_roles.py` (señales `post_save`/`post_delete`) | Gate de paridad (A2) sigue en verde tras el rewrite; test de invalidación (editar `RoleModuloPermiso` → cache se limpia → próxima lectura refleja el cambio); test de performance básico (N requests no disparan N queries — mock/assert de `assertNumQueries`) | A2 | **high** | no | ❌ |
| A4 | Retrofit puntual: `Usuario.es_operario_campo` (nivel BD-backed) + `usuarios/views.py` dropdown dinámico (líneas 78/91) | `apps/usuarios/models.py`, `apps/usuarios/views.py` | Crear usuario nuevo ve el dropdown con roles BD (incluye uno recién creado en A5); `es_operario_campo` da el mismo resultado que antes para los 14 roles legacy (reusa aserciones del gate de A2) | A3 | medium | no | ❌ |
| A5 | UI matriz roles × módulos (CRUD `Role` + grid editable con HTMX, bajo Parametrización) | `apps/core/views.py` (nueva sección), `apps/core/urls.py`, `apps/core/forms_roles.py` (nuevo), `templates/core/roles_lista.html`, `templates/core/roles_matriz.html` (nuevos), `templates/components/sidebar.html` | Crear rol nuevo (ej. "Encargado de Obra Civil") + asignarle permisos vía matriz + confirmar que aparece en dropdown de A4; editar celda invalida cache (A3) | A3, A4 | high | no | ❌ |
| A6 | Retrofit de tests existentes que referencian `Usuario.Rol.choices`/dicts de `permissions.py` directamente (si los hay) + tests unitarios de `Role`/`RoleModuloPermiso` CRUD | grep exhaustivo `ROL_MODULOS\|ROL_NIVEL\|ROL_SUBMODULOS` sobre `tests_*`/`apps/*/tests*` antes de cerrar (repetir el grep de F1 sobre el propio diff, mismo criterio del precedente §"Riesgo #3") | `pytest apps/core apps/usuarios apps/lineas -k rbac` en verde | A2, A3, A4, A5 | medium | no | ❌ |
| A7 | Smoke E2E (journey `Instelec_186.yaml`) + comentario de cierre con: URLs, rol legacy validado en prod, y **pendiente explícito de Gabriel** (sub-item E — 3 cargos nuevos, matriz Excel no adjunta) | - | Journey completo en verde (incluye el journey de paridad de acceso, §Journey) | A1-A6 | trivial | no | ❌ |

### Tabla de entregables (gate anti-FIX_INCOMPLETO)

| # | Entregable | Evidencia esperada | ✅/❌ |
|---|---|---|---|
| a | Modelos `Role`/`RoleModuloPermiso` en BD | Migración `0001_role_rolemodulopermiso` aplicada en prod; `python manage.py showmigrations apps.core` limpio | ❌ |
| b | Migración de datos 14 roles → BD **con Gate de Paridad de Acceso obligatorio** | `apps/core/tests_issue_186_paridad_rbac.py` en verde (252 aserciones/rol); `Role.objects.count()==14` en prod | ❌ |
| c | UI matriz roles × módulos editable (crear rol nuevo + asignar permisos) | URL `/parametrizacion/roles/matriz/` smokeada en prod; screenshot de rol nuevo creado y asignado a un usuario de prueba | ❌ |
| d | `permissions.py` reescrito leyendo BD + caching por-rol con invalidación | Test de invalidación en verde; `assertNumQueries` no degrada por request del middleware | ❌ |
| e | 🟡 Pendiente explícito: matriz real de Gabriel (3 cargos nuevos) | Comentario de cierre declara explícitamente el pendiente, NO se fabrica data ficticia | ❌ (se cierra como 🟡 por diseño, no bloquea a-d) |

### DAG de dependencias

```
A1 (Role+RoleModuloPermiso, deployable_solo)
 └─→ A2 (seed data + GATE DE PARIDAD, alto riesgo — bloqueante)
      └─→ A3 (permissions.py reescrito + caching, alto riesgo)
           ├─→ A4 (retrofit es_operario_campo + dropdown usuarios)
           │    └─→ A5 (UI matriz, puede empezar en paralelo con A4 una vez A3 listo)
           └─→ A5
                └─→ A6 (retrofit tests, depende de A2+A3+A4+A5)
                     └─→ A7 (journey E2E + comentario cierre)
```

Nota: A4 y A5 SÍ pueden trabajarse en paralelo una vez A3 está mergeado
dentro del mismo branch (ver §9 — no son branches separadas, son commits
secuenciales o casi-paralelos dentro del mismo worktree), porque A5 (UI)
consume `Role`/permisos ya pobladas por A2 y ya cacheadas por A3, y A4 es un
retrofit acotado a 2 archivos que no colisiona con las plantillas nuevas de
A5.

## 8. Riesgos y mitigaciones

- **Riesgo #1 (el más alto): mapeo incorrecto en la migración de datos (A2)
  rompe acceso real en prod, silenciosamente.** Mitigado 100% por el Gate de
  Paridad (§3) — es un gate de test automatizado, no smoke visual. Si el
  gate no está en verde, A2 no se considera terminado y no bloquea deploy.
- **Riesgo #2: degradación de latencia por dict→BD en el middleware
  global.** Mitigado por el caching por-rol de §4 (catálogo pequeño, TTL 1h
  + invalidación explícita por señal) — NO cache por-sesión (multiplicaría
  el tamaño y quedaría stale).
- **Riesgo #3: blast radius mayor al estimado en la próxima pasada de
  grep.** F3, antes de cerrar A6, debe re-correr
  `grep -rn "ROL_MODULOS\|ROL_NIVEL\|ROL_SUBMODULOS" apps/ templates/ tests/`
  contra su propio diff — si aparece algo no cubierto en §6, se agrega al
  ledger o se justifica como fuera de scope.
- **Riesgo #4: el dropdown de asignación de rol (A4) permite escribir un
  `Usuario.rol` que no tiene fila en `Role` (sin FK real, §1).** Mitigado
  porque el dropdown SIEMPRE lee de `Role.objects.filter(activo=True)` — no
  hay ruta de UI que permita texto libre. El riesgo residual es solo vía
  Django admin/shell directo, aceptado explícitamente (mismo nivel de riesgo
  que ya existe hoy con `CharField+choices`, que tampoco es una constraint
  de BD).
- **Riesgo #5 (bajo, ya decidido): 3 cargos nuevos de Gabriel no se cargan
  esta sesión.** Documentado como 🟡 explícito en A7, no bloquea a-d.

## 9. Recomendación: worktree/branch ÚNICO para todo el sprint

**Recomendación: SÍ, un solo worktree/branch para A1-A7 completo,
secuencial dentro del mismo branch — NO branches paralelas por sub-item.**

Razones:
1. `RBACModuloMiddleware` es código que corre en CADA request de la
   aplicación completa — un merge de 4 branches parciales (ej. A1+A2 en una
   rama, A3 en otra, A5 en una tercera) puede dejar al middleware en un
   estado intermedio inconsistente durante la ventana entre merges (ej.
   `permissions.py` ya lee de BD pero la migración de datos de A2 aún no
   está en esa rama) — el precedente de Cargo (#176) ya documentó
   exactamente este riesgo para un caso de MENOR blast radius ("A3+A4+A5+A6
   DEBEN ir en un SEGUNDO deploy atómico... desplegar A3 sin A4/A5 rompe en
   producción CUALQUIER vista que toque rol_cuadrilla").
2. A5 (UI) lee de A2 (datos) y A3 (funciones cacheadas) — es la definición
   de "no paralelizable de forma segura": construir la UI de matriz contra
   un esquema/dato que todavía puede cambiar de forma en otra rama duplica
   trabajo de merge.
3. El Gate de Paridad (§3) es el semáforo real de si el sprint completo
   puede promoverse a prod — tiene sentido que sea UN solo PR/deploy
   atómico, no 4 deploys parciales donde cada uno individualmente no es
   seguro de promover solo (A2 sin A3 deja el sistema viejo funcionando
   pero con datos duplicados sin usar; A3 sin A2 aplicado rompe TODO el
   acceso porque `_get_role_permisos` no encontraría filas).
4. Único punto en contra: sesión más larga sin puntos de entrega
   intermedios — aceptable dado que Miguel ya autorizó el riesgo alto de
   este issue completo, y el Gate de Paridad da la señal de "seguro para
   prod" al final, no a mitad de camino.

## 10. Validación esperada (smoke E2E + instrucciones cliente)

- Login como usuario QA (rol legacy `admin`) → sigue viendo TODO (Home,
  Construcción, Mantenimiento, Parametrización) — paridad de acceso del
  rol más amplio.
- Crear usuario temporal QA_E2E con rol `operario_construccion` → confirmar
  que el sidebar SOLO muestra el menú CONSTRUCCION (no Mantenimiento/
  Financiero/Config) — mismo comportamiento que hoy, ahora servido desde BD.
- Crear un rol NUEVO desde la matriz (ej. "Encargado de Obra Civil QA") con
  acceso `ver` a `OBRA_CIVIL` únicamente → confirmar que aparece en el
  dropdown de asignación de usuarios → asignar a un usuario QA_E2E →
  confirmar que solo ve Obra Civil.
- Instrucciones a cliente (comentario de cierre): URL de la matriz, cómo
  crear un rol nuevo, cómo asignarlo a un usuario, y el pendiente explícito
  de que los 3 cargos del Excel de Gabriel (Construcción/Mantenimiento/
  Financiero) requieren que él mismo los cree con la matriz (o que envíe el
  Excel para que Indunnova los cargue) — no están precargados.
