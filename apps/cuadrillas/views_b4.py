"""
Views B4 — Carga masiva de Cuadrillas con formato Aviso SAP.

Issue: Indunnova16/Instelec#105

Provee:
- ``CuadrillaUploadView``: formulario que recibe Excel con formato Aviso SAP
  (encabezado de cuadrilla + filas de miembros) y delega en
  ``CuadrillaImporter``.
- ``DescargarPlantillaCuadrillasView``: genera Excel-plantilla con encabezados
  + 3 filas de ejemplo (2 cuadrillas, formato heredado por miembros).

Las URLs se exponen mediante ``urlpatterns`` al final del archivo y son
importadas vía ``try/except`` desde ``apps/cuadrillas/urls.py``.

NOTA convivencia con vista pre-block: ``CuadrillaMasivaUploadView`` (en
``views.py``) usa formato "una cuadrilla por fila + miembros en columnas
H..L". B4 NO la reemplaza — usa la URL ``b4/upload-cuadrillas/`` para no
chocar. Cuando el cliente valide B4, podremos retirar el view legacy.
"""
from io import BytesIO

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import path
from django.views import View
from django.views.generic import TemplateView

from apps.core.mixins import RoleRequiredMixin

from .importers import CuadrillaImporter


class CuadrillaUploadView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Carga masiva de cuadrillas desde Excel formato Aviso SAP."""

    template_name = 'cuadrillas/cuadrilla_upload.html'
    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = 'Cargar Cuadrillas Masivamente'
        return context

    def post(self, request, *args, **kwargs):
        archivo = request.FILES.get('archivo_cuadrillas')
        if not archivo:
            return render(request, self.template_name, {
                'titulo': 'Cargar Cuadrillas Masivamente',
                'error': 'Por favor selecciona un archivo Excel.',
            })

        # Validar extensión.
        if not archivo.name.lower().endswith(('.xlsx', '.xls')):
            return render(request, self.template_name, {
                'titulo': 'Cargar Cuadrillas Masivamente',
                'error': f'Archivo "{archivo.name}" no es Excel (.xlsx/.xls).',
            })

        actualizar = request.POST.get('actualizar_existentes') == 'on'

        importer = CuadrillaImporter()
        resultado = importer.importar(archivo, {'actualizar_existentes': actualizar})

        return render(request, self.template_name, {
            'titulo': 'Cargar Cuadrillas Masivamente',
            'resultado': resultado,
            'mensaje_exito': resultado.get('exito', False),
            'error': resultado.get('error') if not resultado.get('exito') else None,
        })


class DescargarPlantillaCuadrillasB4View(LoginRequiredMixin, RoleRequiredMixin, View):
    """Descarga plantilla Excel para CuadrillaUploadView (formato Aviso SAP)."""

    allowed_roles = ['admin', 'director', 'coordinador', 'ing_residente']

    def get(self, request, *args, **kwargs):
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill

        wb = Workbook()
        ws = wb.active
        ws.title = 'Cuadrillas'

        header_font = Font(bold=True, color='FFFFFF')
        header_fill = PatternFill(start_color='1F3A93', end_color='1F3A93', fill_type='solid')
        header_align = Alignment(horizontal='center', vertical='center')

        headers = [
            '#', 'CUADRILLA', 'LÍNEA', 'SUPERVISOR', 'PERSONAL',
            'CEDULA', 'CARGO', 'CELULAR', 'PLACA', 'ESTADO', 'OBSERVACIONES',
        ]

        for col_idx, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align

        # 3 filas de ejemplo: cuadrilla 1 con 2 miembros, cuadrilla 2 con 1 miembro.
        ejemplo = [
            [1, 'CUA-001', 'L1', 'Juan Pérez', 'Carlos González', '1055688', 'Liniero',
             '3161234567', 'JAK-520', 'Activa', 'Cuadrilla principal sector norte'],
            ['', '', '', '', 'María Rodríguez', '1098765', 'Ayudante',
             '3167654321', '', '', ''],
            [2, 'CUA-002', 'L2', 'Carlos López', 'Luis Martínez', '1033333', 'Supervisor',
             '3197654321', 'HMV-123', 'Activa', ''],
        ]
        for row_idx, row_data in enumerate(ejemplo, start=2):
            for col_idx, value in enumerate(row_data, start=1):
                ws.cell(row=row_idx, column=col_idx, value=value)

        # Anchos de columna.
        anchos = [5, 14, 8, 22, 25, 14, 18, 14, 12, 10, 35]
        for idx, ancho in enumerate(anchos, start=1):
            ws.column_dimensions[chr(64 + idx)].width = ancho

        output = BytesIO()
        wb.save(output)
        output.seek(0)

        response = HttpResponse(
            output.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = 'attachment; filename=plantilla_cuadrillas_aviso_sap.xlsx'
        return response


# Re-export para compatibilidad con el spec del issue. Algunos templates legacy
# de Instelec usan el nombre corto ``DescargarPlantillaCuadrillasView``; pero
# ya hay uno con ese nombre en ``views.py`` (formato pre-block). Mantenemos un
# alias explícito B4 para evitar colisión.
DescargarPlantillaCuadrillasView = DescargarPlantillaCuadrillasB4View


# urlpatterns expuesto aquí por contrato con ``apps/cuadrillas/urls.py``
# (que hace ``urlpatterns += views_b4.urlpatterns``). Se mantiene en sync
# con ``urls_b4.py`` que es el archivo "canónico" del bloque.
urlpatterns = [
    path('b4/upload-cuadrillas/', CuadrillaUploadView.as_view(), name='b4_upload_cuadrillas'),
    path('b4/descargar-plantilla/', DescargarPlantillaCuadrillasB4View.as_view(),
         name='b4_descargar_plantilla'),
]
