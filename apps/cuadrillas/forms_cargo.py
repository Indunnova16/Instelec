"""
Forms del maestro de Cargos (Cargo), issue #176 (Maestro 3, bounce 2).

`CargoForm` es un ModelForm sobre `Cargo` para el CRUD en
`/cuadrillas/cargos/`. `codigo` es de solo lectura en edicion (ver
CargoEditView) — el trade-off documentado en models_cargo.py: con el FK
`to_field='codigo'` que referencian PersonalCuadrilla/CuadrillaMiembro
(A3), Postgres bloquea el UPDATE de un codigo ya referenciado.
"""

from django import forms

from .models_cargo import Cargo

# Clase Tailwind compartida (espeja apps/actividades/forms.py::INPUT_CLS).
INPUT_CLS = (
    "mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 "
    "px-3 py-2 shadow-sm focus:border-blue-500 focus:ring-blue-500 "
    "bg-white dark:bg-gray-700 text-gray-900 dark:text-white sm:text-sm"
)


class CargoForm(forms.ModelForm):
    """Crear/editar un Cargo. `codigo` deshabilitado si la instancia ya existe."""

    class Meta:
        model = Cargo
        fields = ["codigo", "nombre", "activo"]
        widgets = {
            "codigo": forms.TextInput(
                attrs={
                    "class": INPUT_CLS,
                    "placeholder": "Ej: SOLDADOR",
                }
            ),
            "nombre": forms.TextInput(
                attrs={
                    "class": INPUT_CLS,
                    "placeholder": "Ej: Soldador",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # OJO: Cargo.pk es UUID con default=uuid.uuid4 — una instancia NUEVA
        # sin guardar (Cargo(), la que ModelForm crea internamente cuando no
        # se pasa `instance=`) YA tiene un .pk truthy por el default del
        # campo. `self.instance.pk` por si solo NO distingue crear/editar;
        # hay que usar `_state.adding` (True hasta que la fila exista en BD).
        es_edicion = not self.instance._state.adding
        if es_edicion:
            # codigo de solo lectura en edicion (ver docstring del modulo).
            self.fields["codigo"].disabled = True
            self.fields["codigo"].help_text = (
                "El codigo no se puede modificar una vez creado (queda referenciado "
                "por Colaboradores/Miembros de cuadrilla existentes)."
            )

    def clean_codigo(self):
        codigo = (self.cleaned_data.get("codigo") or "").strip().upper()
        if not codigo:
            raise forms.ValidationError("El código es obligatorio.")
        qs = Cargo.objects.filter(codigo=codigo)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'Ya existe un cargo con el código "{codigo}".')
        return codigo

    def clean_nombre(self):
        nombre = (self.cleaned_data.get("nombre") or "").strip()
        if not nombre:
            raise forms.ValidationError("El nombre es obligatorio.")
        return nombre
