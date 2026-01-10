"""
Management command to seed the database with initial data.

This command populates the database with development/testing data including:
- Users with various roles (admin, supervisors, linieros, etc.)
- Transmission lines and towers with GPS coordinates
- Activity types with dynamic form definitions
- Vehicles and work crews

Usage:
    python manage.py seed_data          # Add seed data
    python manage.py seed_data --clear  # Clear existing data first

Configuration:
    All seed data is defined in apps/core/seed_config.py
    Modify that file to customize the initial data.
"""

from decimal import Decimal
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction

# Import seed data configuration
from apps.core.seed_config import (
    USERS_DATA,
    DEFAULT_USER_PASSWORD,
    LINEAS_DATA,
    BASE_COORDINATES,
    TOWERS_PER_LINE,
    TOWER_LAT_INCREMENT,
    TOWER_LON_INCREMENT,
    TIPOS_ACTIVIDAD_DATA,
    VEHICULOS_DATA,
    CUADRILLAS_DATA,
    FORM_OPTIONS,
)

User = get_user_model()


class Command(BaseCommand):
    """
    Django management command to seed the database with initial data.

    The seed data is loaded from apps/core/seed_config.py which contains
    all configurable data for users, lines, towers, activity types,
    vehicles, and crews.
    """

    help = "Seed the database with initial data for development/testing"

    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing data before seeding",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        """
        Main command handler.

        Executes all seed operations within a database transaction
        to ensure atomicity - if any operation fails, all changes
        are rolled back.
        """
        if options["clear"]:
            self.stdout.write("Clearing existing data...")
            self._clear_data()

        self.stdout.write("Seeding database...")
        self.stdout.write(f"  Using configuration from: apps/core/seed_config.py")

        # Execute seed operations in dependency order
        self._create_users()
        self._create_lineas()
        self._create_tipos_actividad()
        self._create_vehiculos()
        self._create_cuadrillas()
        self._create_actividades()

        self.stdout.write(self.style.SUCCESS("Database seeded successfully!"))

    def _clear_data(self):
        """
        Clear all seeded data from the database.

        Deletes data in reverse dependency order to avoid
        foreign key constraint violations. Preserves superuser
        accounts created outside of seeding.
        """
        from apps.campo.models import Evidencia, RegistroCampo
        from apps.actividades.models import Actividad, ProgramacionMensual, TipoActividad
        from apps.cuadrillas.models import CuadrillaMiembro, Cuadrilla, Vehiculo
        from apps.lineas.models import PoligonoServidumbre, Torre, Linea

        # Delete in reverse dependency order
        Evidencia.objects.all().delete()
        RegistroCampo.objects.all().delete()
        Actividad.objects.all().delete()
        ProgramacionMensual.objects.all().delete()
        TipoActividad.objects.all().delete()
        CuadrillaMiembro.objects.all().delete()
        Cuadrilla.objects.all().delete()
        Vehiculo.objects.all().delete()
        PoligonoServidumbre.objects.all().delete()
        Torre.objects.all().delete()
        Linea.objects.all().delete()
        # Preserve manually created superusers
        User.objects.exclude(is_superuser=True).delete()

    def _create_users(self):
        """
        Create initial users from USERS_DATA configuration.

        Each user is created with:
        - Email as the primary identifier
        - Username derived from email
        - Role-based permissions
        - Auto-generated phone number
        - Default password (configurable in seed_config.py)
        """
        self.stdout.write("  Creating users...")

        self.users = {}
        for data in USERS_DATA:
            user, created = User.objects.get_or_create(
                email=data["email"],
                defaults={
                    "username": data["email"].split("@")[0],
                    "first_name": data["first_name"],
                    "last_name": data["last_name"],
                    "rol": data["rol"],
                    "is_staff": data.get("is_staff", False),
                    "is_superuser": data.get("is_superuser", False),
                    # Generate a deterministic phone number based on email hash
                    "telefono": f"3{hash(data['email']) % 100000000:09d}",
                }
            )
            if created:
                user.set_password(DEFAULT_USER_PASSWORD)
                user.save()
            self.users[data["rol"]] = user

        self.stdout.write(f"    Created {len(USERS_DATA)} users")

    def _create_lineas(self):
        """
        Create transmission lines and towers from LINEAS_DATA configuration.

        For each line:
        - Creates the line record with technical specifications
        - Generates TOWERS_PER_LINE towers with GPS coordinates
        - Tower positions are calculated from BASE_COORDINATES
        - Tower types cycle through SUSPENSION, ANCLAJE, TERMINAL
        """
        from apps.lineas.models import Linea, Torre
        from django.contrib.gis.geos import Point

        self.stdout.write("  Creating lines and towers...")

        self.lineas = {}
        total_towers = 0

        for idx, data in enumerate(LINEAS_DATA):
            # Create or get the transmission line
            linea, _ = Linea.objects.get_or_create(
                codigo=data["codigo"],
                defaults={
                    "nombre": data["nombre"],
                    "cliente": data["cliente"],
                    "longitud_km": Decimal(str(data["longitud_km"])),
                    "tension_kv": data["tension_kv"],
                }
            )
            self.lineas[data["codigo"]] = linea

            # Create towers along the line
            # Get base coordinates for this line
            base_lat, base_lon = BASE_COORDINATES[idx]

            for i in range(1, TOWERS_PER_LINE + 1):
                # Calculate tower position with incremental offset
                lat = Decimal(str(base_lat)) + (Decimal(i) * TOWER_LAT_INCREMENT)
                lon = Decimal(str(base_lon)) + (Decimal(i) * TOWER_LON_INCREMENT)

                # Cycle through tower types from FORM_OPTIONS
                tower_types = FORM_OPTIONS["tipo_torre"]
                tower_type = tower_types[i % len(tower_types)]

                Torre.objects.get_or_create(
                    linea=linea,
                    numero=f"T-{i:03d}",
                    defaults={
                        "tipo": tower_type,
                        "latitud": lat,
                        "longitud": lon,
                        "altitud": Decimal(str(100 + (i * 10))),
                        "geometria": Point(float(lon), float(lat), srid=4326),
                    }
                )
                total_towers += 1

        self.stdout.write(f"    Created {len(LINEAS_DATA)} lines with {total_towers} towers")

    def _create_tipos_actividad(self):
        """
        Create activity types from TIPOS_ACTIVIDAD_DATA configuration.

        Each activity type includes:
        - Unique code and descriptive name
        - Category classification (PODA, HERRAJES, INSPECCION, etc.)
        - Dynamic form definition (campos_formulario) that determines
          what data the mobile app collects in the field

        Form fields support types: text, number, select, textarea, boolean
        Select options are defined in FORM_OPTIONS for easy customization.
        """
        from apps.actividades.models import TipoActividad

        self.stdout.write("  Creating activity types...")

        self.tipos_actividad = {}
        for data in TIPOS_ACTIVIDAD_DATA:
            tipo, _ = TipoActividad.objects.get_or_create(
                codigo=data["codigo"],
                defaults={
                    "nombre": data["nombre"],
                    "categoria": data["categoria"],
                    "campos_formulario": data["campos_formulario"],
                }
            )
            self.tipos_actividad[data["codigo"]] = tipo

        self.stdout.write(f"    Created {len(TIPOS_ACTIVIDAD_DATA)} activity types")

    def _create_vehiculos(self):
        """
        Create vehicles from VEHICULOS_DATA configuration.

        Vehicles can be assigned to crews and include:
        - License plate (unique identifier)
        - Type (CAMIONETA, CAMION, MOTO)
        - Make and model
        - Passenger capacity
        - Daily cost rate
        """
        from apps.cuadrillas.models import Vehiculo

        self.stdout.write("  Creating vehicles...")

        self.vehiculos = {}
        for data in VEHICULOS_DATA:
            vehiculo, _ = Vehiculo.objects.get_or_create(
                placa=data["placa"],
                defaults={
                    "tipo": data["tipo"],
                    "marca": data["marca"],
                    "modelo": data["modelo"],
                    "capacidad_pasajeros": data["capacidad"],
                    "costo_dia": Decimal(str(data["costo"])),
                }
            )
            self.vehiculos[data["placa"]] = vehiculo

        self.stdout.write(f"    Created {len(VEHICULOS_DATA)} vehicles")

    def _create_cuadrillas(self):
        """
        Create work crews from CUADRILLAS_DATA configuration.

        Each crew includes:
        - Unique code and name
        - Supervisor assignment (must exist in USERS_DATA)
        - Vehicle assignment (must exist in VEHICULOS_DATA)
        - Crew members (linieros are distributed across crews)
        """
        from apps.cuadrillas.models import Cuadrilla, CuadrillaMiembro

        self.stdout.write("  Creating work crews...")

        self.cuadrillas = {}
        for data in CUADRILLAS_DATA:
            # Get supervisor user
            supervisor = User.objects.get(email=data["supervisor_email"])

            # Create or get crew
            cuadrilla, _ = Cuadrilla.objects.get_or_create(
                codigo=data["codigo"],
                defaults={
                    "nombre": data["nombre"],
                    "supervisor": supervisor,
                    "vehiculo": self.vehiculos.get(data["placa"]),
                }
            )
            self.cuadrillas[data["codigo"]] = cuadrilla

            # Add supervisor as crew member
            CuadrillaMiembro.objects.get_or_create(
                cuadrilla=cuadrilla,
                usuario=supervisor,
                defaults={"rol_cuadrilla": "supervisor"}
            )

        # Distribute linieros across crews evenly
        linieros = User.objects.filter(rol="liniero")
        cuadrilla_list = list(self.cuadrillas.values())
        for i, liniero in enumerate(linieros):
            cuadrilla = cuadrilla_list[i % len(cuadrilla_list)]
            CuadrillaMiembro.objects.get_or_create(
                cuadrilla=cuadrilla,
                usuario=liniero,
                defaults={"rol_cuadrilla": "liniero"}
            )

        self.stdout.write(f"    Created {len(CUADRILLAS_DATA)} work crews")

    def _create_actividades(self):
        """
        Create scheduled activities for demonstration purposes.

        Generates activities for the current month by:
        - Creating monthly programming for each line
        - Assigning activities to the first 10 towers of each line
        - Distributing activity types and crews
        - Setting varied states and priorities for realistic data
        """
        from apps.actividades.models import Actividad, ProgramacionMensual
        from apps.lineas.models import Torre

        self.stdout.write("  Creating activities...")

        today = date.today()
        total_activities = 0

        # Create monthly programming and activities for each line
        for linea in self.lineas.values():
            # Create or get monthly programming
            prog, _ = ProgramacionMensual.objects.get_or_create(
                linea=linea,
                anio=today.year,
                mes=today.month,
                defaults={"estado": "APROBADA"}
            )

            # Get first 10 towers for this line
            torres = Torre.objects.filter(linea=linea)[:10]
            tipos = list(self.tipos_actividad.values())
            cuadrillas = list(self.cuadrillas.values())

            # Create activities with varied states and priorities
            estados = FORM_OPTIONS["estado_actividad"]
            prioridades = FORM_OPTIONS["prioridad"]

            for i, torre in enumerate(torres):
                Actividad.objects.get_or_create(
                    linea=linea,
                    torre=torre,
                    tipo_actividad=tipos[i % len(tipos)],
                    fecha_programada=today + timedelta(days=(i % 14)),
                    defaults={
                        "programacion": prog,
                        "cuadrilla": cuadrillas[i % len(cuadrillas)],
                        "estado": estados[i % len(estados)],
                        "prioridad": prioridades[i % len(prioridades)],
                    }
                )
                total_activities += 1

        self.stdout.write(f"    Created {total_activities} activities")
