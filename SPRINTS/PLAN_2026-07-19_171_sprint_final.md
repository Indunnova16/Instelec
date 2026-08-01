# PLAN — Instelec#171 · Sprint final (v1.0 completa, sin más partición)

- **Issue:** Instelec#171
- **Ruta:** sprint_path (epic, decisión de alcance YA tomada por Miguel — ver Contexto)
- **Fecha plan:** 2026-07-19 · **Run:** RUN_2026-07-19_1814 · F1→F2
- **Complexity global:** epic (dominado por B2-B7, columnas configurables)
- **Riesgo global:** alto (refactor de `avance_ponderado` sobre datos existentes) — mitigado, ver sección Riesgos
- **Sprint único:** TODO el alcance restante entra en este sprint. NO se difiere nada a "Sprint C".

## Contexto

Instelec#171 pidió 2 bloques: (1) gestión de torres (insertar + numeración
alfanumérica + distinguir "Anulada" de "No aplica"), (2) columnas/actividades
configurables por capítulo (Obra Civil/Montaje/Tendido). Lleva 2 rondas de
cierre parcial (Sprint A 2026-07-01, Hochiminh Fase 1 2026-07-12) que
resolvieron todo EXCEPTO los 2 frentes de mayor complejidad/decisión: V3
("Anulada") y columnas configurables (V4-V7) — este último sigue en 0% de
implementación y es, según el propio revisor (2026-07-17), "el issue más
grande de los 4 abiertos de Construcción".

**Decisión de Miguel (HITL, ya tomada, no reabrir):** completar el epic 1.0
entero en este sprint, sin partir más. Diseñar defaults razonables para las
2 preguntas de discovery que siguen sin respuesta de Gabriel (V3, segundo
ejemplo de Hochiminh) en vez de esperar. Este PLAN reemplaza — no extiende —
los 2 PLAN.md anteriores (`PLAN_2026-07-01_171_sprint_a_torres.md`,
`PLAN_2026-07-12_171_hochiminh_fase1.md`), que quedan como historial, no
como referencia de scope vigente.

Alcance de este sprint (los 4 frentes vivos del hilo hoy):
1. **V3** — estado "Anulada" aditivo, separado de "No aplica" (`aplica`).
2. **Columnas configurables por capítulo (V4-V7)** — modelo genérico +
   refactor de las 3 matrices (Obra Civil, Montaje, Tendido).
3. **`entrega.html`** (`EntregaElectromecanica`) — activar, mismo patrón que
   `torre_form.html` en Sprint A.
4. **Follow-ups no-bug del QA de Hochiminh Fase 1** (07-14) — documentación,
   sin código.

### Por qué esto NO es un 3er rebote

**Qué falló en las 2 rondas previas:** no fue código roto — Sprint A y
Hochiminh Fase 1 se validaron 🟢/🟡 correctamente cada uno para su propio
alcance acotado. El patrón que rebotó fue de **planificación**: cada sprint
dejó fuera, explícita y deliberadamente, los 2 frentes más difíciles y
dependientes de una decisión de negocio (V3, columnas configurables),
esperando respuesta de Gabriel que nunca llegó. Tras 19 días y 2 rondas, el
pedido de mayor valor del issue original sigue en 0%.

**Por qué este plan sí cierra los frentes diferidos:** no vuelve a preguntar
lo mismo. Para V3, se implementa el default más seguro (aditivo, no toca
`aplica`) documentado abajo. Para columnas configurables, se diseña un
modelo genérico usando la arquitectura YA verificada en código (3 clases con
`COLUMNAS`/`COLUMNAS_CONDUCTOR`/`COLUMNAS_FIBRA` + pesos en
`ProyectoConstruccion`) en vez de esperar el segundo ejemplo de Hochiminh que
Gabriel no ha conseguido — exactamente la autorización que el propio
`@mbrt26` pidió el 2026-07-19 ("¿autorizás que diseñemos algo genérico sin
ese segundo ejemplo?"), concedida ahora por Miguel.

**Default concreto para V3:** se agrega un campo NUEVO e independiente
`TorreConstruccion.anulada` (`BooleanField`, default `False`), puramente
informativo — **no** altera `aplica` ni el cálculo de `avance_ponderado`
(que sigue gobernado 100% por `aplica`, sin tocar). Es seguro porque:
(a) el propio toggle `aplica` ya rebotó 5 veces en Instelec#149 por
ambigüedad de intent (`DECISIONS_2026-06-28_171-149.md`) — no se reutiliza
ni se pisa esa semántica; (b) aditivo puro = reversible sin costo si Gabriel
responde algo distinto (borrar 1 columna, sin migración de datos existente
que deshacer); (c) el propio comentario de 2026-06-29 del cliente usa
"Anular"/"Anulada" como sinónimo informal de exclusión de alcance, distinto
de "No aplica" que hoy excluye del cálculo — mapear "Anulada" a un estado
visual/informativo (torre cancelada del alcance planeado del proyecto, ej.
se decidió no construirla) separado de "aplica" (excluida del % de avance)
respeta esa distinción sin inventar una tercera regla de negocio.

## Verificación BD prod (F2, SOLO SELECT, proxy 127.0.0.1:5434, `instelec_db`)

Antes de diseñar la migración de `ColumnaConfigurable`, se verificó la
distribución REAL de columnas/pesos por proyecto en prod (instrucción
explícita del F1):

| Query | Resultado |
|---|---|
| `SELECT count(*) FROM construccion_proyectos` | **1 proyecto** en toda la BD (QA test #49 — Puerta de Oro, `ec2a68aa-…`) |
| Pesos Obra Civil (`peso_cerramiento_pct`…`peso_compactacion_pct`) | `5 / 30 / 5 / 15 / 30 / 15` (idénticos al default hardcodeado del modelo) |
| Pesos Montaje (`peso_mont_*_pct`) | `10 / 20 / 45 / 25` (idénticos al default) |
| Pesos Tendido conductor (`peso_tend_riega_manila_pct`…`peso_tend_balizas_pct`) | `20 / 20 / 30 / 10 / 10 / 10` (idénticos al default) |
| Pesos Tendido fibra (`peso_tend_*_fibra_pct`/`_opgw_pct`) | `10 / 20 / 40 / 20 / 10` (idénticos al default) |
| `count(*)` torres / `ObraCivilTorre` / `MontajeEstructuraTorre` / `TendidoTorre` | `65 / 65 / 65 / 65` (1:1, sin huérfanos) |

**Implicación de diseño:** con 1 solo proyecto real y sus pesos = default de
fábrica, la migración de datos de B2 tiene un caso de verificación exacto y
acotado (no hay que reconciliar N configuraciones distintas). El riesgo real
no es "¿qué pesos migro?" (ya se sabe, son los de arriba) sino "¿el refactor
de `avance_ponderado` produce el mismo resultado numérico antes/después
para las 65 torres reales?" — cubierto como verificación obligatoria en B3/B4.

## PDF "instructivo Hochiminh" (adjunto 2026-07-10, descargado y leído por F2)

Se descargó `LT.PDO.230KV_V1-HMG_2024.pdf` (2 páginas, 65 torres del mismo
proyecto Puerta de Oro). Confirma exactamente las mismas 11 columnas ya
implementadas en Hochiminh Fase 1 (Torre, Tipo, Cimentación, Estado Predial,
Estado Ambiental, Marcación A/B/C/D, Replanteo A/B/C/D, Instalación de
Guarda, Instalación Cables Conductores) — **es el mismo ejemplo ya
consumido**, no aporta un segundo caso de columnas distintas. Confirma lo
que Gabriel ya dijo el 07-10 ("mismo proyecto, no uno distinto"): no hay
insumo nuevo para dimensionar V4-V7 más allá del que ya se usó. El diseño de
`ColumnaConfigurable` de abajo se basa, por tanto, en generalizar la
arquitectura de código YA existente (3 capítulos con columnas+pesos), no en
un segundo ejemplo que no existe — consistente con la autorización de
Miguel de diseñar algo genérico sin esperarlo.

## Arquitectura actual (confirmada en código, línea por línea)

| Capítulo | Modelo | Columnas hoy | Tipo de valor | Pesos (en `ProyectoConstruccion`) |
|---|---|---|---|---|
| Obra Civil | `ObraCivilTorre` (`models.py:972`) | 6 (`cerramiento`…`compactacion`) | `DecimalField` 0–1 (fracción) | `peso_cerramiento_pct`…`peso_compactacion_pct` |
| Montaje | `MontajeEstructuraTorre` (`models.py:1104`) | 4 (`estructura_sitio`…`revisada`) | `DecimalField` 0–1 | `peso_mont_*_pct` |
| Tendido — conductor | `TendidoTorre` (`models.py:1374`) | 6 (`riega_manila_conductor`…`balizas_desviadores`) | **`BooleanField`** (0/1, no decimal) | `peso_tend_riega_manila_pct`…`peso_tend_balizas_pct` |
| Tendido — fibra | `TendidoTorre` (`models.py:1382`) | 5 (`riega_manila_fibra`…`empalmes_opgw`) | **`BooleanField`** | `peso_tend_*_fibra_pct`/`_opgw_pct` |

Los 3 `avance_ponderado`/`avance_conductor`/`avance_fibra` calculan
`SUMPRODUCT(peso, valor) / SUM(peso)` — mismo patrón matemático en los 3
modelos, solo cambia si `valor` es `Decimal` (OC/Montaje) o `1 if bool else
0` (Tendido). Este patrón compartido es lo que permite un solo modelo
`ColumnaConfigurable` para los 4 sub-capítulos.

Nota: `TendidoTorre` tiene además 2 campos NO ponderados
(`placas_senalizacion`, `facturadas_hmv`, control administrativo) y 2 campos
gate (`vestida_conductor`, `vestida_fibra`) que **no** entran en
`ColumnaConfigurable` — no son parte del SUMPRODUCT, fuera de scope de este
refactor.

## Sub-items

| ID | Sub-item | Complexity | Deployable solo | Dependencias | Archivos a tocar |
|----|----------|------------|------------------|---------------|-------------------|
| B1 | V3 — `TorreConstruccion.anulada` aditivo | low | sí | — | `apps/construccion/models.py`, migración nueva, `apps/construccion/views.py` (agregar `anulada` a `fields` de `TorreCreateView`/`TorreEditView`), `templates/construccion/torre_form.html`, `templates/construccion/obra_civil_matriz.html`/`montaje_matriz.html`/`tendido_matriz.html`/`hochiminh_matriz.html` (badge visual) |
| B2 | Modelo `ColumnaConfigurable` + migración de datos (fundamento, sin UI) | high | no (base de B3-B7) | — | `apps/construccion/models.py`, migración nueva (schema + data migration), `apps/construccion/signals.py` o `ProyectoConstruccion.save()` (defaults para proyectos nuevos) |
| B3 | Refactor `avance_ponderado` (Obra Civil + Montaje) sobre `ColumnaConfigurable` | medium | no | B2 | `apps/construccion/models.py` (`ObraCivilTorre.avance_ponderado`, `MontajeEstructuraTorre.avance_ponderado`) |
| B4 | Refactor `avance_conductor`/`avance_fibra` (Tendido) sobre `ColumnaConfigurable` | medium | no | B2 | `apps/construccion/models.py` (`TendidoTorre.avance_conductor`, `.avance_fibra`) |
| B5 | Modelo `ColumnaConfigurableValor` (EAV) para columnas custom nuevas | high | no | B2 | `apps/construccion/models.py`, migración nueva |
| B6 | UI administración de columnas por proyecto/capítulo (agregar/quitar/reordenar/pesos) | high | no | B2, B5 | `apps/construccion/views.py` (nueva `ColumnasConfigurablesView` + `ColumnaToggleView`/`ColumnaCrearView`/`ColumnaReordenarView`), `apps/construccion/urls.py`, `templates/construccion/columnas_configurables.html` (nuevo) |
| B7 | Matrices dinámicas — Obra Civil/Montaje/Tendido renderizan columnas activas (sistema+custom) | epic | no | B3, B4, B5, B6 | `apps/construccion/views.py` (`ObraCivilListView`/`MontajeListView`/`TendidoListView` context), `apps/construccion/urls.py` (endpoint genérico `ColumnaValorUpdateView`), `templates/construccion/obra_civil_matriz.html`, `montaje_matriz.html`, `tendido_matriz.html` |
| B8 | `entrega.html` — activar matriz + detalle editable por torre | low | sí | — | `templates/construccion/entrega.html`, `templates/construccion/entrega_torre.html` (nuevo), `apps/construccion/views.py` (nueva `EntregaTorreView`), `apps/construccion/urls.py` |
| B9 | Follow-ups QA Hochiminh (no-bug): documentar flujo clic-torre + declarar scope de Tipo/Cimentación vacíos | trivial | sí | — | `Instelec/CLAUDE.md` o `Documentacion/` (nota), sin código de app |

### DAG de dependencias

```
B1 (independiente)
B8 (independiente)
B9 (independiente, sin código)

B2 (ColumnaConfigurable + data migration)
 ├──> B3 (avance_ponderado OC/Montaje)
 ├──> B4 (avance_conductor/fibra Tendido)
 ├──> B5 (ColumnaConfigurableValor EAV)
 │      └──> B6 (UI administración columnas)
 └──> [B3+B4+B5+B6] ──> B7 (matrices dinámicas — integra todo)
```

**B2→B7 es UN solo bloque deployable** (columnas configurables completo) —
no tiene sentido desplegar B3 sin B2, ni B7 sin B3/B4/B5/B6 (romperían el
cálculo de avance a medio camino). B1, B8, B9 sí son deployables
independientes y pueden ir en el mismo PR/deploy sin acoplarse al bloque de
columnas.

## Diseño detallado

### B1 — V3 "Anulada"

```python
# TorreConstruccion, junto a `aplica`
anulada = models.BooleanField(
    'Torre anulada', default=False,
    help_text='Torre cancelada del alcance planeado del proyecto (ej. se '
              'decidió no construirla). Distinto de "No aplica" (aplica=False, '
              'que excluye del % de avance pero la torre sigue en alcance). '
              'No afecta avance_ponderado ni ningún cálculo — solo informativo (#171 V3).')
```

Render: badge rojo tachado "Anulada" junto al número de torre en las 4
matrices (Obra Civil/Montaje/Tendido/Hochiminh), visualmente distinto del
gris de `aplica=False` (mismo lugar donde hoy se aplica `opacity-50` a la
fila si `not fila.torre.aplica` — se agrega una segunda clase condicional,
no se reemplaza la existente). Checkbox nuevo en `torre_form.html`, mismo
patrón que el resto de campos del form (`{{ field }}` genérico, sin HTML a
mano).

### B2 — `ColumnaConfigurable`

```python
class ColumnaConfigurable(BaseModel):
    CAPITULO_CHOICES = [
        ('OBRA_CIVIL', 'Obra Civil'),
        ('MONTAJE', 'Montaje'),
        ('TENDIDO_CONDUCTOR', 'Tendido — Conductor'),
        ('TENDIDO_FIBRA', 'Tendido — Fibra/OPGW'),
    ]
    TIPO_VALOR_CHOICES = [('DECIMAL', 'Avance % (0-100)'), ('BOOLEAN', 'Check (hecho/no hecho)')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    proyecto = models.ForeignKey(ProyectoConstruccion, on_delete=models.CASCADE,
                                  related_name='columnas_configurables')
    capitulo = models.CharField(max_length=20, choices=CAPITULO_CHOICES)
    clave = models.SlugField('Clave interna', max_length=40)
    etiqueta = models.CharField('Etiqueta visible', max_length=100)
    orden = models.PositiveSmallIntegerField(default=0)
    peso_pct = models.PositiveSmallIntegerField('Peso %', default=0)
    tipo_valor = models.CharField(max_length=10, choices=TIPO_VALOR_CHOICES)
    es_sistema = models.BooleanField(
        default=False,
        help_text='True = una de las columnas originales hardcodeadas (Cerramiento, '
                  'Excavación, etc.) — no se puede ELIMINAR, solo desactivar (activa=False). '
                  'False = columna nueva agregada por el cliente vía UI (B6), usa '
                  'ColumnaConfigurableValor (EAV) para su dato.')
    activa = models.BooleanField(default=True)

    class Meta:
        db_table = 'construccion_columna_configurable'
        unique_together = [['proyecto', 'capitulo', 'clave']]
        ordering = ['proyecto', 'capitulo', 'orden']
```

**Migración `0044_columna_configurable.py`:**
1. `CreateModel ColumnaConfigurable`.
2. **Data migration** — para CADA `ProyectoConstruccion` existente (hoy: 1,
   Puerta de Oro), crear las 21 filas `es_sistema=True, activa=True` con
   `clave`/`etiqueta`/`orden` tomados literal de las 4 listas
   `COLUMNAS`/`COLUMNAS_CONDUCTOR`/`COLUMNAS_FIBRA` del código y `peso_pct`
   tomado del valor REAL de `proyecto.peso_*_pct` verificado arriba (5/30/5/
   15/30/15 OC, 10/20/45/25 Montaje, 20/20/30/10/10/10 tend-conductor,
   10/20/40/20/10 tend-fibra) — **no** un default distinto, el valor exacto
   que ya rige hoy, para que el refactor de B3/B4 sea matemáticamente
   idéntico antes/después.
3. Migración **reversible** (`reverse_code` que borra las filas creadas) —
   requisito estándar del repo para cualquier data migration.

**Proyectos nuevos (post-B2):** override de `ProyectoConstruccion.save()`
(o señal `post_save` si el patrón dominante del repo la usa — confirmar en
`apps/construccion/models.py` cuál usa `ProyectoConstruccion` hoy antes de
elegir) que, solo en creación (`created=True`), invoca un helper
`crear_columnas_configurables_default(proyecto)` con las MISMAS 21 filas de
fábrica de la data migration — mismo resultado que hoy (proyecto nuevo con
`peso_*_pct` = default del `PositiveSmallIntegerField`), sin regresión.

Los campos legacy `peso_*_pct` en `ProyectoConstruccion` **NO se eliminan**
en este sprint — quedan vestigiales (comentario `# DEPRECADO #171: fuente de'
verdad ahora es ColumnaConfigurable` en el modelo) para no forzar una
migración de reversión más arriesgada; se limpian en un issue aparte de
housekeeping si Miguel lo autoriza.

### B3/B4 — Refactor de `avance_ponderado`/`avance_conductor`/`avance_fibra`

Patrón común (ejemplo Obra Civil):

```python
@property
def avance_ponderado(self):
    from decimal import Decimal
    columnas = self.proyecto.columnas_configurables.filter(
        capitulo='OBRA_CIVIL', activa=True)
    avances_sistema = self.avances_dict  # dict clave->Decimal, ya existe
    total_peso = 0
    suma = Decimal('0')
    for col in columnas:
        peso = col.peso_pct
        total_peso += peso
        if col.es_sistema:
            valor = avances_sistema.get(col.clave, Decimal('0'))
        else:
            valor = col.valor_para_torre(self.torre)  # B5, Decimal 0-1
        suma += valor * Decimal(peso)
    return suma / Decimal(total_peso or 1)
```

Tendido usa el mismo patrón pero `valor = Decimal('1') if getattr(self,
col.clave, False) else Decimal('0')` para columnas sistema (booleanas), y
`col.valor_para_torre(self.torre)` (booleano) para custom.

**Verificación obligatoria (no opcional):** correr, ANTES y DESPUÉS del
refactor, `avance_ponderado_pct`/`avance_conductor_pct`/`avance_fibra_pct`
para las 65 torres reales del proyecto QA y comparar — deben ser
IDÉNTICOS byte a byte (mismos pesos, misma fórmula, solo cambia la fuente).
Vive como test de regresión (`tests_issue_171_columnas.py`), no solo
verificación manual — corre en CI en cada deploy futuro.

### B5 — `ColumnaConfigurableValor` (EAV para columnas nuevas)

```python
class ColumnaConfigurableValor(BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    columna = models.ForeignKey(ColumnaConfigurable, on_delete=models.CASCADE,
                                 related_name='valores')
    torre = models.ForeignKey(TorreConstruccion, on_delete=models.CASCADE,
                               related_name='valores_columnas_configurables')
    valor_decimal = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    valor_boolean = models.BooleanField(null=True, blank=True)

    class Meta:
        db_table = 'construccion_columna_configurable_valor'
        unique_together = [['columna', 'torre']]
```

Solo se crea/consulta para columnas `es_sistema=False` (custom) — las 21
columnas de fábrica siguen leyendo/escribiendo sus `DecimalField`/
`BooleanField` reales de siempre (cero migración de datos existentes hacia
EAV, cero riesgo de performance sobre el camino ya probado en prod).

### B6 — UI administración de columnas

Vista `ColumnasConfigurablesView` en
`/construccion/{proyecto_uuid}/columnas/` (`allowed_roles = ['admin',
'director']` — es configuración, no operación de campo), tabs por capítulo
(4), tabla por capítulo con: etiqueta, peso %, tipo, activa (toggle AJAX,
mismo patrón `HochiminhToggleView`), botón eliminar (solo si
`es_sistema=False`, columnas sistema solo se desactivan), botón "+ Agregar
columna" (modal: etiqueta + tipo_valor + peso_pct, crea `clave` como slug de
la etiqueta). Reordenar: botones ↑/↓ por fila (AJAX que intercambia `orden`
con la fila adyacente) — más simple y confiable que drag-and-drop para v1.0.

Advertencia no bloqueante (badge) si `sum(peso_pct activos) != 100` por
capítulo — el cálculo YA normaliza por `total_peso` real (tolera != 100
matemáticamente, mismo patrón que hoy), pero es una señal útil para Gabriel/
Rodrigo si se desconfigura por error.

### B7 — Matrices dinámicas

`ObraCivilListView`/`MontajeListView`/`TendidoListView.get_context_data`
agregan `columnas_activas = proyecto.columnas_configurables.filter(capitulo=X,
activa=True).order_by('orden')` al contexto. Los 3 templates
(`obra_civil_matriz.html`, `montaje_matriz.html`, `tendido_matriz.html`)
iteran `columnas_activas` para el `<thead>` y, por fila, renderizan: si
`col.es_sistema` → el input/checkbox EXISTENTE de siempre (mismo endpoint de
guardado que ya funciona en prod, cero cambio de comportamiento); si NO
(`custom`) → un input nuevo (decimal % o checkbox según `tipo_valor`) que
postea a un endpoint genérico nuevo:

```
POST /construccion/{proyecto_id}/columnas/{columna_id}/torres/{torre_id}/valor/
```

(`ColumnaValorUpdateView`, mismo patrón que `HochiminhToggleView` — `get_or_create`
+ guardar `valor_decimal` o `valor_boolean` según `columna.tipo_valor`).

`data-testid` sugeridos (F3 puede usar otros, F6 reconcilia):
`columna-custom-{clave}` en el `<th>`, `valor-columna-{columna_id}-torre-{torre_id}`
en cada celda editable.

### B8 — `entrega.html`

`EntregaView` YA construye `context['entregas']` (queryset de
`EntregaElectromecanica` por torre, ordenado). El template implementa una
matriz de solo-listado (Torre-link | Formato obs (icono si hay texto) |
Firmó HMV (check) | Firmó WSP (check) | Cajas OPGW | Fecha 1ra visita |
Fecha 2da visita | Avance % | Estado badge Liberada/Pendiente/Rechazada),
mismo patrón sticky-header que el resto de matrices. Torre es un link a
`EntregaTorreView` (nueva, patrón `ObraCivilTorreView`/`TorreEditView`) en
`/construccion/{proyecto_uuid}/entrega/{torre_uuid}/editar/` — form completo
con TODOS los campos de `EntregaElectromecanica` (observaciones SPT/
estructura/conductor A-B-C/OPGW izq-der, firmas, cajas OPGW, fechas, avance,
estado, observaciones adicionales), reusando `_form_generico.html` o el
patrón inline de `torre_form.html` (decisión de F3).

Ya existe URL/vista `EntregaView` en `/entrega/` (confirmado en
`urls.py:51`, ruta ya reachable desde `proyecto_dashboard.html`, sin
necesidad de agregar entrada de sidebar) — el gap es 100% de template +
la vista de detalle nueva, mismo patrón que `torre_form.html` en Sprint A
(complexity baja, sin sorpresas de backend).

### B9 — Follow-ups QA Hochiminh (sin código)

1. **Flujo clic-torre:** documentar en `Instelec/CLAUDE.md` (sección
   Hochiminh, o nota en `Documentacion/`) que el clic en el número de torre
   de la matriz Hochiminh abre "Editar torre" general (Tipo/Cimentación/
   Peso/Cuadrillas) — Marcación, Replanteo, Predial y Ambiental se editan
   DIRECTO en la matriz (checks inline), no en una pantalla dedicada. Este
   es el comportamiento confirmado con el cliente el 07-14 ("no bug") — se
   documenta para que no se vuelva a levantar como duda.
2. **Backlog Tipo/Cimentación vacíos:** se declara ❌ fuera de scope de
   #171 (no pedido explícitamente en el issue). Diligenciamiento manual
   torre-por-torre ya es posible hoy vía "Editar torre" (Sprint A). Si
   Gabriel pide carga masiva (import Excel), es un issue nuevo aparte —
   documentado como sugerencia, no ejecutado acá.

## Tabla de entregables (gate anti-FIX_INCOMPLETO)

| # | Entregable | Evidencia esperada | ✅/❌ |
|---|---|---|---|
| 1 | `TorreConstruccion.anulada` — campo nuevo, checkbox en form, badge visual en las 4 matrices | GET torre_form muestra checkbox "Anulada"; POST con `anulada=on` → torre creada con `anulada=True`; matrices muestran badge distinto de `aplica=False` | ❌ pendiente ejecución |
| 2 | Modelo `ColumnaConfigurable` + 21 filas de datos para el proyecto QA existente (valores idénticos a los verificados en BD) | `SELECT * FROM construccion_columna_configurable WHERE proyecto_id='ec2a68aa-…'` → 21 filas, `peso_pct` idéntico a los valores de la tabla de verificación BD arriba | ❌ pendiente ejecución |
| 3 | `avance_ponderado_pct` (OC/Montaje) idéntico antes/después del refactor para las 65 torres reales | Test de regresión automatizado, 0 diffs | ❌ pendiente ejecución |
| 4 | `avance_conductor_pct`/`avance_fibra_pct` (Tendido) idéntico antes/después para las 65 torres reales | Test de regresión automatizado, 0 diffs | ❌ pendiente ejecución |
| 5 | UI de administración de columnas (`/columnas/`) — agregar, desactivar (sistema), eliminar (custom), reordenar, editar peso | Smoke E2E: agregar 1 columna custom nueva, verla en la matriz correspondiente (B7), desactivarla, confirma que desaparece de la matriz | ❌ pendiente ejecución |
| 6 | Matrices Obra Civil/Montaje/Tendido renderizan columnas custom activas con input editable que persiste | E2E: crear columna custom "Prueba QA" en Obra Civil, escribir un valor en una torre real, recargar, confirmar persistencia en `ColumnaConfigurableValor` y que `avance_ponderado` la incluye en el cálculo | ❌ pendiente ejecución |
| 7 | `entrega.html` — matriz real (no placeholder) + detalle editable por torre | GET `/construccion/{uuid}/entrega/` → 200, sin "En Desarrollo", lista 65 torres; GET/POST detalle de una torre real → 200, campos pre-poblados/guardan | ❌ pendiente ejecución |
| 8 | Follow-up Hochiminh: flujo clic-torre documentado | Nota agregada en `CLAUDE.md`/`Documentacion/`, comentario del issue la referencia | ❌ pendiente ejecución |
| 9 | Follow-up Hochiminh: backlog Tipo/Cimentación declarado explícitamente (fuera de scope, sin código) | Comentario del issue lo declara ℹ️ con justificación | ❌ pendiente ejecución |

## Riesgos y mitigaciones

- **Riesgo alto — refactor de `avance_ponderado` sobre datos reales de 65
  torres × 3 capítulos.** Mitigado: (a) valores de pesos ya verificados
  contra BD prod (tabla arriba, idénticos a los defaults hardcodeados —
  sin sorpresas de reconciliación), (b) test de regresión obligatorio
  antes/después con las 65 torres reales (entregable #3/#4), (c) migración
  de datos reversible.
- **Riesgo medio — 2 modelos nuevos (`ColumnaConfigurable`,
  `ColumnaConfigurableValor`) + 1 UI de administración nueva sin precedente
  exacto en el repo.** Mitigado por reusar el patrón `HochiminhToggleView`
  (AJAX get_or_create + guardar) ya probado en prod desde Fase 1, y por NO
  tocar el camino de datos de las 21 columnas de fábrica (siguen en sus
  `DecimalField`/`BooleanField` reales, EAV solo para lo genuinamente nuevo).
- **Riesgo bajo — V3 (`anulada`)** aditivo puro, sin lógica de negocio
  nueva, reversible sin costo.
- **Riesgo bajo — `entrega.html`** mismo patrón ya ejecutado y validado en
  Sprint A para `torre_form.html`.
- **Sin insumo del cliente para columnas configurables (2do ejemplo
  Hochiminh nunca llegó).** Aceptado explícitamente por Miguel — el diseño
  usa la arquitectura de código YA existente como fuente de verdad de las
  columnas "de fábrica", y la UI de administración (B6) resuelve
  cualquier variabilidad futura entre proyectos sin necesitar ese ejemplo
  (es precisamente la funcionalidad que lo hace innecesario).
- **Alcance grande para un solo sprint (epic, B2-B7 con 5 sub-items
  high/epic encadenados).** Documentado como riesgo explícito — consistente
  con la estimación previa ("≈3x el tiempo" en `DECISIONS_2026-06-28_171-149.md`).
  Miguel decidió ir completo igual; si el tiempo aprieta, B1/B8/B9 son
  recortables sin tocar la columna vertebral (B2-B7) porque son
  independientes — priorizar B2-B7 sobre B1/B8/B9 si hay que elegir.

## Validación esperada (smoke E2E post-deploy)

1. `/construccion/{uuid}/torres/crear/` → checkbox "Anulada" visible, crear
   torre con `anulada=True`, verificar badge en `/construccion/{uuid}/obra-civil/`.
2. `/construccion/{uuid}/columnas/` → 200, 4 tabs (Obra Civil/Montaje/
   Tendido Conductor/Tendido Fibra), cada uno lista sus columnas de fábrica
   (6/4/6/5) con peso y activa=✓.
3. Agregar columna custom en Obra Civil ("QA_E2E_171_columna_test", tipo
   DECIMAL, peso 10) → aparece en `/construccion/{uuid}/obra-civil/` como
   columna nueva; escribir un valor en torre E1 real → recarga → valor
   persiste → `avance_ponderado_pct` de E1 cambia reflejando el nuevo peso.
   Cleanup: eliminar la columna custom (`DELETE FROM
   construccion_columna_configurable WHERE clave='qa_e2e_171_columna_test'`).
4. Repetir un caso equivalente en Tendido (columna BOOLEAN).
5. `/construccion/{uuid}/entrega/` → 200, sin "En Desarrollo", 65 torres
   listadas; abrir detalle de una torre real (ej. E1) → 200, form con los
   campos de `EntregaElectromecanica`.
6. Regresión: `avance_ponderado_pct` de las 65 torres en Obra Civil/Montaje
   y `avance_conductor_pct`/`avance_fibra_pct` en Tendido — idénticos a los
   valores pre-deploy (capturados como baseline antes del deploy).

## Referencias

- Planes previos (historial, no vigentes): `PLAN_2026-07-01_171_sprint_a_torres.md`,
  `PLAN_2026-07-12_171_hochiminh_fase1.md`.
- Decisión de discovery original: `DECISIONS_2026-06-28_171-149.md`.
- Triage F1 de hoy: `SPRINTS/RUN_2026-07-19_1814/agents/Instelec_171_f1.json`.
- PDF instructivo (descargado y leído por F2): `LT.PDO.230KV_V1-HMG_2024.pdf`
  (adjunto issue, comentario 2026-07-10).
- Arquitectura fuente: `apps/construccion/models.py` líneas 522-600
  (`TorreConstruccion`), 972 (`ObraCivilTorre.COLUMNAS`), 1104
  (`MontajeEstructuraTorre.COLUMNAS`), 1374/1382 (`TendidoTorre.COLUMNAS_*`),
  2240 (`EntregaElectromecanica`); `apps/construccion/views.py` líneas
  124-186 (Torre CRUD), 396-412 (`EntregaView`), 1191-1240
  (`ObraCivilTorreView`, patrón de detalle por torre), 2198-2280 (Hochiminh
  Fase 1, patrón de matriz + toggle AJAX).
