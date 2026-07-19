"""
Core models - Base classes for all models.
"""
import uuid
from django.db import models

# NEW MODELS GO IN A NEW FILE (issue #186, RBAC dinámico) — re-exportado acá
# para que `from apps.core.models import Role` siga funcionando (mismo
# patrón que apps/cuadrillas/models.py re-exporta models_cargo.py).
# Import diferido al final del archivo — ver models_roles.py.


class BaseModel(models.Model):
    """
    Abstract base model with common fields for all models.

    Provides:
    - UUID primary key
    - Created/updated timestamps
    - Soft delete support (optional)
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name='ID'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de creación'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Fecha de actualización'
    )

    class Meta:
        abstract = True
        ordering = ['-created_at']

    def __str__(self):
        return str(self.id)


class SoftDeleteModel(BaseModel):
    """
    Abstract model with soft delete support.
    """
    is_deleted = models.BooleanField(
        default=False,
        verbose_name='Eliminado'
    )
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Fecha de eliminación'
    )

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        """Soft delete - marks as deleted instead of removing."""
        from django.utils import timezone
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])

    def hard_delete(self, using=None, keep_parents=False):
        """Actually delete the record from database."""
        super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        """Restore a soft-deleted record."""
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])


class ActiveManager(models.Manager):
    """Manager that only returns non-deleted records."""

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class SoftDeleteModelWithManager(SoftDeleteModel):
    """
    Soft delete model with custom manager.
    """
    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True


# Import al final del archivo (después de BaseModel) para evitar import
# circular: models_roles.py hace `from apps.core.models import BaseModel`.
from .models_roles import *  # noqa: E402, F401, F403 — issue #186
