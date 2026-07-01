"""
Forms del módulo Actividades — Tipos de Actividad (issue #176, A1).

`TipoActividadForm` es un ModelForm sobre `TipoActividad` para exponer el
CRUD del maestro a usuarios no-admin en `/actividades/tipos/`. `inactivar`
no se hace vía este form (nunca se borra) sino con una vista dedicada que
solo togglea `activo`.
"""

from django import forms

from .models import TipoActividad

# Clase Tailwind compartida (espeja apps/cuadrillas/forms_pc.py::INPUT_CLS).
INPUT_CLS = (
    "mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 "
    "px-3 py-2 shadow-sm focus:border-blue-500 focus:ring-blue-500 "
    "bg-white dark:bg-gray-700 text-gray-900 dark:text-white sm:text-sm"
)


class TipoActividadForm(forms.ModelForm):
    """Crear/editar un Tipo de Actividad."""

    class Meta:
        model = TipoActividad
        fields = [
            "codigo",
            "nombre",
            "categoria",
            "descripcion",
            "requiere_fotos_antes",
            "requiere_fotos_durante",
            "requiere_fotos_despues",
            "min_fotos",
            "tiempo_estimado_horas",
            "rendimiento_estandar_vanos",
            "activo",
        ]
        widgets = {
            "codigo": forms.TextInput(
                attrs={
                    "class": INPUT_CLS,
                    "placeholder": "Ej: PODA-01",
                }
            ),
            "nombre": forms.TextInput(
                attrs={
                    "class": INPUT_CLS,
                    "placeholder": "Ej: Poda de Vegetación",
                }
            ),
            "categoria": forms.Select(attrs={"class": INPUT_CLS}),
            "descripcion": forms.Textarea(
                attrs={
                    "class": INPUT_CLS,
                    "rows": 3,
                    "placeholder": "Descripción del tipo de actividad (opcional)",
                }
            ),
            "requiere_fotos_antes": forms.CheckboxInput(
                attrs={
                    "class": "rounded border-gray-300 text-blue-600 focus:ring-blue-500",
                }
            ),
            "requiere_fotos_durante": forms.CheckboxInput(
                attrs={
                    "class": "rounded border-gray-300 text-blue-600 focus:ring-blue-500",
                }
            ),
            "requiere_fotos_despues": forms.CheckboxInput(
                attrs={
                    "class": "rounded border-gray-300 text-blue-600 focus:ring-blue-500",
                }
            ),
            "min_fotos": forms.NumberInput(
                attrs={
                    "class": INPUT_CLS,
                    "min": 0,
                    "step": 1,
                }
            ),
            "tiempo_estimado_horas": forms.NumberInput(
                attrs={
                    "class": INPUT_CLS,
                    "min": 0,
                    "step": "0.25",
                }
            ),
            "rendimiento_estandar_vanos": forms.NumberInput(
                attrs={
                    "class": INPUT_CLS,
                    "min": 0,
                    "step": 1,
                }
            ),
            "activo": forms.CheckboxInput(
                attrs={
                    "class": "rounded border-gray-300 text-blue-600 focus:ring-blue-500",
                }
            ),
        }

    def clean_codigo(self):
        """Edge case: mensaje de dominio claro en vez del IntegrityError
        crudo cuando el código ya existe (unique=True en el modelo)."""
        codigo = (self.cleaned_data.get("codigo") or "").strip()
        if not codigo:
            raise forms.ValidationError("El código es obligatorio.")
        qs = TipoActividad.objects.filter(codigo__iexact=codigo)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'Ya existe un Tipo de Actividad con el código "{codigo}".')
        return codigo

    def clean_nombre(self):
        nombre = (self.cleaned_data.get("nombre") or "").strip()
        if not nombre:
            raise forms.ValidationError("El nombre es obligatorio.")
        return nombre
