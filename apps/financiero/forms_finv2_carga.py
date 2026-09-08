"""Formulario de archivo para la carga financiera trazable (#246)."""
from django import forms


class CargaFinancieraArchivoForm(forms.Form):
    archivo = forms.FileField(label='Libro financiero (.xlsx)', widget=forms.ClearableFileInput(attrs={'accept': '.xlsx'}))

    def clean_archivo(self):
        archivo = self.cleaned_data['archivo']
        if not (archivo.name or '').lower().endswith('.xlsx'):
            raise forms.ValidationError('Seleccione un archivo Excel .xlsx.')
        if archivo.size > 20 * 1024 * 1024:
            raise forms.ValidationError('El archivo excede el tamaño máximo de 20 MB.')
        return archivo


# Nombre semántico para la vista B2; se conserva el alias para no acoplarla al UI.
CargaFinancieraForm = CargaFinancieraArchivoForm
