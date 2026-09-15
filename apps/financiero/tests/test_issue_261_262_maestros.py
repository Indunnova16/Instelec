from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.financiero.forms_finv2_gastos import FacturaGastoForm
from apps.financiero.forms_finv2_ingresos import FacturaIngresoForm
from apps.financiero.models import AuditoriaTercero, CargaTerceros, Cliente, Proveedor
from apps.core.models_roles import RoleModuloPermiso


NIVELES_MAESTROS = {
    "admin": RoleModuloPermiso.VER_EDITAR,
    "admin_general": RoleModuloPermiso.VER_EDITAR,
    "coordinador": RoleModuloPermiso.VER,
    "coordinador_general": RoleModuloPermiso.VER,
    "supervisor": RoleModuloPermiso.VER,
    "director": RoleModuloPermiso.VER,
}


def _sembrar_permisos_maestros():
    """Equivale a la migración: pytest usa --nomigrations."""
    for codigo, nivel in NIVELES_MAESTROS.items():
        RoleModuloPermiso.objects.update_or_create(
            role_id=codigo,
            modulo=RoleModuloPermiso.MODULO_MANTENIMIENTO,
            submodulo="FIN_MAESTROS",
            defaults={"nivel_acceso": nivel},
        )


def _usuario_con_rol(email, rol):
    usuario = get_user_model().objects.create(
        email=email, rol=rol, documento=email[:10], first_name="Rol", last_name="QA",
    )
    usuario.set_password("testpass123!")
    usuario.save()
    return usuario


@pytest.mark.django_db
def test_cliente_ciclo_vida_auditable_y_nit_inmutable(client, admin_user):
    client.force_login(admin_user)
    response = client.post(
        "/financiero/maestros/clientes/nuevo/",
        {"nombre": "Cliente primera carga", "nit": "900261001", "plazo_pago_dias": 30, "activo": "on"},
    )
    assert response.status_code == 302
    cliente = Cliente.objects.get(nit="900261001")
    response = client.post(
        f"/financiero/maestros/clientes/{cliente.pk}/",
        {"nombre": cliente.nombre, "nit": "CAMBIAR", "plazo_pago_dias": 30, "activo": "", "motivo_inactivacion": "Fin de contrato"},
    )
    cliente.refresh_from_db()
    assert response.status_code == 302
    assert cliente.nit == "900261001"
    assert not cliente.activo and cliente.inactivo_desde == date.today()
    assert AuditoriaTercero.objects.filter(tercero_id=cliente.pk, campo="activo").exists()


@pytest.mark.django_db
def test_maestros_rechazan_plazo_y_fechas_invalidas(client, admin_user):
    client.force_login(admin_user)
    response = client.post(
        "/financiero/maestros/proveedores/nuevo/",
        {"nombre": "Proveedor", "nit": "900262001", "plazo_pago_dias": 0, "activo": "on"},
    )
    assert response.status_code == 200
    assert "plazo_pago_dias" in response.context["form"].errors
    response = client.post(
        "/financiero/maestros/clientes/nuevo/",
        {"nombre": "Cliente", "nit": "900261002", "plazo_pago_dias": 30, "fecha_inicio_contrato": "2026-12-02", "fecha_fin_contrato": "2026-12-01", "activo": "on"},
    )
    assert "fecha_fin_contrato" in response.context["form"].errors


@pytest.mark.django_db
def test_selectores_nuevos_solo_muestran_activos():
    cliente_activo = Cliente.objects.create(nombre="Activo", nit="900261003")
    Cliente.objects.create(nombre="Inactivo", nit="900261004", activo=False)
    proveedor_activo = Proveedor.objects.create(nombre="Activo", nit="900262003")
    Proveedor.objects.create(nombre="Inactivo", nit="900262004", activo=False)
    assert list(FacturaIngresoForm().fields["cliente"].queryset) == [cliente_activo]
    assert list(FacturaGastoForm().fields["proveedor"].queryset) == [proveedor_activo]


@pytest.mark.django_db
def test_filtros_preservan_activos_e_inactivos(client, admin_user):
    client.force_login(admin_user)
    Cliente.objects.create(nombre="Visible", nit="900261005")
    Cliente.objects.create(nombre="Archivado", nit="900261006", activo=False)
    assert b"Visible" in client.get("/financiero/maestros/clientes/?estado=activos").content
    assert b"Archivado" not in client.get("/financiero/maestros/clientes/?estado=activos").content
    assert b"Archivado" in client.get("/financiero/maestros/clientes/?estado=inactivos").content


@pytest.mark.django_db
def test_importador_clientes_preview_confirma_lote_y_guarda_historial(client, admin_user):
    client.force_login(admin_user)
    contenido = (
        "nombre,nit,email,telefono,direccion,plazo_pago_dias,fecha_inicio_contrato,fecha_fin_contrato,activo,industria\n"
        "Cliente importado,900261010,importado@example.test,3000000000,Calle 1,45,2026-01-01,2026-12-31,TRUE,Infraestructura\n"
        "Cliente inactivo importado,900261011,,,Calle 2,30,,,FALSE,Servicios\n"
    )
    response = client.post("/financiero/maestros/clientes/importar/", {"archivo": SimpleUploadedFile("clientes.csv", contenido.encode(), content_type="text/csv")})
    assert response.status_code == 200
    assert not Cliente.objects.filter(nit="900261010").exists()
    assert b"Vista previa" in response.content
    response = client.post("/financiero/maestros/clientes/importar/", {"confirmar": "1"})
    assert response.status_code == 302
    assert Cliente.objects.filter(nit="900261010", plazo_pago_dias=45, activo=True).exists()
    assert Cliente.objects.filter(nit="900261011", activo=False).exists()
    assert CargaTerceros.objects.filter(tercero_tipo="CLIENTE", resultado="CONFIRMADA").exists()


@pytest.mark.django_db
@pytest.mark.parametrize("fila,error_esperado", [
    ("Tel invalido,900261020,,abc,Calle 1,30,,,TRUE,Servicios", "telefono"),
    ("Industria mala,900261021,,,Calle 1,30,,,TRUE,Sector Inventado", "industria"),
    ("Plazo alto,900261022,,,Calle 1,250,,,TRUE,Servicios", "plazo_pago_dias"),
    ("Activo raro,900261023,,,Calle 1,30,,,tal_vez,Servicios", "activo"),
])
def test_importador_clientes_rechaza_filas_invalidas(client, admin_user, fila, error_esperado):
    """Regresión de los 4 huecos que encontró el validador-cierre de #261:
    teléfono sin formato, industria fuera del catálogo, plazo fuera de
    1-120 (desalineado del viejo tope 365) y columna activo no reconocida."""
    client.force_login(admin_user)
    contenido = (
        "nombre,nit,email,telefono,direccion,plazo_pago_dias,fecha_inicio_contrato,fecha_fin_contrato,activo,industria\n"
        f"{fila}\n"
    )
    response = client.post("/financiero/maestros/clientes/importar/", {"archivo": SimpleUploadedFile("clientes.csv", contenido.encode(), content_type="text/csv")})
    assert response.status_code == 200
    assert error_esperado.encode() in response.content
    assert not Cliente.objects.filter(nombre__startswith=fila.split(",")[0]).exists()


@pytest.mark.django_db
def test_importador_proveedores_rechaza_columnas_y_nit_duplicado(client, admin_user):
    client.force_login(admin_user)
    Proveedor.objects.create(nombre="Existente", nit="900262010")
    contenido = (
        "nombre,nit,email,telefono,direccion,plazo_pago_dias,fecha_inicio_contrato,fecha_fin_contrato,activo,tipo_servicio\n"
        "Duplicado,900262010,,,Calle 1,30,,,TRUE,Servicios\n"
    )
    response = client.post("/financiero/maestros/proveedores/importar/", {"archivo": SimpleUploadedFile("proveedores.csv", contenido.encode(), content_type="text/csv")})
    assert response.status_code == 200
    assert b"NIT duplicado" in response.content
    assert not Proveedor.objects.filter(nombre="Duplicado").exists()
    assert CargaTerceros.objects.filter(tercero_tipo="PROVEEDOR", resultado="RECHAZADA").exists()


@pytest.mark.django_db
def test_importador_proveedores_respeta_columna_activo(client, admin_user):
    """Regresión: el importador ignoraba la columna Activo por completo y
    creaba todo como activo=True sin importar lo que dijera el archivo."""
    client.force_login(admin_user)
    contenido = (
        "nombre,nit,email,telefono,direccion,plazo_pago_dias,fecha_inicio_contrato,fecha_fin_contrato,activo,tipo_servicio\n"
        "Prov activo,900262020,,,Calle 1,30,,,1,Servicios\n"
        "Prov inactivo,900262021,,,Calle 1,30,,,0,Servicios\n"
    )
    client.post("/financiero/maestros/proveedores/importar/", {"archivo": SimpleUploadedFile("proveedores.csv", contenido.encode(), content_type="text/csv")})
    client.post("/financiero/maestros/proveedores/importar/", {"confirmar": "1"})
    assert Proveedor.objects.get(nit="900262020").activo is True
    assert Proveedor.objects.get(nit="900262021").activo is False


@pytest.mark.django_db
@pytest.mark.parametrize("ruta", [
    "/financiero/maestros/clientes/",
    "/financiero/maestros/proveedores/",
])
def test_roles_de_consulta_ven_listado_historial_sin_controles_de_gestion(client, ruta):
    _sembrar_permisos_maestros()
    cliente = Cliente.objects.create(nombre="Cliente consulta", nit="900261100")
    client.force_login(_usuario_con_rol("supervisor-maestros@test.com", "supervisor"))
    listado = client.get(ruta)
    assert listado.status_code == 200
    assert f'href="{ruta}nuevo/"'.encode() not in listado.content
    assert f'href="{ruta}importar/"'.encode() not in listado.content
    assert b">Editar<" not in listado.content
    historial = client.get(f"/financiero/maestros/clientes/{cliente.pk}/auditoria/")
    assert historial.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("ruta", [
    "/financiero/maestros/clientes/",
    "/financiero/maestros/proveedores/",
    "/financiero/maestros/clientes/nuevo/",
    "/financiero/maestros/proveedores/nuevo/",
    "/financiero/maestros/clientes/importar/",
    "/financiero/maestros/proveedores/importar/",
])
def test_rol_no_autorizado_no_entra_a_ninguna_ruta_de_maestros(client, ruta):
    client.force_login(_usuario_con_rol("operario-maestros@test.com", "operario_general"))
    assert client.get(ruta).status_code == 302


@pytest.mark.django_db
@pytest.mark.parametrize("modelo,ruta", [
    (Cliente, "/financiero/maestros/clientes/"),
    (Proveedor, "/financiero/maestros/proveedores/"),
])
def test_rol_de_consulta_no_puede_gestionar_ni_por_url_directa(client, modelo, ruta):
    _sembrar_permisos_maestros()
    tercero = modelo.objects.create(nombre="Tercero protegido", nit="900261101")
    client.force_login(_usuario_con_rol("coordinador-maestros@test.com", "coordinador"))
    assert client.get(f"{ruta}{tercero.pk}/").status_code == 403
    assert client.get(f"{ruta}nuevo/").status_code == 403
    # Las mutaciones se interceptan primero en RBACModuloMiddleware, cuyo
    # contrato establecido es redirigir al inicio con un mensaje flash.
    assert client.post(ruta, {"nombre": "Intruso"}).status_code == 302


@pytest.mark.django_db
def test_auditoria_inactivar_registra_valor_anterior_y_nuevo_no_vacios(client, admin_user):
    """Regresión: el validador-cierre de #261/#262 encontró que inactivar/
    reactivar dejaba valor_anterior/valor_nuevo vacíos o duplicados en la
    auditoría — la causa era doble: (a) el "antes" se leía después de que
    ModelForm.is_valid() ya había mutado la instancia in-place, y (b)
    `False or ""` colapsaba el booleano activo=False a cadena vacía."""
    client.force_login(admin_user)
    client.post(
        "/financiero/maestros/clientes/nuevo/",
        {"nombre": "Cliente auditoria", "nit": "900261900", "plazo_pago_dias": 30, "activo": "on"},
    )
    cliente = Cliente.objects.get(nit="900261900")
    client.post(
        f"/financiero/maestros/clientes/{cliente.pk}/",
        {"nombre": cliente.nombre, "nit": cliente.nit, "plazo_pago_dias": 30, "activo": "",
         "motivo_inactivacion": "Regresion QA"},
    )
    evento = AuditoriaTercero.objects.get(tercero_id=cliente.pk, campo="activo")
    assert evento.valor_anterior == "True"
    assert evento.valor_nuevo == "False"
    assert evento.valor_anterior != evento.valor_nuevo


@pytest.mark.django_db
def test_plazo_pago_dias_rechaza_por_encima_de_120(client, admin_user):
    """Regresión: el plan (#261/#262) especifica el rango 1-120; el validador
    encontró que plazo=121 era ACEPTADO por el MaxValueValidator(365)."""
    client.force_login(admin_user)
    response = client.post(
        "/financiero/maestros/proveedores/nuevo/",
        {"nombre": "Proveedor plazo alto", "nit": "900262900", "plazo_pago_dias": 121, "activo": "on"},
    )
    assert response.status_code == 200
    assert "plazo_pago_dias" in response.context["form"].errors
    assert not Proveedor.objects.filter(nit="900262900").exists()
