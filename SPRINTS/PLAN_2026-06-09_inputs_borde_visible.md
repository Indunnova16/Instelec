# PLAN — Borde visible en inputs/textareas/selects vacíos (issue #138)

**Fecha:** 2026-06-09
**Issue:** [Indunnova16/instelec#138](https://github.com/Indunnova16/instelec/issues/138)
**Estado:** Planning completado, listo para ejecución

## Contexto

Los campos de texto vacíos (inputs, textareas, selects) en todo el aplicativo
no muestran ningún borde ni delimitación visual, por lo que el usuario no sabe
dónde hacer clic para ingresar datos. El issue lo reporta sobre el campo
"Observaciones" del módulo Construcción pero aclara: **"Aplica para todo el
aplicativo, en todos los módulos"**.

### Causa raíz (confirmada en código)

Las class strings de los campos llevan el **color** del borde
(`border-gray-300 dark:border-gray-600`) pero **NO el ancho** (`border`). En
Tailwind, `border-gray-300` sin la utilidad `border` no pinta ningún borde
hasta `:focus`. El patrón buggy aparece en:

- `apps/contratos/forms.py` → `CSS = 'rounded-lg border-gray-300 ... w-full'` (sin `border`)
- `apps/financiero/forms.py` → 2 constantes con `'w-full rounded-lg border-gray-300 ...'`
- `apps/lineas/forms.py` → ~8 widgets con `'... rounded-md border-gray-300 ...'`
- Decenas de inputs/selects crudos en templates con el patrón
  `w-full rounded-lg border-gray-300 ...` (sin `border`)

(Los inputs crudos que YA tienen `border border-gray-300` — ej.
`spt_pintura_torre.html`, `financiero_grid.html` — están correctos y NO se tocan.)

### Solución preferida (global, no parche por template)

**Una regla CSS global en el bloque `<style>` de `templates/base.html`** que
aplique un borde base sutil a `input` / `textarea` / `select` de texto
(excluyendo `checkbox`, `radio`, `hidden`, `file`, `range`), de modo que el
campo vacío **siempre** tenga borde visible, esté o no lleno. Al vivir en
`base.html` (heredado por TODA plantilla vía `{% extends "base.html" %}`),
el fix cubre **todos los módulos** en un único lugar, sin tocar template por
template ni cada `forms.py`.

Ejemplo de regla (Tailwind por CDN respeta CSS plano en el `<style>`; este NO
es JS ni va dentro de `x-data`, así que **no hay riesgo Alpine/HTMX**):

```css
input:not([type="checkbox"]):not([type="radio"]):not([type="hidden"]):not([type="file"]):not([type="range"]),
textarea,
select {
  border-width: 1px;
  border-style: solid;
}
/* el color ya lo aportan las clases border-gray-300 / dark:border-gray-600;
   donde falte, un fallback neutro para light/dark */
input:not([type="checkbox"]):not([type="radio"]):not([type="hidden"]),
textarea, select { border-color: rgb(209 213 219); }      /* gray-300 */
.dark input:not([type="checkbox"]):not([type="radio"]):not([type="hidden"]),
.dark textarea, .dark select { border-color: rgb(75 85 99); } /* gray-600 */
```

Detalles a cuidar en ejecución (F3):
- NO meter este CSS dentro de `x-data` ni como comentario `{# #}` multilínea
  (ver memorias: rompe Alpine). Va en el `<style>` plano existente de base.html.
- Especificidad: usar `border-width: 1px` (no `@apply`, el CDN no compila
  `@apply` en `<style>` plano). Las clases `border-2` puntuales de la app
  ganan por especificidad/orden, así que no se aplastan cajas con borde grueso
  intencional.
- Excluir `checkbox`/`radio`/`file`/`range` para no deformar esos controles.

## Sub-items por sprint

### Sprint A (deployable_solo: true)

| # | Sub-item | Archivos | Tests | Dependencias | Estado |
|---|---|---|---|---|---|
| A1 | Audit: confirmar inventario de campos sin `border` width (forms.py contratos/financiero/lineas + inputs crudos en templates). Salida: lista de selectores afectados para el smoke. | (read-only) | — | - | ⏳ pendiente |
| A2 | Regla CSS global en el `<style>` de `templates/base.html` para input(texto)/textarea/select. Excluir checkbox/radio/file/range. Light + dark. | `templates/base.html` | regresión render contrato (status 200, no rompe layout) | A1 | ⏳ pendiente |
| A3 | Verificar que la regla NO aplasta los controles que ya tienen `border-2`/estilos especiales y NO deforma checkboxes (revisar visualmente spt_pintura_torre + un dashboard). | `templates/base.html` (ajuste fino si hace falta) | — | A2 | ⏳ pendiente |
| A4 | Smoke E2E + screenshots (journey `instelec_138.yaml`): campos vacíos del Contrato (Observaciones, Objeto, codigo/nombre/valor, estado) con borde visible. | (journey) | `instelec_138.yaml` (2 journeys) | A2, A3 | ⏳ pendiente |
| A5 | Comentario al cliente: URL `/construccion/<proyecto>/contrato/` + pasos para validar (campos vacíos ahora tienen borde) + nota de alcance global (todos los módulos vía base.html). | (comentario GH) | — | A4 | ⏳ pendiente |

> **DoD v1.0:** el fix es CSS-only en el layout compartido. No hay migration,
> no hay endpoint/form/lógica nueva (el `border-gray-300` ya existe; solo faltaba
> el ancho). El "backend" del DoD no aplica; los gates relevantes son UI completa
> (light+dark, checkboxes intactos), regresión de render, smoke E2E visual y
> comentario de validación.

## DAG dependencias

```
A1 → A2 → A3 → A4 → A5
```

(Lineal: cadena CSS → verificación visual → smoke → cliente.)

## Riesgos y mitigaciones

- **Romper Alpine/HTMX** (memorias recurrentes): el fix es CSS plano en el
  `<style>` existente, NO va en `x-data` ni en comentarios multilínea →
  riesgo nulo si se respeta la ubicación. **Mitigación:** F3 inserta dentro del
  `<style>` ya presente (líneas 41-45 de base.html), no en atributos.
- **Aplastar bordes intencionales** (cajas con `border-2`, tablas con
  `border-collapse`): la regla solo fija `border-width: 1px` sobre
  input/textarea/select de texto; las clases utilitarias específicas mantienen
  precedencia. **Mitigación:** A3 verifica spt_pintura_torre + un grid financiero.
- **Deformar checkbox/radio/file**: excluidos por selector `:not([type=...])`.
- **Dark mode**: regla con fallback `.dark` para que el borde se vea en ambos temas.
- **Falsos positivos del cliente** ("sigue sin borde"): validar ≥2 campos vacíos
  reales (Observaciones + Objeto), no un solo fixture — cubierto por los 2 journeys.

## Validación esperada (qa_claude smoke maestros)

Journey `RUN_.../journeys/instelec_138.yaml` (2 journeys, autenticado qa_claude):

1. `i138_a_contrato_observaciones_borde` — `/construccion/{proyecto}/contrato/`:
   status 200, existen `textarea[name=observaciones]` + `input[name=codigo]` +
   `select[name=estado]`, screenshot del campo "Observaciones" vacío con borde
   (el escenario EXACTO del screenshot del issue).
2. `i138_a_contrato_objeto_borde` — mismo route, segundo campo vacío:
   `textarea[name=objeto]` + `input[name=valor]` + `input[name=nombre]`,
   screenshot del "Objeto del Contrato" con borde. Valida >1 campo (no 1 fixture).

**Validación visual (cierre F5):** abrir los PNG y confirmar borde sutil visible
en los campos vacíos. La regla `run_journey` no tiene primitiva de
`getComputedStyle`, así que el borde se valida por screenshot, no por assert de
clase (el fix puede aplicar vía CSS global, no vía clase en el atributo).

**Smoke maestros adicional (F5):** crawl status 200 de
`/construccion/{p}/contrato/`, `/construccion/{p}/ingenieria/`,
`/construccion/{p}/financiero/` para confirmar que la regla global no rompió
render en otras pantallas.
