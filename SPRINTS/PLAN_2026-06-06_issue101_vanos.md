# Plan #101 — Vanos no cargan en Registrar Avances (re-apertura Sofi 2026-06-06)

## Causa raíz (confirmada)
- `lineas.cantidad_vanos` es un **contador metadato** (PositiveIntegerField). Editarlo
  (acción AJAX `actualizar_vanos` en `LineaDetailView.post`) NO crea filas `Vano`.
- La grilla de Registrar Avances (`RegistroAvanceCreateView`) se construye de filas
  `Vano` reales (tabla `vanos`). LN5114: `cantidad_vanos=100`, 104 torres, **0 vanos** →
  "No hay vanos registrados".
- Los PRs #106/#107/#108 arreglaron el 500 (UUID, `ignore missing`, rol admin_general)
  pero el gap real era que nunca se materializan los vanos.
- Bonus: el check de permiso de `actualizar_vanos` excluye `admin_general`/`ing_residente`
  (RBAC v2) → esos roles reciben 403.

## Decisión (Miguel → "qué recomiendas" → Opción A)
Materializar vanos desde el contador, idempotente y NO destructivo.

## Pasos
1. `Linea.sincronizar_vanos(cantidad)` en `models_base.py` — crea Vano `1..N` faltantes,
   nunca borra, tope 5000. [prioridad 1]
2. `LineaDetailView.post` (`actualizar_vanos`): llamar sincronizar + JSON con creados/total
   + ampliar roles a admin_general/ing_residente. [prioridad 1, dep 1]
3. `RegistroAvanceCreateView._build_context`: ordenar vanos numéricamente (evita 1,10,100,11). [prioridad 2]
4. Tests: idempotencia, no-destructivo, cap, integración POST. [prioridad 1, dep 1-2]
5. Deploy → smoke: re-guardar 100 en LN5114 vía endpoint (materializa la línea real +
   valida) → grid muestra 100 casillas. Cleanup NO (es el dato que el cliente quiere). [dep 4]
6. Comentario a Sofi + assignee validador.

## Bloqueos
- Ninguno. BD prod accesible vía proxy 5433.
