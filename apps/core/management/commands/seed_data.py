"""Management command to seed the database with initial data."""

from decimal import Decimal
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction

User = get_user_model()


class Command(BaseCommand):
    help = "Seed the database with initial data for development/testing"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing data before seeding",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["clear"]:
            self.stdout.write("Clearing existing data...")
            self._clear_data()

        self.stdout.write("Seeding database...")

        self._create_users()
        self._create_lineas()
        self._create_tipos_actividad()
        self._create_vehiculos()
        self._create_cuadrillas()
        self._create_actividades()

        self.stdout.write(self.style.SUCCESS("Database seeded successfully!"))

    def _clear_data(self):
        """Clear all data from the database."""
        from apps.campo.models import Evidencia, RegistroCampo
        from apps.actividades.models import Actividad, ProgramacionMensual, TipoActividad
        from apps.cuadrillas.models import CuadrillaMiembro, Cuadrilla, Vehiculo
        from apps.lineas.models import PoligonoServidumbre, Torre, Linea

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
        User.objects.exclude(is_superuser=True).delete()

    def _create_users(self):
        """Create initial users."""
        self.stdout.write("  Creating users...")

        users_data = [
            {"email": "admin@transmaint.com", "first_name": "Admin", "last_name": "Sistema", "rol": "admin", "is_staff": True, "is_superuser": True},
            {"email": "director@transmaint.com", "first_name": "Carlos", "last_name": "Mendoza", "rol": "director"},
            {"email": "coordinador@transmaint.com", "first_name": "Ana", "last_name": "Rodríguez", "rol": "coordinador"},
            {"email": "residente1@transmaint.com", "first_name": "Juan", "last_name": "Pérez", "rol": "ing_residente"},
            {"email": "ambiental@transmaint.com", "first_name": "María", "last_name": "García", "rol": "ing_ambiental"},
            {"email": "supervisor1@transmaint.com", "first_name": "Pedro", "last_name": "López", "rol": "supervisor"},
            {"email": "supervisor2@transmaint.com", "first_name": "Luis", "last_name": "Martínez", "rol": "supervisor"},
            {"email": "liniero1@transmaint.com", "first_name": "Andrés", "last_name": "Gómez", "rol": "liniero"},
            {"email": "liniero2@transmaint.com", "first_name": "Jorge", "last_name": "Díaz", "rol": "liniero"},
            {"email": "liniero3@transmaint.com", "first_name": "Miguel", "last_name": "Torres", "rol": "liniero"},
            {"email": "liniero4@transmaint.com", "first_name": "Diego", "last_name": "Ramírez", "rol": "liniero"},
            {"email": "auxiliar1@transmaint.com", "first_name": "Camilo", "last_name": "Hernández", "rol": "auxiliar"},
        ]

        self.users = {}
        for data in users_data:
            user, created = User.objects.get_or_create(
                email=data["email"],
                defaults={
                    "username": data["email"].split("@")[0],
                    "first_name": data["first_name"],
                    "last_name": data["last_name"],
                    "rol": data["rol"],
                    "is_staff": data.get("is_staff", False),
                    "is_superuser": data.get("is_superuser", False),
                    "telefono": f"3{hash(data['email']) % 100000000:09d}",
                }
            )
            if created:
                user.set_password("TransMaint2026!")
                user.save()
            self.users[data["rol"]] = user

    def _create_lineas(self):
        """Create transmission lines and towers."""
        from apps.lineas.models import Linea, Torre
        from django.contrib.gis.geos import Point

        self.stdout.write("  Creating lines and towers...")

        lineas_data = [
            {"codigo": "LT-001", "nombre": "Línea Barranquilla - Cartagena", "cliente": "TRANSELCA", "longitud_km": 120.5, "tension_kv": 220},
            {"codigo": "LT-002", "nombre": "Línea Medellín - Bogotá", "cliente": "INTERCOLOMBIA", "longitud_km": 380.2, "tension_kv": 500},
            {"codigo": "LT-003", "nombre": "Línea Cali - Buenaventura", "cliente": "TRANSELCA", "longitud_km": 145.8, "tension_kv": 110},
            {"codigo": "LT-004", "nombre": "Línea Santa Marta - Valledupar", "cliente": "TRANSELCA", "longitud_km": 200.3, "tension_kv": 220},
        ]

        self.lineas = {}
        base_coords = [
            (10.9878, -74.7889),  # Barranquilla
            (6.2442, -75.5812),   # Medellín
            (3.4516, -76.5320),   # Cali
            (11.2404, -74.2110),  # Santa Marta
        ]

        for idx, data in enumerate(lineas_data):
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

            # Create towers
            base_lat, base_lon = base_coords[idx]
            for i in range(1, 21):  # 20 towers per line
                lat = Decimal(str(base_lat + (i * 0.01)))
                lon = Decimal(str(base_lon + (i * 0.005)))
                Torre.objects.get_or_create(
                    linea=linea,
                    numero=f"T-{i:03d}",
                    defaults={
                        "tipo": ["SUSPENSION", "ANCLAJE", "TERMINAL"][i % 3],
                        "latitud": lat,
                        "longitud": lon,
                        "altitud": Decimal(str(100 + (i * 10))),
                        "geometria": Point(float(lon), float(lat), srid=4326),
                    }
                )

    def _create_tipos_actividad(self):
        """Create activity types."""
        from apps.actividades.models import TipoActividad

        self.stdout.write("  Creating activity types...")

        tipos_data = [
            {
                "codigo": "PODA-001",
                "nombre": "Poda de vegetación en franja de servidumbre",
                "categoria": "PODA",
                "campos_formulario": {
                    "fields": [
                        {"name": "altura_poda", "type": "number", "label": "Altura de poda (m)", "required": True},
                        {"name": "tipo_vegetacion", "type": "select", "label": "Tipo de vegetación", "options": ["Arbórea", "Arbustiva", "Herbácea"]},
                        {"name": "area_intervenida", "type": "number", "label": "Área intervenida (m²)"},
                    ]
                }
            },
            {
                "codigo": "HER-001",
                "nombre": "Cambio de herrajes y accesorios",
                "categoria": "HERRAJES",
                "campos_formulario": {
                    "fields": [
                        {"name": "herraje_retirado", "type": "text", "label": "Herraje retirado", "required": True},
                        {"name": "herraje_instalado", "type": "text", "label": "Herraje instalado", "required": True},
                        {"name": "cantidad", "type": "number", "label": "Cantidad"},
                    ]
                }
            },
            {
                "codigo": "INS-001",
                "nombre": "Inspección visual de estructuras",
                "categoria": "INSPECCION",
                "campos_formulario": {
                    "fields": [
                        {"name": "estado_estructura", "type": "select", "label": "Estado de estructura", "options": ["Bueno", "Regular", "Malo", "Crítico"], "required": True},
                        {"name": "hallazgos", "type": "textarea", "label": "Hallazgos"},
                        {"name": "requiere_intervencion", "type": "boolean", "label": "Requiere intervención"},
                    ]
                }
            },
            {
                "codigo": "LIM-001",
                "nombre": "Limpieza de aisladores",
                "categoria": "LIMPIEZA",
                "campos_formulario": {
                    "fields": [
                        {"name": "metodo_limpieza", "type": "select", "label": "Método de limpieza", "options": ["Manual", "Hidrolavado", "Químico"]},
                        {"name": "aisladores_limpiados", "type": "number", "label": "Cantidad de aisladores"},
                    ]
                }
            },
            {
                "codigo": "MED-001",
                "nombre": "Medición de resistencia de puesta a tierra",
                "categoria": "OTRO",
                "campos_formulario": {
                    "fields": [
                        {"name": "valor_resistencia", "type": "number", "label": "Valor de resistencia (Ω)", "required": True},
                        {"name": "cumple_norma", "type": "boolean", "label": "Cumple norma (<10Ω)"},
                        {"name": "equipo_utilizado", "type": "text", "label": "Equipo utilizado"},
                    ]
                }
            },
        ]

        self.tipos_actividad = {}
        for data in tipos_data:
            tipo, _ = TipoActividad.objects.get_or_create(
                codigo=data["codigo"],
                defaults={
                    "nombre": data["nombre"],
                    "categoria": data["categoria"],
                    "campos_formulario": data["campos_formulario"],
                }
            )
            self.tipos_actividad[data["codigo"]] = tipo

    def _create_vehiculos(self):
        """Create vehicles."""
        from apps.cuadrillas.models import Vehiculo

        self.stdout.write("  Creating vehicles...")

        vehiculos_data = [
            {"placa": "ABC123", "tipo": "CAMIONETA", "marca": "Toyota", "modelo": "Hilux 2024", "capacidad": 5, "costo": 350000},
            {"placa": "DEF456", "tipo": "CAMIONETA", "marca": "Chevrolet", "modelo": "D-Max 2023", "capacidad": 5, "costo": 320000},
            {"placa": "GHI789", "tipo": "CAMION", "marca": "Hino", "modelo": "FC 2022", "capacidad": 10, "costo": 500000},
            {"placa": "JKL012", "tipo": "MOTO", "marca": "Honda", "modelo": "XRE 300", "capacidad": 2, "costo": 80000},
        ]

        self.vehiculos = {}
        for data in vehiculos_data:
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

    def _create_cuadrillas(self):
        """Create work crews."""
        from apps.cuadrillas.models import Cuadrilla, CuadrillaMiembro

        self.stdout.write("  Creating work crews...")

        cuadrillas_data = [
            {"codigo": "CUA-001", "nombre": "Cuadrilla Norte", "supervisor_email": "supervisor1@transmaint.com", "placa": "ABC123"},
            {"codigo": "CUA-002", "nombre": "Cuadrilla Sur", "supervisor_email": "supervisor2@transmaint.com", "placa": "DEF456"},
        ]

        self.cuadrillas = {}
        for data in cuadrillas_data:
            supervisor = User.objects.get(email=data["supervisor_email"])
            cuadrilla, _ = Cuadrilla.objects.get_or_create(
                codigo=data["codigo"],
                defaults={
                    "nombre": data["nombre"],
                    "supervisor": supervisor,
                    "vehiculo": self.vehiculos.get(data["placa"]),
                }
            )
            self.cuadrillas[data["codigo"]] = cuadrilla

            # Add supervisor as member
            CuadrillaMiembro.objects.get_or_create(
                cuadrilla=cuadrilla,
                usuario=supervisor,
                defaults={"rol_cuadrilla": "supervisor"}
            )

        # Add linieros to crews
        linieros = User.objects.filter(rol="liniero")
        for i, liniero in enumerate(linieros):
            cuadrilla = list(self.cuadrillas.values())[i % 2]
            CuadrillaMiembro.objects.get_or_create(
                cuadrilla=cuadrilla,
                usuario=liniero,
                defaults={"rol_cuadrilla": "liniero"}
            )

    def _create_actividades(self):
        """Create scheduled activities."""
        from apps.actividades.models import Actividad, ProgramacionMensual
        from apps.lineas.models import Torre

        self.stdout.write("  Creating activities...")

        today = date.today()

        # Create monthly programming
        for linea in self.lineas.values():
            prog, _ = ProgramacionMensual.objects.get_or_create(
                linea=linea,
                anio=today.year,
                mes=today.month,
                defaults={"estado": "APROBADA"}
            )

            # Create activities for each tower
            torres = Torre.objects.filter(linea=linea)[:10]  # First 10 towers
            tipos = list(self.tipos_actividad.values())
            cuadrillas = list(self.cuadrillas.values())

            for i, torre in enumerate(torres):
                Actividad.objects.get_or_create(
                    linea=linea,
                    torre=torre,
                    tipo_actividad=tipos[i % len(tipos)],
                    fecha_programada=today + timedelta(days=(i % 14)),
                    defaults={
                        "programacion": prog,
                        "cuadrilla": cuadrillas[i % len(cuadrillas)],
                        "estado": ["PENDIENTE", "EN_CURSO", "COMPLETADA"][i % 3],
                        "prioridad": ["NORMAL", "ALTA", "URGENTE"][i % 3],
                    }
                )
