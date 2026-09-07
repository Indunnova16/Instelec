"""Vistas de plantilla, exportación e importación XLSX PSC (#225, B4)."""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import FileResponse
from django.shortcuts import render
from django.views import View

from apps.core.mixins import RoleRequiredMixin

from .excel_psc import (
    exportar_programacion_semanal,
    importar_programacion_semanal,
    plantilla_programacion_semanal,
)
from .models import ProyectoConstruccion
from .views_psc_programacion import PSC_ADMIN_ROLES


class _PSCExcelAccessMixin(LoginRequiredMixin, RoleRequiredMixin):
    allowed_roles = PSC_ADMIN_ROLES


class ProgramacionSemanalConstruccionExcelView(_PSCExcelAccessMixin, View):
    template_name = 'construccion/programacion_semanal/importar.html'

    def get(self, request):
        return render(request, self.template_name, {
            'proyectos': ProyectoConstruccion.objects.order_by('nombre'),
        })

    def post(self, request):
        uploaded_file = request.FILES.get('archivo')
        if not uploaded_file:
            messages.error(request, 'Seleccione un archivo XLSX antes de importar.')
            return render(request, self.template_name, {'proyectos': ProyectoConstruccion.objects.order_by('nombre')}, status=400)
        if not uploaded_file.name.lower().endswith('.xlsx'):
            messages.error(request, 'El archivo debe estar en formato XLSX.')
            return render(request, self.template_name, {'proyectos': ProyectoConstruccion.objects.order_by('nombre')}, status=400)
        proyecto_id = request.POST.get('proyecto_historico')
        try:
            proyecto_historico = ProyectoConstruccion.objects.filter(pk=proyecto_id).first()
        except (ValidationError, ValueError):
            # proyecto_id vacío/mal formado (ej. placeholder "Seleccione un
            # proyecto" del <select> sin elegir) -- UUIDField rechaza el
            # filtro antes de poder devolver None, y sin este catch el 500
            # tapaba el mensaje 400 que el usuario debía ver.
            proyecto_historico = None
        if proyecto_historico is None:
            messages.error(request, 'Seleccione explícitamente el proyecto destino antes de importar.')
            return render(request, self.template_name, {
                'proyectos': ProyectoConstruccion.objects.order_by('nombre'),
                'proyecto_historico_id': proyecto_id,
            }, status=400)
        result = importar_programacion_semanal(uploaded_file, proyecto_historico=proyecto_historico)
        if result.ok:
            messages.success(request, f'Se importaron {result.created} programaciones de forma atómica.')
        else:
            messages.error(request, 'No se importó ninguna programación; corrija los errores indicados.')
        return render(request, self.template_name, {
            'import_result': result,
            'proyectos': ProyectoConstruccion.objects.order_by('nombre'),
            'proyecto_historico_id': proyecto_id,
        }, status=200 if result.ok else 400)


class ProgramacionSemanalConstruccionPlantillaView(_PSCExcelAccessMixin, View):
    def get(self, request):
        return FileResponse(
            plantilla_programacion_semanal(), as_attachment=True,
            filename='plantilla_programacion_semanal_construccion.xlsx',
        )


class ProgramacionSemanalConstruccionExportView(_PSCExcelAccessMixin, View):
    def get(self, request):
        return FileResponse(
            exportar_programacion_semanal(), as_attachment=True,
            filename='programacion_semanal_construccion.xlsx',
        )
