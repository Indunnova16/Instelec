# PLAN — #268 Presupuesto Real (Ejecutado) · ejecución directa 2026-09-25

Reemplaza el diseño de `PLAN_2026-09-22_268_presupuesto_real_ejecutado.md` (vista
`/financiero/presupuesto-real-v2/` por contrato): #267 construyó el Presupuesto
Planeado **dentro del proyecto de Construcción**, y ahí mismo existía la pestaña
"Presupuesto Real" con un "Cargar Ejecución" roto (la vista no tenía `post()`).
El real vive ahora al lado del planeado, en el mismo proyecto:
`/construccion/{proyecto}/financiero/presupuesto-real/`.

**Clave del cruce:** el planeado de prod guarda, bajo cada rubro, las mismas
"cuentas equivalentes" que trae el Excel real (Prestaciones Sociales, Seguridad
Social, CIF…) con meses por nombre → comparación cuenta a cuenta, subtotal por
rubro (`MapeoCtaRubro`, el mismo mapeo del importador del planeado). Se compara
contra el presupuesto de los **meses con ejecución cargada** (o el período filtrado).

## Tabla de entregables (criterios de aceptación del issue)

| # | Entregable | Evidencia esperada | ✅/❌ |
|---|---|---|---|
| 1 | Carga Excel 18 columnas (orden exacto) | POST en la pestaña "Cargar gastos reales" → mensaje de éxito | |
| 2 | Validación NIT contra maestro #262 (error si no existe, aviso si inactivo) | error/aviso visible; nada se guarda si hay errores | |
| 3 | Matriz "Gastos Reales × Meses" | tabla Ene–Dic por cuenta/rubro | |
| 4 | Columnas Total Real, Presupuesto, Variación ($), % | columnas en la matriz | |
| 5 | KPI cards Planeado / Real / Variación / Cumplimiento % | 4 cards | |
| 6 | Semáforo 🟢 < presupuesto · 🟡 0–10 % · 🔴 > 10 % | columna semáforo | |
| 7 | Filtros Clasificación / Proveedor / Centro de costo / Período | form de filtros | |
| 8 | Relación proveedor: nombre, estado, total + link a #262 | tabla Proveedores | |
| 9 | Historial de cargas (fecha, usuario, filas, total, período, estado) | tabla en la pestaña de carga | |
| 10 | UPSERT por período (re-subir reemplaza, no duplica) | test + re-carga | |
| 11 | API `GET /api/presupuesto-real/{proyecto}/periodo/{mes}/{año}` para #246 | 200 JSON | |
| 12 | Reportes PDF / Excel / CSV | descargas | |
| V | Validaciones: .xlsx, encabezados, Periodo AAAAMM, Neto > 0, Fecha ≤ 30 días antes del período, Docto no duplicado | tests | |

## Decisiones de interpretación (ℹ️, van en el comentario)

- **Fecha "no retroactiva (máx 30 días)"**: se mide contra el inicio del Periodo de
  la línea (no contra hoy — si fuera contra hoy, el archivo de febrero no podría
  cargarse en septiembre, contradiciendo el criterio "156 líneas sin errores").
- **"Docto único por período"**: un comprobante contable trae varias líneas
  (nómina, varios terceros). Se rechaza la línea **repetida** (mismo Docto +
  Auxiliar + NIT + Neto en el período); el re-cargue del período nunca duplica.
- **Clasificación** Fijo/Variable sale de la columna "Fijo" (Sí/X/1 → Fijo).
- Los filtros de proveedor/centro de costo aplican a lo real; el planeado no
  tiene esas dimensiones.

## Pendiente del cliente

- Los 10 NIT citados en el comentario del issue **no están** hoy en el maestro de
  proveedores de prod — la carga los listará como error hasta registrarlos (#262).
- `presupuesto_test_real.xlsx` no está adjunto: se probó con archivos generados
  con la estructura exacta de 18 columnas.
