"""Generador de planillas FT-XXX en PDF para firma de interventoría (#64).

Framework + 2 plantillas demo (FT-022 Excavación, FT-029 SPT). El resto
de FTs se agregan creando templates HTML en templates/construccion/planillas/
y registrándolos en PLANILLAS_DISPONIBLES.
"""
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required


# Catálogo de planillas — agregar entradas cuando se cree el template.
# clave = código FT, valor = (nombre legible, módulo de origen).
PLANILLAS_DISPONIBLES = {
    'FT-022': ('Procedimiento de excavación', 'Obra Civil - Excavación'),
    'FT-023': ('Documentación SST excavaciones', 'Obra Civil - Excavación'),
    'FT-028': ('Cartilla de acero', 'Obra Civil - Acero'),
    'FT-029': ('Medición puesta a tierra', 'SPT'),
    'FT-046': ('Control riega y tendido de cable', 'Tendido'),
    'FT-047': ('Control empalmes y terminales', 'Tendido'),
    'FT-056': ('Control de fundaciones de concreto', 'Obra Civil - Vaciado'),
    'FT-068': ('Control de compensación SPT', 'SPT'),
    'FT-912': ('Control espesor pintura patas', 'Pintura'),
    'FT-914': ('Control de compactación', 'Obra Civil - Compactación'),
    'FT-916': ('Planilla nivelación de stub', 'Obra Civil - Acero'),
    'FT-918': ('Tabla de cruces post-tendido', 'Tendido'),
    'FT-922': ('Concepto de entibado', 'Obra Civil - Excavación'),
    'FT-925': ('Prueba de carga de pilotes', 'Obra Civil - Excavación'),
    'FT-926': ('Marcación de pilotes', 'Obra Civil - Excavación'),
    'FT-927': ('Registro de cantidades de pilotes', 'Obra Civil - Excavación'),
    'FT-928': ('Registro de torques de pilotes', 'Obra Civil - Excavación'),
    'FT-929': ('Localización final de pilotes', 'Obra Civil - Excavación'),
    'FT-930': ('Revisión acero/formaleta/SPT base', 'Obra Civil - Acero'),
    'FT-932': ('Control regulación conductor', 'Tendido'),
    # Iteración 2 — catálogo Transelca extendido
    'FT-032': ('Control de montaje y revisión', 'Montaje'),
    'FT-058': ('Concepto técnico de entibado', 'Obra Civil - Excavación'),
    'FT-380': ('IT-380 Instructivo de cimentación', 'Obra Civil - Vaciado'),
    'FT-919': ('Pintura — Control general por torre', 'Pintura'),
    'FT-931': ('Control regulación OPGW', 'Tendido'),
}


def render_planilla_html(codigo_ft, contexto):
    """Renderiza la plantilla HTML del FT con el contexto."""
    template = f'construccion/planillas/{codigo_ft.lower()}.html'
    return render_to_string(template, contexto)


def html_a_pdf(html_string):
    """Convierte HTML → bytes PDF usando WeasyPrint."""
    from weasyprint import HTML
    return HTML(string=html_string).write_pdf()


def generar_planilla_pdf(codigo_ft, contexto):
    """API principal: codigo_ft + dict contexto → bytes PDF."""
    html = render_planilla_html(codigo_ft, contexto)
    return html_a_pdf(html)


def descargar_planilla_torre(request, codigo_ft, torre_id):
    """Endpoint genérico: descarga la planilla FT para una torre.
    Cada FT decide qué contexto necesita en su template.

    URL: /construccion/planilla/<codigo>/torre/<uuid>/
    """
    from .models import TorreConstruccion
    if codigo_ft not in PLANILLAS_DISPONIBLES:
        return HttpResponse(
            f'Planilla {codigo_ft} no implementada. Catálogo: '
            f'{", ".join(PLANILLAS_DISPONIBLES.keys())}',
            status=404)
    torre = get_object_or_404(TorreConstruccion, id=torre_id)
    contexto = {
        'torre': torre,
        'proyecto': torre.proyecto,
        'contrato': torre.proyecto.contrato,
        'patas': list(torre.pata_obra.all()),
        'fase': getattr(torre, 'fase', None),
        'codigo_ft': codigo_ft,
        'nombre_planilla': PLANILLAS_DISPONIBLES[codigo_ft][0],
        'modulo': PLANILLAS_DISPONIBLES[codigo_ft][1],
    }
    try:
        pdf_bytes = generar_planilla_pdf(codigo_ft, contexto)
    except Exception as e:
        return HttpResponse(
            f'Error generando planilla {codigo_ft}: {e}', status=500)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="{codigo_ft}_{torre.numero_display}.pdf"')
    return response
