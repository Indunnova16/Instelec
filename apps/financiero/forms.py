"""
Forms for financial management.
"""
from django import forms

from .models import ChecklistFacturacion


TAILWIND_INPUT = (
    'w-full rounded-lg border-gray-300 dark:border-gray-600 '
    'dark:bg-gray-700 dark:text-white text-sm'
)


class ChecklistEditForm(forms.ModelForm):
    """Inline edit form for numero_factura and observaciones."""

    class Meta:
        model = ChecklistFacturacion
        fields = ['numero_factura', 'observaciones']
        widgets = {
            'numero_factura': forms.TextInput(attrs={
                'class': TAILWIND_INPUT,
                'placeholder': 'Ej: FV-2026-001',
            }),
            'observaciones': forms.Textarea(attrs={
                'class': TAILWIND_INPUT,
                'rows': 3,
                'placeholder': 'Observaciones de facturacion...',
            }),
        }


class ArchivoChecklistForm(forms.Form):
    """File upload form for per-activity attachments."""

    archivos = forms.FileField(
        label='Archivos',
        widget=forms.FileInput(attrs={
            'class': TAILWIND_INPUT,
            'multiple': True,
            'accept': '.pdf,.xlsx,.xls,.jpg,.jpeg,.png,.webp',
        }),
    )


class ArchivoPeriodoForm(forms.Form):
    """File upload form for period-level attachments."""

    archivos = forms.FileField(
        label='Archivos del periodo',
        widget=forms.FileInput(attrs={
            'class': TAILWIND_INPUT,
            'multiple': True,
            'accept': '.pdf,.xlsx,.xls,.jpg,.jpeg,.png,.webp',
        }),
    )
    descripcion = forms.CharField(
        label='Descripcion',
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': TAILWIND_INPUT,
            'placeholder': 'Ej: Factura mensual enero 2026',
        }),
    )
