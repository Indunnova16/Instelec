# Issue #176 (A1): sembrar el catálogo Cargo con los 14 códigos de la unión
# de PersonalCuadrilla.RolCuadrilla / CuadrillaMiembro.RolCuadrilla
# (idénticos código-por-código y label-por-label, confirmado en el plan de
# F2 — ver SPRINTS/PLAN_2026-07-10_maestro_cargos.md). Puramente aditivo,
# no toca PersonalCuadrilla ni CuadrillaMiembro todavía (eso es A3).
from django.db import migrations

# Copia estática de los 14 códigos/labels (NO importar RolCuadrilla desde el
# modelo histórico — TextChoices no está disponible vía apps.get_model en
# migraciones; y de todas formas la migración debe quedar congelada aunque
# el enum en código fuente cambie/desaparezca en A3).
CARGOS = [
    ("SUPERVISOR", "Supervisor"),
    ("LINIERO_I", "Liniero I"),
    ("LINIERO_II", "Liniero II"),
    ("AYUDANTE", "Ayudante"),
    ("CONDUCTOR", "Conductor"),
    ("ADMINISTRADOR_OBRA", "Administrador de Obra"),
    ("PROFESIONAL_SST", "Profesional SST"),
    ("ING_RESIDENTE", "Ingeniero Residente"),
    ("SERVICIO_GENERAL", "Servicio General"),
    ("ALMACENISTA", "Almacenista"),
    ("SUPERVISOR_FOREST", "Supervisor Forestal"),
    ("ASISTENTE_FOREST", "Asistente Forestal"),
    ("MALACATERO", "Malacatero"),
    ("COORDINADOR_HSQ", "Coordinador HSQ"),
]


def seed_cargos(apps, schema_editor):
    Cargo = apps.get_model("cuadrillas", "Cargo")
    for codigo, nombre in CARGOS:
        Cargo.objects.get_or_create(
            codigo=codigo,
            defaults={"nombre": nombre, "activo": True},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("cuadrillas", "0018_cargo"),
    ]

    operations = [
        migrations.RunPython(seed_cargos, reverse_code=migrations.RunPython.noop),
    ]
