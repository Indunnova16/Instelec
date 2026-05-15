# Guía de Usuario — Mantenimiento de Líneas

Esta guía cubre el módulo de Mantenimiento de Líneas de TransMaint para los
roles Inspector, Supervisor y Coordinador.

## 1. Cómo registrar una inspección desde el móvil

1. Inicia sesión y abre el menú **Formato de Campo → Nuevo Registro**.
2. **Pantalla 1 — Seleccionar línea:** elige la línea y opcionalmente la torre.
3. **Pantalla 2 — Detalles:** fecha, tipo de inspección, cuadrilla.
4. **Pantalla 3 — Hallazgos:** descripción y **severidad** (Baja / Media / Alta / Crítica).
5. **Pantalla 4 — Evidencia:** fotos Antes / Durante / Después.

Al sincronizar el registro:
- Se crea un `HistorialIntervencion` automáticamente.
- Se actualiza `last_inspection_date` y `inspection_status` de la línea y la torre.
- Si la severidad es Alta/Crítica, el estado escala a `CRITICA`.

## 2. Cómo interpretar la timeline de una línea

Entra a **Líneas → \<línea\> → Hoja de Vida**. Eventos posibles:

| Icono | Tipo | Fuente |
|-------|------|--------|
| 🔧 | Intervención | `HistorialIntervencion` (cierre formal de actividad) |
| 📋 | Registro de campo | `RegistroCampo` sin historial aún |
| ⚠ | Reporte de daño | `ReporteDano` (severidad y descripción) |
| ✓ | Avance de vano | `AvanceVano` (vano por vano) |

**Severidades** (colores):
- Baja → gris
- Media → amarillo
- Alta → naranja
- Crítica → rojo

## 3. Cómo leer alertas

- **"Revisión vencida"** (badge rojo en el listado): `last_inspection_date` excede el umbral (30 días por defecto). El comando `marcar_inspecciones_vencidas` corre diariamente vía Celery beat.
- **"Próxima a vencer"** (badge amarillo): falta menos de 10 días para vencer.
- **"Crítica"** (badge rojo oscuro): existe un registro reciente con severidad Alta/Crítica.

## 4. Cómo usar el mapa

**Menú → Mapa en Vivo.** El mapa carga las 4586 torres Transelca con clustering.

- **Click en cluster:** zoom automático para abrir el grupo.
- **Click en torre:** popup con número, línea, voltaje y enlace a la hoja de vida.
- **Filtros:** voltaje (34.5 / 110 / 220 kV) y estado de inspección.
- **Tab Mantenimiento / Construcción:** se aplica desde el sidebar; el mapa respeta la unidad de negocio activa.

## 5. Filtros globales Mantenimiento / Construcción

El selector del sidebar guarda la unidad activa en sesión. Afecta:
- Listado de contratos (`/contratos/`).
- Actividades (`/actividades/`).
- Mapa (`/lineas/mapa/`).
- Dashboard de mantenimiento (`/indicadores/mantenimiento/`).

## 6. Troubleshooting

| Síntoma | Causa probable | Acción |
|---------|----------------|--------|
| No veo mis registros sincronizados | Sesión móvil sin conexión | Reabrir la app, verificar `sincronizado=True` |
| El mapa se ve lento | Demasiadas torres en viewport | Hacer zoom — el cluster optimiza > 12 |
| El badge no se actualiza | Cache de 5 min en dashboard | Esperar o limpiar cache Redis |
| Edito un contrato y faltan torres | Reducción previa de `numero_torres` | Subir el número y se reactivan las archivadas (#38) |

## 7. Referencia rápida

| Concepto | Modelo / archivo |
|----------|------------------|
| Inspección | `apps.campo.RegistroCampo` |
| Daño | `apps.campo.ReporteDano` |
| Intervención (cierre) | `apps.actividades.HistorialIntervencion` |
| Avance de vano | `apps.campo.AvanceVano` |
| Torre soft-deleted (contratos) | `apps.ingenieria.TorreContrato.archivada` |

## 8. Contactos y escalación

- **Coordinador de mantenimiento:** Alcides (alcides@…)
- **Supervisor de cuadrillas:** asignado por contrato
- **Soporte técnico aplicativo:** Miguel Rodríguez (mrodriguez@indunnova.com)
