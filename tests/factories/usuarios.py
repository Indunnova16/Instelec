"""Factories for usuarios app."""

import factory
from django.contrib.auth import get_user_model

User = get_user_model()


class UsuarioFactory(factory.django.DjangoModelFactory):
    """Factory for Usuario model."""

    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"usuario{n}@test.com")
    username = factory.LazyAttribute(lambda obj: obj.email.split("@")[0])
    first_name = factory.Faker("first_name", locale="es_CO")
    last_name = factory.Faker("last_name", locale="es_CO")
    telefono = factory.Faker("phone_number", locale="es_CO")
    rol = "liniero"
    is_active = True

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        password = extracted or "testpass123!"
        self.set_password(password)
        if create:
            self.save()


class AdminFactory(UsuarioFactory):
    """Factory for admin users."""

    rol = "admin"
    is_staff = True
    is_superuser = True


class CoordinadorFactory(UsuarioFactory):
    """Factory for coordinador users."""

    rol = "coordinador"


class IngenieroResidenteFactory(UsuarioFactory):
    """Factory for ingeniero residente users."""

    rol = "ing_residente"


class SupervisorFactory(UsuarioFactory):
    """Factory for supervisor users."""

    rol = "supervisor"


class LinieroFactory(UsuarioFactory):
    """Factory for liniero users."""

    rol = "liniero"
