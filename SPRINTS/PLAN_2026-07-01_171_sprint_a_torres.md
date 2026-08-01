# PLAN — Instelec#171: Sprint A — activar `torre_form.html` real (torres)

- **Issue:** Instelec#171
- **Ruta:** sprint_path (epic, scope partido por decisión del orquestador — ver abajo)
- **Fecha plan:** 2026-07-01
- **Complexity global (Sprint A):** low (backend ya completo, solo falta template + validación de UI)
- **Riesgo global:** bajo
- **Sprint único de este run:** A (A1, A2, A3) — Sprint B (columnas configurables) queda diferido, ver sección final

## Contexto

Instelec#171 es una épica de configurabilidad multi-proyecto con 2 frentes de
tamaño muy distinto, triada 4 veces (27-jun, 28-jun ×2, hoy) con el mismo
veredicto de fondo. El `DECISIONS_2026-06-28_171-149.md` dejó 2 opciones de
scope pendientes de Miguel (A=partir vs B=completo) y pedía 2 ejemplos del
"instructivo Hochiminh" para dimensionar la parte grande.

**Decisión de scope para este run (tomada por el orquestador, no por este
agente):** ejecutar SOLO Sprint A — código-only, bajo riesgo, backend ya
completo. Sprint B (columnas configurables V4-V7) y V3 (No aplica vs Anulada)
quedan explícitamente fuera, documentados abajo con la razón de bloqueo.

El 29-jun `@Indunnova` validó parcialmente en producción y confirmó: el botón
"+ Nueva Torre" y el checkbox "Torre aplica" SÍ existen y funcionan, pero
`torre_form.html` es un placeholder de 1 línea (`"torre_form.html - En
Desarrollo"`) que bloquea crear/editar torres. También reportó `entrega.html`
(módulo `EntregaElectromecanica`, fuera de scope semántico de #171) y una
discrepancia 64 vs 65 torres en el proyecto QA, que es consecuencia directa
de A1 (la torre 65 nunca pudo crearse porque el form está roto), no un bug
de conteo aparte.

No es reproceso: `git log` no muestra commits previos tocando
`torre_form.html` ni `TorreCreateView`/`TorreEditView` desde el 25-jun —
nunca se ejecutó un sprint real para #171 antes de este.

## Inspección de código (confirmada hoy contra `origin/main`)

`apps/construccion/views.py` líneas 124-179 — `TorreCreateView` y
`TorreEditView` (ambas `LoginRequiredMixin`, `RoleRequiredMixin`,
`allowed_roles = ['admin', 'director', 'coordinador']`) ya están completas:

```python
class TorreCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    model = TorreConstruccion
    template_name = 'construccion/torre_form.html'
    fields = [
        'numero', 'tipo', 'tipo_cimentacion', 'peso_kg', 'tramo_tendido',
        'latitud', 'longitud', 'cuadrilla_civil', 'cuadrilla_montaje',
        'cuadrilla_tendido', 'observaciones'
    ]
    # get_context_data agrega `proyecto` al contexto
    # form_valid crea PataObra (A/B/C/D), FaseTorre, SocialPredial,
    # AmbientalTorre, EntregaElectromecanica, CorreccionEntrega
    # get_success_url -> construccion:torres_lista
```

`TorreEditView` es idéntica en `fields` (UpdateView, mismo template, mismo
`get_success_url`).

`apps/construccion/models.py` líneas 513-553 — `TorreConstruccion.numero` es
`CharField(max_length=20)` — **ya soporta alfanumérico** (ej. "T-1A"), no
requiere cambio de backend ni migración. `aplica` (BooleanField, default
True) es el toggle "No aplica" (issue #160), separado de V3.

`apps/construccion/urls.py`:
```
<uuid:proyecto_id>/torres/crear/           -> construccion:torre_crear   (TorreCreateView)
<uuid:proyecto_id>/torres/<uuid:pk>/editar/-> construccion:torre_editar  (TorreEditView)
<uuid:proyecto_id>/torres/                 -> construccion:torres_lista  (success_url de ambas)
```

`templates/construccion/torre_form.html` actual (completo, es todo el archivo):
```html
{% extends 'base.html' %}{% block content %}<h1>torre_form.html - En Desarrollo</h1>{% endblock %}
```

**Patrón de referencia ya existente en el mismo directorio** (mismo tipo de
vista Django genérica `CreateView`/`UpdateView` con `fields` de model form,
mismo layout Tailwind `base.html`) — `protecciones_form.html` y
`kits_form.html` son form templates YA implementados y funcionando en prod
para modelos hermanos (`ObraProteccion`, kit de cerramiento) dentro de la
misma app `construccion`. Ambos siguen el mismo esqueleto:

```html
{% extends 'base.html' %}
{% block title %}{% if object %}Editar{% else %}Nuevo{% endif %} <objeto>{% endblock %}
{% block content %}
<div class="max-w-3xl mx-auto space-y-6">
  <h1 class="text-2xl font-bold">{% if object %}Editar{% else %}Nueva{% endif %} torre</h1>
  <p class="text-sm text-gray-500">{{ proyecto.nombre }}</p>
  <form method="post" class="bg-white dark:bg-gray-800 rounded-lg shadow p-6 space-y-4">
    {% csrf_token %}
    {% for field in form %}
      <div>
        <label class="block text-sm font-medium mb-1">{{ field.label }}</label>
        <div>{{ field }}</div>
        {% if field.help_text %}<p class="text-xs text-gray-500">{{ field.help_text }}</p>{% endif %}
        {% if field.errors %}<p class="text-xs text-red-600">{{ field.errors.0 }}</p>{% endif %}
      </div>
    {% endfor %}
    <div class="flex justify-end gap-3 pt-4 border-t">
      <a href="{% url 'construccion:torres_lista' proyecto.id %}" class="px-4 py-2 border rounded-lg">Cancelar</a>
      <button type="submit" class="px-4 py-2 bg-blue-600 text-white rounded-lg">Guardar</button>
    </div>
  </form>
</div>
<style>input,select,textarea{width:100%;padding:.5rem .75rem;border:1px solid #d1d5db;border-radius:.5rem;}textarea{min-height:80px;}</style>
{% endblock %}
```

Esto **reduce la complejidad de A1 a "trivial"** en la práctica: no hay
diseño nuevo que inventar, es replicar un patrón que ya vive 2 veces en el
mismo directorio (`protecciones_form.html`, `kits_form.html`), ajustando el
título/label a "torre" y usando `construccion:torres_lista` como
`cancel_url`/`success_url` (ya resuelto por `get_success_url` en la view, no
requiere tocar la view).

También existe `_form_generico.html` (include genérico con label + asterisco
de requerido + help_text + errores) que F3 puede usar directamente vía
`{% include %}` en vez de repetir el `{% for field in form %}` a mano —
queda a discreción de F3 cuál de los 2 patrones usar; ambos son válidos
porque ya están en producción. Si usa `_form_generico.html`, la view debe
pasar `titulo`/`subtitulo`/`cancel_url` en `get_context_data` (hoy
`TorreCreateView`/`TorreEditView` solo pasan `proyecto`) — en ese caso
**sí** hay un cambio mínimo de 3 líneas en `views.py` (agregar esas 3 keys
al contexto), no un rediseño de la lógica de negocio.

## Tabla de entregables (gate anti-FIX_INCOMPLETO)

| # | Entregable | Evidencia esperada (URL/campo/comportamiento) | ✅/❌ |
|---|---|---|---|
| 1 | `torre_form.html` deja de ser el placeholder "En Desarrollo" y renderiza un form Django real con los 11 campos de `TorreCreateView.fields` | GET `/construccion/{proyecto_uuid}/torres/crear/` → 200, NO contiene el texto "En Desarrollo", contiene `<form method="post">` con inputs para `numero`, `tipo`, `tipo_cimentacion`, `peso_kg`, `tramo_tendido`, `latitud`, `longitud`, `cuadrilla_civil`, `cuadrilla_montaje`, `cuadrilla_tendido`, `observaciones` | ❌ pendiente ejecución |
| 2 | El mismo template sirve para `TorreEditView` (edición) sin duplicar HTML | GET `/construccion/{proyecto_uuid}/torres/{torre_uuid}/editar/` → 200, form pre-poblado con los valores existentes de una torre real (ej. T-1) | ❌ pendiente ejecución |
| 3 | Crear una torre nueva vía el form real funciona end-to-end (POST → 302 → aparece en el listado) | POST a `/construccion/{proyecto_uuid}/torres/crear/` con `numero=T-QAE2E1` → redirect 302 a `construccion:torres_lista`, torre visible en `/construccion/{proyecto_uuid}/torres/` | ❌ pendiente ejecución |
| 4 | `numero` acepta alfanumérico sin error de validación (ej. "T-1A", "T-QAE2E1") | El campo `numero` en el form es un `CharField` estándar (sin regex/validator numérico agregado); no se requiere cambio de backend, solo confirmar que el widget no le agrega `type="number"` ni JS que lo bloquee | ❌ pendiente ejecución |
| 5 | El conteo 64/65 en `SocialPredialView`/`AmbientalView` se resuelve solo al poder crear la torre 65 vía el form arreglado (verificación, no código) | Tras crear una torre 65ª real en el proyecto QA (o confirmar que ya existen 65 tras el fix), el conteo mostrado en `/construccion/{proyecto_uuid}/social-predial/` y `/construccion/{proyecto_uuid}/ambiental/` refleja el total correcto sin tocar esas views | ❌ pendiente ejecución (NO requiere cambio de código si la hipótesis del F1 es correcta) |

## Sub-items Sprint A

| ID | Sub-item | Prioridad | Dependencias | Complexity | Deployable solo | Archivos a tocar |
|----|----------|-----------|---------------|------------|------------------|-------------------|
| A1 | Implementar `templates/construccion/torre_form.html` real (reemplazar placeholder por form Django completo, reusando el patrón de `protecciones_form.html`/`kits_form.html`) | P0 | — | trivial-low | sí | `templates/construccion/torre_form.html` (+ opcionalmente 3 líneas en `apps/construccion/views.py` si F3 decide usar `_form_generico.html` con `titulo`/`subtitulo`/`cancel_url` en contexto) |
| A2 | Confirmar que `numero` (label/help-text) comunica claramente que acepta alfanumérico (ej. help_text "Ej: T-1, T-1A, T-25B") — ajuste de label/help_text en el `ModelForm` implícito, sin nuevo campo ni validator | P1 | A1 | trivial | sí | `templates/construccion/torre_form.html` (help_text vía `{{ field.help_text }}` ya lo soporta; si se quiere help_text propio del campo `numero`, un `help_text=` de 1 línea en el `CharField` de `models.py`, opcional) |
| A3 | Verificar (sin cambio de código) que el conteo 64/65 en `SocialPredialView`/`AmbientalView` se resuelve solo al poder crear la torre 65 vía el form arreglado | P1 | A1 | trivial | no (depende de A1 deployado) | ninguno — solo verificación post-deploy contra prod |

### DAG de dependencias

```
A1 (torre_form.html real)
 ├──> A2 (help_text numero alfanumérico)
 └──> A3 (verificación conteo 64/65 — post-deploy, no código)
```

A1 es el único sub-item con cambio de archivo real. A2 puede ir en el mismo
commit que A1 (mismo archivo). A3 es puramente verificación post-deploy
contra el proyecto QA de referencia (Puerta de Oro, UUID
`ec2a68aa-47fe-4772-89bc-2cd2b1c8b5c7`).

## Riesgos

- **Bajo.** No hay migración de BD, no hay cambio de modelo, no hay lógica
  de negocio nueva — `form_valid` y `fields` de las views ya están completos
  y probados en el código (aunque nunca ejercitados end-to-end porque el
  template bloqueaba el flujo).
- Único riesgo real: que F3 rompa el layout de `base.html` al copiar el
  patrón (mitigado porque el patrón ya está en 2 templates hermanos
  funcionando en prod, `protecciones_form.html` y `kits_form.html` — copiar,
  no inventar).
- Si F3 decide usar `_form_generico.html` (el include), toca 3 líneas en
  `views.py` (agregar `titulo`/`subtitulo`/`cancel_url` a
  `get_context_data`) — cambio quirúrgico, no estructural, ambas views
  (`Create`/`Edit`) ya comparten `get_context_data` con la misma firma.
- El campo `latitud`/`longitud` son `FloatField(null=True, blank=True)` —
  el form no debe forzarlos como requeridos (Django ya lo maneja vía
  `blank=True` → `required=False` en el ModelForm implícito, sin acción
  extra).

## Validación esperada (smoke post-deploy)

1. GET `/construccion/{proyecto_uuid}/torres/crear/` → 200, sin el texto
   "En Desarrollo", form con los 11 campos visibles.
2. POST crear torre `numero=T-QAE2E1` (+ campos mínimos requeridos) → 302 a
   `torres_lista`, la torre aparece en el listado.
3. GET `/construccion/{proyecto_uuid}/torres/{uuid_torre_existente}/editar/`
   sobre una torre legacy (ej. T-1 del proyecto QA) → 200, form pre-poblado
   con sus valores reales (no solo el dato recién creado — dato legacy
   obligatorio).
4. Confirmar en `/construccion/{proyecto_uuid}/social-predial/` y
   `/construccion/{proyecto_uuid}/ambiental/` que el conteo total de torres
   sube a reflejar la torre creada (verificación A3).
5. Cleanup: borrar la torre `T-QAE2E1` de prueba (vía UI si hay
   `TorreDeleteView`, o `DELETE FROM construccion_torreconstruccion WHERE
   numero = 'T-QAE2E1'` solo si el cleanup vía UI no está disponible — ver
   journey YAML).

## Diferido — requiere insumo externo (NO ejecutar en este run)

| Item | Razón de bloqueo |
|------|-------------------|
| **V3 — ¿"No aplica" alcanza o necesita "Anulada" separado?** | Requiere respuesta explícita de Gabriel (cliente). **Instelec#149 de este mismo repo ya rebotó 5 veces tocando exactamente este mismo toggle (`TorreConstruccion.aplica`) sin claridad de intent** — categoría MALENTENDIDO documentada en `DECISIONS_2026-06-28_171-149.md`. No se adivina una 6ª vez. |
| **Sprint B — columnas configurables (V4-V7)** | Feature nueva de cero: no existe metadata JSON en `ProyectoConstruccion`, ni CRUD, ni UI matriz dinámica para ObraCivil/Montaje/Tendido. Bloqueado hasta que el cliente provea 2 ejemplos del "instructivo Hochiminh" (de 2 proyectos distintos) para saber si las columnas difieren en *nombres* (scope bajo) o en *estructura completa* (scope alto, ≈3x el tiempo). Pregunta ya registrada en el F1 de hoy y en el DECISIONS previo — pendiente de Miguel/Gabriel. |
| **`entrega.html` (EntregaElectromecanica)** | Reportado por QA como placeholder similar, pero **fuera de scope semántico de #171** — el issue original nunca menciona "Entrega"/"EntregaElectromecanica". No tocar salvo instrucción explícita de Miguel o un issue propio. |

## Referencias

- Triage F1 de hoy: `agents/Instelec_171_f1.json` (dentro del run actual).
- Historial de decisión: `Instelec/SPRINTS/DECISIONS_2026-06-28_171-149.md`.
- Patrón de template a replicar: `templates/construccion/protecciones_form.html`,
  `templates/construccion/kits_form.html`, `templates/construccion/_form_generico.html`.
