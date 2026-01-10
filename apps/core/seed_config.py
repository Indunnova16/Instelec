"""
Seed Data Configuration for TransMaint.

This module contains all the configurable seed data for initializing the database
with development/testing data. By externalizing these configurations, it becomes
easier to:
- Modify seed data without changing the command logic
- Add new data categories
- Understand the data structure at a glance
- Reuse configurations across different environments

Usage:
    from apps.core.seed_config import (
        USERS_DATA, LINEAS_DATA, TIPOS_ACTIVIDAD_DATA,
        VEHICULOS_DATA, CUADRILLAS_DATA
    )
"""

from decimal import Decimal


# =============================================================================
# FORM FIELD OPTIONS
# =============================================================================
# Configurable options for dynamic forms in activity types.
# These options appear in the mobile app when filling out field records.

FORM_OPTIONS = {
    # Vegetation types for pruning activities
    "tipo_vegetacion": ["Arborea", "Arbustiva", "Herbacea"],

    # Structure condition options for inspections
    "estado_estructura": ["Bueno", "Regular", "Malo", "Critico"],

    # Cleaning methods for insulator maintenance
    "metodo_limpieza": ["Manual", "Hidrolavado", "Quimico"],

    # Activity priorities
    "prioridad": ["NORMAL", "ALTA", "URGENTE"],

    # Activity states
    "estado_actividad": ["PENDIENTE", "EN_CURSO", "COMPLETADA"],

    # Tower types
    "tipo_torre": ["SUSPENSION", "ANCLAJE", "TERMINAL"],

    # Vehicle types
    "tipo_vehiculo": ["CAMIONETA", "CAMION", "MOTO"],
}


# =============================================================================
# USERS SEED DATA
# =============================================================================
# Initial users for development and testing.
# Password for all users: TransMaint2026!

USERS_DATA = [
    {
        "email": "admin@transmaint.com",
        "first_name": "Admin",
        "last_name": "Sistema",
        "rol": "admin",
        "is_staff": True,
        "is_superuser": True,
    },
    {
        "email": "director@transmaint.com",
        "first_name": "Carlos",
        "last_name": "Mendoza",
        "rol": "director",
    },
    {
        "email": "coordinador@transmaint.com",
        "first_name": "Ana",
        "last_name": "Rodriguez",
        "rol": "coordinador",
    },
    {
        "email": "residente1@transmaint.com",
        "first_name": "Juan",
        "last_name": "Perez",
        "rol": "ing_residente",
    },
    {
        "email": "ambiental@transmaint.com",
        "first_name": "Maria",
        "last_name": "Garcia",
        "rol": "ing_ambiental",
    },
    {
        "email": "supervisor1@transmaint.com",
        "first_name": "Pedro",
        "last_name": "Lopez",
        "rol": "supervisor",
    },
    {
        "email": "supervisor2@transmaint.com",
        "first_name": "Luis",
        "last_name": "Martinez",
        "rol": "supervisor",
    },
    {
        "email": "liniero1@transmaint.com",
        "first_name": "Andres",
        "last_name": "Gomez",
        "rol": "liniero",
    },
    {
        "email": "liniero2@transmaint.com",
        "first_name": "Jorge",
        "last_name": "Diaz",
        "rol": "liniero",
    },
    {
        "email": "liniero3@transmaint.com",
        "first_name": "Miguel",
        "last_name": "Torres",
        "rol": "liniero",
    },
    {
        "email": "liniero4@transmaint.com",
        "first_name": "Diego",
        "last_name": "Ramirez",
        "rol": "liniero",
    },
    {
        "email": "auxiliar1@transmaint.com",
        "first_name": "Camilo",
        "last_name": "Hernandez",
        "rol": "auxiliar",
    },
]

# Default password for all seeded users
DEFAULT_USER_PASSWORD = "TransMaint2026!"


# =============================================================================
# TRANSMISSION LINES SEED DATA
# =============================================================================
# Transmission lines with technical specifications.
# Each line will have towers auto-generated based on BASE_COORDINATES.

LINEAS_DATA = [
    {
        "codigo": "LT-001",
        "nombre": "Linea Barranquilla - Cartagena",
        "cliente": "TRANSELCA",
        "longitud_km": 120.5,
        "tension_kv": 220,
    },
    {
        "codigo": "LT-002",
        "nombre": "Linea Medellin - Bogota",
        "cliente": "INTERCOLOMBIA",
        "longitud_km": 380.2,
        "tension_kv": 500,
    },
    {
        "codigo": "LT-003",
        "nombre": "Linea Cali - Buenaventura",
        "cliente": "TRANSELCA",
        "longitud_km": 145.8,
        "tension_kv": 110,
    },
    {
        "codigo": "LT-004",
        "nombre": "Linea Santa Marta - Valledupar",
        "cliente": "TRANSELCA",
        "longitud_km": 200.3,
        "tension_kv": 220,
    },
]

# Base coordinates for tower generation (latitude, longitude)
# These represent starting points for each transmission line
BASE_COORDINATES = [
    (10.9878, -74.7889),  # Barranquilla
    (6.2442, -75.5812),   # Medellin
    (3.4516, -76.5320),   # Cali
    (11.2404, -74.2110),  # Santa Marta
]

# Number of towers to generate per line
TOWERS_PER_LINE = 20

# Tower spacing increments (degrees)
TOWER_LAT_INCREMENT = Decimal("0.01")
TOWER_LON_INCREMENT = Decimal("0.005")


# =============================================================================
# ACTIVITY TYPES SEED DATA
# =============================================================================
# Configurable activity types with dynamic form definitions.
# Each type defines what data needs to be collected in the field.

TIPOS_ACTIVIDAD_DATA = [
    {
        "codigo": "PODA-001",
        "nombre": "Poda de vegetacion en franja de servidumbre",
        "categoria": "PODA",
        "campos_formulario": {
            "fields": [
                {
                    "name": "altura_poda",
                    "type": "number",
                    "label": "Altura de poda (m)",
                    "required": True,
                },
                {
                    "name": "tipo_vegetacion",
                    "type": "select",
                    "label": "Tipo de vegetacion",
                    "options": FORM_OPTIONS["tipo_vegetacion"],
                },
                {
                    "name": "area_intervenida",
                    "type": "number",
                    "label": "Area intervenida (m2)",
                },
            ]
        },
    },
    {
        "codigo": "HER-001",
        "nombre": "Cambio de herrajes y accesorios",
        "categoria": "HERRAJES",
        "campos_formulario": {
            "fields": [
                {
                    "name": "herraje_retirado",
                    "type": "text",
                    "label": "Herraje retirado",
                    "required": True,
                },
                {
                    "name": "herraje_instalado",
                    "type": "text",
                    "label": "Herraje instalado",
                    "required": True,
                },
                {
                    "name": "cantidad",
                    "type": "number",
                    "label": "Cantidad",
                },
            ]
        },
    },
    {
        "codigo": "INS-001",
        "nombre": "Inspeccion visual de estructuras",
        "categoria": "INSPECCION",
        "campos_formulario": {
            "fields": [
                {
                    "name": "estado_estructura",
                    "type": "select",
                    "label": "Estado de estructura",
                    "options": FORM_OPTIONS["estado_estructura"],
                    "required": True,
                },
                {
                    "name": "hallazgos",
                    "type": "textarea",
                    "label": "Hallazgos",
                },
                {
                    "name": "requiere_intervencion",
                    "type": "boolean",
                    "label": "Requiere intervencion",
                },
            ]
        },
    },
    {
        "codigo": "LIM-001",
        "nombre": "Limpieza de aisladores",
        "categoria": "LIMPIEZA",
        "campos_formulario": {
            "fields": [
                {
                    "name": "metodo_limpieza",
                    "type": "select",
                    "label": "Metodo de limpieza",
                    "options": FORM_OPTIONS["metodo_limpieza"],
                },
                {
                    "name": "aisladores_limpiados",
                    "type": "number",
                    "label": "Cantidad de aisladores",
                },
            ]
        },
    },
    {
        "codigo": "MED-001",
        "nombre": "Medicion de resistencia de puesta a tierra",
        "categoria": "OTRO",
        "campos_formulario": {
            "fields": [
                {
                    "name": "valor_resistencia",
                    "type": "number",
                    "label": "Valor de resistencia (Ohm)",
                    "required": True,
                },
                {
                    "name": "cumple_norma",
                    "type": "boolean",
                    "label": "Cumple norma (<10 Ohm)",
                },
                {
                    "name": "equipo_utilizado",
                    "type": "text",
                    "label": "Equipo utilizado",
                },
            ]
        },
    },
]


# =============================================================================
# VEHICLES SEED DATA
# =============================================================================
# Vehicles available for crew assignment.

VEHICULOS_DATA = [
    {
        "placa": "ABC123",
        "tipo": "CAMIONETA",
        "marca": "Toyota",
        "modelo": "Hilux 2024",
        "capacidad": 5,
        "costo": 350000,  # COP per day
    },
    {
        "placa": "DEF456",
        "tipo": "CAMIONETA",
        "marca": "Chevrolet",
        "modelo": "D-Max 2023",
        "capacidad": 5,
        "costo": 320000,
    },
    {
        "placa": "GHI789",
        "tipo": "CAMION",
        "marca": "Hino",
        "modelo": "FC 2022",
        "capacidad": 10,
        "costo": 500000,
    },
    {
        "placa": "JKL012",
        "tipo": "MOTO",
        "marca": "Honda",
        "modelo": "XRE 300",
        "capacidad": 2,
        "costo": 80000,
    },
]


# =============================================================================
# CREWS SEED DATA
# =============================================================================
# Work crews with supervisor assignments.

CUADRILLAS_DATA = [
    {
        "codigo": "CUA-001",
        "nombre": "Cuadrilla Norte",
        "supervisor_email": "supervisor1@transmaint.com",
        "placa": "ABC123",
    },
    {
        "codigo": "CUA-002",
        "nombre": "Cuadrilla Sur",
        "supervisor_email": "supervisor2@transmaint.com",
        "placa": "DEF456",
    },
]
