"""Cierre del checklist cliente sobre Facturas de Gasto (#248, B1 -- /modulo).

El CRUD base (registro/aprobación/pago) ya estaba en `main` cuando arrancó
esta sub-feature (RUN previo, ver comentario del 2026-09-08 en el issue).
Este archivo cubre el GAP confirmado en la pre-validación de Andrea del
2026-09-15:

1. (Corrección 2026-09-23, rechazo del 22-sep) La generación de facturas de
   gasto desde `LineaCargaFinanciera` (#246) tiene su propia suite en
   `test_issue_248_generar_desde_carga.py` -- el upload CSV con columnas
   inventadas que cubría este archivo antes fue retirado por ser la causa
   raíz del rechazo (ver PLAN_2026-09-23_248...).
2. Alertas del listado: pendientes de aprobación (>$1M).
3. RBAC granular (`FIN_FACTURAS_GASTOS`) en vez de `allowed_roles` legacy --
   rol `contador` (sembrado por S1) gestiona, un rol sin el submódulo no ve.
4. Auditoría (creación/rechazo) y compatibilidad con datos legacy
   (facturas creadas antes de la migración 0023, sin `fecha_vencimiento`).
"""

from datetime import date
from decimal import Decimal

import pytest
from django.core.cache import cache

from apps.contratos.models import Contrato
from apps.core.models import Role, RoleModuloPermiso
from apps.core.permissions import SUBMODULOS_FINANCIERO
from apps.financiero.models import (
    AuditoriaFacturaGasto,
    FacturaGasto,
    HomologacionProjectsContable,
    Proveedor,
)


@pytest.fixture
def datos_gasto(db):
    proveedor = Proveedor.objects.create(nombre="Proveedor 248 S.A.S", nit="900248900", activo=True)
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.MANTENIMIENTO,
        codigo="FINV2-248",
        nombre="Proyecto gasto 248",
    )
    homologacion = HomologacionProjectsContable.objects.create(
        tipo="GASTO",
        concepto="Materiales 248",
        codigo_contable="5110",
        centro_costo="CC-248",
        activo=True,
    )
    return proveedor, contrato, homologacion


# ---------------------------------------------------------------------------
# gasto_mayor_1m_alerta_pendiente_aprobacion
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_gasto_mayor_1m_alerta_pendiente_aprobacion(client, admin_user, datos_gasto):
    proveedor, contrato, homologacion = datos_gasto
    factura = FacturaGasto.objects.create(
        proveedor=proveedor,
        contrato=contrato,
        numero_documento="ALERTA-001",
        fecha=date.today(),
        concepto="Compra grande",
        categoria="Materiales",
        centro_costo=homologacion.centro_costo,
        subtotal=Decimal("1500000"),
        iva=Decimal("285000"),
        total=Decimal("1785000"),
        estado=FacturaGasto.Estado.PENDIENTE_APROBACION,
    )
    otra_pequena = FacturaGasto.objects.create(
        proveedor=proveedor,
        contrato=contrato,
        numero_documento="SIN-ALERTA-001",
        fecha=date.today(),
        concepto="Compra pequeña",
        categoria="Materiales",
        centro_costo=homologacion.centro_costo,
        subtotal=Decimal("50000"),
        iva=Decimal("9500"),
        total=Decimal("59500"),
        estado=FacturaGasto.Estado.PENDIENTE_PAGO,
    )
    client.force_login(admin_user)
    respuesta = client.get("/financiero/facturas-gastos/")
    assert respuesta.status_code == 200
    pendientes = list(respuesta.context["alertas"]["pendientes_aprobacion"])
    assert factura in pendientes
    assert otra_pequena not in pendientes
    assert factura in list(respuesta.context["alertas"]["sin_pagar"])
    html = respuesta.content.decode()
    assert "Pendientes de aprobación" in html
    assert str(proveedor) in html


# ---------------------------------------------------------------------------
# rol_contador_ve_menu_gestiona_rol_sin_permiso_no_ve
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_rol_contador_ve_menu_gestiona_rol_sin_permiso_no_ve(
    client, django_user_model, datos_gasto
):
    proveedor, contrato, homologacion = datos_gasto
    # 'contador' viene sembrado por S1 (migración core 0008, RunPython) con
    # ver_editar sobre TODOS los submódulos Financiero (incluido
    # FIN_DASHBOARD, a propósito -- ver docstring de esa migración: es la
    # línea base que el catch-all de RBACModuloMiddleware necesita, la
    # restricción fina por tipo de reporte es una regla de negocio de B4)
    # -- pero la suite corre con `--nomigrations` (pyproject.toml), que
    # salta las migraciones de datos (mismo criterio que
    # `test_issue_249_v2.py::test_gap1_admin_legacy_conserva_acceso_via_seed`).
    # Se siembra la fila explícitamente acá reproduciendo EXACTAMENTE lo que
    # sembraría 0008 en prod, no solo el submódulo bajo prueba.
    role_contador, _ = Role.objects.get_or_create(
        codigo="contador", defaults={"nombre": "Contador", "nivel": "operario"}
    )
    for submodulo in SUBMODULOS_FINANCIERO:
        RoleModuloPermiso.objects.update_or_create(
            role=role_contador,
            modulo="MANTENIMIENTO",
            submodulo=submodulo,
            defaults={"nivel_acceso": "ver_editar"},
        )
    # NOTA (hallazgo fuera de FILES_OWNED de B1): la migración real de S1
    # (`core/migrations/0008_seed_fin_facturas_gastos_y_roles_248.py`) SOLO
    # siembra hojas granulares para 'contador'/'gerente_financiero' -- a
    # diferencia de los roles legacy (`0002_seed_roles_permisos.py`), no
    # crea la fila de módulo completo (`submodulo=''`) que
    # `{% puede_acceder 'MANTENIMIENTO' as ok_mant %}` exige para mostrar
    # TODA la sección Mantenimiento del sidebar (no solo Facturas de
    # Gastos). Sin esa fila, 'contador'/'gerente_financiero' navegan por
    # URL directa (RBAC de vista OK) pero no ven ningún ítem del sidebar
    # bajo Mantenimiento. Se siembra acá para aislar la prueba de ESE gap
    # de S1 y testear lo que sí es responsabilidad de B1 (context_processor
    # + sidebar.html de Facturas de Gastos) -- reportado en el cierre de
    # este issue para que se corrija en S1/0008.
    RoleModuloPermiso.objects.update_or_create(
        role=role_contador,
        modulo="MANTENIMIENTO",
        submodulo="",
        defaults={"nivel_acceso": "ver_editar"},
    )
    cache.clear()
    contador = django_user_model.objects.create_user(
        email="contador-248@example.test", password="x", rol="contador"
    )
    client.force_login(contador)
    respuesta = client.get("/financiero/facturas-gastos/")
    assert respuesta.status_code == 200
    html = respuesta.content.decode()
    assert "Facturas de Gastos" in html
    assert "/financiero/facturas-gastos/importar/" in html

    # "Gestiona": ver_editar habilita la mutación de registrar un gasto.
    respuesta_post = client.post(
        "/financiero/facturas-gastos/nueva/",
        {
            "proveedor": str(proveedor.pk),
            "contrato": str(contrato.pk),
            "numero_documento": "GEST-001",
            "fecha": "2026-09-10",
            "concepto": "Gestión contador",
            "categoria": "Materiales",
            "centro_costo": homologacion.centro_costo,
            "subtotal": "50000",
        },
    )
    assert respuesta_post.status_code == 302
    assert FacturaGasto.objects.filter(numero_documento="GEST-001").exists()

    # Rol SIN el submódulo -- la VISTA (RoleRequiredMixin, required_submodulo
    # =SUBMODULO_FIN_FACTURAS_GASTOS) lo bloquea con 403.
    #
    # NOTA (hallazgo fuera de FILES_OWNED de B1): `apps/core/middleware.py`
    # (`SUBMODULO_PREFIXES`, nivel 1 "granular") no tiene una entrada
    # específica para `/financiero/facturas-gastos/` -- cae en el catch-all
    # `('/financiero/', SUBMODULO_FIN_DASHBOARD)`, el mismo bug de
    # especificidad que el propio middleware documenta como ya corregido
    # para `/financiero/facturas-ingresos/` ("#249 v2 gap 1"). Por eso un
    # rol con SOLO `FIN_DASHBOARD` (como este) pasa el middleware y llega a
    # la vista, que sí lo bloquea correctamente (403) -- no hay hueco de
    # seguridad, pero la UX es peor (403 duro en vez de un redirect con
    # mensaje) y un rol con SOLO `FIN_FACTURAS_GASTOS` sin `FIN_DASHBOARD`
    # quedaría bloqueado por el middleware ANTES de llegar a la vista.
    # Reportado en el cierre del issue para agregar la entrada en
    # `SUBMODULO_PREFIXES` (mismo patrón que facturas-ingresos).
    role_sin, _ = Role.objects.get_or_create(
        codigo="qa_sin_gastos_248", defaults={"nombre": "QA sin gastos 248", "nivel": "operario"}
    )
    RoleModuloPermiso.objects.update_or_create(
        role=role_sin,
        modulo="MANTENIMIENTO",
        submodulo="FIN_DASHBOARD",
        defaults={"nivel_acceso": "ver"},
    )
    cache.clear()
    sin_permiso = django_user_model.objects.create_user(
        email="sin-gastos-248@example.test", password="x", rol=role_sin.codigo
    )
    client.force_login(sin_permiso)
    respuesta_bloqueada = client.get("/financiero/facturas-gastos/")
    assert respuesta_bloqueada.status_code in (302, 403)
    if respuesta_bloqueada.status_code == 302:
        assert b"facturas-gastos" not in respuesta_bloqueada.content


# ---------------------------------------------------------------------------
# Auditoría: rechazo (checklist #248 sección 3 -- "aprobar o rechazar")
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_rechazar_gasto_registra_auditoria(client, admin_user, datos_gasto):
    proveedor, contrato, homologacion = datos_gasto
    factura = FacturaGasto.objects.create(
        proveedor=proveedor,
        contrato=contrato,
        numero_documento="RECHAZO-001",
        fecha=date.today(),
        concepto="Compra a revisar",
        categoria="Materiales",
        centro_costo=homologacion.centro_costo,
        subtotal=Decimal("1200000"),
        iva=Decimal("228000"),
        total=Decimal("1428000"),
        estado=FacturaGasto.Estado.PENDIENTE_APROBACION,
    )
    client.force_login(admin_user)
    respuesta = client.post(
        f"/financiero/facturas-gastos/{factura.pk}/",
        {"accion": "rechazar", "comentario_decision": "Falta soporte contable"},
    )
    assert respuesta.status_code == 302
    factura.refresh_from_db()
    assert factura.estado == FacturaGasto.Estado.RECHAZADA
    assert factura.comentario_decision == "Falta soporte contable"
    auditoria = AuditoriaFacturaGasto.objects.get(factura=factura, campo="estado")
    assert auditoria.valor_anterior == FacturaGasto.Estado.PENDIENTE_APROBACION
    assert auditoria.valor_nuevo == FacturaGasto.Estado.RECHAZADA


# ---------------------------------------------------------------------------
# Dato legacy (OBLIGATORIO -- FacturaGasto ya tenía datos en prod)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_dato_legacy_preservado(client, admin_user, datos_gasto):
    """Una `FacturaGasto` creada antes de la migración 0023 (sin
    `fecha_vencimiento`, sin filas de auditoría) sigue funcionando: aparece
    en el listado y su detalle sigue respondiendo 200 -- el `AddField`
    nullable no puede romper filas existentes."""
    proveedor, contrato, _ = datos_gasto
    legacy = FacturaGasto.objects.create(
        proveedor=proveedor,
        contrato=contrato,
        numero_documento="LEGACY-001",
        fecha=date(2026, 1, 15),
        concepto="Gasto legacy pre-#248",
        categoria="Legacy",
        subtotal=Decimal("300000"),
        iva=Decimal("57000"),
        total=Decimal("357000"),
        estado=FacturaGasto.Estado.PENDIENTE_PAGO,
    )
    assert legacy.fecha_vencimiento is None

    client.force_login(admin_user)
    respuesta = client.get("/financiero/facturas-gastos/")
    assert respuesta.status_code == 200
    assert "LEGACY-001" in respuesta.content.decode()

    respuesta_detalle = client.get(f"/financiero/facturas-gastos/{legacy.pk}/")
    assert respuesta_detalle.status_code == 200
