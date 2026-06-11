"""
B1 — Subsección administrativa "Programación de Cuadrillas" en Construcción (#155).

Punto de entrada del módulo `programacion_cuadrillas`. Expone la vista índice
`ProgramacionCuadrillaIndexView`: listado de `ProgramacionSemanalCuadrilla` con
filtros por cuadrilla, año y semana ISO (y, opcionalmente, proyecto). Las
sub-features B2 (CRUD), B3 (ejecución) y B4 (dashboard) cuelgan de esta entrada.

Patrón de autorización heredado de las vistas de `construccion`/`cuadrillas`:
`LoginRequiredMixin` + `RoleRequiredMixin` (con `allowed_roles`). El template base
lo provee el scaffolding S1 (`construccion/programacion_cuadrilla_lista.html`).
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView

from apps.core.mixins import RoleRequiredMixin

from .models_pc import ProgramacionSemanalCuadrilla, EjecucionSemanalCuadrilla  # noqa: F401
from .models import Cuadrilla


class ProgramacionCuadrillaIndexView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    """
    Índice de programaciones semanales de cuadrilla.

    Filtros soportados (querystring, todos opcionales):
      - ``cuadrilla``: UUID de la cuadrilla.
      - ``anio``: año ISO (entero).
      - ``semana``: número de semana ISO (1-53).
      - ``proyecto``: UUID del proyecto de construcción.

    Cada filtro inválido se ignora silenciosamente (no rompe el listado): un
    `semana=abc` o un `cuadrilla=no-es-uuid` simplemente no filtra, en lugar de
    lanzar 500. Esto cubre el edge case de un enlace viejo/manipulado.
    """

    model = ProgramacionSemanalCuadrilla
    template_name = 'construccion/programacion_cuadrilla_lista.html'
    context_object_name = 'programaciones'
    paginate_by = 50
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente', 'supervisor']

    def get_queryset(self):
        qs = (
            ProgramacionSemanalCuadrilla.objects
            .select_related('cuadrilla', 'proyecto')
            .prefetch_related('ejecucion')
        )

        # --- Filtro por cuadrilla (UUID) ---
        cuadrilla_id = (self.request.GET.get('cuadrilla') or '').strip()
        if cuadrilla_id:
            # FK por UUID: un valor no-UUID no debe reventar el listado.
            try:
                qs = qs.filter(cuadrilla_id=cuadrilla_id)
            except (ValueError, TypeError):
                pass

        # --- Filtro por proyecto (UUID) ---
        proyecto_id = (self.request.GET.get('proyecto') or '').strip()
        if proyecto_id:
            try:
                qs = qs.filter(proyecto_id=proyecto_id)
            except (ValueError, TypeError):
                pass

        # --- Filtro por año ISO (entero) ---
        anio = self._parse_int(self.request.GET.get('anio'))
        if anio is not None:
            qs = qs.filter(anio=anio)

        # --- Filtro por semana ISO (1-53) ---
        semana = self._parse_int(self.request.GET.get('semana'))
        if semana is not None and 1 <= semana <= 53:
            qs = qs.filter(semana=semana)

        return qs

    @staticmethod
    def _parse_int(value):
        """Parsea un querystring a int; retorna None si vacío/ inválido."""
        value = (value or '').strip()
        if not value:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Cuadrillas activas para el selector de filtro.
        context['cuadrillas'] = (
            Cuadrilla.objects.filter(activa=True).order_by('codigo')
        )

        # Semanas disponibles (distintas) presentes en las programaciones, para
        # alimentar el <select name="semana"> del template base.
        semanas = (
            ProgramacionSemanalCuadrilla.objects
            .order_by('-semana')
            .values_list('semana', flat=True)
            .distinct()
        )
        context['semanas'] = sorted({s for s in semanas}, reverse=True)

        # Años disponibles (distintos) para el filtro de año.
        anios = (
            ProgramacionSemanalCuadrilla.objects
            .order_by('-anio')
            .values_list('anio', flat=True)
            .distinct()
        )
        context['anios'] = sorted({a for a in anios}, reverse=True)

        # Eco de los filtros activos para que el template marque el selected y
        # arme los enlaces de paginación sin perder el filtro.
        context['cuadrilla_actual'] = (self.request.GET.get('cuadrilla') or '').strip()
        context['proyecto_actual'] = (self.request.GET.get('proyecto') or '').strip()
        context['anio_actual'] = self._parse_int(self.request.GET.get('anio'))
        context['semana_actual'] = self._parse_int(self.request.GET.get('semana'))

        return context
