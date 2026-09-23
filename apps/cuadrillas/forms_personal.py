"""
Forms del maestro de Colaboradores (PersonalCuadrilla), issue #176 (A3).

`PersonalCuadrillaForm` es un ModelForm sobre `PersonalCuadrilla` para el
CRUD en `/cuadrillas/colaboradores/`. NO reutiliza `forms_pc.py` — ese
módulo es de `ProgramacionSemanalCuadrilla` (otro submódulo, #155).
"""

from django import forms

from .models_base import PersonalCuadrilla
from .models_cargo import Cargo

# Clase Tailwind compartida (espeja apps/actividades/forms.py::INPUT_CLS).
INPUT_CLS = (
    "mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 "
    "px-3 py-2 shadow-sm focus:border-blue-500 focus:ring-blue-500 "
    "bg-white dark:bg-gray-700 text-gray-900 dark:text-white sm:text-sm"
)


class PersonalCuadrillaForm(forms.ModelForm):
    """Crear/editar un Colaborador (PersonalCuadrilla)."""

    class Meta:
        model = PersonalCuadrilla
        fields = [
            "nombre",
            "documento",
            "rol_cuadrilla",
            "area",
            "salario_base",
            "fecha_firma_contrato",
            "fecha_ingreso_proyecto",
            "fecha_salida",
        ]
        widgets = {
            "nombre": forms.TextInput(
                attrs={
                    "class": INPUT_CLS,
                    "placeholder": "Nombre completo",
                }
            ),
            "documento": forms.TextInput(
                attrs={
                    "class": INPUT_CLS,
                    "placeholder": "Número de documento",
                }
            ),
            "rol_cuadrilla": forms.Select(attrs={"class": INPUT_CLS}),
            "area": forms.Select(attrs={"class": INPUT_CLS}),
            "salario_base": forms.NumberInput(
                attrs={
                    "class": INPUT_CLS,
                    "min": 0,
                    "step": "0.01",
                    "placeholder": "0",
                }
            ),
            "fecha_firma_contrato": forms.DateInput(
                format="%Y-%m-%d",
                attrs={
                    "class": INPUT_CLS,
                    "type": "date",
                },
            ),
            "fecha_ingreso_proyecto": forms.DateInput(
                format="%Y-%m-%d",
                attrs={
                    "class": INPUT_CLS,
                    "type": "date",
                },
            ),
            "fecha_salida": forms.DateInput(
                format="%Y-%m-%d",
                attrs={
                    "class": INPUT_CLS,
                    "type": "date",
                },
            ),
        }

    def __init__(self, *args, **kwargs):
        """Issue #176 (A4): `rol_cuadrilla` pasó de Select sobre choices
        estático a ModelChoiceField automático (Django lo infiere del FK).
        Acotar el queryset a cargos activos — si no, el dropdown de
        "nuevo colaborador" mostraría cargos inactivados. Se incluye
        también el cargo YA asignado a esta instancia aunque esté
        inactivo (edge case: alguien inactivó un cargo después de que un
        colaborador ya lo tuviera asignado — el edit no debe romperse)."""
        super().__init__(*args, **kwargs)
        qs = Cargo.objects.filter(activo=True)
        codigo_actual = self.instance.rol_cuadrilla_id if self.instance else None
        if codigo_actual:
            qs = qs | Cargo.objects.filter(codigo=codigo_actual)
        self.fields["rol_cuadrilla"].queryset = qs.distinct()

    def clean_documento(self):
        """Edge case: mensaje de dominio claro en vez del IntegrityError
        crudo cuando el documento ya existe (unique=True en el modelo)."""
        documento = (self.cleaned_data.get("documento") or "").strip()
        if not documento:
            raise forms.ValidationError("El documento es obligatorio.")
        qs = PersonalCuadrilla.objects.filter(documento=documento)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'Ya existe un colaborador con el documento "{documento}".')
        return documento

    def clean_nombre(self):
        nombre = (self.cleaned_data.get("nombre") or "").strip()
        if not nombre:
            raise forms.ValidationError("El nombre es obligatorio.")
        return nombre

    def clean(self):
        """Edge case (issue #271, A2): fecha_salida no puede ser anterior a
        fecha_ingreso_proyecto -- reformulado desde la comparación legacy
        contra `fecha_ingreso` (deprecado en A1, ya no expuesto en este
        form). `fecha_ingreso_proyecto` es la fecha operativa de
        disponibilidad, por eso es el punto de comparación correcto contra
        el retiro del colaborador."""
        cleaned = super().clean()
        fecha_ingreso_proyecto = cleaned.get("fecha_ingreso_proyecto")
        fecha_salida = cleaned.get("fecha_salida")
        if fecha_ingreso_proyecto and fecha_salida and fecha_salida < fecha_ingreso_proyecto:
            raise forms.ValidationError(
                "La fecha de salida no puede ser anterior a la fecha de ingreso a proyecto."
            )
        return cleaned
