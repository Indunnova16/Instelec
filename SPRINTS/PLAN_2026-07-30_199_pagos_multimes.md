# PLAN — Pagos multi-mes: n_meses persistido + grilla informativa (issue #199)

**Fecha:** 2026-07-30
**Issue:** [Indunnova16/Instelec#199](https://github.com/Indunnova16/Instelec/issues/199)
**Estado:** Planning completado, listo para ejecución
**Ruta:** sprint_path (port de `Indunnova16/pagos-template`, commit `f05a303`)

## ⚠️ Alcance ajustado — sin selector, mantiene pago forzado (decisión Miguel 2026-07-30)

El issue original pide portar el selector interactivo "cuántos meses querés
pagar" de `pagos-template`. **Miguel decidió NO portar el selector.**
Verificado en código (`apps/pagos/views.py` línea 193,
`PagoPortalView.get_context_data`):

```python
context['monto_centavos'] = int(plan.precio * 100 * meses_adeudados)
```

Instelec ya cobra automáticamente **TODO lo adeudado en una sola
transacción** (sin selector) — mismo patrón confirmado en
FundicionesMedellin/ObrajeCRM/FormasFuturo. Miguel decidió **mantener el pago
forzado total** en este repo. El template `portal.html` (líneas 100-122) ya
muestra un único botón WOMPI con el monto total — no hay UI de selección de
meses que portar, y no se construye una.

**Scope real de este plan (5 puntos, ninguno es el selector):**
1. Persistir `Pago.n_meses` (migración) — para que Alegra facture el monto
   real de meses cobrados en vez de re-derivarlo con `round()`.
2. Helper `calcular_n_meses(monto, precio_mes)` centralizado.
3. `Suscripcion.meses_atraso` (property nueva, no existía).
4. Grilla informativa "Estado por mes" — **solo lectura, sin selector**.
5. Journey de regresión: confirmar que el flujo de cobro forzado sigue
   **exactamente igual** (sin cambio de UX de pago).

## Contexto

Port consolidado desde `pagos-template#11` (commit `f05a303`) que en el
template trae selector N meses + grilla + JS sin reload. Instelec **ya
tiene lógica propia que diverge del template** — no es un port mecánico,
es una **reconciliación**:

- El bug original del issue (`_avanzar_fecha_proximo_pago` reseteando a
  HOY en vez de la fecha vencida real) **NO existe en Instelec**:
  `apps/pagos/views.py` línea 31 ya usa
  `actual = suscripcion.fecha_proximo_pago or timezone.localdate()`.
- El cálculo `meses = max(1, round(monto/precio))` **ya existe** inline
  (`views.py` línea 30) — no hay que portarlo, hay que **centralizarlo**
  (hoy vive triplicado: `views.py` líneas 30 y 185-189, y `alegra.py`
  líneas 86-91).
- La alerta "meses pendientes" **ya existe** vía
  `context_processors.recordatorio_pago` (líneas 34-64 de
  `context_processors.py`) y se renderiza en `portal.html` líneas 19-29.
  El plan **reusa/centraliza** este mecanismo (vía `Suscripcion.meses_atraso`)
  en vez de duplicar una segunda alerta con `Suscripcion.alerta_pago_vencido`
  (por eso ese sub-item del template se **omite** — sería una alerta
  duplicada, ver decisión abajo).
- `CHECKLIST_PORT.md` ítem #1 (middleware de login custom bloqueando el
  webhook): **no aplica** — Instelec no tiene `LoginRequiredMiddleware`
  custom ni `LOGIN_EXEMPT_PATTERNS`; el webhook (`WompiWebhookView`, sin
  `LoginRequiredMixin`) ya funciona sin ese problema.

### Decisión: `Suscripcion.alerta_pago_vencido` — OMITIDA

El template trae `Suscripcion.alerta_pago_vencido` como property nueva.
Instelec ya tiene el mismo dato vía `recordatorio_pago` (context processor,
ya wireado en `portal.html`). Agregar la property duplicaría la alerta con
dos mecanismos calculando lo mismo de forma independiente (riesgo de que
diverjan con el tiempo). **Decisión: NO se agrega** — en su lugar,
`Suscripcion.meses_atraso` (sub-item A3) se convierte en la fuente única de
verdad, y tanto `context_processors.recordatorio_pago` como
`views.PagoPortalView.get_context_data` pasan a leer de ahí en vez de
recalcular cada uno su propio `delta // 30 + 1`.

### Hallazgos adicionales (checklist port, Kaizen #371) — fuera de este scope

Verificando `CHECKLIST_PORT.md` §2 (hardening que el template ya tiene)
contra el código real de Instelec aparecieron 2 gaps que **no están en los
5 puntos que Miguel aprobó** — se documentan acá para que quede registro,
NO se implementan en este RUN (recomendado como issue separado si se
prioriza):

- **Idempotencia del webhook** (`WompiWebhookView.post`, `views.py` líneas
  226-280): no tiene el guard `ya_estaba_aprobado` que trae el template. Si
  WOMPI reintenta el webhook de una transacción YA `APROBADO` (patrón común
  de pasarelas de pago), `_avanzar_fecha_proximo_pago` se vuelve a ejecutar
  y avanza la fecha un mes adicional de más. El redirect (`_procesar_transaccion_wompi`)
  SÍ tiene guard (`if Pago.objects.filter(wompi_transaction_id=tx_id).exists(): return`,
  línea 132) — el webhook no.
- **Colisión de referencia WOMPI**: `views.py` línea 205 usa
  `f"...{now:%Y%m}-{meses_adeudados}M"` (granularidad de mes), el template
  usa microsegundos (`%Y%m%d%H%M%S%f`). Un reintento de pago en el mismo mes
  con el mismo `meses_adeudados` puede colisionar de referencia.

Ninguno de los dos es parte del scope aprobado por Miguel (que es
específicamente sobre `n_meses`/grilla) — quedan documentados como hallazgo,
no como sub-item ejecutable de este plan.

## Verificación BD prod (lectura, proxy Cloud SQL — 2026-07-30)

`requiere_BD_prod_lectura=true` en F1 para confirmar si hay atraso real en
prod antes de tocar código. Resultado (SOLO SELECT, vía proxy
`127.0.0.1:5434`, `instelec_db`):

```sql
SELECT id, estado, fecha_proximo_pago, (CURRENT_DATE - fecha_proximo_pago) AS dias_atraso, plan_id
FROM pagos_suscripcion ORDER BY id;
--  id |  estado   | fecha_proximo_pago | dias_atraso | plan_id
--   2 | PENDIENTE | 2026-08-01         |          -2 |       1

SELECT id, nombre, precio, activo FROM pagos_planservicio ORDER BY id;
--  id |    nombre     |  precio   | activo
--   1 | Plan Instelec | 150000.00 | t

SELECT COUNT(*) FROM pagos_pago;  -- 0 filas
```

**Hallazgo clave para F2/F5:** prod tiene **exactamente 1 Suscripcion**
(singleton real, `Suscripcion.objects.first()` se usa en todo el código sin
filtro adicional — es asumido singleton), **sin atraso real hoy**
(`fecha_proximo_pago` vence en 2 días, no vencida) y **0 Pagos históricos**.
Esto significa:

- El escenario "atraso multi-mes real" (el que motiva todo el port) **no
  existe hoy en prod** — no hay dato legacy contra el cual validar
  `meses_atraso > 1`.
- **No se debe fabricar** ese escenario mutando `fecha_proximo_pago` de la
  Suscripcion real (id=2): es un singleton usado por `.first()` en toda la
  vista de pagos del cliente real — mutar su fecha de vencimiento, aunque
  sea temporalmente con restore, arriesga que el cliente real vea un estado
  de pago incorrecto si carga el portal durante la ventana del test, o que
  un fallo de cleanup deje la fecha real corrupta. **Se declara
  `data_seed_absent` para el ángulo "atraso > 1 mes"** (ver journey A7,
  Kaizen #53) — se valida en su lugar con el registro real actual
  (sin atraso, delta=-2) para confirmar que NO hay falso-positivo de atraso,
  y el caso multi-mes queda cubierto por tests unitarios (A6, fixtures
  locales) en vez de E2E prod.
- El webhook (`WompiWebhookView`) y el redirect (`_procesar_transaccion_wompi`)
  no se pueden ejercitar vía journey YAML sin una transacción WOMPI real
  (requieren firma HMAC real / `tx_id` real de la pasarela) — no hay step
  `http_post` en el runner de journeys. La persistencia de `n_meses` se
  valida por tests unitarios (A6) creando `Pago` directamente, no por E2E.
  El smoke del webhook en sí (que responda, no que persista) sigue el
  patrón de `CHECKLIST_PORT.md` §1.5: `curl -X POST
  https://instelec-api-*.run.app/pagos/webhook/ -d '{}'` debe responder
  400/401 (no 302 a login) — se agrega como paso de smoke Bash en F5,
  fuera del journey YAML.

## Sub-items por sprint

### Sprint A (deployable_solo: true — v1.0 completa, un solo deploy)

| # | Sub-item | Archivos | Tests | Dependencias | Complexity | Estado |
|---|---|---|---|---|---|---|
| A1 | Helper `calcular_n_meses(monto, precio_mes)` centralizado | `apps/pagos/models.py` (o `apps/pagos/utils.py` si se prefiere sacarlo de models) | tests_issue_199.py::CalcularNMesesTests | - | low | ⏳ pendiente |
| A2 | Campo `Pago.n_meses` (PositiveSmallIntegerField default=1) + migración 0002 + ambos call sites (`_procesar_transaccion_wompi` redirect y `WompiWebhookView.post`) calculan `n_meses` con A1 al crear `Pago`; refactor `_avanzar_fecha_proximo_pago(pago)` nueva firma (recibe `pago`, ya no `monto_pagado` suelto) | `apps/pagos/models.py`, `apps/pagos/migrations/0002_pago_n_meses.py`, `apps/pagos/views.py` | tests_issue_199.py::AvanzarFechaProximoPagoHelperTests, PagoNMesesPersistenceTests | A1 | medium | ⏳ pendiente |
| A3 | Property `Suscripcion.meses_atraso` — centraliza el cálculo hoy duplicado en `context_processors.recordatorio_pago` y `views.PagoPortalView.get_context_data`; ambos pasan a leer de la property | `apps/pagos/models.py`, `apps/pagos/context_processors.py`, `apps/pagos/views.py` | tests_issue_199.py::MesesAtrasoPropertyTests (incluye edge: `fecha_proximo_pago=None`, `estado='ACTIVA'`, `delta<0`) | - | medium | ⏳ pendiente |
| A4 | `alegra.py::crear_factura` reusa `pago.n_meses` en vez de recalcular con `round(monto/precio)` (líneas 86-91) — fix de sub-facturación potencial si el redondeo diverge del n_meses real cobrado | `apps/pagos/alegra.py` | tests_issue_199.py::AlegraFacturaNMesesTests (mockeando `requests`) | A2 | low | ⏳ pendiente |
| A5 | Grilla informativa "Estado por mes" (solo lectura, ventana 6 meses desde `fecha_proximo_pago`, SIN selector interactivo) en `portal.html`, alimentada por `meses_atraso` + `n_meses` de pagos recientes | `apps/pagos/views.py` (`PagoPortalView.get_context_data` agrega `grid_meses`), `templates/pagos/portal.html` | tests_issue_199.py::GrillaEstadoPorMesContextTests | A2, A3 | medium | ⏳ pendiente |
| A6 | Tests: `apps/pagos/tests_issue_199.py` (convención local, plano — no paquete `pagos/tests/`), usa `AUTH_USER_MODEL=usuarios.Usuario` (`USERNAME_FIELD='email'`) | `apps/pagos/tests_issue_199.py` | (es el propio archivo de tests) | A1, A2, A3, A4, A5 | medium | ⏳ pendiente |
| A7 | Smoke E2E — journey de regresión (pago forzado sin cambios) + grilla nueva + no-falso-atraso con dato real + curl webhook (fuera de YAML, ver nota) | `apps/pagos/views.py`, `templates/pagos/portal.html` | journey `Instelec_199.yaml` | A5 | medium | ⏳ pendiente |

No hay Sprint B — decisión explícita de Miguel de mantener el pago forzado
descarta el sub-item de selector interactivo que hubiera justificado partir
el scope.

## DAG dependencias

```
A1 → A2 → A4
A1 → A2 → A5
A3 → A5
A2, A3 → A5
A1, A2, A3, A4, A5 → A6
A5 → A7
```

## Riesgos y mitigaciones

- **Riesgo (medio): facturación Alegra.** `alegra.py::crear_factura` calcula
  `quantity`/`price` de la factura DIAN a partir del monto pagado. Un
  desalineamiento entre `n_meses` persistido y lo que Alegra factura
  produciría facturas incorrectas al cliente real de Instelec (Instelec
  paga a Indunnova). Mitigación: A4 hace que Alegra lea `pago.n_meses`
  directo (fuente única), no un recálculo independiente; A6 cubre con test
  el caso `round()` no exacto (ej. pago parcial) para no romper el fallback
  existente (`quantity=1, price=monto_pago` cuando no cuadra exacto).
- **Riesgo (bajo): migración aditiva.** `Pago.n_meses` con `default=1` es
  segura para los 0 registros históricos de `Pago` en prod (confirmado
  arriba) — no hay backfill que hacer, el default cubre el caso vacío.
- **Riesgo (bajo): singleton `Suscripcion.objects.first()`.** El código
  entero de `pagos` asume una sola Suscripcion activa por instancia. Ningún
  sub-item de este plan cambia esa asunción (fuera de scope) — se documenta
  para que F3 no la toque de pasada.
- **Riesgo (bajo, aceptado): sin dato legacy de atraso multi-mes.** Ver
  sección "Verificación BD prod" — se acepta 🟡 en el ángulo específico
  "atraso > 1 mes contra dato real" (no hay dato real disponible hoy y no
  se fabrica por el riesgo al singleton); el resto de sub-items sí valida
  con dato real (0 Pagos, Suscripcion id=2 real, sin atraso).
- **Hallazgos fuera de scope** (idempotencia webhook, colisión de
  referencia) — ver sección arriba, documentados, no implementados por
  decisión de scope de Miguel.

## Validación esperada (qa_claude smoke + journey)

- Login `qa_claude@instelec.com` vía `/usuarios/login/` (campo `username`,
  `USERNAME_FIELD='email'`).
- `/pagos/` (portal): plan Instelec ($150,000 COP), sin atraso real hoy →
  1 botón WOMPI, monto = 1 mes (`monto_centavos=15000000`), **sin selector**
  (regresión explícita — confirma que no se agregó UI de selección).
- `/pagos/` grilla nueva "Estado por mes" visible (ventana 6 meses,
  solo lectura) — marcada `# RECONCILIAR_DOM` hasta que F3 construya el
  template real.
- `/pagos/historial/` — estado vacío "No hay pagos registrados" (dato real:
  0 filas en `pagos_pago` hoy).
- `curl -X POST https://instelec-api-*.run.app/pagos/webhook/ -d '{}'` →
  400/401 (no 302 a login) — smoke Bash post-deploy, fuera del journey YAML
  (protocolo `CHECKLIST_PORT.md` §1.5).
- `PlanServicio.objects.exists()` sigue `True` en prod (ya lo está, no hay
  regresión de `crear_plan`).
