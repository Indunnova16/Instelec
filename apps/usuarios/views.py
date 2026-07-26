"""
User views.
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, TemplateView, UpdateView

from apps.core.mixins import RoleRequiredMixin
from apps.core.models import Role
from apps.core.permissions import AREA_CHOICES

from .forms import LoginForm, PerfilForm, UsuarioChangeForm
from .models import Usuario


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
        # Issue #186 (186-M4): filtro DE VISTA por área (Construcción/
        # Mantenimiento/Financiero) -- pedido de Gabriel Valencia para no ver
        # "todo el listado de mantenimiento" al estar parado en Construcción.
        # El listado SIN filtrar sigue mostrando TODOS los usuarios (Financiero
        # los necesita a todos también) -- esto no segmenta la BD, solo acota
        # el queryset cuando se pasa `?area=`.
        area = self.request.GET.get('area', '').strip()
        if area:
            qs = qs.filter(area=area)
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
        # Issue #186 (A4): dropdown dinámico BD-backed -- antes
        # `Usuario.Rol.choices` (hardcodeado). Con esto, un rol creado desde
        # la matriz (A5) aparece disponible sin deploy.
        context['roles'] = Role.objects.filter(activo=True).values_list('codigo', 'nombre')
        context['rol_actual'] = self.request.GET.get('rol', '')
        context['buscar'] = self.request.GET.get('buscar', '')
        # Issue #186 (186-M4): catálogo de áreas para el dropdown de filtro.
        context['areas'] = AREA_CHOICES
        context['area_actual'] = self.request.GET.get('area', '')
        return context


class EditarUsuarioView(LoginRequiredMixin, RoleRequiredMixin, UpdateView):
    """Edit an existing user (#194 -- el form ya existia, faltaba cablear urls+view)."""
    model = Usuario
    form_class = UsuarioChangeForm
    template_name = 'usuarios/editar_usuario.html'
    context_object_name = 'usuario'
    allowed_roles = ['admin', 'director']
    success_url = reverse_lazy('usuarios:gestion')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Mismo patron BD-backed que GestionUsuariosView/CrearUsuarioAdminView
        # (issue #186 A4): un rol creado/desactivado desde la matriz RBAC
        # queda disponible/no-disponible aqui sin deploy.
        context['roles'] = Role.objects.filter(activo=True).values_list('codigo', 'nombre')
        # Issue #186 (186-M4): catálogo de áreas para editar el campo Área.
        context['areas'] = AREA_CHOICES
        return context

    def form_valid(self, form):
        messages.success(
            self.request,
            f'Usuario {form.instance.get_full_name()} actualizado exitosamente.'
        )
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, 'Corrija los errores del formulario.')
        return super().form_invalid(form)


class CrearUsuarioAdminView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """Create a new admin user."""
    template_name = 'usuarios/crear_admin.html'
    allowed_roles = ['admin']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Issue #186 (A4): dropdown dinámico BD-backed -- ver GestionUsuariosView arriba.
        context['roles'] = Role.objects.filter(activo=True).values_list('codigo', 'nombre')
        # Issue #186 (186-M4): catálogo de áreas para asignar al crear.
        context['areas'] = AREA_CHOICES
        return context

    def post(self, request, *args, **kwargs):
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        rol = request.POST.get('rol', 'coordinador')
        password = request.POST.get('password', '').strip()
        # Issue #186 (186-M4): área opcional -- valor no reconocido cae a
        # '' (mismo comportamiento que un usuario legacy sin área asignada).
        area = request.POST.get('area', '').strip()
        if area not in dict(AREA_CHOICES):
            area = ''

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
            area=area,
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
        # Issue #194: mismo catalogo BD-backed usado para validar la columna Rol en post().
        context['roles_validos'] = Role.objects.filter(activo=True).values_list('codigo', 'nombre')
        return context

    # Issue #194: valores reconocidos para la columna Estado (F=6ta columna).
    ESTADOS_ACTIVO = {'activo', 'active', 'true', '1', 'si', 'sí', 'x', ''}
    ESTADOS_INACTIVO = {'inactivo', 'inactive', 'false', '0', 'no'}

    def post(self, request, *args, **kwargs):
        archivo = request.FILES.get('archivo')
        if not archivo:
            messages.error(request, 'Debe seleccionar un archivo Excel.')
            return self.get(request, *args, **kwargs)

        # Issue #194: catalogo BD-backed de roles validos (mismo patron #186 A4
        # que el dropdown de EditarUsuarioView/GestionUsuariosView/CrearUsuarioAdminView).
        roles_validos = set(
            Role.objects.filter(activo=True).values_list('codigo', flat=True)
        )

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
                    # Issue #194: 6 columnas -- Nombre, Documento, Email, Cargo, Rol, Estado
                    # (antes: Nombre, Documento, Cargo, Telefono -- 4 columnas, sin email/rol
                    # explicito). El nuevo orden alinea la plantilla con los campos que ya
                    # se pueden editar uno-por-uno desde EditarUsuarioView.
                    nombre = str(row[0]).strip()
                    documento = str(row[1]).strip() if len(row) > 1 and row[1] else ''
                    email = str(row[2]).strip() if len(row) > 2 and row[2] else ''
                    cargo = str(row[3]).strip().upper() if len(row) > 3 and row[3] else ''
                    rol = str(row[4]).strip().lower() if len(row) > 4 and row[4] else ''
                    estado_raw = str(row[5]).strip().lower() if len(row) > 5 and row[5] is not None else ''

                    if not nombre or not documento:
                        errores.append(f'Fila {row_num}: nombre y documento son obligatorios.')
                        continue

                    # Rol explicito y validado -- ya NO se infiere por keyword del cargo.
                    # Un codigo no reconocido rechaza la fila (no asume un default silencioso).
                    if not rol:
                        errores.append(f'Fila {row_num}: la columna Rol es obligatoria.')
                        continue
                    if rol not in roles_validos:
                        errores.append(
                            f"Fila {row_num}: rol '{rol}' no reconocido. "
                            f"Roles validos: {', '.join(sorted(roles_validos))}."
                        )
                        continue

                    # Estado -> is_active. Vacio se toma como Activo (default del modelo).
                    if estado_raw in self.ESTADOS_ACTIVO:
                        is_active = True
                    elif estado_raw in self.ESTADOS_INACTIVO:
                        is_active = False
                    else:
                        errores.append(
                            f"Fila {row_num}: estado '{estado_raw}' no reconocido "
                            f"(use 'Activo' o 'Inactivo')."
                        )
                        continue

                    # Split name into first/last
                    parts = nombre.split()
                    first_name = parts[0] if parts else nombre
                    last_name = ' '.join(parts[1:]) if len(parts) > 1 else ''

                    # Generate password: cedula + 3 first letters of first name lowercase
                    password = _generar_password_campo(documento, first_name)

                    # Email real si vino en la columna; fallback autogenerado SOLO si
                    # vino vacio (antes siempre se regeneraba, ignorando un email real).
                    if not email:
                        email = f'{documento}@campo.instelec.co'

                    usuario, created = Usuario.objects.get_or_create(
                        documento=documento,
                        defaults={
                            'email': email,
                            'first_name': first_name,
                            'last_name': last_name,
                            'rol': rol,
                            'cargo': cargo,
                            'is_active': is_active,
                        }
                    )

                    if created:
                        usuario.set_password(password)
                        usuario.save(update_fields=['password'])
                        creados += 1
                    else:
                        # Issue #194: antes este branch NUNCA tocaba rol/is_active --
                        # justo el gap principal que reporto el issue ("nunca el rol,
                        # y no permite inactivarla").
                        usuario.first_name = first_name
                        usuario.last_name = last_name
                        usuario.cargo = cargo
                        usuario.rol = rol
                        usuario.is_active = is_active
                        usuario.save(update_fields=[
                            'first_name', 'last_name', 'cargo', 'rol', 'is_active', 'updated_at',
                        ])
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
