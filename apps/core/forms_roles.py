"""
Forms del maestro de Roles (`Role`), issue #186 (A5).

`RoleForm` es un ModelForm sobre `Role` para el CRUD en `/parametrizacion/roles/`.
`codigo` es de solo lectura en edición (mismo patrón que `CargoForm`,
apps/cuadrillas/forms_cargo.py, precedente issue #176) -- acá no hay FK real
que lo fuerce (ver PLAN §1), pero el dropdown de asignación de usuario
(apps/usuarios/views.py, A4) referencia el `codigo` textualmente, así que
renombrarlo tras crear rompería usuarios ya asignados a ese rol.
"""

from django import forms

from .models_roles import Role

# Clase Tailwind compartida (espeja apps/cuadrillas/forms_cargo.py::INPUT_CLS).
INPUT_CLS = (
    "mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 "
    "px-3 py-2 shadow-sm focus:border-blue-500 focus:ring-blue-500 "
    "bg-white dark:bg-gray-700 text-gray-900 dark:text-white sm:text-sm"
)


class RoleForm(forms.ModelForm):
    """Crear/editar un `Role`. `codigo` deshabilitado si la instancia ya existe."""

    class Meta:
        model = Role
        fields = ["codigo", "nombre", "nivel", "activo"]
        widgets = {
            "codigo": forms.TextInput(
                attrs={"class": INPUT_CLS, "placeholder": "Ej: encargado_obra_civil"}
            ),
            "nombre": forms.TextInput(
                attrs={"class": INPUT_CLS, "placeholder": "Ej: Encargado de Obra Civil"}
            ),
            "nivel": forms.Select(attrs={"class": INPUT_CLS}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ver models_cargo.py/CargoForm (precedente #176): `Role.pk` es UUID
        # con default=uuid.uuid4 -- una instancia nueva sin guardar YA tiene
        # un .pk truthy por el default del campo, por eso se usa
        # `_state.adding` (True hasta que la fila exista en BD) y no `.pk`.
        es_edicion = not self.instance._state.adding
        if es_edicion:
            self.fields["codigo"].disabled = True
            self.fields["codigo"].help_text = (
                "El código no se puede modificar una vez creado -- queda referenciado "
                "textualmente por Usuarios ya asignados a este rol (ver apps/usuarios/views.py)."
            )

    def clean_codigo(self):
        codigo = (self.cleaned_data.get("codigo") or "").strip().lower()
        if not codigo:
            raise forms.ValidationError("El código es obligatorio.")
        qs = Role.objects.filter(codigo=codigo)
        if self.instance and self.instance.pk and not self.instance._state.adding:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'Ya existe un rol con el código "{codigo}".')
        return codigo

    def clean_nombre(self):
        nombre = (self.cleaned_data.get("nombre") or "").strip()
        if not nombre:
            raise forms.ValidationError("El nombre es obligatorio.")
        return nombre
