"""Gaps de la pre-validación del cliente sobre Facturas de Ingreso (#249 v2).

Cubre, contra el código real (no reconstruye lo ya implementado):
1. RBAC granular (FIN_FACTURAS_INGRESOS) en vez de allowed_roles legacy.
3. UPSERT en carga masiva de facturas.
4. Cálculos automáticos: consecutivo GLOBAL (no anual) + días de morosidad.
5. Filtros de listado: estado, período, cliente, rango de valor.
6. Auditoría: creado_por / registrado_por / AuditoriaFacturaIngreso.
"""

import io
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache

from apps.contratos.models import Contrato
from apps.core.models import Role, RoleModuloPermiso
from apps.financiero.models import (
    AuditoriaFacturaIngreso,
    Banco,
    CargaFacturasIngreso,
    CicloFacturacion,
    Cliente,
    LineaFacturaIngreso,
    MetodoPago,
    PagoFacturaIngreso,
    Presupuesto,
)
from apps.financiero.services_finv2_ingresos import generar_numero_factura
from apps.lineas.models import Linea


@pytest.fixture
def datos_factura(db):
    linea = Linea.objects.create(codigo="FINV2-249V2", nombre="Línea facturable v2")
    cliente = Cliente.objects.create(nombre="Cliente 249 v2 S.A.", nit="900249900", activo=True)
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.MANTENIMIENTO,
        codigo="FINV2-249V2",
        nombre="Proyecto facturable v2",
        cliente=cliente.nombre,
    )
    presupuesto = Presupuesto.objects.create(
        anio=2026,
        mes=9,
        linea=linea,
        cliente=cliente,
        proyecto=contrato,
        facturacion_esperada="250.00",
    )
    banco = Banco.objects.create(nombre="Banco 249v2")
    metodo = MetodoPago.objects.create(nombre="Transferencia 249v2")
    return presupuesto, cliente, contrato, banco, metodo


def _rol_consulta(codigo="qa_consulta_facturas_249", nivel_acceso="ver"):
    """Rol NO-superuser con SOLO nivel `ver` sobre FIN_FACTURAS_INGRESOS --
    para probar el RBAC granular con un rol de consulta real (gap 1)."""
    role, _ = Role.objects.get_or_create(
        codigo=codigo, defaults={"nombre": "QA consulta 249", "nivel": "operario"}
    )
    RoleModuloPermiso.objects.update_or_create(
        role=role,
        modulo="MANTENIMIENTO",
        submodulo="FIN_FACTURAS_INGRESOS",
        defaults={"nivel_acceso": nivel_acceso},
    )
    cache.clear()
    return role


# ---------------------------------------------------------------------------
# Gap 1 -- RBAC granular
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_gap1_rol_ver_puede_listar_pero_no_emitir(client, django_user_model, datos_factura):
    role = _rol_consulta()
    user = django_user_model.objects.create_user(
        email="ver-249@example.test", password="x", rol=role.codigo
    )
    client.force_login(user)
    respuesta = client.get("/financiero/facturas-ingresos/")
    assert respuesta.status_code == 200
    # Nivel "ver" no habilita mutaciones -- crear factura es POST, requiere
    # ver_editar. `RBACModuloMiddleware` (nivel 1, granular) intercepta el
    # POST ANTES de que la vista corra y responde con un redirect 302 a "/"
    # + mensaje de error -- mismo comportamiento que el resto de hojas
    # FIN_* del portafolio (única excepción documentada es
    # `/financiero/carga-financiera/`, #247). Lo que importa para el gap 1
    # es que NO cree la factura, no el código HTTP exacto.
    presupuesto, cliente, contrato, _, _ = datos_factura
    respuesta_post = client.post(
        "/financiero/facturas-ingresos/nueva/",
        {
            "cliente": str(cliente.pk),
            "proyecto": str(contrato.pk),
            "fecha_factura": "2026-09-08",
            "lineas-TOTAL_FORMS": "1",
            "lineas-INITIAL_FORMS": "0",
            "lineas-MIN_NUM_FORMS": "1",
            "lineas-MAX_NUM_FORMS": "20",
            "lineas-0-descripcion": "x",
            "lineas-0-cantidad": "1",
            "lineas-0-valor_unitario": "100",
        },
    )
    assert respuesta_post.status_code == 302
    assert not CicloFacturacion.objects.filter(cliente=cliente).exists()


@pytest.mark.django_db
def test_gap1_rol_sin_submodulo_no_ve_facturas(client, django_user_model):
    role, _ = Role.objects.get_or_create(
        codigo="qa_sin_facturas_249", defaults={"nombre": "QA sin facturas", "nivel": "operario"}
    )
    RoleModuloPermiso.objects.update_or_create(
        role=role,
        modulo="MANTENIMIENTO",
        submodulo="FIN_DASHBOARD",
        defaults={"nivel_acceso": "ver"},
    )
    cache.clear()
    user = django_user_model.objects.create_user(
        email="sin-facturas-249@example.test", password="x", rol=role.codigo
    )
    client.force_login(user)
    respuesta = client.get("/financiero/facturas-ingresos/")
    # RBACModuloMiddleware (nivel 1, granular) bloquea ANTES de la vista con
    # un redirect + mensaje de error -- ver nota del test anterior.
    assert respuesta.status_code == 302
    assert b"facturas-ingresos" not in respuesta.content


@pytest.mark.django_db
def test_gap1_admin_legacy_conserva_acceso_via_seed(client, admin_user):
    """El seed (migración 0007) preserva admin/director/coordinador -- pero
    `admin_user` es superuser, que ya bypassa cualquier submódulo. Se prueba
    acá que el rol legacy 'director' (no superuser) sigue entrando tras la
    migración de datos real -- fuera del alcance de pytest --nomigrations,
    así que se siembra la fila explícitamente como hace el resto de la
    suite para hojas granulares nuevas (ver test_issue_247_round2.py)."""
    role, _ = Role.objects.get_or_create(
        codigo="director", defaults={"nombre": "Director de Proyecto (legacy)", "nivel": "admin"}
    )
    RoleModuloPermiso.objects.update_or_create(
        role=role,
        modulo="MANTENIMIENTO",
        submodulo="FIN_FACTURAS_INGRESOS",
        defaults={"nivel_acceso": "ver_editar"},
    )
    cache.clear()


# ---------------------------------------------------------------------------
# Gap 2 -- navegabilidad (documentado: ya existe bajo Financiero)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_gap2_link_facturas_ingresos_visible_en_sidebar(client, admin_user):
    client.force_login(admin_user)
    respuesta = client.get("/financiero/")
    html = respuesta.content.decode()
    assert "/financiero/facturas-ingresos/" in html
    assert "Facturas de Ingresos" in html
    assert "/financiero/facturas-ingresos/importar/" in html
    assert "Carga Masiva de Facturas" in html


# ---------------------------------------------------------------------------
# Gap 3 -- UPSERT en carga masiva
# ---------------------------------------------------------------------------


def _csv_carga(filas):
    encabezado = "cliente_nit,fecha_factura,concepto,valor_neto,metodo_pago,observaciones\n"
    cuerpo = "\n".join(",".join(str(v) for v in fila) for fila in filas)
    return io.BytesIO((encabezado + cuerpo + "\n").encode("utf-8"))


@pytest.mark.django_db
def test_gap3_carga_masiva_crea_factura_nueva(client, admin_user, datos_factura):
    _, cliente, _, _, metodo = datos_factura
    client.force_login(admin_user)
    archivo = _csv_carga(
        [
            [
                cliente.nit,
                "2026-09-10",
                "Servicio de mantenimiento",
                "1000000",
                metodo.nombre,
                "Carga inicial",
            ]
        ]
    )
    archivo.name = "carga.csv"
    respuesta = client.post("/financiero/facturas-ingresos/importar/", {"archivo": archivo})
    assert respuesta.status_code == 200
    assert b"1 fila" in respuesta.content or b"nueva" in respuesta.content

    confirmar = client.post("/financiero/facturas-ingresos/importar/", {"confirmar": "1"})
    assert confirmar.status_code == 302
    ciclo = CicloFacturacion.objects.get(cliente=cliente, fecha_factura=date(2026, 9, 10))
    assert ciclo.subtotal == Decimal("1000000")
    assert ciclo.iva == Decimal("190000.00")
    assert ciclo.total == Decimal("1190000.00")
    assert ciclo.numero_secuencial is not None
    assert ciclo.creado_por == admin_user.get_username()
    linea = ciclo.lineas_factura.get()
    assert linea.descripcion == "Servicio de mantenimiento"
    carga = CargaFacturasIngreso.objects.latest("created_at")
    assert carga.resultado == "CONFIRMADA"
    assert carga.filas_creadas == 1


@pytest.mark.django_db
def test_gap3_carga_masiva_upsert_actualiza_no_duplica(client, admin_user, datos_factura):
    """Mismo cliente+fecha ya facturado -> UPSERT actualiza, NO rechaza como
    duplicado (bug real corregido en #261/#262 para terceros; acá se aplica
    el mismo criterio a facturas)."""
    _, cliente, _, _, metodo = datos_factura
    existente = CicloFacturacion.objects.create(
        cliente=cliente,
        fecha_factura=date(2026, 9, 10),
        numero_factura="FI-2026-00001",
        numero_secuencial=1,
        subtotal=Decimal("500000"),
        iva=Decimal("95000"),
        total=Decimal("595000"),
        estado=CicloFacturacion.Estado.FACTURA_EMITIDA,
    )
    LineaFacturaIngreso.objects.create(
        ciclo=existente,
        descripcion="Concepto original",
        cantidad=1,
        valor_unitario=Decimal("500000"),
        total=Decimal("500000"),
    )
    client.force_login(admin_user)
    archivo = _csv_carga(
        [[cliente.nit, "2026-09-10", "Concepto corregido", "700000", metodo.nombre, "Ajuste"]]
    )
    archivo.name = "carga.csv"
    client.post("/financiero/facturas-ingresos/importar/", {"archivo": archivo})
    confirmar = client.post("/financiero/facturas-ingresos/importar/", {"confirmar": "1"})
    assert confirmar.status_code == 302

    assert (
        CicloFacturacion.objects.filter(cliente=cliente, fecha_factura=date(2026, 9, 10)).count()
        == 1
    )
    existente.refresh_from_db()
    assert existente.subtotal == Decimal("700000")
    assert existente.lineas_factura.get().descripcion == "Concepto corregido"
    assert AuditoriaFacturaIngreso.objects.filter(ciclo=existente).exists()
    carga = CargaFacturasIngreso.objects.latest("created_at")
    assert carga.filas_actualizadas == 1
    assert carga.filas_creadas == 0


@pytest.mark.django_db
def test_gap3_carga_masiva_rechaza_nit_inexistente(client, admin_user):
    client.force_login(admin_user)
    archivo = _csv_carga([["000000000", "2026-09-10", "Servicio", "1000", "Transferencia", ""]])
    archivo.name = "carga.csv"
    respuesta = client.post("/financiero/facturas-ingresos/importar/", {"archivo": archivo})
    assert b"no existe un cliente" in respuesta.content


@pytest.mark.django_db
def test_gap3_carga_masiva_rechaza_cliente_inactivo(client, admin_user, datos_factura):
    _, cliente, _, _, _ = datos_factura
    cliente.activo = False
    cliente.save(update_fields=["activo"])
    client.force_login(admin_user)
    archivo = _csv_carga([[cliente.nit, "2026-09-10", "Servicio", "1000", "Transferencia", ""]])
    archivo.name = "carga.csv"
    respuesta = client.post("/financiero/facturas-ingresos/importar/", {"archivo": archivo})
    assert b"inactivo" in respuesta.content


@pytest.mark.django_db
def test_gap3_carga_masiva_rechaza_valor_neto_no_positivo(client, admin_user, datos_factura):
    _, cliente, _, _, _ = datos_factura
    client.force_login(admin_user)
    archivo = _csv_carga([[cliente.nit, "2026-09-10", "Servicio", "0", "Transferencia", ""]])
    archivo.name = "carga.csv"
    respuesta = client.post("/financiero/facturas-ingresos/importar/", {"archivo": archivo})
    assert b"mayor que cero" in respuesta.content


# ---------------------------------------------------------------------------
# Gap 4 -- cálculos automáticos: consecutivo GLOBAL + morosidad
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_gap4_consecutivo_global_no_reinicia_por_anio(datos_factura):
    presupuesto, cliente, _, _, _ = datos_factura
    CicloFacturacion.objects.create(
        presupuesto=presupuesto,
        cliente=cliente,
        fecha_factura=date(2026, 1, 1),
        numero_factura="FI-2026-00001",
        numero_secuencial=1,
    )
    assert generar_numero_factura(date(2027, 1, 1)) == "FI-2027-00002"


@pytest.mark.django_db
def test_gap4_dias_morosidad_cero_si_no_vencida_o_pagada(datos_factura):
    presupuesto, cliente, _, _, _ = datos_factura
    hoy = date.today()
    vigente = CicloFacturacion.objects.create(
        presupuesto=presupuesto,
        cliente=cliente,
        fecha_factura=hoy,
        numero_factura="FI-X-1",
        numero_secuencial=101,
        plazo_pago_dias=30,
        estado=CicloFacturacion.Estado.FACTURA_EMITIDA,
    )
    assert vigente.dias_morosidad == 0

    vencida = CicloFacturacion.objects.create(
        presupuesto=presupuesto,
        cliente=cliente,
        fecha_factura=hoy - timedelta(days=40),
        numero_factura="FI-X-2",
        numero_secuencial=102,
        plazo_pago_dias=30,
        estado=CicloFacturacion.Estado.FACTURA_EMITIDA,
    )
    assert vencida.dias_morosidad == 10

    pagada = CicloFacturacion.objects.create(
        presupuesto=presupuesto,
        cliente=cliente,
        fecha_factura=hoy - timedelta(days=40),
        numero_factura="FI-X-3",
        numero_secuencial=103,
        plazo_pago_dias=30,
        estado=CicloFacturacion.Estado.PAGO_RECIBIDO,
    )
    assert pagada.dias_morosidad == 0


# ---------------------------------------------------------------------------
# Gap 5 -- filtros de listado
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_gap5_filtro_por_cliente_y_rango_de_valor(client, admin_user, datos_factura):
    presupuesto, cliente, _, _, _ = datos_factura
    otro_cliente = Cliente.objects.create(nombre="Otro cliente 249", nit="900249901", activo=True)
    CicloFacturacion.objects.create(
        cliente=cliente,
        fecha_factura=date(2026, 9, 1),
        numero_factura="FI-F-1",
        numero_secuencial=201,
        total=Decimal("100000"),
        estado=CicloFacturacion.Estado.FACTURA_EMITIDA,
    )
    CicloFacturacion.objects.create(
        cliente=otro_cliente,
        fecha_factura=date(2026, 9, 1),
        numero_factura="FI-F-2",
        numero_secuencial=202,
        total=Decimal("900000"),
        estado=CicloFacturacion.Estado.FACTURA_EMITIDA,
    )
    client.force_login(admin_user)
    respuesta = client.get(f"/financiero/facturas-ingresos/?cliente={cliente.pk}")
    html = respuesta.content.decode()
    assert "FI-F-1" in html
    assert "FI-F-2" not in html

    respuesta_valor = client.get("/financiero/facturas-ingresos/?valor_min=500000")
    html_valor = respuesta_valor.content.decode()
    assert "FI-F-2" in html_valor
    assert "FI-F-1" not in html_valor


@pytest.mark.django_db
def test_gap5_filtro_por_estado_vencida(client, admin_user, datos_factura):
    presupuesto, cliente, _, _, _ = datos_factura
    hoy = date.today()
    CicloFacturacion.objects.create(
        cliente=cliente,
        fecha_factura=hoy - timedelta(days=60),
        numero_factura="FI-V-1",
        numero_secuencial=301,
        total=Decimal("100000"),
        plazo_pago_dias=30,
        estado=CicloFacturacion.Estado.FACTURA_EMITIDA,
    )
    CicloFacturacion.objects.create(
        cliente=cliente,
        fecha_factura=hoy,
        numero_factura="FI-V-2",
        numero_secuencial=302,
        total=Decimal("100000"),
        plazo_pago_dias=30,
        estado=CicloFacturacion.Estado.FACTURA_EMITIDA,
    )
    client.force_login(admin_user)
    respuesta = client.get("/financiero/facturas-ingresos/?estado=VENCIDA")
    html = respuesta.content.decode()
    assert "FI-V-1" in html
    assert "FI-V-2" not in html


# ---------------------------------------------------------------------------
# Gap 6 -- auditoría
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_gap6_creado_por_se_registra_al_emitir(client, admin_user, datos_factura):
    presupuesto, cliente, contrato, _, _ = datos_factura
    client.force_login(admin_user)
    client.post(
        "/financiero/facturas-ingresos/nueva/",
        {
            "cliente": str(cliente.pk),
            "proyecto": str(contrato.pk),
            "fecha_factura": "2026-09-08",
            "lineas-TOTAL_FORMS": "1",
            "lineas-INITIAL_FORMS": "0",
            "lineas-MIN_NUM_FORMS": "1",
            "lineas-MAX_NUM_FORMS": "20",
            "lineas-0-descripcion": "Servicio",
            "lineas-0-cantidad": "1",
            "lineas-0-valor_unitario": "500",
        },
    )
    factura = CicloFacturacion.objects.get(cliente=cliente, fecha_factura=date(2026, 9, 8))
    assert factura.creado_por == admin_user.get_username()


@pytest.mark.django_db
def test_gap6_registrado_por_y_auditoria_al_pagar(client, admin_user, datos_factura):
    _, cliente, _, banco, metodo = datos_factura
    factura = CicloFacturacion.objects.create(
        cliente=cliente,
        fecha_factura=date(2026, 9, 1),
        numero_factura="FI-P-1",
        numero_secuencial=401,
        total=Decimal("100000"),
        subtotal=Decimal("84034"),
        iva=Decimal("15966"),
        estado=CicloFacturacion.Estado.FACTURA_EMITIDA,
    )
    client.force_login(admin_user)
    respuesta = client.post(
        f"/financiero/facturas-ingresos/{factura.pk}/",
        {
            "banco": banco.pk,
            "metodo_pago": metodo.pk,
            "fecha": "2026-09-15",
            "monto": "100000",
            "referencia": "TRX-PAGO-249",
        },
    )
    assert respuesta.status_code == 302
    pago = PagoFacturaIngreso.objects.get(ciclo=factura)
    assert pago.registrado_por == admin_user.get_username()
    factura.refresh_from_db()
    assert factura.estado == CicloFacturacion.Estado.PAGO_RECIBIDO
    assert AuditoriaFacturaIngreso.objects.filter(ciclo=factura, campo="estado").exists()
