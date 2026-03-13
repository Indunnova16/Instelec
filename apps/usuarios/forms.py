"""
User forms.
"""
from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm, UserChangeForm

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
    """Form for updating users."""

    class Meta:
        model = Usuario
        fields = ('email', 'first_name', 'last_name', 'rol', 'telefono', 'documento', 'cargo')
