"""
User models for TransMaint.
"""
import uuid
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UsuarioManager(BaseUserManager):
    """Custom manager for Usuario model."""

    def create_user(self, email, password=None, **extra_fields):
        """Create and save a regular User with the given email and password."""
        if not email:
            raise ValueError('El email es obligatorio')
        email = self.normalize_email(email)

        # Asignar is_staff=True automáticamente para roles administrativos
        # Fix 1 abril 2026: Usuarios admin/director/coordinador necesitan is_staff=True
        rol = extra_fields.get('rol', '')
        if rol in ['admin', 'director', 'coordinador']:
            extra_fields.setdefault('is_staff', True)

        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """Create and save a SuperUser with the given email and password."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('rol', Usuario.Rol.ADMIN)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class Usuario(AbstractUser):
    """
    Custom User model for TransMaint.
    Uses email as the unique identifier instead of username.
    """

    class Rol(models.TextChoices):
        ADMIN = 'admin', 'Administrador'
        DIRECTOR = 'director', 'Director de Proyecto'
        COORDINADOR = 'coordinador', 'Coordinador'
        ING_RESIDENTE = 'ing_residente', 'Ingeniero Residente'
        ING_AMBIENTAL = 'ing_ambiental', 'Ingeniero Ambiental'
        SUPERVISOR = 'supervisor', 'Supervisor de Cuadrilla'
        LINIERO = 'liniero', 'Liniero'
        AUXILIAR = 'auxiliar', 'Auxiliar'

    # Override id to use UUID
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    # Remove username, use email as identifier
    username = None
    email = models.EmailField(
        'Correo electrónico',
        unique=True,
        error_messages={
            'unique': 'Ya existe un usuario con este correo electrónico.',
        }
    )

    # Additional fields
    telefono = models.CharField(
        'Teléfono',
        max_length=20,
        blank=True
    )
    rol = models.CharField(
        'Rol',
        max_length=20,
        choices=Rol.choices,
        default=Rol.LINIERO
    )
    documento = models.CharField(
        'Documento de identidad',
        max_length=20,
        blank=True
    )
    cargo = models.CharField(
        'Cargo',
        max_length=100,
        blank=True
    )
    foto = models.ImageField(
        'Foto de perfil',
        upload_to='usuarios/fotos/',
        blank=True,
        null=True
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    objects = UsuarioManager()

    class Meta:
        db_table = 'usuarios'
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'
        ordering = ['first_name', 'last_name']

    def __str__(self):
        return self.get_full_name() or self.email

    def get_full_name(self):
        """Return the first_name plus the last_name, with a space in between."""
        full_name = f'{self.first_name} {self.last_name}'.strip()
        return full_name or self.email

    def get_short_name(self):
        """Return the short name for the user."""
        return self.first_name or self.email.split('@')[0]

    @property
    def is_admin(self):
        return self.rol == self.Rol.ADMIN or self.is_superuser

    @property
    def is_director(self):
        return self.rol == self.Rol.DIRECTOR

    @property
    def is_coordinador(self):
        return self.rol == self.Rol.COORDINADOR

    @property
    def is_supervisor(self):
        return self.rol == self.Rol.SUPERVISOR

    @property
    def is_campo(self):
        """Returns True if user is field personnel."""
        return self.rol in [self.Rol.LINIERO, self.Rol.AUXILIAR, self.Rol.SUPERVISOR]

    @property
    def cuadrilla_actual(self):
        """Returns the current cuadrilla for field personnel."""
        from apps.cuadrillas.models import CuadrillaMiembro
        miembro = CuadrillaMiembro.objects.filter(
            usuario=self,
            activo=True
        ).select_related('cuadrilla').first()
        return miembro.cuadrilla if miembro else None

    def has_role(self, roles):
        """Check if user has any of the specified roles."""
        if isinstance(roles, str):
            roles = [roles]
        return self.rol in roles or self.is_superuser
