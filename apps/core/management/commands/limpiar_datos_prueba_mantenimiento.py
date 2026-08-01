"""
Limpieza de datos de prueba del módulo Mantenimiento — Issue #205.

Contexto: Alcides probó el módulo de Mantenimiento (Programación Semanal /
Cuadrillas, Asistencia, Actividades, Colaboradores) en PRODUCCIÓN y quedaron
datos de prueba. Antes de que empiece a usar el sistema en serio hay que
limpiarlos.

    "...le pedí el favor a Miguel de que nos borre estos ejemplos de prueba
    que teníamos para que ya tú los puedas empezar a organizar desde cero...
    todas las pruebas menos lo de los vanos, porque los vanos sí está ok,
    pero que nos borre el resto para que ya tú puedas empezar todo desde
    cero." — Andrea (grabación citada en el issue)

EXCEPCIÓN explícita (issue #205): los VANOS ya cargados (`lineas.Vano` /
`lineas.VanoSemestre`) NO se tocan — ni este comando los importa ni los
consulta.

Ampliación (comentario del issue, #176/#178): además, en Colaboradores
(`/cuadrillas/colaboradores/`) hay que (a) borrar los inactivos y (b)
backfillear `area='MANTENIMIENTO'` a los colaboradores actuales que no
tengan área asignada.

SEGURO POR DEFECTO
-------------------
Sin `--commit` el comando SOLO reporta (dry-run) — no escribe nada en la
base de datos. Correr primero así, revisar el reporte a mano contra lo que
se espera (¿los conteos tienen sentido? ¿la sección de riesgo dio 0
coincidencias?), y solo entonces repetir con `--commit`.

Clasificación de tablas
------------------------
1) Exclusivas de Mantenimiento (sin overlap con Construcción — Construcción
   tiene su propio árbol de modelos: `ProyectoConstruccion` /
   `TorreConstruccion` / `ProgramacionSemanalCuadrilla`, no usa
   `lineas.Linea`/`lineas.Torre`). Cualquier fila que exista hoy en estas
   tablas es dato de la prueba de Alcides — se borran TODAS sin filtro
   adicional:
       - actividades.Actividad
       - actividades.ProgramacionMensual
       - actividades.HistorialIntervencion
       - actividades.InformeDiario
       - cuadrillas.Asistencia (hija de Cuadrilla)
       - cuadrillas.TrackingUbicacion / NovedadPersonalSemana (hijas de
         Cuadrilla, se borran en cascada al borrar Cuadrilla — se listan
         aparte solo para el conteo del reporte)

2) Compartida con Construcción, requiere chequeo de riesgo antes de borrar:
       - cuadrillas.Cuadrilla / CuadrillaMiembro: el modelo `Cuadrilla`
         también se referencia (de solo lectura, por NOMBRE, no FK) desde
         el filtrado legacy de operarios de Construcción
         (`apps.construccion.views.filtrar_torres_por_cuadrilla` y
         `views_b3_mont_detalle._filtrar_torres_por_cuadrilla`), que
         matchea contra los campos de texto libre
         `TorreConstruccion.cuadrilla_civil/montaje/tendido` y los mismos
         campos en sus modelos relacionados `pata_obra`/`fase`
         (`cuadrilla_civil`, `cuadrilla_montaje`, `cuadrilla_tendido`,
         `cuadrilla_prearmado`). Este comando cruza `Cuadrilla.nombre`
         contra esos campos ANTES de borrar y excluye cualquier
         coincidencia del `--commit` (las reporta como riesgo, no las
         toca). Si el reporte da 0 coincidencias, es seguro asumir que la
         tabla completa es dato de prueba de Mantenimiento.

3) `cuadrillas.PersonalCuadrilla` (colaboradores) — NO se borra en bloque.
   Por pedido explícito del comentario del issue:
       (a) DELETE solo los inactivos (`activo=False`).
       (b) UPDATE (no delete) de los que quedan activos: backfill
           `area='' -> area='MANTENIMIENTO'`, sin pisar ningún valor de
           `area` ya asignado (ej. si alguno ya quedó en CONSTRUCCION o
           FINANCIERO por otra vía, se deja intacto).

NUNCA se toca (ni se importa el modelo):
    - lineas.Vano
    - lineas.VanoSemestre
    - lineas.Linea / lineas.Torre (catálogo real de líneas/torres — no es
      "dato de prueba"; lo que se prueba son las actividades/programaciones
      sobre esas líneas, no el catálogo físico en sí)

Uso
---
    python manage.py limpiar_datos_prueba_mantenimiento            # dry-run
    python manage.py limpiar_datos_prueba_mantenimiento --commit    # ejecuta
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q


class Command(BaseCommand):
    help = (
        "Issue #205: reporta (dry-run por defecto) y opcionalmente borra "
        "(--commit) los datos de prueba del módulo Mantenimiento generados "
        "durante las validaciones con Alcides. Nunca toca Vano/VanoSemestre."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Ejecuta los DELETE/UPDATE. Sin este flag el comando solo reporta (dry-run).",
        )

    def handle(self, *args, **options):
        commit = options["commit"]

        self.stdout.write(
            self.style.WARNING(
                f"Modo: {'COMMIT (se va a escribir en la BD)' if commit else 'DRY-RUN (solo reporte, no escribe nada)'}"
            )
        )
        self.stdout.write("")

        if commit:
            with transaction.atomic():
                self._run(commit=True)
        else:
            self._run(commit=False)

    # ------------------------------------------------------------------
    # Reporte + (opcional) ejecución
    # ------------------------------------------------------------------
    def _run(self, commit: bool):
        self._seccion_exclusivas_mantenimiento(commit)
        self._seccion_cuadrillas_y_asistencia(commit)
        self._seccion_colaboradores(commit)
        self._seccion_exclusiones()

        self.stdout.write("")
        if commit:
            self.stdout.write(self.style.SUCCESS("Listo — cambios aplicados."))
        else:
            self.stdout.write(
                self.style.NOTICE(
                    "Dry-run terminado. Nada se escribió. Repetir con --commit para ejecutar."
                )
            )

    def _seccion_exclusivas_mantenimiento(self, commit: bool):
        from apps.actividades.models import (
            Actividad,
            HistorialIntervencion,
            InformeDiario,
            ProgramacionMensual,
        )

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                "1) Tablas exclusivas de Mantenimiento (sin overlap con Construcción)"
            )
        )
        modelos = [
            (Actividad, "actividades.Actividad"),
            (ProgramacionMensual, "actividades.ProgramacionMensual"),
            (HistorialIntervencion, "actividades.HistorialIntervencion"),
            (InformeDiario, "actividades.InformeDiario"),
        ]
        for modelo, etiqueta in modelos:
            qs = modelo.objects.all()
            n = qs.count()
            self.stdout.write(f"  - {etiqueta}: {n} fila(s) a borrar")
            if commit and n:
                qs.delete()
        self.stdout.write("")

    def _seccion_cuadrillas_y_asistencia(self, commit: bool):
        from apps.cuadrillas.models import Asistencia, Cuadrilla

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                "2) Cuadrilla (bloques de programación semanal) + Asistencia"
            )
        )

        nombres_cuadrilla = list(
            Cuadrilla.objects.exclude(nombre="").values_list("nombre", flat=True)
        )
        nombres_en_riesgo = set(
            self._nombres_cuadrilla_referenciados_en_construccion(nombres_cuadrilla)
        )

        cuadrillas_seguras = Cuadrilla.objects.exclude(nombre__in=nombres_en_riesgo)
        cuadrillas_riesgo = Cuadrilla.objects.filter(nombre__in=nombres_en_riesgo)

        n_seguras = cuadrillas_seguras.count()
        n_riesgo = cuadrillas_riesgo.count()
        n_asistencia = Asistencia.objects.filter(cuadrilla__in=cuadrillas_seguras).count()

        self.stdout.write(f"  - Cuadrilla total: {Cuadrilla.objects.count()}")
        self.stdout.write(
            f"  - Cuadrilla SEGURAS para borrar (nombre no referenciado en Construcción): {n_seguras}"
        )
        self.stdout.write(f"  - Asistencia asociada a esas cuadrillas seguras: {n_asistencia}")
        if n_riesgo:
            self.stdout.write(
                self.style.ERROR(
                    f"  - ⚠️  Cuadrilla EXCLUIDAS del --commit por riesgo de colisión con "
                    f"Construcción (nombre encontrado en TorreConstruccion/pata_obra/fase "
                    f"cuadrilla_civil|montaje|tendido|prearmado): {n_riesgo} "
                    f"→ revisar a mano: {sorted(nombres_en_riesgo)}"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("  - Riesgo de colisión con Construcción: 0 coincidencias.")
            )

        if commit:
            # Asistencia se borra primero explícitamente aunque Cuadrilla la
            # arrastraría en cascada — así el conteo reportado arriba es
            # exactamente lo que se borra, sin sorpresas de cascada oculta.
            Asistencia.objects.filter(cuadrilla__in=cuadrillas_seguras).delete()
            cuadrillas_seguras.delete()
        self.stdout.write("")

    def _nombres_cuadrilla_referenciados_en_construccion(self, nombres):
        """Devuelve el subconjunto de `nombres` que aparece en cualquiera de
        los campos de texto libre `cuadrilla_civil/montaje/tendido/prearmado`
        de Construcción (TorreConstruccion directo + sus relacionados
        pata_obra/fase). Import diferido: apps.construccion es opcional en
        contextos donde no está instalada."""
        if not nombres:
            return []
        try:
            from apps.construccion.models import TorreConstruccion
        except Exception:
            return []

        encontrados = set()

        # Campos directos legacy en TorreConstruccion
        qs_directo = TorreConstruccion.objects.filter(
            Q(cuadrilla_civil__in=nombres)
            | Q(cuadrilla_montaje__in=nombres)
            | Q(cuadrilla_tendido__in=nombres)
        )
        for t in qs_directo.only("cuadrilla_civil", "cuadrilla_montaje", "cuadrilla_tendido"):
            for campo in ("cuadrilla_civil", "cuadrilla_montaje", "cuadrilla_tendido"):
                v = getattr(t, campo, "")
                if v in nombres:
                    encontrados.add(v)

        # pata_obra / fase relacionados (related_name usados en el filtrado
        # legacy de apps.construccion.views.filtrar_torres_por_cuadrilla)
        for related_name, campos in (
            ("pata_obra", ("cuadrilla_civil",)),
            ("fase", ("cuadrilla_montaje", "cuadrilla_tendido", "cuadrilla_prearmado")),
        ):
            try:
                related_qs = TorreConstruccion.objects.filter(
                    **{f"{related_name}__isnull": False}
                ).values_list(*[f"{related_name}__{c}" for c in campos], flat=False)
            except Exception as exc:
                self.stderr.write(
                    self.style.WARNING(
                        f"  (no se pudo chequear '{related_name}' contra Construcción: {exc})"
                    )
                )
                continue
            for row in related_qs:
                for v in row:
                    if v in nombres:
                        encontrados.add(v)

        return encontrados

    def _seccion_colaboradores(self, commit: bool):
        from apps.core.permissions import AREA_MANTENIMIENTO
        from apps.cuadrillas.models import PersonalCuadrilla

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                "3) Colaboradores (PersonalCuadrilla) — /cuadrillas/colaboradores/"
            )
        )

        inactivos = PersonalCuadrilla.objects.filter(activo=False)
        n_inactivos = inactivos.count()
        self.stdout.write(f"  - Inactivos a BORRAR: {n_inactivos}")

        activos_sin_area = PersonalCuadrilla.objects.filter(activo=True, area="")
        n_backfill = activos_sin_area.count()
        n_activos_total = PersonalCuadrilla.objects.filter(activo=True).count()
        self.stdout.write(
            f"  - Activos totales: {n_activos_total} (el issue asume 61 — verificar que "
            f"coincida antes de --commit; si no coincide, DETENERSE y avisar)"
        )
        self.stdout.write(
            f"  - Activos con área en blanco a ACTUALIZAR → area='{AREA_MANTENIMIENTO}': {n_backfill}"
        )
        n_ya_con_area = n_activos_total - n_backfill
        if n_ya_con_area:
            self.stdout.write(
                self.style.WARNING(
                    f"  - ⚠️  {n_ya_con_area} activo(s) YA tienen área asignada (no MANTENIMIENTO "
                    f"en blanco) — se dejan intactos, no se pisan."
                )
            )

        if commit:
            inactivos.delete()
            activos_sin_area.update(area=AREA_MANTENIMIENTO)
        self.stdout.write("")

    def _seccion_exclusiones(self):
        self.stdout.write(
            self.style.MIGRATE_HEADING("4) Nunca tocado (exclusión explícita del issue)")
        )
        self.stdout.write("  - lineas.Vano — NO se importa, NO se consulta, NO se borra.")
        self.stdout.write("  - lineas.VanoSemestre — NO se importa, NO se consulta, NO se borra.")
        self.stdout.write("  - lineas.Linea / lineas.Torre — catálogo real, no es dato de prueba.")
