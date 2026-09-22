"""#261 — persistencia PARCIAL en el importador de terceros.

Antes del fix: si CUALQUIER fila del archivo tenía un error de validación
(p.ej. industria fuera del catálogo cerrado INDUSTRIAS_VALIDAS), el archivo
COMPLETO quedaba rechazado y NINGUNA fila se persistía -- ni siquiera las
filas válidas del mismo archivo (caso real de Andrea 2026-09-22: NIT nuevo
999888777 + actualización de PM COMMERCIAL en el mismo archivo, 0 filas
creadas/actualizadas).

Después del fix: las filas SIN error se crean/actualizan aunque otras filas
del mismo archivo tengan error de validación.
"""
from django.core.files.uploadedfile import SimpleUploadedFile

import pytest

from apps.financiero.models import CargaTerceros, Cliente


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
def test_confirma_filas_validas_aunque_otra_fila_del_archivo_tenga_error(client, admin_user):
    """Reproduce el escenario reportado por Andrea: un NIT nuevo válido +
    una actualización de un cliente legacy válida, mezcladas en el MISMO
    archivo con una tercera fila cuya industria no está en el catálogo
    cerrado. Antes del fix, esto rechazaba el archivo completo (0
    persistencias). Después del fix, las 2 filas válidas se guardan."""
    legacy = Cliente.objects.create(
        nombre="PM Commercial", nit="900261PM", email="antes@example.test",
        plazo_pago_dias=30, industria="Servicios",
    )
    client.force_login(admin_user)
    archivo = _archivo_clientes(
        "Cliente nuevo,900261NEW,nuevo@example.test,3000000000,Calle Nueva,45,,,TRUE,Energía",
        "PM Commercial actualizado,900261PM,despues@example.test,3000000001,Calle Legacy,60,,,TRUE,Servicios",
        "Cliente industria invalida,900261BAD,,,Calle 3,30,,,TRUE,Tecnología",
    )

    preview = client.post("/financiero/maestros/clientes/importar/", {"archivo": archivo})
    assert preview.status_code == 200
    assert b"2 fila(s) v\xc3\xa1lida(s)" in preview.content
    assert b"industria &#x27;Tecnolog\xc3\xada&#x27; no es v\xc3\xa1lida" in preview.content
    # El botón "Confirmar" debe estar presente aunque haya errores en el archivo.
    assert b'name="confirmar"' in preview.content
    # Nada se persiste todavía en el paso de preview.
    assert Cliente.objects.count() == 1

    confirmacion = client.post("/financiero/maestros/clientes/importar/", {"confirmar": "1"})
    assert confirmacion.status_code == 302

    # Las 2 filas válidas SÍ se persistieron.
    assert Cliente.objects.filter(nit="900261NEW").exists()
    legacy.refresh_from_db()
    assert legacy.nombre == "PM Commercial actualizado"
    assert legacy.email == "despues@example.test"
    # La fila inválida NO se persistió (no hay 900261BAD).
    assert not Cliente.objects.filter(nit="900261BAD").exists()
    assert Cliente.objects.count() == 2

    carga = CargaTerceros.objects.filter(tercero_tipo="CLIENTE").latest("created_at")
    assert carga.resultado == "CONFIRMADA"
    assert carga.filas_validas == 2
    assert carga.filas_error == 1
    assert carga.detalle_errores[0]["fila"] == 4


@pytest.mark.django_db
def test_no_confirma_si_ninguna_fila_es_valida(client, admin_user):
    """Si TODAS las filas tienen error (0 filas válidas), el comportamiento
    previo se mantiene: no hay nada que confirmar."""
    client.force_login(admin_user)
    archivo = _archivo_clientes(
        "Cliente industria invalida,900261ONLYBAD,,,Calle 3,30,,,TRUE,Tecnología",
    )
    preview = client.post("/financiero/maestros/clientes/importar/", {"archivo": archivo})
    assert preview.status_code == 200
    assert b'name="confirmar"' not in preview.content

    confirmacion = client.post("/financiero/maestros/clientes/importar/", {"confirmar": "1"})
    assert confirmacion.status_code == 302
    assert Cliente.objects.count() == 0
