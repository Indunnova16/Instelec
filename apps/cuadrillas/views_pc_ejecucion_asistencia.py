"""
Asistencia semanal por persona/día en la ejecución de una programación
(#270, sub-item D) — 1 vista AJAX de guardado por celda (persona × día).

DEPENDE del sub-item C (roster que gestiona `EjecucionSemanalPersonal`):
la tabla Lun-Dom se arma sobre las filas de ese roster (una persona sin fila
en `EjecucionSemanalPersonal` no puede tener asistencia). Vive en un archivo
NUEVO (no `views_pc_ejecucion.py`, ya tocado por B, ni
`views_pc_ejecucion_personal.py`, ya tocado por C) para reducir la
superficie de conflicto entre sub-items paralelos del mismo RUN.

URL del contrato (la registra `apps/construccion/urls_pc.py`):

    path('ejecucion/personal/<uuid:pk>/asistencia/<str:fecha>/',
         AsistenciaEjecucionSemanalGuardarView.as_view(),
         name='programacion_cuadrilla_ejecucion_asistencia_guardar')
    # pk = UUID de la fila EjecucionSemanalPersonal (el roster de C).
    # fecha = 'AAAA-MM-DD', debe caer dentro de la semana ISO de la
    #   programación (anio/semana) -- 400 si no.

Hace *upsert* por (ejecucion, personal, fecha) -- `unique_together` del
modelo respalda el guardado idempotente (guardar la misma celda dos veces
actualiza, no duplica).

Reusa `ALL_ADMIN_ROLES + OPERARIO_ROLES` de `views_pc_ejecucion.py` (mismo
conjunto de roles autorizados que el resto del módulo de ejecución).
"""
from datetime import date, datetime

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View

from apps.core.mixins import RoleRequiredMixin

from .forms_pc import AsistenciaEjecucionSemanalForm
from .models_pc import AsistenciaEjecucionSemanal, EjecucionSemanalPersonal
from .views_pc_ejecucion import ALL_ADMIN_ROLES, OPERARIO_ROLES


def _asistencia_payload(registro):
    """Serializa un registro `AsistenciaEjecucionSemanal` para el JSON de la UI."""
    return {
        'id': str(registro.pk),
        'personal_asignado_id': None,  # se completa en la vista (no lo sabe el modelo)
        'fecha': registro.fecha.isoformat(),
        'tipo_novedad': registro.tipo_novedad,
        'tipo_novedad_display': registro.get_tipo_novedad_display(),
        'horas_trabajadas': str(registro.horas_trabajadas),
        'horas_extra': str(registro.horas_extra),
    }


class AsistenciaEjecucionSemanalGuardarView(LoginRequiredMixin, RoleRequiredMixin, View):
    """POST AJAX — guarda (upsert) UNA celda de la tabla de asistencia:
    `pk` = UUID de la fila `EjecucionSemanalPersonal` (persona del roster de
    C), `fecha` = 'AAAA-MM-DD' del día dentro de la semana ISO.

    Recibe `tipo_novedad` (choices de `Asistencia.TipoNovedad`, default
    PRESENTE si viene vacío), `horas_trabajadas` y `horas_extra` (decimales
    ≥ 0). `tipo_novedad != PRESENTE` con `horas_trabajadas` > 0 se limpia
    (se fuerza a 0) -- ver `forms_pc.AsistenciaEjecucionSemanalForm.clean`.

    Respuestas:
      - 200 {'ok': True, 'registro': {...}}
      - 400 {'error': <str>}  (fecha inválida / fuera de la semana ISO de
             la programación, tipo_novedad inválido, horas fuera de rango)
      - 404 si la fila del roster (`pk`) no existe.
      - 403 (RoleRequiredMixin) si el rol no está permitido.
    """

    allowed_roles = ALL_ADMIN_ROLES + OPERARIO_ROLES

    def post(self, request, pk, fecha, *args, **kwargs):
        fila_roster = get_object_or_404(
            EjecucionSemanalPersonal.objects.select_related(
                'ejecucion__programacion', 'personal',
            ),
            pk=pk,
        )

        # --- Validación de la fecha ------------------------------------------
        try:
            fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
        except (TypeError, ValueError):
            return JsonResponse(
                {'error': 'Fecha inválida (formato esperado AAAA-MM-DD).'},
                status=400,
            )

        programacion = fila_roster.ejecucion.programacion
        # Rango Lun-Dom de la semana ISO de la programación. `date.
        # fromisocalendar` (Python 3.8+) resuelve directo desde año+semana+día
        # ISO, sin aritmética manual de offsets (evita el típico bug de "la
        # semana 1 puede empezar en diciembre del año anterior").
        semana_inicio = date.fromisocalendar(programacion.anio, programacion.semana, 1)
        semana_fin = date.fromisocalendar(programacion.anio, programacion.semana, 7)
        if not (semana_inicio <= fecha_obj <= semana_fin):
            return JsonResponse(
                {'error': f'La fecha debe estar dentro de la semana ISO '
                          f'{programacion.anio}-S{programacion.semana:02d} '
                          f'({semana_inicio.isoformat()} a {semana_fin.isoformat()}).'},
                status=400,
            )

        # --- Upsert -----------------------------------------------------------
        # (ejecucion, personal, fecha) es el unique_together del modelo: al
        # menos un registro por celda. Buscamos la instancia previa (si la
        # hay) para que el ModelForm haga UPDATE en vez de crear un
        # duplicado.
        registro_previo = AsistenciaEjecucionSemanal.objects.filter(
            ejecucion=fila_roster.ejecucion,
            personal=fila_roster.personal,
            fecha=fecha_obj,
        ).first()

        form = AsistenciaEjecucionSemanalForm(request.POST, instance=registro_previo)
        if not form.is_valid():
            primer_error = next(iter(form.errors.values()))[0]
            return JsonResponse({'error': primer_error}, status=400)

        registro = form.save(commit=False)
        registro.ejecucion = fila_roster.ejecucion
        registro.personal = fila_roster.personal
        registro.fecha = fecha_obj
        registro.save()

        payload = _asistencia_payload(registro)
        payload['personal_asignado_id'] = str(fila_roster.pk)
        return JsonResponse({'ok': True, 'registro': payload})
