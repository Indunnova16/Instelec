# PLAN — Instelec#171 · Hochiminh Fase 1 (matriz por torre)

**Fecha:** 2026-07-12 · **Run:** RUN_2026-07-12_1258 · **F1→F2** · Ruta: `sprint_path`

## Contexto (no reabrir)

Frente 2 de #171 ("columnas configurables por capítulo"), bloqueado en discovery
desde 2026-06-28 (`SPRINTS/DECISIONS_2026-06-28_171-149.md`), resuelto por el
cliente el 2026-07-10 con specs exactos + PDF real (San Felipe-Puerta de Oro) +
mockup. Reproceso bounce=1 confirmado por F1 como **no-bug**: continuación de
discovery, no rechazo de Sprint A (2026-07-01, 🟢 validado, no tocar de nuevo).

Decisiones YA aprobadas por Miguel (no reabrir):
1. Semáforo LITERAL del cliente: verde≥100%, amarillo 40-99%, rojo<40% (NO el
   75/50 que usa el resto de la app).
2. Tendido/Guarda % = promedio simple de `avance_conductor_pct` + `avance_fibra_pct`.

## Verificación BD prod (F2, SOLO SELECT, proxy 127.0.0.1:5434)

| Bloqueo F1 | Resultado verificado | Impacto en diseño |
|---|---|---|
| Valores reales de `tipo`/`tipo_cimentacion` (65 torres, proyecto QA `ec2a68aa-…`) | **100% vacíos** (`tipo=''`, `tipo_cimentacion=''` en las 65 filas) — NO hay dato legacy inconsistente que migrar. El help_text "e.g. D6,B4,C5" era aspiracional, nunca se usó. | Sin migración de datos. Solo `AlterField` agregando `choices=` — todas las torres quedan sin valor hasta que el cliente las llene desde el form de Hochiminh. |
| Cruce Predial/Ambiental: `TorreConstruccion.numero` (formato real: **`E1`..`E65`**, NO `T-1`..`T-64` como decía CLAUDE.md — ese es el `numero_display` ya normalizado) vs `TorreContrato.nombre` (formato real: `T1`..`T65`) | Cruce por **sufijo numérico** (`regexp_replace(numero,'[^0-9]','','g')`) sobre las 65 torres del contrato QA (`3489cb9d-…`) da **65/65 matched, 0 duplicados**. `preliminares_predial.liberacion_predial` tiene valor real en 65/65 filas (todas `true`). `preliminares_ambiental.liberacion_pdo` existe en 65/65 filas pero **NULL en todas** (columna sin poblar aún — el fallback "—" se ejercita naturalmente en QA hoy). | Cruce por sufijo numérico normalizado + `contrato_id` compartido (vía `TorreConstruccion.proyecto.contrato_id == TorreContrato.contrato_id`) es seguro para el proyecto real. Implementar como property/helper, no como FK. |
| % de avance Obra Civil/Montaje/Tendido en datos reales — ¿hay casos verde/amarillo/rojo? | Obra Civil y Montaje: **100% en 64/65 torres, 0% en E25** (torre `aplica=False`, confirmado). Tendido conductor+fibra: **100% en las 65** (incl. E25 — sus booleans de tendido SÍ están todos en `true` pese a `aplica=False`). **No existe caso amarillo (40-99%) natural en prod hoy.** | Verde y rojo se validan con datos reales (E1=100%→verde, E25 OC/Montaje=0%→rojo). Amarillo se garantiza con **unit test de función pura** `estado_color(pct)` cubriendo límites 0/39/40/99/100 (no depende de datos prod). Documentado como decisión de ingeniería, no gap. |

### Hallazgo adicional (fuera del bloqueo original, relevante para F3)

Existen **dos** candidatos para "Estado Predial/Ambiental", no uno:
- **(A) `apps.preliminares.PredialTorre`/`AmbientalTorre`** — cuelgan de
  `TorreContrato` (app `ingenieria`), es lo que el sidebar rotula "Actividades
  Preliminares" (`preliminares:seleccionar`) — el término que usa el cliente en
  su comentario. Requiere el cruce por sufijo numérico verificado arriba.
- **(B) `apps.construccion.SocialPredial`/`AmbientalTorre`** — OneToOne
  **directo** a `TorreConstruccion` (`related_name='social_predial'`/`'ambiental'`),
  ya usado internamente por `TorreConstruccion.puede_iniciar_obra_civil`. Sin
  riesgo de cruce, pero semántica distinta (`semaforo` exige las 4 actas con
  fecha — 0/64 en verde hoy en QA) y **sin entrada en el sidebar** (subsistema
  huérfano de navegación, no necesariamente el que el equipo de campo llena).

**Decisión:** usar (A), consistente con el diseño de F1 y con el término literal
del cliente ("Actividades Preliminares"). (B) se documenta para que F3/Miguel lo
tengan presente si el cliente objeta el resultado — podría ser una confusión de
qué pantalla usan en campo.

## Contrato exacto a construir

### Modelo — sin modelo nuevo para reuso; 1 modelo nuevo para lo genuinamente nuevo

No se crea `HochiminhTorre` como modelo "matriz" — la fila de Hochiminh se
**compone en la vista** a partir de:
- `TorreConstruccion` (numero, tipo, tipo_cimentacion — reuso directo)
- `torre.obra_civil.avance_ponderado_pct` (reuso directo, ya existe)
- `torre.montaje_estructura.avance_ponderado_pct` (reuso directo, ya existe)
- `torre.tendido.avance_conductor_pct` / `.avance_fibra_pct` (reuso, combinar en la vista/property)
- Predial/Ambiental — helper de cruce (nuevo, vive en `views_hochiminh.py` o `models.py` como función)
- **`HochiminhMarcacionReplanteo`** (modelo NUEVO, OneToOne a `TorreConstruccion`) —
  únicos campos genuinamente nuevos: `marcacion_a/b/c/d` (BooleanField×4),
  `replanteo_a/b/c/d` (BooleanField×4).

### 1. `apps/construccion/models.py` — choices nuevos (sin migración de datos)

```python
tipo = models.CharField(
    'Tipo de estructura', max_length=20, blank=True,
    choices=[('A','A'), ('AE','AE'), ('B','B'), ('C','C'), ('D','D'), ('TAE','TAE')],
    help_text='Dominio confirmado por leyenda "TIPO DE TORRE" del PDF Hochiminh del cliente (#171).')

tipo_cimentacion = models.CharField(
    'Tipo de cimentación', max_length=20, blank=True,
    choices=[
        ('ZAPATA', 'Exc. Zapata'),
        ('PARRILLA_PESADA', 'Parrilla pesada'),
        ('PARRILLA_LIVIANA', 'Parrilla liviana'),
        ('PILA_CAMPANA', 'Exc. Pila con campana'),
        ('PILA_DADO', 'Exc. Pila con dado'),
        ('MICROPILOTE', 'Micropilote'),
    ],
)
```

Nota: se **retiran** `HELICOIDAL`/`PILOTE`/`PARRILLA` (dominio viejo, sin uso
real — 0 filas con esos valores en prod) y se reemplazan por el dominio de 6
valores del PDF. Sin filas legacy a remapear (confirmado arriba).

### 2. `apps/construccion/models_hochiminh.py` (nuevo)

```python
class HochiminhMarcacionReplanteo(BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    torre = models.OneToOneField(TorreConstruccion, on_delete=models.CASCADE,
                                  related_name='hochiminh')
    marcacion_a = models.BooleanField('Marcación pata A', default=False)
    marcacion_b = models.BooleanField('Marcación pata B', default=False)
    marcacion_c = models.BooleanField('Marcación pata C', default=False)
    marcacion_d = models.BooleanField('Marcación pata D', default=False)
    replanteo_a = models.BooleanField('Replanteo pata A', default=False)
    replanteo_b = models.BooleanField('Replanteo pata B', default=False)
    replanteo_c = models.BooleanField('Replanteo pata C', default=False)
    replanteo_d = models.BooleanField('Replanteo pata D', default=False)

    class Meta:
        db_table = 'construccion_hochiminh'
        verbose_name = 'Hochiminh — Marcación/Replanteo'

    @property
    def obra_civil_pct(self):
        oc = getattr(self.torre, 'obra_civil', None)
        return oc.avance_ponderado_pct if oc else 0.0

    @property
    def montaje_pct(self):
        m = getattr(self.torre, 'montaje_estructura', None)
        return m.avance_ponderado_pct if m else 0.0

    @property
    def tendido_pct(self):
        """#171 2026-07-10: promedio simple conductor+fibra (aprobado Miguel)."""
        t = getattr(self.torre, 'tendido', None)
        if not t:
            return 0.0
        return round((t.avance_conductor_pct + t.avance_fibra_pct) / 2, 1)

    @property
    def estado_general_pct(self):
        return round((self.obra_civil_pct + self.montaje_pct + self.tendido_pct) / 3, 1)

    @staticmethod
    def color_semaforo(pct):
        """#171 2026-07-10: umbral LITERAL del cliente — NO el 75/50 del resto
        de la app. Cubierto por unit test (0/39/40/99/100/101) — no depende de
        datos de prod para el caso amarillo (ausente hoy en QA)."""
        if pct >= 100:
            return 'text-green-600'
        if pct >= 40:
            return 'text-amber-600'
        return 'text-red-600'
```

### 3. Migración `0043_hochiminh_fase1.py`

- `AlterField` `TorreConstruccion.tipo` (choices nuevos)
- `AlterField` `TorreConstruccion.tipo_cimentacion` (choices nuevos, dominio 6 valores)
- `CreateModel` `HochiminhMarcacionReplanteo`

### 4. Vista — `apps/construccion/views_hochiminh.py` (nuevo)

`HochiminhMatrizView(LoginRequiredMixin, RoleRequiredMixin, TemplateView)` —
mismo patrón que `TendidoMatrizView` (views.py:2035): `ALLOWED_ROLES =
ALL_ADMIN_ROLES + OPERARIO_ROLES`, `torres_qs = TorreConstruccion.objects.filter(
proyecto=proyecto)` + `ordenar_torres_construccion(qs, incluir_no_aplica=True)`
(todas las torres visibles, grisadas si `aplica=False`, sin toggle — #160 no se
toca), `get_or_create` de `HochiminhMarcacionReplanteo` por torre.

Cruce Predial/Ambiental (función helper, no property de modelo — cruza apps):

```python
def _cruzar_preliminares(proyecto, torres):
    """#171: cruce TorreConstruccion↔TorreContrato por sufijo numérico +
    contrato_id compartido. Verificado 65/65 en QA (F2, 2026-07-12).
    Fallback: '—' si no hay match."""
    contrato_id = proyecto.contrato_id
    torres_contrato = {
        re.sub(r'[^0-9]', '', tc.nombre): tc
        for tc in TorreContrato.objects.filter(contrato_id=contrato_id)
    }
    resultado = {}
    for t in torres:
        suf = re.sub(r'[^0-9]', '', t.numero)
        tc = torres_contrato.get(suf)
        if tc is None:
            resultado[t.id] = {'predial': None, 'ambiental': None}
            continue
        predial = getattr(tc, 'predial', None)
        ambiental = getattr(tc, 'ambiental', None)
        resultado[t.id] = {
            'predial': predial.liberacion_predial if predial else None,
            'ambiental': ambiental.liberacion_pdo if ambiental else None,
        }
    return resultado
```

Renderiza `'—'` en template cuando el valor es `None` (sin match o sin dato).

Endpoints AJAX (mismo patrón toggle que `TendidoToggleView`):
- `POST /construccion/{proyecto_id}/hochiminh/torres/{torre_id}/toggle/` —
  campo=marcacion_a|b|c|d|replanteo_a|b|c|d, valor=1/0.

### 5. URLs — `apps/construccion/urls.py`

```python
path('<uuid:proyecto_id>/hochiminh/',
     views.HochiminhMatrizView.as_view(), name='hochiminh_lista'),
path('<uuid:proyecto_id>/hochiminh/torres/<uuid:torre_id>/toggle/',
     views.HochiminhToggleView.as_view(), name='hochiminh_toggle'),
```

(No `urls_hochiminh.py`/`views_hochiminh.py` separados de más — el patrón real
del repo mete las vistas en `views.py` monolítico salvo excepciones B3; se sigue
el patrón dominante, `models_hochiminh.py` sí separado porque el precedente
`models_b1_actividades_finales.py` existe para módulos nuevos grandes.)

### 6. Template — `templates/construccion/hochiminh_matriz.html` (nuevo)

Copiar **literal** el patrón sticky de `templates/construccion/tendido_matriz.html`:
- thead sticky: línea 112 (`class="bg-gray-50 dark:bg-gray-900 sticky top-0 z-20"`)
- primera columna sticky: líneas 159-162 (`sticky left-0 z-10` + `<a>` a detalle,
  sin columna Detalle/Editar separada — precedente #147/#183)
- fila grisada si `not fila.torre.aplica`: línea 157 (`opacity-50`)

11 columnas en este orden (spec literal del cliente, comentario 2026-07-10):
Torre (link, sticky) | Tipo (badge/texto) | Cimentación (texto) | Predial (1 check
o "—") | Ambiental (1 check o "—") | Marcación A/B/C/D (4 checks editables) |
Replanteo A/B/C/D (4 checks editables) | Obra Civil % (color semáforo) | Montaje
% (color semáforo) | Tendido/Guarda % (color semáforo) | Estado general (badge,
color semáforo, `estado_general_pct`).

Clases de color: `HochiminhMarcacionReplanteo.color_semaforo(pct)` en vez de
hardcodear el umbral en el template (a diferencia de `tendido_matriz.html` que
sí lo hardcodea inline) — centraliza el umbral distinto para que no se confunda
con el 75/50 del resto de la app.

### 7. Sidebar — `templates/components/sidebar.html`

Nueva entrada `catUrl('hochiminh')` (resuelve a
`/construccion/{proyectoId}/hochiminh/` vía la función `catUrl` existente,
línea ~301 — no requiere mapeo adicional) junto a Tendido/Dashboard Tendido
(líneas 393-410), antes de "Obras de Protección".

### 8. Tests — `apps/construccion/tests_hochiminh.py` (nuevo; NO reusar
`tests_issue_171.py`, que es de Sprint A y corre en paralelo con otro frente —
mismo criterio que la nota de cabecera de ese archivo)

- Unit: `HochiminhMarcacionReplanteo.color_semaforo` — límites 0, 39, 40, 99,
  100, 101 (cubre el caso amarillo ausente en datos prod).
- Unit: `tendido_pct` = promedio simple, `estado_general_pct` = promedio de 3.
- Integration: cruce Predial/Ambiental con match y sin match (fallback `—`).
- View: matriz renderiza 200 con torres reales; toggle persiste.

## Journey E2E

`SPRINTS/RUN_2026-07-12_1258/journeys/Instelec_171.yaml` — proyecto QA real
(`ec2a68aa-47fe-4772-89bc-2cd2b1c8b5c7`), torre T-1/E1 (caso verde 100%) y
T-25/E25 (caso rojo, `aplica=False`, grisada). Amarillo NO se valida E2E contra
prod (no existe ese dato hoy) — cubierto por unit test de `color_semaforo`
(ver Tests arriba). Login autenticado (`qa_claude@instelec.com`, `/usuarios/login/`).

## Riesgo de deploy: medio

- Migración quita 2 valores del choices legacy de `tipo_cimentacion`
  (`HELICOIDAL`, `PILOTE`) — sin impacto porque 0 filas los usan hoy (verificado).
- Modelo nuevo `HochiminhMarcacionReplanteo` — aditivo, sin riesgo de romper
  módulos existentes (Obra Civil/Montaje/Tendido no se tocan).
- Cruce Predial/Ambiental es de LECTURA — sin riesgo de escritura cruzada.
