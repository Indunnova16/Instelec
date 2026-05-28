"""Forms del complemento PDEO (#103)."""
from django import forms

from .models import ProyectoConstruccion


class CargarPDEOForm(forms.Form):
    """Carga del Excel PDEO 4-hojas asociado a un proyecto."""
    proyecto = forms.ModelChoiceField(
        queryset=ProyectoConstruccion.objects.exclude(estado='FINALIZADO').order_by('nombre'),
        label='Proyecto destino',
        empty_label='Seleccione un proyecto…')
    archivo = forms.FileField(
        label='Archivo Excel PDEO (.xlsx)',
        help_text='El Excel debe tener las 4 hojas: Presupuesto, Res EP, BD, pyg.')

    def clean_archivo(self):
        f = self.cleaned_data['archivo']
        name = (f.name or '').lower()
        if not name.endswith(('.xlsx', '.xlsm')):
            raise forms.ValidationError('Solo se aceptan archivos .xlsx o .xlsm.')
        # Cap: 50 MB
        if f.size > 50 * 1024 * 1024:
            raise forms.ValidationError('El archivo excede 50 MB.')
        return f
