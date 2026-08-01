# PLAN — Maestro 3: Cargos (issue #176, bounce 2)

**Fecha:** 2026-07-10
**Issue:** [Indunnova16/Instelec#176](https://github.com/Indunnova16/Instelec/issues/176)
**Estado:** Planning F2 confirmado, listo para F3 sprint_exec

## Contexto y por qué este bounce es scope nuevo, no un fix incompleto

El fix del 2026-07-04 (navbar + moneda + botón) quedó validado por el cliente
con screenshot el 2026-07-06 — el submenú Parametrización muestra Tipos de
Actividad y Colaboradores funcionando en prod. En el MISMO comentario el
cliente pidió algo que el cierre anterior ya había diferido explícitamente
como fuera de scope: "necesito un maestro visible y autogestionable con los
cargos". Ese pedido es este plan — construir el **Maestro 3 (Cargos)**,
análogo a Tipos de Actividad/Colaboradores, que reemplace el `TextChoices`
`RolCuadrilla` hoy hardcoded y **duplicado byte-a-byte** en
`PersonalCuadrilla.rol_cuadrilla` (`models_base.py:80-97`) y
`CuadrillaMiembro.rol_cuadrilla` (`models_base.py:227-244`).

## Hallazgo de código que corrige/amplía el estimado de F1

F1 estimó "38 referencias en 6 archivos". La inspección real (`grep -rn
"rol_cuadrilla\|RolCuadrilla"`) encuentra referencias en **~20 archivos**:
`apps/cuadrillas/{models_base,views,views_semanal,importers,api,admin,
forms_personal}.py`, `apps/financiero/{reports,views}.py`,
`apps/actividades/exporters.py`, `apps/core/management/commands/seed_data.py`,
`templates/cuadrillas/{detalle,colaboradores_lista,colaboradores_form}.html`,
`templates/financiero/nomina.html`, y 9 archivos de test (`tests_issue_176.py`,
`tests_s18.py`, `tests_b4.py`, `tests_issue_178.py`, `tests_issue_178_bc.py`,
`tests/unit/test_cuadrillas.py`, `tests/integration/test_flujo_actividades.py`,
`tests/e2e/test_flujo_mensual.py`, `tests/factories/cuadrillas.py`,
`apps/campo/tests_b12.py`). El "Retrofit Ledger" (§4) lista cada uno con la
acción exacta — es la tabla contra la que se cierra el issue (gate
anti-FIX_INCOMPLETO: ninguna fila puede quedar sin ✅ o sin justificación de
scope).

**Ya se verificó contra prod (2026-07-10, lectura, sin escritura):** las
1,110 filas existentes (`personal_cuadrilla`: 2, `cuadrilla_miembros`: 1,108)
tienen **100% valores válidos, NOT NULL**, todos dentro del set de 14 códigos
del enum. Cero filas huérfanas. Esto de-riesga la migración de esquema — no
hace falta limpieza de datos previa a agregar el FK constraint.

## Decisión de diseño: unificar `CuadrillaMiembro.rol_cuadrilla` con `PersonalCuadrilla.rol_cuadrilla`

**Decisión: UNIFICAR.** Ambos `RolCuadrilla` TextChoices son idénticos
código-por-código y label-por-label (14 entradas cada uno, incluyendo el
sync manual que forzó el issue #178 A6 — el comentario en
`models_base.py:93-95` literalmente documenta que ya hubo que sincronizarlos
a mano una vez). Es el caso de libro del criterio "mismo dominio, mismos
valores posibles → unificar": dejarlos separados garantiza que en 6 meses
alguien agregue un cargo nuevo a un solo enum (ya pasó con MALACATERO/
COORDINADOR_HSQ) y el otro modelo quede desincronizado silenciosamente.

**Riesgo de confusión de nombres (documentar en el modelo, no dejarlo
implícito):** `CuadrillaMiembro` YA tiene un campo llamado `cargo`
(`CargoJerarquico`: `JT_CTA`/`MIEMBRO` — jerarquía dentro de la cuadrilla,
NO el mismo concepto). El nuevo catálogo se llama `Cargo` (coincide con el
vocabulario del cliente y con el `verbose_name` ya existente `'Cargo / Rol'`),
pero el **campo** que lo referencia en ambos modelos sigue llamándose
`rol_cuadrilla` (NO se renombra a `cargo` para no colisionar con el campo
`cargo` de `CargoJerarquico` en `CuadrillaMiembro`). Poner un docstring
explícito en `Cargo` que diga "no confundir con `CuadrillaMiembro.
CargoJerarquico`".

## Decisión de diseño: FK con `to_field='codigo'` (no a la PK UUID)

Para minimizar el blast radius del retrofit (~20 archivos), el nuevo campo
`rol_cuadrilla` se implementa como:

```python
rol_cuadrilla = models.ForeignKey(
    'cuadrillas.Cargo',
    to_field='codigo',
    db_column='rol_cuadrilla',   # conserva el nombre de columna físico actual
    on_delete=models.PROTECT,
    default='LINIERO_I',
    related_name='...',
    verbose_name='Cargo / Rol',
)
```

Por qué: con `to_field='codigo'` y `db_column` igual al nombre actual, la
columna física NO se renombra ni cambia de tipo (sigue siendo
`varchar(20)`) — solo se le agrega una FK constraint contra
`cargos(codigo)`. Esto significa:
- `instance.rol_cuadrilla_id` sigue siendo el **string del código**
  (`'SUPERVISOR'`, `'LINIERO_I'`...) exactamente como antes — la mayoría de
  los `.filter(rol_cuadrilla__in=[...])`, `.values('rol_cuadrilla')`,
  `.order_by('rol_cuadrilla')` siguen funcionando SIN CAMBIOS (Django
  resuelve lookups de FK contra `to_field` cuando se le pasan strings).
- `instance.rol_cuadrilla` (sin `_id`) es ahora el objeto `Cargo` completo —
  ahí SÍ hay que retrofitear cualquier comparación `== 'STRING'` o
  serialización directa a JSON (ver Retrofit Ledger).
- `get_rol_cuadrilla_display()` YA NO se auto-genera (Django solo lo hace
  para campos con `choices=`) — se agrega un método manual en ambos modelos
  que retorna `self.rol_cuadrilla.nombre if self.rol_cuadrilla_id else ''`,
  lo que neutraliza ~10 de los ~20 call sites SIN tocarlos (ver Retrofit
  Ledger, columna "Acción").

**Trade-off aceptado:** con `to_field='codigo'`, el `codigo` de un `Cargo`
YA REFERENCIADO por al menos un `PersonalCuadrilla`/`CuadrillaMiembro` no se
puede editar libremente (Postgres bloquea el `UPDATE` con
`IntegrityError` de FK si se intenta cambiar un valor referenciado). El CRUD
de Cargo (A1) debe hacer `codigo` **de solo lectura al editar** (editable
solo en creación) — el cliente sigue pudiendo renombrar el `nombre`
(display) libremente, solo no el `codigo` técnico. Es el mismo patrón que ya
existe implícitamente en `TipoActividad` (nadie renombra códigos de tipos en
uso), formalizado aquí porque acá sí hay una FK real que lo hace explícito.

## 1. Modelo `Cargo` (análogo a `TipoActividad`, sin `categoria`)

Nuevo archivo `apps/cuadrillas/models_cargo.py` (convención del aggregator:
"NEW MODELS GO IN A NEW FILE", ver `models.py:10`):

```python
class Cargo(BaseModel):
    """Catálogo editable de cargos/roles de cuadrilla (issue #176, Maestro 3).

    NO confundir con CuadrillaMiembro.CargoJerarquico (JT_CTA/MIEMBRO) —
    ese es un concepto distinto (jerarquía dentro de la cuadrilla), no
    tocado por este maestro.
    """
    codigo = models.CharField('Código', max_length=20, unique=True)
    nombre = models.CharField('Nombre', max_length=100)
    activo = models.BooleanField('Activo', default=True)

    class Meta:
        db_table = 'cargos'
        verbose_name = 'Cargo'
        verbose_name_plural = 'Cargos'
        ordering = ['nombre']

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"
```

Re-exportar en `apps/cuadrillas/models.py` con `from .models_cargo import *`.

## 2. Migraciones (orden estricto — cada una depende de que la anterior haya corrido)

| # | Archivo | Contenido | Reversible |
|---|---|---|---|
| 1 | `0018_cargo.py` | `CreateModel Cargo` (schema puro, tabla nueva `cargos`) | Sí, trivial (DROP TABLE) |
| 2 | `0019_seed_cargos.py` | `RunPython` con modelo histórico (`apps.get_model('cuadrillas','Cargo')`): `get_or_create(codigo=code, defaults={'nombre': label, 'activo': True})` para las 14 entradas de la UNIÓN de `PersonalCuadrilla.RolCuadrilla.choices`/`CuadrillaMiembro.RolCuadrilla.choices` (idénticas, confirmado). `reverse_code=migrations.RunPython.noop` | Noop reverso (aceptable — el DROP TABLE de la migración 1 al revertir se lleva las filas) |
| 3 | `0020_personalcuadrilla_rol_cuadrilla_fk.py` | `AlterField` `PersonalCuadrilla.rol_cuadrilla`: `CharField(choices=...)` → `ForeignKey(Cargo, to_field='codigo', db_column='rol_cuadrilla', on_delete=PROTECT, default='LINIERO_I')` | Sí (AlterField es reversible por Django; revertir solo quita la FK constraint, no toca datos) |
| 4 | `0021_cuadrillamiembro_rol_cuadrilla_fk.py` | Igual que 3 pero sobre `CuadrillaMiembro.rol_cuadrilla` | Sí |

**Verificación obligatoria ANTES de aplicar 3 y 4 en prod (riesgo #1):**
1. Correr `python manage.py makemigrations --check --dry-run` tras escribir el
   código del modelo para confirmar que Django genera exactamente estas 4
   migraciones (no un `RemoveField`+`AddField` que borre la columna — con
   `db_column` explícito debería generar `AlterField`, pero HAY QUE
   INSPECCIONAR el archivo generado a mano antes de aplicar).
2. Re-correr el query de verificación de datos huérfanos (§ ya ejecutado en
   F2, repetir en F3 justo antes de migrar por si hubo escritura entre
   medio):
   ```sql
   SELECT rol_cuadrilla, count(*) FROM personal_cuadrilla
   WHERE rol_cuadrilla NOT IN (SELECT codigo FROM cargos) GROUP BY 1;
   -- debe ser 0 filas antes de aplicar la migración 3
   ```
   (mismo query contra `cuadrilla_miembros` antes de la migración 4).
3. **Plan de rollback:** si la migración 3/4 falla en el job `instelec-migrate`
   (Cloud Run), NO hay pérdida de datos posible — `AlterField` solo agrega
   una constraint, no reescribe valores. Rollback = `python manage.py migrate
   cuadrillas 0019` (deshace las 2 FK constraints, el resto de la app sigue
   funcionando con el modelo viejo si el deploy también se revierte).
4. Tras deploy: `python manage.py makemigrations --check` debe salir limpio
   (0 migraciones pendientes) — confirma que el estado del modelo en código
   coincide 100% con la BD.

## 3. CRUD `Cargo` (analogía exacta con `TipoActividad`)

- **Vistas** (`apps/cuadrillas/views.py`, nueva sección al final, mismo
  patrón que `TipoActividadListView/CreateView/EditView/InactivarView` en
  `apps/actividades/views.py:1448-1531`): `CargoListView`, `CargoCreateView`,
  `CargoEditView`, `CargoInactivarView`. Nomenclatura sigue el patrón
  `Colaborador*View` ya usado en este mismo archivo para `PersonalCuadrilla`
  (no `PersonalCuadrilla*View`).
- **`CargoEditView`/form:** `codigo` **read-only en edición** (ver trade-off
  §"FK con to_field") — mostrar como texto plano, no input, cuando
  `modo == 'editar'`. Editable en creación.
- **Form** (`apps/cuadrillas/forms_cargo.py`, nuevo): `CargoForm` sobre
  `codigo/nombre/activo`, mismo `INPUT_CLS` que `forms_personal.py`.
- **URLs** (`apps/cuadrillas/urls.py`, junto a `colaboradores/*`):
  `cargos/` → `cargos_lista`, `cargos/crear/` → `cargos_crear`,
  `cargos/<uuid:pk>/editar/` → `cargos_editar`,
  `cargos/<uuid:pk>/inactivar/` → `cargos_inactivar`.
- **Navbar** (`templates/components/sidebar.html:507`, después de
  "Colaboradores"): `<li role="none"><a href="{% url
  'cuadrillas:cargos_lista' %}" ...>Cargos</a></li>`.
- **`PersonalCuadrillaForm`** (`forms_personal.py:29,47`): el campo
  `rol_cuadrilla` pasa de `Select` sobre `choices` estático a
  `ModelChoiceField` automático (Django lo infiere del FK) — hay que acotar
  el queryset a activos en `__init__`:
  `self.fields['rol_cuadrilla'].queryset = Cargo.objects.filter(activo=True)`
  (si no, el dropdown de "nuevo colaborador" mostraría cargos inactivados).

## 4. Retrofit Ledger — cada archivo, el patrón encontrado, la acción exacta

| Archivo | Patrón | Acción | Riesgo si se omite |
|---|---|---|---|
| `apps/cuadrillas/models_base.py:101-106,262-267` | `CharField(choices=RolCuadrilla.choices)` en ambos modelos | AlterField a FK (§2). Agregar método `get_rol_cuadrilla_display()` manual en ambos que retorna `self.rol_cuadrilla.nombre if self.rol_cuadrilla_id else ''`. Eliminar las clases `RolCuadrilla` TextChoices (ya no se usan) | Sin el método shim, ~10 call sites de `get_rol_cuadrilla_display()` truenan con `AttributeError` |
| `apps/cuadrillas/views.py:188,180,599` | `rol_cuadrilla='SUPERVISOR'` (string literal) en `.create()`/asignación directa | `rol_cuadrilla_id='SUPERVISOR'` | `ValueError: must be a "Cargo" instance` — 500 en crear cuadrilla con supervisor |
| `apps/cuadrillas/views.py:225` | `context['roles_cuadrilla'] = CuadrillaMiembro.RolCuadrilla.choices` | `Cargo.objects.filter(activo=True).values_list('codigo','nombre')` | Dropdown/JS `ROL_CUADRILLA_LABELS` en `detalle.html` queda vacío (el for-loop del template ya es agnóstico a la fuente — cero cambio de template necesario) |
| `apps/cuadrillas/views.py:941,1267` | `dict(CuadrillaMiembro.RolCuadrilla.choices)` / `dict(PersonalCuadrilla.RolCuadrilla.choices)` (carga masiva por Excel, 2 vistas) | `dict(Cargo.objects.filter(activo=True).values_list('codigo','nombre'))` | Carga masiva de Excel (bulk-update roles) deja de reconocer CUALQUIER cargo — 100% de filas a "no encontrado" |
| `apps/cuadrillas/views.py:989-991,1001,1302` | `miembro.rol_cuadrilla = rol_code` / `defaults={'rol_cuadrilla': rol, ...}` (rol es string) | `.rol_cuadrilla_id = rol_code` / `'rol_cuadrilla_id': rol` | Mismo `ValueError` que arriba, en 2 flujos de carga masiva |
| `apps/cuadrillas/views.py:1353,1368` | `'rol_cuadrilla': personal.rol_cuadrilla` en `JsonResponse` (2 endpoints API) | `personal.rol_cuadrilla_id` | `TypeError: Object of type Cargo is not JSON serializable` — 500 en autocompletado AJAX del form de asignación |
| `apps/cuadrillas/views.py:1539,1555` | `rol = personal.rol_cuadrilla` (objeto, 1 rama) vs `rol = 'LINIERO_I'` (string, otra rama) — tipos inconsistentes en la misma variable | Normalizar la rama `personal.rol_cuadrilla` → `personal.rol_cuadrilla_id` para que `rol` sea SIEMPRE string en este método; `defaults={'rol_cuadrilla_id': rol}` | Bug de tipo mixto: `self.COSTOS.get(rol, 0)` falla a devolver 0 silenciosamente cuando `rol` es un objeto `Cargo` (dict lookup nunca matchea) |
| `apps/cuadrillas/importers.py` | `ROL_TEXTO_A_CHOICE` hardcoded (texto libre Excel → código) + `defaults={'rol_cuadrilla': rol_choice}` (3 sitios: `_agregar_miembro`, `_agregar_miembro_s18`, `_crear_personal_cuadrilla`) | Ver §5 (retrofit dedicado del importer) | Ver §5 |
| `apps/cuadrillas/api.py:22,89` | `MiembroOut.rol_cuadrilla: str` schema + `rol_cuadrilla=m.rol_cuadrilla` | `rol_cuadrilla=m.rol_cuadrilla_id` (el tipo del schema `str` ya es correcto, no cambia) | Endpoint Ninja API `/api/cuadrillas/{id}` 500 al serializar `Cargo` como `str` |
| `apps/cuadrillas/admin.py:12,46-47,98-99` | `list_display`/`list_filter` con `rol_cuadrilla` (FK) | Ninguna — Django admin soporta FK nativamente en ambos | Ninguno (verificar visualmente, no requiere código) |
| `apps/cuadrillas/views_semanal.py:122,278` | `m.get_rol_cuadrilla_display()` (shim cubre) / `rol_cuadrilla=m.rol_cuadrilla` (propaga objeto `Cargo` completo al `.create()`, válido sin cambios) | Ninguna | Ninguno — confirmar con test de humo (duplicar semana) |
| `apps/financiero/reports.py:319-324,329` | `valores_dia.get(miembro.rol_cuadrilla, ...)` (bug preexistente: dict con keys lowercase 'supervisor'/'liniero'/'auxiliar' que NUNCA matchean los códigos uppercase reales — ya rota hoy, fuera de scope arreglarla) / `.rol_cuadrilla.title()` | `.rol_cuadrilla_id` en ambos sitios (preserva el comportamiento actual EXACTO, incluido el bug preexistente — no se corrige aquí, no es parte del pedido del cliente) | `AttributeError` al llamar `.title()` sobre un objeto `Cargo` |
| `apps/financiero/views.py:671,713` | `m.get_rol_cuadrilla_display()` (shim cubre) | Ninguna | Ninguno |
| `apps/financiero/views.py:1692-1694` | `rol_cuadrilla__in=ROLES_OPERATIVOS` (filter) + `.order_by('rol_cuadrilla')` + `.values(..., 'rol_cuadrilla')` | Ninguna — Django resuelve `__in`/`order_by`/`values` de un FK con `to_field` directamente contra el string sin joins | Ninguno — cubrir con journey igual (riesgo de que la teoría no aplique en este Django/versión exacta) |
| `apps/actividades/exporters.py:187` | `miembro.get_rol_cuadrilla_display()` (shim cubre) | Ninguna | Ninguno |
| `apps/core/management/commands/seed_data.py:308,319` | `defaults={"rol_cuadrilla": "supervisor"}` / `"liniero"` (strings **lowercase**, YA INVÁLIDOS hoy contra el enum real de códigos uppercase — bug preexistente que solo no truena porque `CharField+choices` no valida en `.create()`) | Corregir a `"rol_cuadrilla_id": "SUPERVISOR"` / `"LINIERO_I"` (uppercase, códigos reales) | `make seed` / bootstrapping de dev local rompe con `IntegrityError` de FK (antes silenciosamente guardaba un valor inválido; ahora la constraint real lo bloquea) |
| `templates/cuadrillas/detalle.html:324-325` | `{% if miembro.rol_cuadrilla == 'SUPERVISOR' %}` / `== 'LINIERO_I'` / `== 'LINIERO_II'` (comparación de objeto contra string) | `miembro.rol_cuadrilla.codigo == 'SUPERVISOR'` (y análogos) | Silencioso: el badge de color SIEMPRE cae al `else` (gris) — no da error, solo se ve mal. Es EXACTAMENTE el tipo de bug que un E2E de "solo status 200" no atrapa — journey debe assertar el color/clase |
| `templates/financiero/nomina.html:370-371` | Igual patrón (`m.rol_cuadrilla == 'SUPERVISOR'` / `'CONDUCTOR'`) | `m.rol_cuadrilla.codigo == 'SUPERVISOR'` | Mismo bug silencioso en el reporte de nómina |
| `templates/cuadrillas/colaboradores_lista.html:73` | `get_rol_cuadrilla_display` (shim cubre) | Ninguna | Ninguno |
| `templates/cuadrillas/colaboradores_form.html:46-51` | `{{ form.rol_cuadrilla }}` (ModelForm auto-render) | Ninguna en el template; SÍ acotar queryset en `PersonalCuadrillaForm.__init__` (§3) | Dropdown de "nuevo colaborador" muestra cargos inactivados si no se acota el queryset |
| `templates/cuadrillas/detalle.html:632-633` (JS `ROL_CUADRILLA_LABELS`) | `{% for value, label in roles_cuadrilla %}` — YA es agnóstico a la fuente | Ninguna (se arregla solo al retrofitear `views.py:225`) | Ninguno |

## 5. Retrofit del importer S18 (`apps/cuadrillas/importers.py`)

Estado actual: `ROL_TEXTO_A_CHOICE` (dict hardcoded, texto libre del Excel →
código canónico) se usa en 3 puntos (`_agregar_miembro` línea ~458,
`_agregar_miembro_s18` línea ~1029, `_crear_personal_cuadrilla` línea
~1071). Cuando el texto no matchea, cae a `'LINIERO_I'` por defecto +
advertencia sugiriendo "agregar a ROL_TEXTO_A_CHOICE" (mensaje que quedará
desactualizado una vez el catálogo sea dinámico).

**Retrofit (preserva estructura, NO reescribe el importer completo):**
1. `ROL_TEXTO_A_CHOICE` se mantiene tal cual — sigue siendo el mapa de alias
   de texto libre ("liniero", "ing residente", "sst"...) a código canónico,
   necesario porque el Excel NUNCA trae el código exacto, trae variantes.
2. Agregar un fallback de 2do nivel ANTES del default a LINIERO_I: si
   `cargo_raw.lower()` no está en `ROL_TEXTO_A_CHOICE`, normalizar
   (`cargo_raw.strip().upper().replace(' ', '_')`) y buscar ese valor
   directamente contra `Cargo.objects.filter(activo=True).values_list(
   'codigo', flat=True)` — esto permite que un cargo NUEVO agregado por el
   coordinador vía el CRUD (ej. "SOLDADOR") se reconozca en la próxima carga
   S18 sin tocar código, con solo escribir "Soldador" en el Excel.
3. Si ninguno de los 2 matchea: mantener el comportamiento actual
   (default `'LINIERO_I'` + advertencia), pero actualizar el texto del
   mensaje a "CARGO '{cargo_raw}' no reconocido, clasificado como LINIERO_I
   por defecto (agregarlo al maestro de Cargos en /cuadrillas/cargos/ si es
   un cargo nuevo real)" — el mensaje viejo referenciaba
   `ROL_TEXTO_A_CHOICE` (dict de código, invisible para el coordinador); el
   nuevo apunta a la UI que sí puede tocar.
4. En los 3 sitios, `rol_choice` sigue siendo **string** de principio a fin
   (nunca se resuelve a instancia `Cargo`) — el `defaults={'rol_cuadrilla':
   rol_choice}` pasa a `defaults={'rol_cuadrilla_id': rol_choice}`. Diff
   mínimo, sin reescribir la lógica de resolución.

## 6. Retrofit de tests

| Archivo | Qué rompe | Fix |
|---|---|---|
| `tests/factories/cuadrillas.py:50` | `rol_cuadrilla = "LINIERO"` — código que **nunca existió** en el enum (ni LINIERO_I ni LINIERO_II), solo "funcionaba" porque `CharField+choices` no valida en `.create()` | `rol_cuadrilla_id = "LINIERO_I"` (sustitución fiel — el test no depende de que sea justo "LINIERO", solo de que sea "un liniero") |
| `tests/integration/test_flujo_actividades.py:75-77` | `rol_cuadrilla='SUPERVISOR'` / `'LINIERO'` (x2, mismo código inválido) | `rol_cuadrilla_id='SUPERVISOR'` / `'LINIERO_I'` |
| `tests/e2e/test_flujo_mensual.py:64,66` | Igual patrón | Igual fix |
| `apps/campo/tests_b12.py:136,160` | `rol_cuadrilla='LINIERO'` (x2) | `rol_cuadrilla_id='LINIERO_I'` |
| `apps/cuadrillas/tests_issue_176.py` (~20 sitios) | `rol_cuadrilla=PersonalCuadrilla.RolCuadrilla.LINIERO_I` (la clase `RolCuadrilla` se ELIMINA) | Reemplazar por el string literal `'LINIERO_I'` (o `Cargo.objects.get(codigo='LINIERO_I')` donde el test compara igualdad de objeto) + kwarg `_id` donde se crea vía `.create()`/factory kwarg |
| `apps/cuadrillas/tests_s18.py:205,209,211` | `jt.rol_cuadrilla == 'LINIERO_I'` (comparación directa contra string) | `jt.rol_cuadrilla_id == 'LINIERO_I'` |
| `apps/cuadrillas/tests_b4.py:168-172` | Igual patrón de comparación | Igual fix |
| `apps/cuadrillas/tests_issue_178.py` (~8 sitios) | Mezcla de creación (`rol_cuadrilla='SUPERVISOR'`) y comparación (`assert m.rol_cuadrilla == 'MALACATERO'`) | `_id` en ambos casos |
| `apps/cuadrillas/tests_issue_178_bc.py:68-72` | `rol_cuadrilla=rol_cuadrilla` (variable de loop, string) | `rol_cuadrilla_id=rol_cuadrilla` |
| `tests/unit/test_cuadrillas.py:137,154-161,250` | `CuadrillaMiembro.RolCuadrilla.SUPERVISOR` etc. (la clase se elimina) + `CuadrillaMiembroFactory(rol_cuadrilla=rol)` | Reemplazar constantes por strings literales; el kwarg de factory pasa a `rol_cuadrilla_id` (o se agrega un parámetro custom a la factory que internamente asigna `_id`, más limpio para no tocar 8 call sites de test) |

**Recomendación de implementación para minimizar diffs de test:** en
`tests/factories/cuadrillas.py`, cambiar `CuadrillaMiembroFactory.rol_cuadrilla`
por `rol_cuadrilla_id = "LINIERO_I"` (factory_boy soporta asignar directamente
al `attname` de un FK). Esto hace que la MAYORÍA de los tests que NO
sobrescriben `rol_cuadrilla=` en el `.create()`/`build()` sigan funcionando
sin tocarlos — solo los que SÍ pasan `rol_cuadrilla=<algo>` explícito
necesitan el rename a `rol_cuadrilla_id=`.

## 7. Sub-items — Sprint A

| # | Sub-item | Archivos | Tests | Dependencias | Complexity | Deployable solo | Estado |
|---|---|---|---|---|---|---|---|
| A1 | Modelo `Cargo` + migración schema + data migration (seed 14 códigos desde la unión de ambos `RolCuadrilla`) | `apps/cuadrillas/models_cargo.py` (nuevo), `apps/cuadrillas/models.py` (re-export), `apps/cuadrillas/migrations/0018_cargo.py`, `0019_seed_cargos.py` | Migración aplica limpio contra copia de esquema; `Cargo.objects.count() == 14` tras seed; códigos coinciden 1:1 con el enum viejo | - | low | **sí** (aditivo puro, cero impacto en tablas existentes) | ⏳ pendiente |
| A2 | CRUD `Cargo` (list/crear/editar/inactivar, `codigo` read-only al editar) + link navbar Parametrización | `apps/cuadrillas/views.py` (nueva sección), `apps/cuadrillas/urls.py`, `apps/cuadrillas/forms_cargo.py` (nuevo), `templates/cuadrillas/cargos_lista.html` (nuevo), `templates/cuadrillas/cargos_form.html` (nuevo), `templates/components/sidebar.html` | Crear/editar/inactivar; código duplicado rechazado; código no editable en `editar`; cargo inactivo no aparece en dropdowns que lo consumen | A1 | medium | **sí** (mismo motivo que A1) | ⏳ pendiente |
| A3 | Migración de esquema: `PersonalCuadrilla.rol_cuadrilla` y `CuadrillaMiembro.rol_cuadrilla` de `CharField+choices` a `FK(Cargo, to_field='codigo')` (unificado) | `apps/cuadrillas/models_base.py`, `apps/cuadrillas/migrations/0020_*.py`, `0021_*.py` | Verificación pre-migración (0 filas huérfanas, ya confirmado); tras migrar, ≥1 `PersonalCuadrilla` y ≥1 `CuadrillaMiembro` LEGACY (existentes en prod, no fixtures) conservan su código exacto | A1 | high | no | ⏳ pendiente |
| A4 | Retrofit de call sites (shim `get_rol_cuadrilla_display()` + Retrofit Ledger completo §4, excluye importer) | `apps/cuadrillas/{models_base,views,views_semanal,api,forms_personal}.py`, `apps/financiero/{reports,views}.py`, `apps/actividades/exporters.py`, `apps/core/management/commands/seed_data.py`, `templates/cuadrillas/detalle.html`, `templates/financiero/nomina.html` | Smoke de cada superficie tocada (ver Journey); `make seed` corre sin `IntegrityError` | A3 | high | no | ⏳ pendiente |
| A5 | Retrofit importer S18 (§5: fallback a catálogo dinámico + mensaje actualizado) | `apps/cuadrillas/importers.py` | Import con cargo nuevo del catálogo (no en `ROL_TEXTO_A_CHOICE`) se reconoce; cargo desconocido sigue con fallback LINIERO_I + advertencia con mensaje nuevo | A3 | medium | no | ⏳ pendiente |
| A6 | Retrofit de tests (§6, incluye fix de `'LINIERO'` inválido preexistente) | `tests/factories/cuadrillas.py`, `apps/cuadrillas/tests_{issue_176,s18,b4,issue_178,issue_178_bc}.py`, `tests/unit/test_cuadrillas.py`, `tests/integration/test_flujo_actividades.py`, `tests/e2e/test_flujo_mensual.py`, `apps/campo/tests_b12.py` | `pytest apps/cuadrillas tests/unit tests/integration tests/e2e apps/campo -k cuadrilla` en verde | A3, A4, A5 | medium | no | ⏳ pendiente |
| A7 | Comentario de cierre con URLs + registros legacy validados + estado explícito de scope (bounce previo cerrado 🟢 se mantiene; esto es ampliación, no corrección) | - | - | A1-A6 | trivial | no | ⏳ pendiente |

### DAG de dependencias

```
A1 (Cargo model+seed, deployable_solo)
 └─→ A2 (CRUD Cargo, deployable_solo)
 └─→ A3 (FK conversion, alto riesgo)
      └─→ A4 (retrofit call sites)
      └─→ A5 (retrofit importer S18)
           └─→ A6 (retrofit tests, depende de A3+A4+A5)
                └─→ A7 (comentario cierre)
```

**Empaquetado de deploys:** A1+A2 pueden ir en un PRIMER deploy aislado
(bajo riesgo, valor inmediato — el cliente ya ve y gestiona el catálogo,
aunque `PersonalCuadrilla`/`CuadrillaMiembro` sigan con el campo viejo).
A3+A4+A5+A6 DEBEN ir en un SEGUNDO deploy atómico (un solo PR/migración) —
desplegar A3 sin A4/A5 rompe en producción CUALQUIER vista que toque
`rol_cuadrilla` (ver Retrofit Ledger, columna "Riesgo si se omite": varios
son 500 directos). Si el tiempo no alcanza para ambos deploys en esta
pasada, A1+A2 solos SÍ son un incremento válido y demostrable a Andrea/
cliente; A3-A6 quedan como continuación explícita del mismo issue (no como
"completo" hasta que el segundo deploy promueva 100% del tráfico).

## 8. Riesgo global

**Riesgo #1 (el más alto): la migración de esquema (A3) pierde o corrompe
datos legacy.** Mitigado por: (a) verificación de datos huérfanos YA
ejecutada en F2 con resultado limpio (0 filas fuera del set válido), (b)
diseño `to_field='codigo'` que evita un rename/retype físico de columna
(la migración es aditiva a nivel de constraint, no reescribe valores), (c)
`AlterField` es reversible por Django sin pérdida de datos, (d) re-verificar
el query de huérfanos inmediatamente antes de aplicar en F3 (por si hubo
escritura entre el F2 y el deploy), (e) journey de F3 valida explícitamente
que un `PersonalCuadrilla` y un `CuadrillaMiembro` REALES de prod (IDs
documentados abajo) conservan su código tras la migración.

**Riesgo #2: retrofit incompleto dejando un call site con comparación
silenciosa rota** (el patrón `== 'STRING'` en templates — no da 500, solo se
ve mal). Mitigado por el Retrofit Ledger exhaustivo (§4) y por journeys que
assertan la CLASE CSS/badge, no solo status 200.

**Riesgo #3: blast radius mayor al estimado por F1 en la siguiente pasada de
grep** (si hay algún call site no encontrado por los patrones usados). Se
recomienda que F3, antes de dar por cerrado A4, corra
`grep -rn "rol_cuadrilla\|RolCuadrilla" apps/ templates/ tests/` de nuevo
sobre su propio diff y confirme que cada resultado está en el Retrofit
Ledger o es justificadamente nuevo código introducido por este mismo plan.

**Riesgo #4 (bajo): `seed_data.py` y factories de test tenían strings
inválidos preexistentes** ('LINIERO' sin sufijo, 'supervisor'/'liniero' en
minúscula) que la validación débil de `CharField+choices` toleraba. La FK
real los expone como fallas — no es una regresión de este plan, es deuda
pre-existente que la migración obliga a pagar (documentado en §6, Riesgo #4
no bloquea el deploy de A3 en prod ya que son solo dev/test, pero si no se
corrigen en A6 rompen `make seed` y la suite de tests).

## Registros legacy de referencia (para la validación de A3 en F3)

- `personal_cuadrilla.id = 2d1fe4f3-d7ab-497e-9618-d80dab73f170` (Andrea,
  documento 43482087, `rol_cuadrilla = LINIERO_I`)
- `cuadrilla_miembros.id = 89d24a85-55da-47dc-ae60-77e9c367fe2e` (Casimiro
  Palomino Armesto, cuadrilla `22-2026-NOVEDADES`, `rol_cuadrilla =
  SUPERVISOR`, `cargo = JT_CTA`)

Ambos deben mantener el MISMO `rol_cuadrilla_id` (string) exactamente después
de aplicar las migraciones 0020/0021 — es la aserción central del riesgo #1.
