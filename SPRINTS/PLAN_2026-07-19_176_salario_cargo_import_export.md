# PLAN — Salario enlazado a Cargo + Import/Export masivo (issue #176, bounce 3)

**Fecha:** 2026-07-19
**Issue:** [Indunnova16/Instelec#176](https://github.com/Indunnova16/Instelec/issues/176)
**Estado:** Planning F2 completado, listo para F3 sprint_exec
**Precedente de formato:** `Instelec/SPRINTS/PLAN_2026-07-10_maestro_cargos.md` (Maestro 3: Cargos,
bounce 2) — mismo issue, blast radius mucho menor esta vez (1 migración aditiva, sin
retype/FK nuevo; el FK `rol_cuadrilla → Cargo` ya existe desde el bounce anterior).

## ⚠️ REPROCESO — bounce 3 confirmado (`reproceso_rate.py`)

Este issue ya rebotó 2 veces por el MISMO patrón: se construye la pieza pedida en el
momento sin re-chequear el issue ORIGINAL completo en busca de vínculos obvios con lo
ya entregado (bounce 1: maestros construidos, no en navbar; bounce 2: Maestro Cargo
construido, sin el salario que el issue original ya pedía). Este plan existe
precisamente para no dejar un 4º hueco escondido — cada fila de la tabla de
entregables de abajo se cierra con evidencia, no con intención.

## Contexto — qué pide el cliente esta vuelta (2026-07-17)

1. `Cargo.salario_base` — el maestro Cargo (bounce 2) no tiene salario; el issue
   original (2026-06-29) ya pedía "salario base... permite calcular costo por
   día/hora en reportes" y nadie conectó ese requisito con el catálogo nuevo.
2. Autocompletado (editable) del salario del Colaborador desde `Cargo.salario_base`
   al crear/editar, sin bloquear el campo.
3. Import/export masivo en `/cuadrillas/cargos/` (código, nombre, salario base).
4. Import masivo de Colaboradores YA EXISTE y funciona (`PersonalCuadrillaUploadView`,
   validado en vivo por el cliente el mismo día) pero vive solo en `/cuadrillas/`
   (modal), no en `/cuadrillas/colaboradores/` — exponerlo ahí + construir su export.
5. Orden de dependencia Cargo→Colaboradores documentado en el copy del import.

**Tipo de pedido — mixto** (confirmado por F1, no se re-litiga aquí): (2) es
FIX_INCOMPLETO real sobre el bounce 2; (4)-exposición es FIX_INCOMPLETO real sobre
el bounce 1 (mismo patrón: feature construida, no navegable desde su pantalla
natural); (1) el campo en sí es aditivo pero cierra un vínculo faltante; (3) y el
export de Colaboradores son AMPLIACIÓN genuina (nunca se pidieron antes). Se trabajan
como una sola tanda v1.0 — el cliente lo pidió junto y es acotado (~7h F1).

## Tabla de entregables (gate anti-FIX_INCOMPLETO — persistida ANTES de codear)

| # | Entregable | Evidencia esperada (URL/campo/comportamiento) | Estado hoy (verificado en código, 2026-07-19) |
|---|---|---|---|
| 1 | `Cargo.salario_base` (DecimalField 12,2 default=0) + migración aditiva | `makemigrations --check` limpio; CRUD `/cuadrillas/cargos/` permite editar salario | ❌ no existe — confirmado: `models_cargo.py` solo tiene `codigo/nombre/activo` |
| 2 | Autocompletado editable: cambiar `rol_cuadrilla` en el form de Colaborador precarga `salario_base` (create Y edit), campo sigue editable | E2E: seleccionar cargo → input se precarga; usuario lo sobreescribe → valor manual persiste al guardar | ❌ no existe — `colaboradores_form.html` no tiene JS; `PersonalCuadrillaForm` no lo hace |
| 3 | `PersonalCuadrilla.salario_base` sigue siendo el campo mostrado/editado en Colaboradores (Cargo solo aporta default al autocompletar) | Sin cambio de comportamiento — ver ⚠️ hallazgo abajo sobre qué SÍ y qué NO lee realmente cada reporte | 🟡 ver hallazgo — el campo existe y se edita en el CRUD, pero **ningún reporte financiero lo consume hoy** (contrario al supuesto original) |
| 4 | Import/export masivo `/cuadrillas/cargos/` (código, nombre, salario_base), upsert por código | Cargar Excel crea código nuevo O actualiza nombre+salario de un código existente; exportar genera xlsx con las 3 columnas | ❌ no existe ningún import/export del catálogo Cargo (el botón "Subir Excel de Cargos" en `detalle.html` es en realidad `miembros_upload`, sube miembros de UNA cuadrilla, no toca el catálogo) |
| 5 | Import masivo de Colaboradores expuesto en `/cuadrillas/colaboradores/` | Botón+modal en `colaboradores_lista.html` que postea al mismo `personal_upload` ya funcional | 🟡 el import YA FUNCIONA (`PersonalCuadrillaUploadView`, validado en vivo 2026-07-17 23:10 por el cliente) pero solo vive en el modal de `/cuadrillas/` (`lista.html:303-333`) |
| 6 | Export masivo de Colaboradores (documento, nombre, cargo, salario, fecha_ingreso, fecha_salida) | Botón en `colaboradores_lista.html` → xlsx descargado con esas columnas | ❌ no existe |
| 7 | Copy de orden de dependencia (Cargos antes que Colaboradores) en el modal de import de Colaboradores | Texto visible en el modal de `colaboradores_lista.html` | ❌ no existe |
| 8 | Decisión sobre `CostoRolAPIView` (3ª fuente divergente hallada por F1) | Ver sección dedicada abajo | ✅ decidido — **huérfano confirmado, se retrofitea** (ver más abajo) |
| 9 | Comentario de cierre con post-mortem bounce 3 + marcador `REPROCESO_DATA` | Publicado por F6 al final | ⏳ previsto (sub-item A10, este plan deja el contenido esperado) |

## ⚠️ Hallazgo crítico (no reportado por F1 — cambia el entregable #3 de "no tocar" a "documentar con precisión")

F1 dio por bueno, sin re-verificar el código exacto, que *"`financiero/reports.py` y
`views_semanal.py` siguen usando `PersonalCuadrilla.salario_base`"* y las instrucciones
de Miguel asumen lo mismo ("NO cambiar esos archivos, solo agregar un test de
regresión que confirme que siguen leyendo de `PersonalCuadrilla.salario_base`"). Re-grep
completo (`grep -rn salario_base apps/`, excluyendo tests/migraciones) muestra que
**eso es falso hoy**: `salario_base` NO aparece ni una sola vez en `financiero/reports.py`
ni en `views_semanal.py`. Lo que realmente usan:

- `financiero/reports.py::_calcular_costos_personal` (línea ~320) tiene su **propio**
  dict hardcoded `valores_dia = {...}` con keys en minúscula (`'supervisor'`,
  `'liniero'`...) que **nunca matchean** los códigos reales en mayúscula — bug
  preexistente **ya documentado y declarado fuera de scope** en el plan del
  2026-07-10 ("bug preexistente, ya rota hoy, fuera de scope arreglarla"). Sigue
  fuera de scope en esta vuelta también — no se toca.
- `views_semanal.py` (líneas 278-280) copia el campo **persistido**
  `CuadrillaMiembro.costo_dia` al duplicar una semana — un valor que se fija UNA
  VEZ al crear el miembro (típicamente desde `CuadrillaMasivaUploadView.COSTOS`,
  ver abajo), no algo que se recalcule desde `salario_base` en cada lectura.

**Consecuencia práctica que hay que comunicarle al cliente en el cierre (para no
generar un bounce 4):** después de esta vuelta, `Cargo.salario_base` alimenta el
autocompletado del formulario de Colaborador — **NO** hace que los reportes
financieros de cuadrilla semanal reflejen el salario real, porque esos reportes
usan una fuente de datos completamente distinta (y con un bug preexistente ya
conocido). El pedido original del issue ("permite calcular costo/día en reportes")
**no queda resuelto por este alcance** — es una decisión de scope explícita de
Miguel (instrucción: no tocar `reports.py`/`views_semanal.py`), no un vacío nuevo,
pero DEBE quedar declarada así en el comentario de cierre, no asumida como resuelta.

**Sub-item A4 (abajo) se ajusta en consecuencia**: en vez de un test que afirme una
premisa falsa ("reports.py lee salario_base"), el test de regresión confirma que
el comportamiento ACTUAL (con su bug incluido) no se rompe por los cambios de este
plan — que es lo único que se puede honestamente garantizar sin tocar esos archivos.

## Decisión: `CostoRolAPIView` — huérfano confirmado, se retrofitea igual

F1 marcó esto como pendiente de decisión. Verificado con grep exhaustivo
(`grep -rn "costo_rol_api\|CostoRolAPIView" --include=*.html --include=*.js --include=*.py .`):
la ÚNICA aparición fuera de su propia definición es el registro en `urls.py:28`
(`path('api/costo-rol/', ..., name='costo_rol_api')`). **Cero templates, cero JS lo
llaman.** Es código muerto desde que se escribió.

**Además, encontré un hallazgo que F1 NO reportó**: el mismo dict hardcoded de
costo-por-rol está duplicado una TERCERA vez (además de `CostoRolAPIView` y de
`financiero/reports.py::valores_dia`) en `CuadrillaMasivaUploadView.COSTOS`
(`views.py:1428-1434`) — y ESE sí tiene consumidor real: alimenta
`CuadrillaMiembro.costo_dia` en la carga masiva de cuadrillas (`views.py:1572`,
`self.COSTOS.get(rol, 0)`). Es decir, hay al menos **4 fuentes de costo/salario por
rol** en el código hoy: `CostoRolAPIView.costos` (huérfana), `CuadrillaMasivaUploadView.
COSTOS` (viva), `financiero/reports.py::valores_dia` (viva, con bug de casing), y
`PersonalCuadrilla.salario_base` (viva, editable, pero no consumida por reportes) —
a la que se suma esta vuelta `Cargo.salario_base` (nueva, alimenta solo el
autocompletado).

**Decisión (siguiendo el default de Miguel, alcance acotado a lo pedido):**
1. `CostoRolAPIView` se retrofitea — reemplaza su dict hardcoded por lectura de
   `Cargo.salario_base` y se convierte en el endpoint real del autocompletado (A2/A3
   abajo). Deja de ser huérfano: pasa a tener su primer consumidor real en 6 años.
2. `CuadrillaMasivaUploadView.COSTOS` y `financiero/reports.py::valores_dia` **NO se
   tocan esta vuelta** — están fuera del pedido del cliente y tocarlos expande el
   scope más allá de lo autorizado (~7h). Quedan documentados aquí explícitamente
   como una **decisión de scope comunicada**, no un descubrimiento escondido, para
   que un futuro issue de "unificar las fuentes de costo por rol" no sea sorpresa.

## 1. `Cargo.salario_base` + migración (A1)

`apps/cuadrillas/models_cargo.py` — agregar campo, mismo patrón que
`PersonalCuadrilla.salario_base`:

```python
salario_base = models.DecimalField(
    'Salario base',
    max_digits=12,
    decimal_places=2,
    default=0,
    help_text='Salario mensual sugerido para este cargo (default/sugerencia al '
               'autocompletar el salario de un Colaborador; el valor efectivo para '
               'costos/reportes sigue siendo PersonalCuadrilla.salario_base).',
)
```

Migración `apps/cuadrillas/migrations/0022_cargo_salario_base.py` — `AddField`
puro, aditivo, default=0 aplica a las 15 filas existentes sin pérdida de datos
(confirmado en prod: `SELECT count(*) FROM cargos` = 15, cero filas huérfanas
relevantes aquí porque no hay FK/retype involucrado).

`apps/cuadrillas/forms_cargo.py` (`CargoForm`) — agregar `"salario_base"` a
`Meta.fields` + widget `NumberInput` (mismo patrón que
`PersonalCuadrillaForm.salario_base`).

`templates/cuadrillas/cargos_form.html` — agregar bloque de campo (mismo patrón
que los demás campos del form, entre `nombre` y `activo`).

`templates/cuadrillas/cargos_lista.html` — agregar:
- `{% load humanize %}` (falta hoy — el template NO lo carga, a diferencia de
  `colaboradores_lista.html` que sí; sin esto `intcomma` falla silenciosamente)
- columna "Salario Base" en `<thead>`/`<tbody>` — mismo patrón que
  `colaboradores_lista.html:62,74`: `${{ cargo.salario_base|floatformat:0|intcomma }}`

**Backfill de salarios reales por cargo: BLOQUEADO, pendiente Alcides/Andrea.**
El cliente mismo aclaró que `Documentacion/BASE DE DATOS.xlsx` NO es fuente
confiable. `Cargo.salario_base` se puebla en 0 por default (mismo comportamiento
que `PersonalCuadrilla.salario_base` tiene hoy) — el feature es 100% funcional sin
esto, pero el autocompletado no aportará valores útiles hasta que lleguen los
datos reales. **Declarar explícitamente en el cierre** — decisión de scope ya
comunicada, no un hueco nuevo si en 2 semanas el cliente nota "todos los cargos
tienen salario 0".

## 2. Retrofit `CostoRolAPIView` (A2)

`apps/cuadrillas/views.py:1385` — reemplazar el dict hardcoded:

```python
class CostoRolAPIView(LoginRequiredMixin, RoleRequiredMixin, View):
    """API endpoint: costo/salario base de un Cargo.

    Retrofit issue #176 (bounce 3): antes tenía un dict hardcoded de costos por
    rol (huérfano — grep 2026-07-19 confirmó CERO consumidores). Se retrofitea
    para leer Cargo.salario_base y se convierte en el backend real del
    autocompletado de colaboradores_form.html (A3). Mantiene el contrato JSON
    original (costo_dia/es_conductor/conductor_interno) para minimizar diff —
    NO se renombra `costo_dia` pese a que hoy contiene un valor MENSUAL (mismo
    nombre confuso que ya traía el dict original, fuera de scope corregirlo).
    """
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'supervisor']

    def get(self, request, *args, **kwargs):
        rol = request.GET.get('rol', '').strip()
        if not rol:
            return JsonResponse({'costo_dia': 0})

        cargo = Cargo.objects.filter(codigo=rol, activo=True).first()
        # float(): Decimal NO es JSON-serializable por default (JsonResponse
        # truena con TypeError si se pasa el Decimal crudo).
        costo = float(cargo.salario_base) if cargo else 0

        es_conductor = rol == 'CONDUCTOR'
        conductor_interno = request.GET.get('conductor_interno', 'true') == 'true'

        return JsonResponse({
            'costo_dia': costo,
            'es_conductor': es_conductor,
            'conductor_interno': conductor_interno if es_conductor else None,
        })
```

**Gotcha documentado para F3:** `Cargo.salario_base` es `DecimalField` — pasarlo
crudo a `JsonResponse` truena (`TypeError: Object of type Decimal is not JSON
serializable`). El `float()` de arriba es obligatorio, no cosmético.

## 3. Autocompletado JS en `colaboradores_form.html` (A3)

Los ids de los campos ya existen y son deterministas (Django default
`id_<field_name>`, confirmado leyendo el template real): `id_rol_cuadrilla`
(select) e `id_salario_base` (input number). Agregar al final del bloque
`{% block content %}`:

```html
<script>
document.addEventListener('DOMContentLoaded', function () {
    var selectCargo = document.getElementById('id_rol_cuadrilla');
    var inputSalario = document.getElementById('id_salario_base');
    if (!selectCargo || !inputSalario) return;

    // Issue #176 (A3): dispara SOLO en el gesto explícito de cambiar el
    // select -- nunca en page load -- para no pisar un valor manual ya
    // guardado en edición sin que el usuario haya tocado el cargo.
    selectCargo.addEventListener('change', function () {
        var codigo = selectCargo.value;
        if (!codigo) return;
        fetch("{% url 'cuadrillas:costo_rol_api' %}?rol=" + encodeURIComponent(codigo))
            .then(function (resp) { return resp.json(); })
            .then(function (data) {
                inputSalario.value = data.costo_dia;
            })
            .catch(function () {
                // Red/JS error: el campo sigue editable manualmente, no se bloquea nada.
            });
    });
});
</script>
```

**Comportamiento documentado (responde `preguntas_pendientes_cliente` de F1):**
el precargado ocurre en CADA `change` del select, incluso en edición de un
colaborador que ya tenía un salario manual — se interpreta como intencional
porque el usuario mismo disparó el evento cambiando el cargo. Si el usuario
edita `salario_base` directamente SIN tocar el select, ese valor se preserva
hasta el submit. Aplica igual en `ColaboradorCreateView` y `ColaboradorEditView`
(mismo template `colaboradores_form.html` para ambos modos).

## 4. Import/export masivo de Cargo (A5)

`apps/cuadrillas/urls.py` — agregar:
```python
path('cargos/subir/', views.CargoUploadView.as_view(), name='cargos_upload'),
path('cargos/exportar/', views.CargoExportView.as_view(), name='cargos_export'),
```

`apps/cuadrillas/views.py` — nuevas vistas junto a la sección de Cargos:

```python
class CargoUploadView(LoginRequiredMixin, RoleRequiredMixin, View):
    """Carga masiva de Cargos (issue #176, A5). Upsert por código: crea el
    código si no existe, actualiza nombre+salario_base si ya existe (NUNCA
    reasigna el propio código -- es el campo de lookup)."""
    allowed_roles = ['admin', 'director', 'coordinador']

    def post(self, request, *args, **kwargs):
        import openpyxl
        from io import BytesIO
        from decimal import Decimal, InvalidOperation

        archivo = request.FILES.get('archivo')
        if not archivo:
            messages.error(request, 'Debe seleccionar un archivo.')
            return redirect('cuadrillas:cargos_lista')

        creados = actualizados = 0
        errores = []
        try:
            wb = openpyxl.load_workbook(BytesIO(archivo.read()))
            ws = wb.active
            for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                if not row or not row[0]:
                    continue
                try:
                    codigo = str(row[0]).strip().upper()
                    nombre = str(row[1]).strip() if len(row) > 1 and row[1] else codigo
                    try:
                        salario_base = Decimal(str(row[2]).replace(',', '').strip() or '0') if len(row) > 2 and row[2] else Decimal('0')
                    except InvalidOperation:
                        salario_base = Decimal('0')

                    _, created = Cargo.objects.update_or_create(
                        codigo=codigo,
                        defaults={'nombre': nombre, 'salario_base': salario_base, 'activo': True},
                    )
                    creados += created
                    actualizados += (not created)
                except Exception as row_exc:
                    errores.append(f'Fila {idx}: {row_exc}')

            msg = f'Cargos cargados: {creados} nuevos, {actualizados} actualizados.'
            if errores:
                msg += f' Errores: {len(errores)} filas.'
            messages.success(request, msg)
        except Exception as e:
            messages.error(request, f'Error al procesar archivo: {str(e)}')

        return redirect('cuadrillas:cargos_lista')


class CargoExportView(LoginRequiredMixin, RoleRequiredMixin, View):
    """Exporta el catálogo Cargo a xlsx (issue #176, A5)."""
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente']

    def get(self, request, *args, **kwargs):
        import openpyxl
        from io import BytesIO

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Cargos'
        ws.append(['Código', 'Nombre', 'Salario Base'])
        for cargo in Cargo.objects.all().order_by('nombre'):
            ws.append([cargo.codigo, cargo.nombre, float(cargo.salario_base)])

        buffer = BytesIO()
        wb.save(buffer)
        response = HttpResponse(
            buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = 'attachment; filename="cargos.xlsx"'
        return response
```

`templates/cuadrillas/cargos_lista.html` — agregar botón "Importar" (abre modal,
mismo patrón visual que el modal `#modal-personal` de `lista.html`) + link
"Exportar" (GET directo a `cargos_export`, sin modal — igual que "📥 Plantilla"
en `lista.html`). Modal nuevo `id="modal-importar-cargos"`, form
`action="{% url 'cuadrillas:cargos_upload' %}"`, columnas esperadas en el copy:
"Código | Nombre | Salario Base".

## 5. Exponer import de Colaboradores + su export (A6, A7)

`templates/cuadrillas/colaboradores_lista.html` — agregar botón "Importar
Colaboradores" que abre un modal **clonado** del `#modal-personal` de
`lista.html` (mismo `action="{% url 'cuadrillas:personal_upload' %}"` — el
import YA FUNCIONA, no se toca su vista, solo se le da una segunda entrada
visual). Modal nuevo `id="modal-importar-colaboradores"` (no reusar el id
`modal-personal` — vive en otro template). **Agregar al copy del modal (A7)**
el orden de dependencia pedido por el cliente:

> "Los Cargos referenciados en la columna Cargo deben existir primero en
> /cuadrillas/cargos/ — si un código no coincide con ningún cargo activo, la
> fila cae al default (Liniero I)."

`apps/cuadrillas/urls.py` — agregar:
```python
path('colaboradores/exportar/', views.ColaboradorExportView.as_view(), name='colaboradores_export'),
```

`apps/cuadrillas/views.py`:
```python
class ColaboradorExportView(LoginRequiredMixin, RoleRequiredMixin, View):
    """Exporta el maestro de Colaboradores a xlsx (issue #176, A6)."""
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente']

    def get(self, request, *args, **kwargs):
        import openpyxl
        from io import BytesIO

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Colaboradores'
        ws.append(['Documento', 'Nombre', 'Cargo', 'Salario Base', 'Fecha Ingreso', 'Fecha Salida'])
        for p in PersonalCuadrilla.objects.select_related('rol_cuadrilla').all().order_by('nombre'):
            ws.append([
                p.documento, p.nombre,
                p.rol_cuadrilla.nombre if p.rol_cuadrilla_id else '',
                float(p.salario_base),
                p.fecha_ingreso.strftime('%Y-%m-%d') if p.fecha_ingreso else '',
                p.fecha_salida.strftime('%Y-%m-%d') if p.fecha_salida else '',
            ])

        buffer = BytesIO()
        wb.save(buffer)
        response = HttpResponse(
            buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = 'attachment; filename="colaboradores.xlsx"'
        return response
```

## 6. Nota aparte (NO fixear, solo observar): `documento` con sufijo `.0` en prod

Al inspeccionar `personal_cuadrilla` en prod encontré 3 filas con `documento` en
formato `'9999000001.0'` (con punto decimal) — típico de que `openpyxl` entregó
la celda como float y `str(row[1])` no lo normalizó antes de guardar (bug
preexistente de `PersonalCuadrillaUploadView`, ya en prod desde antes de este
issue). NO es parte del pedido de #176 y tocarlo expande el scope — se deja
documentado acá para que, si el cliente lo nota alguna vez, no se confunda con
un efecto de este cambio. No se abre issue proactivamente (decisión de Miguel
si vale la pena).

## Sub-items — Sprint A (deploy único, ~7h total, sin gate de scope: 0 epic, 0 high)

| # | Sub-item | Archivos | Tests | Dependencias | Complexity | Deployable solo | Estado |
|---|---|---|---|---|---|---|---|
| A1 | `Cargo.salario_base` + migración 0022 + form + templates (§1) | `models_cargo.py`, `forms_cargo.py`, `migrations/0022_cargo_salario_base.py`, `cargos_form.html`, `cargos_lista.html` | Migración aplica limpio; CRUD permite crear/editar con salario; `{% load humanize %}` presente | - | low | sí (aditivo puro) | ⏳ pendiente |
| A2 | Retrofit `CostoRolAPIView` — lee `Cargo.salario_base`, cast `float()` (§2) | `apps/cuadrillas/views.py` | `GET /cuadrillas/api/costo-rol/?rol=X` devuelve `costo_dia` correcto; rol inexistente → 0; sin 500 por Decimal | A1 | low | no | ⏳ pendiente |
| A3 | Autocompletado JS en `colaboradores_form.html` (§3) | `templates/cuadrillas/colaboradores_form.html` | E2E: cambiar cargo precarga; edición manual posterior se preserva al guardar | A2 | medium | no | ⏳ pendiente |
| A4 | Test de regresión financiero (premisa corregida — ver hallazgo crítico) | Ninguno productivo — solo test; referencia de lectura `apps/financiero/reports.py`, `apps/cuadrillas/views_semanal.py` | Test confirma que `_calcular_costos_personal` sigue usando su propio `valores_dia` (no `Cargo.salario_base` ni `PersonalCuadrilla.salario_base`) y que `views_semanal.py` sigue copiando `CuadrillaMiembro.costo_dia`; smoke E2E render-only de `/financiero/nomina/` | A1, A2, A3 | low | no | ⏳ pendiente |
| A5 | Import/export masivo Cargo — `CargoUploadView` (upsert), `CargoExportView` (§4) | `apps/cuadrillas/views.py`, `apps/cuadrillas/urls.py`, `templates/cuadrillas/cargos_lista.html` | Import crea código nuevo Y actualiza uno existente (2 filas distintas); export descarga xlsx con 3 columnas correctas | A1 | medium | no | ⏳ pendiente |
| A6 | Exponer import Colaboradores + `ColaboradorExportView` (§5) | `templates/cuadrillas/colaboradores_lista.html`, `apps/cuadrillas/views.py`, `apps/cuadrillas/urls.py` | Modal visible y postea a `personal_upload` (sin tocar esa vista); export descarga xlsx con 6 columnas correctas | - | medium | no | ⏳ pendiente |
| A7 | Copy de orden de dependencia Cargo→Colaboradores en el modal de import (§5) | `templates/cuadrillas/colaboradores_lista.html` (mismo archivo que A6, línea separada de trabajo) | Texto visible en el modal | A6 | trivial | no | ⏳ pendiente |
| A8 | Tests unitarios (Cargo CRUD+salario, `costo_rol_api`, import/export Cargo round-trip, export Colaboradores, regresión A4) | `apps/cuadrillas/tests_issue_176_salario.py` (nuevo) | `pytest apps/cuadrillas -k 176_salario` en verde | A1-A7 | medium | no | ⏳ pendiente |
| A9 | Smoke E2E (journey YAML, ver `$RUN_DIR/journeys/Instelec_176.yaml`) | - | 5 journeys (A1, A2+A3 combinados, A5, A6, A4) contra revisión promovida | A8 | low | no | ⏳ pendiente |
| A10 | Comentario de cierre — post-mortem bounce 3 + `REPROCESO_DATA` (contenido previsto abajo) | - | - | A9 | trivial | no | ⏳ pendiente |

### DAG de dependencias

```
A1 (Cargo.salario_base, deployable_solo)
 └─→ A2 (retrofit CostoRolAPIView)
      └─→ A3 (autocompletado JS)
           └─→ A4 (regresión financiero, corre última de las 4 para confirmar
                    que nada de A1-A3 filtró hacia reports.py/views_semanal.py)
 └─→ A5 (import/export Cargo)
A6 (exponer import Colaboradores + export) ── independiente, sin deps de A1-A5
 └─→ A7 (copy dependencia, mismo archivo que A6)
[A1..A7] └─→ A8 (tests unitarios) └─→ A9 (journeys E2E) └─→ A10 (cierre)
```

**Empaquetado de deploy:** UN solo PR / UN solo deploy (a diferencia del bounce 2,
que sí requirió 2 deploys por el riesgo de la conversión FK). Esta vuelta es
aditiva de punta a punta (1 campo nuevo + 2 endpoints nuevos + JS + 2 templates
retocados) — no hay razón para partirlo.

## Riesgos y mitigaciones

- **Riesgo bajo — migración 0022**: `AddField` puro con `default=0`, cero riesgo
  de pérdida de datos, reversible trivialmente (`DROP COLUMN`).
- **Riesgo medio — JSON serialización de `Decimal`**: ya mitigado en el código de
  §2 (`float()` explícito) — si F3 lo omite, `CostoRolAPIView` da 500 en el
  primer click del autocompletado (no en tests unitarios con SQLite si el test
  no fuerza serialización real vía `JsonResponse` — usar `self.client.get(...)`,
  no llamar al método Python directo, para que el test SÍ ejercite `JsonResponse`).
- **Riesgo medio — expectativa del cliente sobre reportes financieros**: ver
  hallazgo crítico arriba. Sin la declaración explícita en el cierre, alto riesgo
  de bounce 4 ("el salario no se refleja en el reporte semanal").
- **Riesgo bajo — import Cargo upsert**: como el `codigo` nunca se reasigna
  (solo se usa como lookup key), no colisiona con la restricción de FK
  `to_field='codigo'` documentada en el bounce 2 (esa restricción bloquea
  CAMBIAR un código ya referenciado, no bloquea actualizar `nombre`/`salario_base`
  de ese mismo código).
- **Riesgo bajo, ya mitigado por diseño — autocompletado no bloquea edición
  manual**: el listener solo dispara en `change` explícito del select, nunca en
  `DOMContentLoaded` — ver §3.
- **Nota de scope explícita (no un riesgo del código, un riesgo de expectativa)**:
  `CuadrillaMasivaUploadView.COSTOS` y `financiero/reports.py::valores_dia`
  siguen divergiendo de `Cargo.salario_base`/`PersonalCuadrilla.salario_base`.
  Documentado arriba — candidato a un issue FUTURO de unificación, no de éste.

## Registros legacy de referencia (para journeys E2E)

- `personal_cuadrilla.id = 2d1fe4f3-d7ab-497e-9618-d80dab73f170` (Andrea,
  documento `43482087`, `rol_cuadrilla = LINIERO_I`, `salario_base = 15000.00`)
  — registro LEGACY real, no fixture, útil para validar que el export de
  Colaboradores incluye datos preexistentes.
- `cargos` — 15 códigos activos hoy (`SELECT codigo FROM cargos`), incluye
  `LINIERO_I`, `AYUDANTE`, `CONDUCTOR`, `SUPERVISOR`. Ninguno tiene
  `salario_base` aún (columna no existe hasta A1) — journeys de autocompletado
  DEBEN crear su propio `Cargo` fixture con salario ≠0 (`QA_E2E_176_*`), no
  asumir que un cargo real ya tiene salario cargado (backfill bloqueado, ver §1).

## Validación esperada (smoke post-deploy)

- `/cuadrillas/cargos/` → columna Salario Base visible, botones Importar/Exportar
- `/cuadrillas/colaboradores/crear/` → cambiar Cargo autocompleta Salario Base
  (editable después)
- `/cuadrillas/colaboradores/` → botón Importar visible (mismo import que ya
  funcionaba), botón Exportar descarga xlsx
- `/financiero/nomina/` → sigue renderizando 200 sin regresión
- Import de Cargo con 2 filas (1 código nuevo + 1 actualización de un
  `QA_E2E_176_*` propio) → ambas persisten correctamente

## Contenido previsto del comentario de cierre (F6 — post-mortem bounce 3)

El comentario DEBE incluir explícitamente:
1. Reconocer que el import de Colaboradores YA funcionaba desde antes (no es
   trabajo nuevo, solo exposición en su pantalla natural).
2. Declarar qué es nuevo: `Cargo.salario_base` + autocompletado + import/export
   de Cargo + export de Colaboradores.
3. Declarar EXPLÍCITAMENTE pendiente/bloqueado: backfill de salarios reales por
   cargo (Alcides/Andrea).
4. Declarar EXPLÍCITAMENTE que el salario NO se refleja en los reportes
   financieros de cuadrilla semanal (hallazgo crítico de este plan) — decisión
   de scope comunicada, no vacío nuevo.
5. Marcador de cierre:
   `<!-- REPROCESO_DATA: {"category":"FIX_INCOMPLETO","root":"otro","bounce":3} -->`
