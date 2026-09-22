"""
Gestión de personal en la ejecución semanal — 3 vistas AJAX (#270, sub-item C).

Espejan el patrón de `EjecucionSemanalUpdateView`
(`views_pc_ejecucion.py`): `View.post(request, pk) -> valida -> guarda ->
JsonResponse`. Viven en un archivo NUEVO (no `views_pc_ejecucion.py`) porque
ese archivo ya lo modificó el sub-item B del mismo sprint (asignación de
vehículo) — separarlo reduce la superficie de conflicto entre sub-items
paralelos del mismo RUN.

URLs del contrato (las registra `apps/construccion/urls_pc.py`):

    path('<uuid:pk>/ejecucion/personal/agregar/',
         EjecucionSemanalPersonalAgregarView.as_view(),
         name='programacion_cuadrilla_ejecucion_personal_agregar')
    # pk = UUID de la PROGRAMACIÓN (igual que EjecucionSemanalUpdateView) --
    # hace upsert de la ejecución si todavía no existe.

    path('ejecucion/personal/<uuid:pk>/editar/',
         EjecucionSemanalPersonalEditarView.as_view(),
         name='programacion_cuadrilla_ejecucion_personal_editar')
    # pk = UUID de la fila EjecucionSemanalPersonal.

    path('ejecucion/personal/<uuid:pk>/remover/',
         EjecucionSemanalPersonalRemoverView.as_view(),
         name='programacion_cuadrilla_ejecucion_personal_remover')
    # pk = UUID de la fila EjecucionSemanalPersonal.

Todas devuelven JSON y reusan `ALL_ADMIN_ROLES + OPERARIO_ROLES` de
`views_pc_ejecucion.py` (mismo conjunto de roles autorizados que el resto del
módulo de ejecución -- se importa en vez de replicar la lista porque es un
archivo *sibling* del mismo módulo `cuadrillas`, no el monolito de
`construccion/views.py`).
"""
from decimal import Decimal, InvalidOperation

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View

from apps.core.mixins import RoleRequiredMixin
from apps.core.permissions import AREA_CONSTRUCCION

from .models_base import PersonalCuadrilla
from .models_pc import (
    EjecucionSemanalCuadrilla,
    EjecucionSemanalPersonal,
    ProgramacionSemanalCuadrilla,
)
from .views_pc_ejecucion import ALL_ADMIN_ROLES, OPERARIO_ROLES


def _fila_payload(ep):
    """Serializa una fila `EjecucionSemanalPersonal` para el JSON de la UI."""
    return {
        'id': str(ep.pk),
        'personal_id': str(ep.personal_id),
        'nombre': ep.personal.nombre,
        'documento': ep.personal.documento,
        'cargo_rol': ep.personal.get_rol_cuadrilla_display(),
        'costo_dia': str(ep.costo_dia),
    }


class EjecucionSemanalPersonalAgregarView(LoginRequiredMixin, RoleRequiredMixin, View):
    """POST AJAX — alta múltiple de personal a la ejecución de una
    programación (`pk` = UUID de la `ProgramacionSemanalCuadrilla`, mismo
    contrato que `EjecucionSemanalUpdateView`).

    Recibe `personal` como lista de UUIDs (name="personal" repetido, el
    `<select multiple>` del Select2 los manda así). Hace *upsert* de la
    `EjecucionSemanalCuadrilla` (puede no existir todavía si nadie guardó
    torres_ejecutadas/vehículo primero -- gestionar personal NO depende de
    eso) y agrega una fila `EjecucionSemanalPersonal` por cada id válido que
    todavía no estuviera asignado.

    Edge cases (no fallan la request completa, se reportan en la respuesta):
      - id ya asignado a esta ejecución -> va a `duplicados`, se ignora.
      - id que no existe, está inactivo, o su `area` no es Construcción
        (incluye `area` vacío/legacy) -> va a `no_validos`, se ignora.
    Si NINGÚN id es válido -> 400.

    Respuesta 200:
      {'ok': True, 'agregados': [...], 'duplicados': [...], 'no_validos': [...]}
    """

    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES

    def post(self, request, pk, *args, **kwargs):
        programacion = get_object_or_404(ProgramacionSemanalCuadrilla, pk=pk)

        ids = [i.strip() for i in request.POST.getlist('personal') if i.strip()]
        if not ids:
            return JsonResponse(
                {'error': 'Seleccioná al menos una persona.'},
                status=400,
            )

        # Solo personal ACTIVO de área Construcción es asignable (issue
        # #270 sub-item C). `area` vacío/legacy NO matchea `area=CONSTRUCCION`
        # -- queda fuera sin caso especial adicional.
        personal_valido = {
            str(p.pk): p
            for p in PersonalCuadrilla.objects.filter(
                pk__in=ids, activo=True, area=AREA_CONSTRUCCION,
            )
        }

        ejecucion, _created = EjecucionSemanalCuadrilla.objects.get_or_create(
            programacion=programacion,
        )

        ya_asignados = set(
            EjecucionSemanalPersonal.objects.filter(
                ejecucion=ejecucion, personal_id__in=list(personal_valido.keys()),
            ).values_list('personal_id', flat=True)
        )
        ya_asignados = {str(pid) for pid in ya_asignados}

        agregados = []
        duplicados = []
        no_validos = [i for i in ids if i not in personal_valido]

        for str_id, personal in personal_valido.items():
            if str_id in ya_asignados:
                duplicados.append(str_id)
                continue
            costo_dia = (
                personal.rol_cuadrilla.salario_base
                if personal.rol_cuadrilla_id else Decimal('0')
            )
            ep = EjecucionSemanalPersonal.objects.create(
                ejecucion=ejecucion,
                personal=personal,
                costo_dia=costo_dia,
            )
            agregados.append(_fila_payload(ep))

        if not agregados and not duplicados:
            return JsonResponse(
                {'error': 'Ninguna de las personas seleccionadas es válida '
                          '(inactiva o fuera del área de Construcción).'},
                status=400,
            )

        return JsonResponse({
            'ok': True,
            'agregados': agregados,
            'duplicados': duplicados,
            'no_validos': no_validos,
        })


class EjecucionSemanalPersonalEditarView(LoginRequiredMixin, RoleRequiredMixin, View):
    """POST AJAX — edita el `costo_dia` snapshot de UNA fila
    `EjecucionSemanalPersonal` (`pk` = UUID de la fila, botón "Editar")."""

    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES

    def post(self, request, pk, *args, **kwargs):
        ep = get_object_or_404(
            EjecucionSemanalPersonal.objects.select_related(
                'personal', 'personal__rol_cuadrilla',
            ),
            pk=pk,
        )
        raw = (request.POST.get('costo_dia') or '').strip()
        if raw == '':
            return JsonResponse(
                {'error': 'El costo por día es obligatorio.'},
                status=400,
            )
        try:
            costo_dia = Decimal(raw)
        except InvalidOperation:
            return JsonResponse(
                {'error': 'El costo por día debe ser un número válido.'},
                status=400,
            )
        if costo_dia < 0:
            return JsonResponse(
                {'error': 'El costo por día no puede ser negativo.'},
                status=400,
            )

        ep.costo_dia = costo_dia
        ep.save(update_fields=['costo_dia', 'updated_at'])

        return JsonResponse({'ok': True, 'fila': _fila_payload(ep)})


class EjecucionSemanalPersonalRemoverView(LoginRequiredMixin, RoleRequiredMixin, View):
    """POST AJAX — remueve UNA fila `EjecucionSemanalPersonal` (`pk` = UUID
    de la fila, botón "Remover"). Quitar el único miembro de la ejecución es
    válido -- la ejecución (`EjecucionSemanalCuadrilla`) sigue existiendo
    sin personal asignado."""

    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES

    def post(self, request, pk, *args, **kwargs):
        ep = get_object_or_404(EjecucionSemanalPersonal, pk=pk)
        removido_id = str(ep.pk)
        ep.delete()
        return JsonResponse({'ok': True, 'removido_id': removido_id})
