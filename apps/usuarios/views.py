"""
User views.
"""
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView, UpdateView, ListView
from django.urls import reverse_lazy
from django.shortcuts import redirect
from django.contrib import messages

from apps.core.mixins import RoleRequiredMixin
from .models import Usuario
from .forms import LoginForm, PerfilForm


class CustomLoginView(LoginView):
    """Custom login view."""
    template_name = 'usuarios/login.html'
    form_class = LoginForm
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy('core:home')


class CustomLogoutView(LogoutView):
    """Custom logout view."""
    next_page = reverse_lazy('usuarios:login')


class PerfilView(LoginRequiredMixin, TemplateView):
    """User profile view."""
    template_name = 'usuarios/perfil.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['usuario'] = self.request.user
        return context


class PerfilEditView(LoginRequiredMixin, UpdateView):
    """Edit user profile."""
    model = Usuario
    form_class = PerfilForm
    template_name = 'usuarios/perfil_edit.html'
    success_url = reverse_lazy('usuarios:perfil')

    def get_object(self):
        return self.request.user


class GestionUsuariosView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    """Admin view for managing all users."""
    model = Usuario
    template_name = 'usuarios/gestion.html'
    context_object_name = 'usuarios'
    allowed_roles = ['admin', 'director']

    def get_queryset(self):
        qs = super().get_queryset().filter(is_active=True)
        rol = self.request.GET.get('rol')
        if rol:
            qs = qs.filter(rol=rol)
        buscar = self.request.GET.get('buscar', '').strip()
        if buscar:
            from django.db.models import Q
            qs = qs.filter(
                Q(first_name__icontains=buscar) |
                Q(last_name__icontains=buscar) |
                Q(documento__icontains=buscar) |
                Q(email__icontains=buscar)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['roles'] = Usuario.Rol.choices
        context['rol_actual'] = self.request.GET.get('rol', '')
        context['buscar'] = self.request.GET.get('buscar', '')
        return context


class CrearUsuarioAdminView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Create a new admin user."""
    template_name = 'usuarios/crear_admin.html'
    allowed_roles = ['admin']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['roles'] = Usuario.Rol.choices
        return context

    def post(self, request, *args, **kwargs):
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        rol = request.POST.get('rol', 'coordinador')
        password = request.POST.get('password', '').strip()

        if not email or not first_name or not password:
            messages.error(request, 'Email, nombre y contrasena son obligatorios.')
            return self.get(request, *args, **kwargs)

        if Usuario.objects.filter(email=email).exists():
            messages.error(request, 'Ya existe un usuario con ese correo.')
            return self.get(request, *args, **kwargs)

        Usuario.objects.create_user(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            rol=rol,
        )
        messages.success(request, f'Usuario {first_name} {last_name} creado exitosamente.')
        return redirect('usuarios:gestion')


class ResetPasswordView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Reset a user's password to the default formula."""
    template_name = 'usuarios/gestion.html'
    allowed_roles = ['admin']

    def post(self, request, *args, **kwargs):
        usuario_id = request.POST.get('usuario_id')
        try:
            usuario = Usuario.objects.get(pk=usuario_id)
            new_password = _generar_password_campo(usuario.documento, usuario.first_name)
            usuario.set_password(new_password)
            usuario.save(update_fields=['password'])
            messages.success(request, f'Contrasena restablecida para {usuario.get_full_name()}.')
        except Usuario.DoesNotExist:
            messages.error(request, 'Usuario no encontrado.')
        return redirect('usuarios:gestion')


class CargaMasivaUsuariosCampoView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Bulk upload of campo users from Excel."""
    template_name = 'usuarios/campo_upload.html'
    allowed_roles = ['admin', 'director', 'coordinador']

    CARGOS_VALIDOS = [
        'SUPERVISOR', 'LINIERO_I', 'LINIERO_II', 'AYUDANTE',
        'CONDUCTOR', 'PROFESIONAL_SST', 'ADMINISTRADOR_OBRA',
    ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cargos_validos'] = self.CARGOS_VALIDOS
        return context

    def post(self, request, *args, **kwargs):
        archivo = request.FILES.get('archivo')
        if not archivo:
            messages.error(request, 'Debe seleccionar un archivo Excel.')
            return self.get(request, *args, **kwargs)

        try:
            import openpyxl
            wb = openpyxl.load_workbook(archivo, read_only=True)
            ws = wb.active

            creados = 0
            actualizados = 0
            errores = []

            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                if not row or not row[0]:
                    continue

                try:
                    nombre = str(row[0]).strip()
                    documento = str(row[1]).strip() if row[1] else ''
                    cargo = str(row[2]).strip().upper() if row[2] else ''
                    telefono = str(row[3]).strip() if len(row) > 3 and row[3] else ''

                    if not nombre or not documento:
                        errores.append(f'Fila {row_num}: nombre y documento son obligatorios.')
                        continue

                    # Split name into first/last
                    parts = nombre.split()
                    first_name = parts[0] if parts else nombre
                    last_name = ' '.join(parts[1:]) if len(parts) > 1 else ''

                    # Generate password: cedula + 3 first letters of first name lowercase
                    password = _generar_password_campo(documento, first_name)

                    # Determine rol based on cargo
                    rol = 'liniero'
                    if 'SUPERVISOR' in cargo:
                        rol = 'supervisor'
                    elif 'AUXILIAR' in cargo or 'AYUDANTE' in cargo:
                        rol = 'auxiliar'

                    # Generate a placeholder email from documento
                    email = f'{documento}@campo.instelec.co'

                    usuario, created = Usuario.objects.get_or_create(
                        documento=documento,
                        defaults={
                            'email': email,
                            'first_name': first_name,
                            'last_name': last_name,
                            'rol': rol,
                            'cargo': cargo,
                            'telefono': telefono,
                        }
                    )

                    if created:
                        usuario.set_password(password)
                        usuario.save(update_fields=['password'])
                        creados += 1
                    else:
                        usuario.first_name = first_name
                        usuario.last_name = last_name
                        usuario.cargo = cargo
                        if telefono:
                            usuario.telefono = telefono
                        usuario.save(update_fields=['first_name', 'last_name', 'cargo', 'telefono', 'updated_at'])
                        actualizados += 1

                except Exception as e:
                    errores.append(f'Fila {row_num}: {str(e)}')

            wb.close()

            msg = f'Carga completada: {creados} creados, {actualizados} actualizados.'
            if errores:
                msg += f' {len(errores)} errores.'
            messages.success(request, msg)

            if errores:
                for err in errores[:10]:
                    messages.warning(request, err)

        except Exception as e:
            messages.error(request, f'Error al procesar el archivo: {str(e)}')

        return self.get(request, *args, **kwargs)


def _generar_password_campo(documento, first_name):
    """Generate password for campo users: cedula + 3 first letters of name lowercase."""
    nombre_part = first_name[:3].lower() if first_name else ''
    return f'{documento}{nombre_part}'
