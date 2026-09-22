"""
Trazabilidad de torres nombradas en la ejecución semanal — 1 vista AJAX
(#270, sub-item A).

Espeja el patrón de `views_pc_ejecucion_personal.py` (`View.post(request, pk)
-> valida -> guarda -> JsonResponse`). Vive en un archivo NUEVO (no
`views_pc_ejecucion.py` ni `views_pc_ejecucion_personal.py`) por el mismo
criterio que ese archivo documenta: reduce la superficie de conflicto entre
sub-items paralelos del mismo RUN.

URL del contrato (la registra `apps/construccion/urls_pc.py`):

    path('<uuid:pk>/ejecucion/torres/guardar/',
         EjecucionSemanalTorresGuardarView.as_view(),
         name='programacion_cuadrilla_ejecucion_torres_guardar')
    # pk = UUID de la PROGRAMACIÓN (igual que EjecucionSemanalUpdateView) --
    # hace upsert de la ejecución si todavía no existe (precondición heredada
    # del sub-item C: la ejecución puede existir vacía, 0 torres, si nadie
    # guardó `torres_ejecutadas` todavía -- ver `EjecucionSemanalCuadrilla.
    # objects.get_or_create`).

Es un guardado MASIVO de "estado completo" (como un `update_or_create` en
lote), no un add/remove por fila: recibe el conjunto completo de torres
marcadas como ejecutadas esta vez, y para cada torre PROGRAMADA
(`programacion.torres`, M2M de #269) que quede fuera de ese conjunto exige un
`motivo_cambio_<torre_id>` no vacío. Mismo criterio de UX que el resto del
módulo: una sola vista, un solo botón "Guardar".
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View

from apps.construccion.models import TorreConstruccion
from apps.core.mixins import RoleRequiredMixin

from .models_pc import (
    EjecucionSemanalCuadrilla,
    EjecucionSemanalTorre,
    ProgramacionSemanalCuadrilla,
)
from .views_pc_ejecucion import ALL_ADMIN_ROLES, OPERARIO_ROLES


def _torre_payload(fila):
    """Serializa una fila `EjecucionSemanalTorre` para el JSON de la UI."""
    return {
        'id': str(fila.pk),
        'torre_id': str(fila.torre_id),
        'numero': fila.torre.numero,
        'ejecutada': fila.ejecutada,
        'motivo_cambio': fila.motivo_cambio,
    }


class EjecucionSemanalTorresGuardarView(LoginRequiredMixin, RoleRequiredMixin, View):
    """POST AJAX — guarda el estado completo de trazabilidad de torres
    nombradas de la ejecución (`pk` = UUID de la `ProgramacionSemanalCuadrilla`,
    mismo contrato que `EjecucionSemanalUpdateView` /
    `EjecucionSemanalPersonalAgregarView`).

    Recibe:
      - `torres_ejecutadas` : lista de UUIDs (name="torres_ejecutadas"
        repetido) -- el conjunto COMPLETO de torres marcadas como ejecutadas
        en este guardado. Puede incluir torres que NO estaban en
        `programacion.torres` (sobre-ejecución, #270 tests_requeridos).
      - `motivo_cambio_<torre_id>` : texto, uno por cada torre de
        `programacion.torres` que quede AFUERA de `torres_ejecutadas` --
        obligatorio (400 si falta alguno).

    Validaciones de dominio:
      - Torre en `torres_ejecutadas` debe ser `aplica=True`, `anulada=False`
        (mismo criterio que `TorresActivasFragmentoView`, #269) y, si la
        programación tiene proyecto asignado, pertenecer a ESE proyecto --
        si no, va a `no_validos` (se ignora, no rompe la request completa).
      - Torre programada (`programacion.torres`) sin `torres_ejecutadas` y
        sin `motivo_cambio_<id>` -> 400 `{'error', 'faltan_motivo': [...]}`.

    Respuesta 200:
      {'ok': True,
       'torres_ejecutadas': [...],       # filas ejecutada=True
       'torres_no_ejecutadas': [...],    # filas ejecutada=False (con motivo)
       'no_validos': [...]}              # ids enviados que no son torres válidas
    """

    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES

    def post(self, request, pk, *args, **kwargs):
        programacion = get_object_or_404(
            ProgramacionSemanalCuadrilla.objects.prefetch_related('torres'),
            pk=pk,
        )

        enviados_ids = [
            i.strip() for i in request.POST.getlist('torres_ejecutadas') if i.strip()
        ]
        programadas_ids = {str(t.pk) for t in programacion.torres.all()}

        # --- Validar torres enviadas como "ejecutadas" ----------------------
        torres_qs = TorreConstruccion.objects.filter(
            pk__in=enviados_ids, aplica=True, anulada=False,
        )
        if programacion.proyecto_id:
            torres_qs = torres_qs.filter(proyecto_id=programacion.proyecto_id)
        torres_validas = {str(t.pk): t for t in torres_qs}
        no_validos = [i for i in enviados_ids if i not in torres_validas]

        # --- Validar motivo_cambio para programadas NO ejecutadas -----------
        no_ejecutadas_ids = programadas_ids - set(torres_validas.keys())
        motivos = {}
        faltan_motivo = []
        for tid in no_ejecutadas_ids:
            motivo = (request.POST.get(f'motivo_cambio_{tid}') or '').strip()
            if motivo:
                motivos[tid] = motivo
            else:
                faltan_motivo.append(tid)
        if faltan_motivo:
            return JsonResponse(
                {
                    'error': 'Falta el motivo del cambio para '
                             f'{len(faltan_motivo)} torre(s) programada(s) que '
                             'no fue(ron) ejecutada(s).',
                    'faltan_motivo': faltan_motivo,
                },
                status=400,
            )

        # --- Upsert -----------------------------------------------------------
        ejecucion, _created = EjecucionSemanalCuadrilla.objects.get_or_create(
            programacion=programacion,
        )
        with transaction.atomic():
            filas_ejecutadas = []
            for torre in torres_validas.values():
                fila, _ = EjecucionSemanalTorre.objects.update_or_create(
                    ejecucion=ejecucion, torre=torre,
                    defaults={'ejecutada': True, 'motivo_cambio': ''},
                )
                filas_ejecutadas.append(fila)

            filas_no_ejecutadas = []
            for tid, motivo in motivos.items():
                fila, _ = EjecucionSemanalTorre.objects.update_or_create(
                    ejecucion=ejecucion, torre_id=tid,
                    defaults={'ejecutada': False, 'motivo_cambio': motivo},
                )
                filas_no_ejecutadas.append(fila)

            # Limpieza: filas viejas de torres que ya no son ni ejecutadas
            # ahora ni programadas-con-motivo (ej. se deseleccionó una torre
            # de sobre-ejecución en un guardado posterior).
            vigentes_ids = set(torres_validas.keys()) | set(motivos.keys())
            EjecucionSemanalTorre.objects.filter(ejecucion=ejecucion).exclude(
                torre_id__in=vigentes_ids,
            ).delete()

        return JsonResponse({
            'ok': True,
            'torres_ejecutadas': [_torre_payload(f) for f in filas_ejecutadas],
            'torres_no_ejecutadas': [_torre_payload(f) for f in filas_no_ejecutadas],
            'no_validos': no_validos,
        })
