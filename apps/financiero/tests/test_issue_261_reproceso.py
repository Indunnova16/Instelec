from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.financiero.importers_terceros import validar_filas
from apps.financiero.models import AuditoriaTercero, Cliente


ENCABEZADO_CLIENTES = (
    "nombre,nit,email,telefono,direccion,plazo_pago_dias,"
    "fecha_inicio_contrato,fecha_fin_contrato,activo,industria\n"
)


def _archivo_clientes(*filas):
    return SimpleUploadedFile(
        "clientes.csv", (ENCABEZADO_CLIENTES + "\n".join(filas)).encode(),
        content_type="text/csv",
    )


@pytest.mark.django_db
def test_importador_hace_upsert_a_legacy_y_audita_cambios(client, admin_user):
    """Un tercero previo al cambio se actualiza sin crear otro registro."""
    legacy = Cliente.objects.create(
        nombre="Cliente legacy", nit="900261LEGACY", email="antes@example.test",
        plazo_pago_dias=30, industria="Servicios",
    )
    client.force_login(admin_user)
    archivo = _archivo_clientes(
        "Cliente nuevo,900261NUEVO,nuevo@example.test,3000000000,Calle Nueva,45,,,TRUE,Energía",
        "Cliente legacy actualizado,900261LEGACY,despues@example.test,3000000001,Calle Legacy,60,2026-01-01,2026-12-31,FALSE,Infraestructura",
    )

    preview = client.post("/financiero/maestros/clientes/importar/", {"archivo": archivo})

    assert preview.status_code == 200
    assert b"1 nueva(s) y 1 actualizar" in preview.content
    assert Cliente.objects.count() == 1
    confirmacion = client.post("/financiero/maestros/clientes/importar/", {"confirmar": "1"})

    assert confirmacion.status_code == 302
    legacy.refresh_from_db()
    assert Cliente.objects.filter(nit="900261LEGACY").count() == 1
    assert legacy.nombre == "Cliente legacy actualizado"
    assert legacy.email == "despues@example.test"
    assert legacy.plazo_pago_dias == 60
    assert legacy.activo is False
    assert Cliente.objects.filter(nit="900261NUEVO").exists()
    assert AuditoriaTercero.objects.filter(
        tercero_id=legacy.pk, campo="nombre", valor_anterior="Cliente legacy",
        valor_nuevo="Cliente legacy actualizado",
    ).exists()


@pytest.mark.django_db
def test_importador_solo_rechaza_nit_duplicado_dentro_del_archivo():
    Cliente.objects.create(nombre="Cliente legacy", nit="900261DUP")
    filas, errores = validar_filas(
        _archivo_clientes(
            "Cliente legacy actualizado,900261DUP,,,Calle 1,30,,,TRUE,Servicios",
            "Cliente nuevo,900261NUEVO2,,,Calle 2,30,,,TRUE,Energía",
            "Cliente duplicado,900261DUP,,,Calle 3,30,,,TRUE,Servicios",
        ),
        "CLIENTE", Cliente,
    )

    assert [fila["_accion"] for fila in filas] == ["actualizar", "crear"]
    assert errores == [{"fila": 4, "error": "NIT duplicado dentro del archivo"}]


def test_sidebar_mueve_maestros_a_parametrizacion_sin_duplicarlos():
    sidebar = Path("templates/components/sidebar.html").read_text()
    financiero, parametrizacion = sidebar.split("<!-- Parametrizacion / Admin -->")

    assert "Maestro de Clientes" not in financiero
    assert "Maestro de Proveedores" not in financiero
    assert parametrizacion.count("Maestro de Clientes") == 1
    assert parametrizacion.count("Maestro de Proveedores") == 1
    assert "{% if ok_fin_maestros %}" in parametrizacion
