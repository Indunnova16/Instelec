# PLAN — Instelec#175: 3 bugs (link GPS, fotos, mapa cuadrillas) + Feature mapa reportes de daño

- **Issue:** Instelec#175
- **Ruta:** sprint_path (epic — 3 bug_fix + 1 feature_nueva)
- **Fecha plan:** 2026-06-30
- **Complexity global:** epic (4 sub-items, sin sub-items individuales que crucen high solos salvo la Feature)
- **Riesgo global:** medio
- **Sprint único:** los 4 sub-items son independientes entre sí (sin dependencias), se ejecutan en 1 sprint en paralelo (A1..A4)

## Contexto

El cliente (Instelec) reportó 3 bugs con evidencia visual (capturas) sobre el
módulo de reportes de daño y el mapa de cuadrillas, más 1 feature nueva
solicitada por el equipo de mantenimiento: un mapa de reportes de daño
filtrable por línea/severidad/tipo, siguiendo el patrón visual ya existente
en `templates/cuadrillas/mapa.html` y `templates/lineas/mapa.html`.

Sin comentarios adicionales del cliente en el issue — solo el body inicial.
No es reproceso (`reproceso_rate.py` no aplicó porque no hay intervención
previa registrada sobre estos 3 bugs/feature).

## Tabla de entregables (gate anti-FIX_INCOMPLETO)

| # | Entregable | Evidencia esperada (URL/campo/comportamiento) | ✅/❌ |
|---|---|---|---|
| 1 | Link "Ver en Google Maps" en detalle de reporte de daño usa punto decimal, no coma | `href` del link en `/campo/reportes-dano/{uuid}/` contiene `10.99194655,-74.81943206` (no `10,99194655,-74,81943206`) | ❌ pendiente ejecución |
| 2 | Diagnóstico documentado de fotos rotas + fix si aplica | Root cause explicado en comentario del issue con evidencia BD; si el registro es dato de prueba (`FOTO_PRUEBA.png`), reporte explícito al cliente, no "fix" de código forzado | ❌ pendiente ejecución |
| 3 | Mapa de cuadrillas: diagnóstico + estado vacío informativo (NO fallback por torre — ver resolución abajo) | `/cuadrillas/mapa/` muestra mensaje explicativo claro cuando `ubicaciones` está vacío, en vez del mapa mudo actual | ❌ pendiente ejecución |
| 4 | Mapa nuevo de reportes de daño con pines filtrables (línea/severidad/tipo) | `/campo/reportes-dano/mapa/` carga Leaflet con 1 pin por reporte con coordenadas, popup con severidad+tipo+foto, filtros funcionando y actualizando pines | ❌ pendiente ejecución |

## Resolución OBLIGATORIA del Bug 3 — evidencia BD (Kaizen #92)

**Query ejecutada contra prod (solo lectura, proxy 127.0.0.1:5434, `instelec_db`):**

```
-- Nota: el nombre real de la tabla es tracking_ubicacion (no cuadrillas_trackingubicacion)
SELECT count(*) AS total, max(created_at) AS mas_reciente, min(created_at) AS mas_antiguo
FROM tracking_ubicacion;

 total | mas_reciente | mas_antiguo
-------+--------------+-------------
     0 |  (null)      |  (null)
```

**Resultado: la tabla `tracking_ubicacion` tiene 0 filas.** Nunca, en ningún
momento, la app móvil ha reportado una ubicación GPS de ninguna cuadrilla.
No es un problema reciente ni un patrón de datos viejos — es una funcionalidad
que nunca se ha activado en campo.

**Decisión (evidencia, no adivinanza):** Bug 3 se resuelve como
**diagnóstico + estado vacío informativo**, NO como un fallback "posición vía
torre asignada". Razones:
1. El código (`MapaCuadrillasPartialView.get_context_data`,
   `apps/cuadrillas/views.py` líneas 389-423) está funcionando exactamente
   como está diseñado: lee `TrackingUbicacion` por cuadrilla, más reciente
   primero. No hay bug de código — el bug percibido es 100% ausencia de dato.
2. `Cuadrilla` no tiene una relación directa a una torre puntual con
   geometría (`linea_asignada` es a nivel de línea completa, no de punto
   georreferenciado) — construir un fallback "posición aproximada por línea"
   sería inventar un producto no solicitado con certeza por el cliente
   (violaría el gate de intent-semántico: "no construir lo que no se pidió
   con certeza").
3. El fix correcto y de bajo riesgo es hacer visible al usuario POR QUÉ no
   ve marcadores (en vez de un mapa vacío mudo que parece roto), y dejar
   documentada la pregunta abierta para Miguel/cliente sobre si en un futuro
   sprint se quiere invertir en un fallback por torre/línea.
4. Este sub-item se cierra en F6 como 🟡/ℹ️ "decisión de scope, no bug de
   código" — NUNCA 🟢 — con la evidencia de la query arriba y la pregunta
   abierta explícita para Miguel.

**Pregunta abierta para Miguel (dejar en el comentario final del issue):**
¿Instelec quiere invertir en un futuro sprint en (a) capacitar al equipo de
campo para activar el reporte de ubicación desde la app móvil, y/o (b) un
fallback que muestre la última posición conocida "vía torre/línea asignada"
cuando no hay tracking GPS reciente?

## Investigación adicional — Bug 2 (fotos rotas)

**Query ejecutada (solo lectura):**

```
SELECT count(*) FROM fotos_dano;                         -- total = 1
SELECT id, imagen, descripcion, reporte_id, created_at
FROM fotos_dano;
-- imagen = 'campo/danos/FOTO_PRUEBA.png'
-- reporte_id = 9af5d4a2-6f67-450b-97aa-b13deb97e6b7  (el mismo reporte de la captura att_02.png)
-- created_at = 2026-05-20 19:27:57
```

**Hallazgo:** hay un único registro de `FotoDano` en toda la BD prod, y su
campo `imagen` es literalmente `campo/danos/FOTO_PRUEBA.png` — un nombre de
archivo de prueba/placeholder, no una foto real subida desde la app móvil.
Es prácticamente seguro que ese archivo **nunca fue subido al bucket GCS**
(se creó el registro de BD sin el binario, probablemente durante una prueba
manual o QA), lo cual explica el `<img>` roto en `detalle_dano.html` línea 45
(`{{ foto.imagen.url }}` genera una URL válida hacia GCS, pero el objeto no
existe ahí → 404 al cargar la imagen).

Esto **no es un bug sistemático de storage/ACL** (la config global
`GS_DEFAULT_ACL=publicRead` + `GS_QUERYSTRING_AUTH=False` en
`config/settings/production.py` ya es correcta, confirmado por F1). Es un
dato de prueba huérfano. Sub-item se resuelve como:
1. Fix defensivo de UI: si `foto.imagen` no tiene un archivo válido /
   lanza excepción al resolver `.url`, mostrar un placeholder "Imagen no
   disponible" en vez de un `<img>` roto (mejora real de robustez, aplica a
   cualquier futuro caso de subida fallida, no solo a este registro).
2. Reportar en el comentario del issue que el registro específico
   (`FOTO_PRUEBA.png`, reporte `9af5d4a2-6f67-450b-97aa-b13deb97e6b7`) es un
   dato de prueba sin archivo real en el bucket — no se puede "reparar" ese
   archivo puntual porque nunca existió, y no hay más registros de fotos en
   producción para verificar si el problema es más amplio.

## Sub-items

| # | Sub-item | Tipo | Complexity | Archivos a tocar | Depende de | Deployable solo |
|---|---|---|---|---|---|---|
| A1 | Fix separador decimal coma → punto en link Google Maps | bug_fix | trivial | `templates/campo/detalle_dano.html` | ninguno | sí |
| A2 | Fotos rotas: fix defensivo UI (placeholder si imagen inválida) + diagnóstico documentado | bug_fix | low | `templates/campo/detalle_dano.html`, (opcional) `apps/campo/models.py` si se agrega property `tiene_archivo` | ninguno | sí |
| A3 | Mapa cuadrillas: estado vacío informativo (diagnóstico, no fallback por torre) | bug_fix (decisión de scope) | low | `templates/cuadrillas/mapa.html`, `templates/cuadrillas/partials/mapa_cuadrillas.html` | ninguno | sí |
| A4 | Feature: mapa de reportes de daño filtrable (línea/severidad/tipo) | feature_nueva | medium | `apps/campo/views.py`, `apps/campo/urls.py`, nuevo `templates/campo/mapa_reportes_dano.html`, `tests/unit/test_campo.py` | ninguno | sí |

### DAG de dependencias

```
A1 (independiente) ─┐
A2 (independiente) ─┼─→ ejecutar en paralelo, sin orden requerido
A3 (independiente) ─┤
A4 (independiente) ─┘
```

Ningún sub-item bloquea a otro. Los 4 pueden ejecutarse y deployarse en
paralelo o en cualquier orden.

## Detalle por sub-item

### A1 — Link Google Maps con coma decimal

- **Root cause confirmado:** `LANGUAGE_CODE = 'es-co'` + `USE_I18N = True`
  (sin `USE_L10N = False`) en `config/settings/base.py` líneas 141/143 →
  Django 5.x localiza automáticamente los `DecimalField` en templates,
  usando coma como separador decimal para `es-co`. La línea 114 de
  `templates/campo/detalle_dano.html` interpola `{{ reporte.latitud }}` y
  `{{ reporte.longitud }}` directamente en el `href`, heredando la
  localización → coma en vez de punto → Google Maps no puede parsear la
  URL (confirmado por att_04.png: "no puede encontrar 6,24610854,-75,62051699").
  `templates/campo/reportar_dano.html` NO tiene este bug (usa Alpine.js
  `x-text`/`:href` con valores JS `toFixed(8)`, que siempre usan punto).
- **Fix:** aplicar el filtro `|unlocalize` (requiere `{% load l10n %}`) SOLO
  al `href` del link, dejando la visualización textual (líneas 108/112) con
  el formato localizado normal (así el usuario ve coma como es convención en
  es-co para lectura, pero el link funcional usa punto):
  ```django
  {% load l10n %}
  ...
  <a href="https://www.google.com/maps?q={{ reporte.latitud|unlocalize }},{{ reporte.longitud|unlocalize }}"
  ```
- **Tests:** test unitario/integración renderizando `detalle_dano.html` con
  un `ReporteDano` fixture con latitud/longitud decimales, assert que el
  `href` generado NO contiene coma entre los dígitos decimales (regex
  `r'q=-?\d+\.\d+,-?\d+\.\d+"'`).
- **Edge case:** reporte sin `latitud`/`longitud` (nulls permitidos en el
  modelo) — el bloque ya tiene `{% if reporte.latitud and reporte.longitud %}`,
  no se rompe.
- **Migración:** no aplica (solo template).

### A2 — Fotos rotas

- **Root cause confirmado:** el único registro de `FotoDano` en prod
  (`campo/danos/FOTO_PRUEBA.png`, reporte `9af5d4a2-6f67-450b-97aa-b13deb97e6b7`)
  es un dato de prueba sin archivo real en el bucket GCS — no un bug de
  configuración de storage.
- **Fix (robustez real, no solo para este registro):** envolver el `<img>`
  en `detalle_dano.html` línea 45 con manejo defensivo — usar `onerror` en
  el `<img>` para mostrar un placeholder visual "Imagen no disponible" en
  vez de un ícono roto del navegador:
  ```html
  <img src="{{ foto.imagen.url }}" alt="Foto del daño"
       onerror="this.onerror=null; this.src=''; this.closest('div').innerHTML='<div class=\'flex items-center justify-center h-32 bg-gray-100 dark:bg-gray-700 rounded text-gray-400 text-sm\'>Imagen no disponible</div>';"
       class="...">
  ```
- **Tests:** test unitario que renderiza el template con un `FotoDano`
  fixture (no requiere archivo real en GCS local — el `onerror` es
  client-side, así que el test verifica que el atributo `onerror` está
  presente en el HTML renderizado).
- **Edge case:** reportes con múltiples fotos, algunas rotas y otras válidas
  — cada `<img>` maneja su propio error independientemente.
- **Migración:** no aplica.
- **Nota para el comentario del issue:** explicitar que el registro
  específico de la captura del cliente es un dato de prueba huérfano
  (`FOTO_PRUEBA.png`) sin archivo real subido, y que no hay otros registros
  de fotos en prod para verificar si el problema es más amplio — el fix de
  robustez cubre cualquier caso futuro de subida fallida.

### A3 — Mapa de cuadrillas sin marcadores

- **Root cause confirmado:** `tracking_ubicacion` tiene 0 filas en prod —
  ninguna cuadrilla ha reportado GPS nunca desde la app móvil. El código de
  `MapaCuadrillasPartialView` funciona correctamente; el mapa está vacío
  porque no hay dato, no porque haya un bug.
- **Fix:** agregar un estado vacío informativo visible cuando
  `ubicaciones` esté vacío, tanto en el mapa (mensaje overlay) como en la
  lista lateral (ya existe el `{% empty %}` en el partial pero el mensaje es
  genérico — mejorarlo para que explique la causa):
  - En `templates/cuadrillas/partials/mapa_cuadrillas.html`, cambiar el
    mensaje `{% empty %}` de "No hay cuadrillas con ubicacion registrada" a
    algo más explicativo: "Ninguna cuadrilla está reportando ubicación GPS en
    este momento. Verificá que la app móvil esté activa y con permisos de
    ubicación habilitados."
  - En `templates/cuadrillas/mapa.html`, en la función JS `updateMarkers`,
    si `ubicaciones.length === 0`, mostrar un overlay/mensaje sobre el mapa
    mismo (no solo en la lista lateral) para que no parezca un mapa "roto"
    sino uno correctamente vacío con explicación.
- **Tests:** test de la vista `MapaCuadrillasPartialView` con 0 registros de
  tracking, assert que el HTML incluye el mensaje explicativo (no solo texto
  genérico "No hay...").
- **NO se construye** fallback de posición-vía-torre (ver resolución
  arriba) — se documenta como pregunta abierta para Miguel/cliente.
- **Migración:** no aplica.

### A4 — Feature: mapa de reportes de daño filtrable

- **Patrón a reutilizar** (ya validado en prod, mismo repo):
  `templates/cuadrillas/mapa.html` (Leaflet + fetch a vista partial que
  devuelve JSON) + `MapaCuadrillasPartialView` (patrón `render_to_response`
  que devuelve JSON si `Accept: application/json`, o el partial HTML si no).
- **Datos disponibles:** los 5 `ReporteDano` en prod tienen `latitud`/
  `longitud` pobladas (campo nullable pero sin nulls en la práctica actual),
  `linea_id`, `severidad`, `tipo_dano` — todo lo necesario para pines +
  filtros.
- **Backend:**
  - Nueva vista `ReportesDanoMapaView` (TemplateView, mismo patrón de roles
    que `ReportesDanoListView`: `allowed_roles = ['admin', 'director',
    'coordinador', 'ing_residente', 'supervisor', 'liniero']`) en
    `apps/campo/views.py`, template `campo/mapa_reportes_dano.html`.
  - Nueva vista `ReportesDanoMapaPartialView` que reutiliza los MISMOS 3
    filtros de `ReportesDanoListView.get_queryset` (`linea`, `severidad`,
    `tipo` vía querystring) y devuelve JSON con: `id`, `lat`, `lng`,
    `severidad`, `severidad_display`, `tipo_dano_display`, `descripcion`
    (truncada), `linea_codigo`, `torre_numero` (si existe), `foto_url`
    (primera foto si existe, o null), `created_at`, y URL al detalle
    (`campo:detalle_dano`).
  - Filtrar `.exclude(latitud__isnull=True).exclude(longitud__isnull=True)`
    (reportes sin GPS no pueden pinearse).
- **URLs** (`apps/campo/urls.py`): agregar
  ```python
  path('reportes-dano/mapa/', views.ReportesDanoMapaView.as_view(), name='reportes_dano_mapa'),
  path('reportes-dano/mapa/data/', views.ReportesDanoMapaPartialView.as_view(), name='reportes_dano_mapa_data'),
  ```
- **Frontend:** clonar el patrón JS de `mapa.html` (Leaflet, `L.marker`,
  `fitBounds`), agregando:
  - Selects de filtro (línea/severidad/tipo) reutilizando las choices de
    `context['lineas']`, `context['tipos']`, `context['severidades']`
    (mismo patrón que `ReportesDanoListView.get_context_data`).
  - Al cambiar un filtro, refetch a la vista partial con querystring y
    re-renderizar pines (sin recargar página).
  - Popup por marcador: severidad (con color, mismo esquema de
    `detalle_dano.html` líneas 79-82: rojo=CRITICA, naranja=ALTA,
    amarillo=MEDIA, verde=BAJA), tipo de daño, línea/torre, foto (si existe,
    con el mismo manejo defensivo `onerror` de A2), link "Ver detalle".
  - Botón/link de entrada desde `templates/campo/lista_danos.html` (agregar
    un link "Ver en mapa" cerca de los filtros existentes).
- **Tests** (`tests/unit/test_campo.py`):
  - Happy path: 3 `ReporteDano` factory con lat/long distintas, request al
    endpoint JSON, assert 3 pines en la respuesta con campos correctos.
  - Filtro por línea: 2 reportes de línea A, 1 de línea B, filtrar por A,
    assert 2 resultados.
  - Filtro por severidad y por tipo: análogo.
  - Edge case: reporte con `latitud`/`longitud` NULL → excluido de la
    respuesta del mapa (no rompe, simplemente no aparece).
  - Edge case: reporte sin fotos → `foto_url` es `null`, no rompe el popup.
  - Permisos: usuario sin rol permitido → 403/redirect (mismo patrón que
    `RoleRequiredMixin` en otras vistas del módulo).
- **Migración:** no aplica — reutiliza campos existentes de `ReporteDano`
  (`latitud`, `longitud`, `linea`, `torre`, `severidad`, `tipo_dano`) y la
  relación existente `fotos` de `FotoDano`.

## Riesgos

- **Riesgo bajo (A1, A2, A3):** cambios acotados a templates + 1 vista
  existente, sin migración, sin tocar lógica de negocio crítica.
- **Riesgo medio (A4):** feature nueva con 2 vistas + 1 template nuevo +
  JS Leaflet — mayor superficie, pero sigue un patrón ya probado en
  producción (mismo repo, mismo Leaflet, mismo esquema de vista
  partial-JSON). El riesgo principal es UI/UX (popups, filtros
  interactivos) más que backend.
- **Riesgo de expectativa del cliente (A3):** el cliente puede haber
  asumido que el mapa de cuadrillas mostraría posición por torre — se
  gestiona con comunicación explícita en el comentario del issue + pregunta
  abierta a Miguel, no con silencio ni con un fallback no solicitado.

## Validación esperada (smoke E2E post-deploy)

1. `/campo/reportes-dano/9af5d4a2-6f67-450b-97aa-b13deb97e6b7/` → click en
   "Ver en Google Maps" → URL generada abre correctamente en Google Maps
   (sin error de coordenadas).
2. Mismo detalle → sección Fotografías muestra placeholder "Imagen no
   disponible" en vez de ícono roto para el registro `FOTO_PRUEBA.png`.
3. `/cuadrillas/mapa/` → mensaje explicativo visible (no mapa mudo) dado
   que `tracking_ubicacion` sigue en 0 filas.
4. `/campo/reportes-dano/mapa/` (nueva) → carga con 5 pines (los 5
   `ReporteDano` de prod), filtros por línea/severidad/tipo funcionando,
   click en pin abre popup con datos + link a detalle.
5. Registro legacy incluido: el reporte `6f444717-...` (creado 2026-03-31,
   el más antiguo, pre-existente al cambio) debe aparecer correctamente
   pineado en el mapa nuevo — cumple la regla de "probar con ≥1 registro
   legacy, no solo fixtures".

## Comentario final del issue (guía para F6)

Debe incluir, por sub-item, el estado explícito:
- A1: 🟢 (si el E2E confirma el href sin coma contra la revisión promovida)
- A2: 🟡 (fix de robustez deployado; el registro puntual del cliente sigue
  sin archivo real porque nunca existió — no es "reparable", es dato huérfano)
- A3: 🟡/ℹ️ decisión de scope — CON la evidencia de la query (`tracking_ubicacion`
  = 0 filas) y la pregunta abierta a Miguel/cliente sobre fallback por torre
- A4: 🟢 (si el E2E confirma pines + filtros contra la revisión promovida,
  probado con ≥2 registros reales, incluyendo el legacy de marzo)
