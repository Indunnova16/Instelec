"""
Ejecución semanal de cuadrillas — guardado inline AJAX (#155, sub-feature B3).

Capa de EJECUCIÓN del módulo `programacion_cuadrillas`: registra/actualiza la
`EjecucionSemanalCuadrilla` (1:1 con `ProgramacionSemanalCuadrilla`) desde el
detalle de una programación, sin recargar la página. El `rendimiento_pct` se
recalcula como propiedad del modelo (S1) y se devuelve en la respuesta JSON
para que el componente Alpine actualice el indicador en vivo.

Espeja `ObraCivilFechasUpdateView` / `ObraCivilAplicaUpdateView` de
`apps/construccion/views.py`:

    View.post(request, pk) -> get_object_or_404 -> valida -> save()
        -> JsonResponse({'ok': True, 'rendimiento_pct': ...})

Como `EjecucionSemanalCuadrilla` es 1:1 con la programación, este endpoint hace
un *upsert*: crea la ejecución la primera vez que se guarda y la actualiza en
los guardados siguientes (`update_or_create` sobre la relación inversa).

URL del contrato (la registra B1 en `apps/construccion/urls_pc.py`):

    path('<uuid:pk>/ejecucion/',
         EjecucionSemanalUpdateView.as_view(),
         name='programacion_cuadrilla_ejecucion_save')

→ name efectivo bajo el namespace de Construcción:
    `construccion:programacion_cuadrilla_ejecucion_save`

`pk` es el UUID de la `ProgramacionSemanalCuadrilla` (no de la ejecución): el
detalle de B2 conoce la programación, no necesariamente una ejecución previa.
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View

from apps.core.mixins import RoleRequiredMixin

from .models_base import Vehiculo
from .models_pc import EjecucionSemanalCuadrilla, ProgramacionSemanalCuadrilla


# Roles que pueden registrar ejecución (mismo conjunto que el resto del módulo
# de Construcción: administrativos + operarios de construcción/generales).
# Se replica la lista en vez de importarla de construccion/views.py para no
# acoplar este módulo de cuadrillas al monolito de vistas de construcción.
ALL_ADMIN_ROLES = [
    'admin', 'director', 'coordinador', 'ing_residente',
    'admin_general', 'coordinador_general', 'admin_construccion',
]
OPERARIO_ROLES = [
    'operario_construccion', 'operario_general',
    'supervisor', 'liniero', 'auxiliar',
]


class EjecucionSemanalUpdateView(LoginRequiredMixin, RoleRequiredMixin, View):
    """POST AJAX para registrar/actualizar la ejecución de una programación.

    Recibe `torres_ejecutadas` (entero ≥ 0), `vehiculo` (uuid opcional, #270
    sub-item B) y `observaciones` (opcional). Hace upsert de
    `EjecucionSemanalCuadrilla` (OneToOne a la programación) y devuelve el
    `rendimiento_pct` recalculado por el modelo + el vehículo asignado.

    `vehiculo`: editable/reasignable en cada POST. Cadena vacía / ausente →
    desasigna (vehiculo=None). Un uuid que no corresponde a un vehículo con
    `estado=ACTIVO` → 400 (mismo criterio que
    `ProgramacionSemanalConstruccionAgregarVehiculoView` en
    `apps/construccion/views_psc_asignacion.py`), salvo que sea el MISMO
    vehículo ya asignado (permite reenviar el form sin tocarlo aunque haya
    pasado a EN_MANTENIMIENTO/INACTIVO después de asignado).

    Respuestas:
      - 200 {'ok': True, 'rendimiento_pct': <float 1 dec>,
             'torres_ejecutadas': <int>, 'torres_programadas': <int>,
             'vehiculo': {'id', 'placa', 'tipo', 'capacidad_personas'} | None}
      - 400 {'error': <str>}  (torres_ejecutadas inválido/faltante,
             vehículo inexistente/no activo)
      - 404 si la programación no existe.
      - 403 (RoleRequiredMixin) si el rol no está permitido.
    """

    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES

    def post(self, request, pk, *args, **kwargs):
        programacion = get_object_or_404(ProgramacionSemanalCuadrilla, pk=pk)

        # --- Validación del input -------------------------------------------
        raw = (request.POST.get('torres_ejecutadas') or '').strip()
        if raw == '':
            return JsonResponse(
                {'error': 'El campo "torres ejecutadas" es obligatorio.'},
                status=400,
            )
        try:
            torres_ejecutadas = int(raw)
        except (TypeError, ValueError):
            return JsonResponse(
                {'error': 'Las torres ejecutadas deben ser un número entero.'},
                status=400,
            )

        # Edge case 1: negativo. El modelo usa PositiveIntegerField; lo
        # rechazamos explícitamente para devolver un 400 limpio en vez de un
        # IntegrityError 500 al guardar.
        if torres_ejecutadas < 0:
            return JsonResponse(
                {'error': 'Las torres ejecutadas no pueden ser negativas.'},
                status=400,
            )

        # Edge case 2: ejecutado > programado. NO se bloquea (en obra puede
        # haber sobre-ejecución real → rendimiento > 100%), pero se anota un
        # flag para que la UI lo resalte sin romper el guardado.
        programadas = programacion.torres_programadas or 0
        sobre_ejecucion = programadas > 0 and torres_ejecutadas > programadas

        observaciones = (request.POST.get('observaciones') or '').strip()

        # --- Validación del vehículo (#270 sub-item B, opcional/reasignable) -
        # Ejecución existente (si la hay) para permitir reenviar el MISMO
        # vehículo aunque ya no esté ACTIVO (edge case, ver docstring).
        ejecucion_previa = EjecucionSemanalCuadrilla.objects.filter(
            programacion=programacion,
        ).first()
        vehiculo_previo_id = (
            ejecucion_previa.vehiculo_id if ejecucion_previa else None
        )
        raw_vehiculo_id = (request.POST.get('vehiculo') or '').strip()
        vehiculo = None
        if raw_vehiculo_id:
            es_el_mismo = (
                vehiculo_previo_id is not None
                and str(vehiculo_previo_id) == raw_vehiculo_id
            )
            if es_el_mismo:
                vehiculo = Vehiculo.objects.filter(pk=raw_vehiculo_id).first()
            else:
                vehiculo = Vehiculo.objects.filter(
                    pk=raw_vehiculo_id, estado=Vehiculo.Estado.ACTIVO,
                ).first()
            if vehiculo is None:
                return JsonResponse(
                    {'error': 'El vehículo seleccionado no existe o no está activo.'},
                    status=400,
                )

        # --- Upsert ---------------------------------------------------------
        # 1:1: la primera vez crea la ejecución, luego la actualiza.
        ejecucion, _created = EjecucionSemanalCuadrilla.objects.update_or_create(
            programacion=programacion,
            defaults={
                'torres_ejecutadas': torres_ejecutadas,
                'vehiculo': vehiculo,
                'observaciones': observaciones,
            },
        )

        vehiculo_payload = None
        if ejecucion.vehiculo_id:
            vehiculo_payload = {
                'id': str(ejecucion.vehiculo_id),
                'placa': ejecucion.vehiculo.placa,
                'tipo': ejecucion.vehiculo.get_tipo_display(),
                'capacidad_personas': ejecucion.vehiculo.capacidad_personas,
            }

        # `rendimiento_pct` es propiedad calculada del modelo (S1) — guarda
        # div/0 (programadas == 0 → 0.0). Redondeamos a 1 decimal para la UI.
        return JsonResponse({
            'ok': True,
            'rendimiento_pct': round(ejecucion.rendimiento_pct, 1),
            'torres_ejecutadas': ejecucion.torres_ejecutadas,
            'torres_programadas': programadas,
            'sobre_ejecucion': sobre_ejecucion,
            'vehiculo': vehiculo_payload,
        })
