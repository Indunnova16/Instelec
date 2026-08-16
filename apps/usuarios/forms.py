"""
User forms.
"""
from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserChangeForm, UserCreationForm

from .models import Usuario


class LoginForm(AuthenticationForm):
    """Custom login form. Accepts email or cedula as username."""
    username = forms.CharField(
        label='Correo o Cedula',
        widget=forms.TextInput(attrs={
            'class': 'form-input w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500',
            'placeholder': 'correo@ejemplo.com o numero de cedula',
            'autofocus': True,
        })
    )
    password = forms.CharField(
        label='Contrasena',
        widget=forms.PasswordInput(attrs={
            'class': 'form-input w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500',
            'placeholder': '••••••••',
        })
    )

    error_messages = {
        'invalid_login': 'Credenciales incorrectas. Use su correo o cedula.',
        'inactive': 'Esta cuenta esta inactiva.',
    }


class PerfilForm(forms.ModelForm):
    """Form for editing user profile."""

    class Meta:
        model = Usuario
        fields = ['first_name', 'last_name', 'telefono', 'foto']
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'form-input w-full px-4 py-2 border rounded-lg'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-input w-full px-4 py-2 border rounded-lg'
            }),
            'telefono': forms.TextInput(attrs={
                'class': 'form-input w-full px-4 py-2 border rounded-lg'
            }),
        }


class UsuarioCreationForm(UserCreationForm):
    """Form for creating new users."""

    class Meta:
        model = Usuario
        fields = ('email', 'first_name', 'last_name', 'rol')


class UsuarioChangeForm(UserChangeForm):
    """Form for updating users.

    Issue #194: agrega 'is_active' -- Requerimiento 1 pide poder editar
    nombre/correo/cargo/rol Y estado (activo/inactivo) desde la vista de
    edicion individual, no solo desde la carga masiva.
    """

    class Meta:
        model = Usuario
        fields = (
            'email', 'first_name', 'last_name', 'rol',
            'telefono', 'documento', 'cargo', 'is_active',
            # Issue #186 (186-M4): campo Área -- editable desde la vista
            # individual de edición, igual que rol/estado.
            'area',
            # It is removed from ``self.fields`` unless the authenticated
            # actor is allowed to manage another Super Admin.  Keeping it in
            # Meta lets ModelForm persist the intentionally exposed field.
            'is_superuser',
        )

    def __init__(self, *args, actor=None, **kwargs):
        """Expose the Super Admin switch only to a different Super Admin.

        The view passes the authenticated actor explicitly.  Keeping the field
        out of the form for every other case makes a forged POST harmless: a
        ModelForm only persists fields it declares.
        """
        self.actor = actor
        super().__init__(*args, **kwargs)

        if actor and actor.is_superuser and self.instance.pk != getattr(actor, 'pk', None):
            self.fields['is_superuser'] = forms.BooleanField(
                label='Super Admin',
                required=False,
                help_text='Otorga acceso total a todos los módulos y permisos.',
            )
        else:
            self.fields.pop('is_superuser', None)

    def clean(self):
        cleaned_data = super().clean()
        if (
            'is_superuser' in self.fields
            and self.instance.is_superuser
            and not cleaned_data.get('is_superuser')
            and Usuario.objects.filter(is_superuser=True).count() <= 1
        ):
            self.add_error(
                'is_superuser',
                'No se puede retirar Super Admin al último Super Admin del sistema.',
            )
        return cleaned_data
