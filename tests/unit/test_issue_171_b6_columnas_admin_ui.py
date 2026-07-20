"""Instelec#171 (Sprint final, GRUPO A) — B6: UI de administración de
columnas configurables por proyecto/capítulo — `ColumnasConfigurablesView`
(GET, tabs por capítulo) + `ColumnaToggleView`/`ColumnaCrearView`/
`ColumnaEliminarView`/`ColumnaReordenarView` (POST AJAX).

Cubre: agregar columna custom, desactivar columna de sistema (no eliminar),
intentar eliminar columna de sistema (debe rechazar 400), eliminar columna
custom, reordenar, badge de advertencia si suma de pesos activos != 100, y
el gate role-gated (`allowed_roles=['admin', 'director']`, MÁS ANGOSTO que
`ALL_ADMIN_ROLES` — coordinador/liniero deben recibir 403, no solo
liniero — ver `feedback_validar_role_gated_con_rol_real_no_superuser`,
NUNCA testear con superuser porque pasa todo).

Convención de colección: `tests/unit/` (`pyproject.toml` → `testpaths =
["tests"]`).
"""
import pytest
from django.urls import reverse

from apps.construccion.models import (
    ColumnaConfigurable,
    ProyectoConstruccion,
)
from apps.contratos.models import Contrato


@pytest.fixture
def proyecto(db):
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-171-B6-001',
        nombre='Proyecto test #171 B6 — admin columnas',
        cliente='Test',
    )
    # El signal post_save ya crea las 21 columnas de fábrica.
    return ProyectoConstruccion.objects.create(
        contrato=contrato, nombre='Proyecto B6', estado='EJECUCION',
    )


@pytest.fixture
def admin_director_client(client, user_password, django_user_model):
    """Usuario con rol='director' — dentro del allowed_roles angosto de B6
    (['admin', 'director']), pero NO superuser (evita falso positivo)."""
    user = django_user_model.objects.create_user(
        email='director_b6@test.com', password=user_password,
        first_name='Director', last_name='B6', rol='director',
    )
    client.login(username=user.email, password=user_password)
    return client


# ==============================================================================
# 1) GET — vista + tabs + badge de suma de pesos
# ==============================================================================

@pytest.mark.django_db
def test_get_columnas_configurables_200_obra_civil_default(admin_director_client, proyecto):
    url = reverse('construccion:columnas_configurables', kwargs={'proyecto_id': proyecto.id})
    resp = admin_director_client.get(url)
    assert resp.status_code == 200
    assert resp.context['capitulo_activo'] == ColumnaConfigurable.CAPITULO_OBRA_CIVIL
    assert len(resp.context['columnas']) == 6  # 6 columnas OC de fábrica
    assert resp.context['suma_pesos_ok'] is True  # 5+30+5+15+30+15=100


@pytest.mark.django_db
def test_get_columnas_configurables_tab_montaje_via_querystring(admin_director_client, proyecto):
    url = reverse('construccion:columnas_configurables', kwargs={'proyecto_id': proyecto.id})
    resp = admin_director_client.get(url, {'capitulo': ColumnaConfigurable.CAPITULO_MONTAJE})
    assert resp.status_code == 200
    assert resp.context['capitulo_activo'] == ColumnaConfigurable.CAPITULO_MONTAJE
    assert len(resp.context['columnas']) == 4  # 4 columnas Montaje de fábrica


@pytest.mark.django_db
def test_get_columnas_configurables_capitulo_invalido_cae_a_default(admin_director_client, proyecto):
    url = reverse('construccion:columnas_configurables', kwargs={'proyecto_id': proyecto.id})
    resp = admin_director_client.get(url, {'capitulo': 'NO_EXISTE'})
    assert resp.status_code == 200
    assert resp.context['capitulo_activo'] == ColumnaConfigurable.CAPITULO_OBRA_CIVIL


@pytest.mark.django_db
def test_badge_suma_pesos_no_ok_tras_desactivar_columna(admin_director_client, proyecto):
    """Al desactivar 'excavacion' (peso 30), la suma de pesos ACTIVOS pasa
    a 70 — la vista debe reportarlo como no-ok (badge de advertencia)."""
    ColumnaConfigurable.objects.filter(
        proyecto=proyecto, capitulo=ColumnaConfigurable.CAPITULO_OBRA_CIVIL, clave='excavacion',
    ).update(activa=False)

    url = reverse('construccion:columnas_configurables', kwargs={'proyecto_id': proyecto.id})
    resp = admin_director_client.get(url)
    assert resp.status_code == 200
    assert resp.context['suma_pesos_ok'] is False
    assert resp.context['suma_pesos_activos'] == 70
    assert b'70' in resp.content  # badge visible en el HTML


# ==============================================================================
# 2) Agregar columna custom
# ==============================================================================

@pytest.mark.django_db
def test_columna_crear_agrega_columna_custom(admin_director_client, proyecto):
    url = reverse('construccion:columna_crear', kwargs={'proyecto_id': proyecto.id})
    resp = admin_director_client.post(url, {
        'capitulo': ColumnaConfigurable.CAPITULO_OBRA_CIVIL,
        'etiqueta': 'Pintura extra',
        'tipo_valor': ColumnaConfigurable.TIPO_DECIMAL,
        'peso_pct': '10',
    })
    assert resp.status_code == 200, resp.content[:300]
    data = resp.json()
    assert data['ok'] is True
    assert data['clave'] == 'pintura_extra'

    columna = ColumnaConfigurable.objects.get(proyecto=proyecto, clave='pintura_extra')
    assert columna.es_sistema is False
    assert columna.activa is True
    assert columna.peso_pct == 10
    assert columna.capitulo == ColumnaConfigurable.CAPITULO_OBRA_CIVIL
    # orden = max existente (5, la última de las 6 de fábrica: orden 0-5) + 1
    assert columna.orden == 6


@pytest.mark.django_db
def test_columna_crear_rechaza_clave_duplicada(admin_director_client, proyecto):
    """Si la etiqueta genera una clave que ya existe en el capítulo (ej.
    'Cerramiento' → 'cerramiento', ya usada por la columna de fábrica),
    debe rechazar con 400 explicativo."""
    url = reverse('construccion:columna_crear', kwargs={'proyecto_id': proyecto.id})
    resp = admin_director_client.post(url, {
        'capitulo': ColumnaConfigurable.CAPITULO_OBRA_CIVIL,
        'etiqueta': 'Cerramiento',
        'tipo_valor': ColumnaConfigurable.TIPO_DECIMAL,
        'peso_pct': '10',
    })
    assert resp.status_code == 400
    assert 'clave' in resp.json()['error'].lower()


@pytest.mark.django_db
def test_columna_crear_rechaza_peso_fuera_de_rango(admin_director_client, proyecto):
    url = reverse('construccion:columna_crear', kwargs={'proyecto_id': proyecto.id})
    resp = admin_director_client.post(url, {
        'capitulo': ColumnaConfigurable.CAPITULO_OBRA_CIVIL,
        'etiqueta': 'Columna rara',
        'tipo_valor': ColumnaConfigurable.TIPO_DECIMAL,
        'peso_pct': '150',
    })
    assert resp.status_code == 400


@pytest.mark.django_db
def test_columna_crear_boolean_tendido(admin_director_client, proyecto):
    """slugify normaliza acentos (Inspección → inspeccion) y espacios/guiones
    a '_' — clave final ASCII, sin tildes."""
    url = reverse('construccion:columna_crear', kwargs={'proyecto_id': proyecto.id})
    resp = admin_director_client.post(url, {
        'capitulo': ColumnaConfigurable.CAPITULO_TENDIDO_CONDUCTOR,
        'etiqueta': 'Inspección extra',
        'tipo_valor': ColumnaConfigurable.TIPO_BOOLEAN,
        'peso_pct': '5',
    })
    assert resp.status_code == 200, resp.content[:300]
    data = resp.json()
    assert data['clave'] == 'inspeccion_extra'
    columna = ColumnaConfigurable.objects.get(proyecto=proyecto, clave='inspeccion_extra')
    assert columna.tipo_valor == ColumnaConfigurable.TIPO_BOOLEAN
    assert columna.capitulo == ColumnaConfigurable.CAPITULO_TENDIDO_CONDUCTOR


# ==============================================================================
# 3) Desactivar columna de sistema (NO eliminar) + intentar eliminar rechaza
# ==============================================================================

@pytest.mark.django_db
def test_columna_toggle_desactiva_columna_de_sistema(admin_director_client, proyecto):
    columna = ColumnaConfigurable.objects.get(
        proyecto=proyecto, capitulo=ColumnaConfigurable.CAPITULO_OBRA_CIVIL, clave='cerramiento',
    )
    assert columna.activa is True

    url = reverse('construccion:columna_toggle', kwargs={'proyecto_id': proyecto.id, 'columna_id': columna.id})
    resp = admin_director_client.post(url, {'activa': '0'})
    assert resp.status_code == 200
    assert resp.json()['activa'] is False

    columna.refresh_from_db()
    assert columna.activa is False
    assert ColumnaConfigurable.objects.filter(id=columna.id).exists(), "Desactivar NO debe eliminar la fila."


@pytest.mark.django_db
def test_columna_eliminar_rechaza_columna_de_sistema(admin_director_client, proyecto):
    columna = ColumnaConfigurable.objects.get(
        proyecto=proyecto, capitulo=ColumnaConfigurable.CAPITULO_OBRA_CIVIL, clave='cerramiento',
    )
    url = reverse('construccion:columna_eliminar', kwargs={'proyecto_id': proyecto.id, 'columna_id': columna.id})
    resp = admin_director_client.post(url)
    assert resp.status_code == 400
    assert 'sistema' in resp.json()['error'].lower()
    assert ColumnaConfigurable.objects.filter(id=columna.id).exists()


@pytest.mark.django_db
def test_columna_eliminar_columna_custom_ok(admin_director_client, proyecto):
    columna = ColumnaConfigurable.objects.create(
        proyecto=proyecto, capitulo=ColumnaConfigurable.CAPITULO_OBRA_CIVIL,
        clave='custom_borrar', etiqueta='Custom a borrar', orden=99,
        peso_pct=5, tipo_valor=ColumnaConfigurable.TIPO_DECIMAL,
        es_sistema=False, activa=True,
    )
    url = reverse('construccion:columna_eliminar', kwargs={'proyecto_id': proyecto.id, 'columna_id': columna.id})
    resp = admin_director_client.post(url)
    assert resp.status_code == 200
    assert resp.json()['ok'] is True
    assert not ColumnaConfigurable.objects.filter(id=columna.id).exists()


# ==============================================================================
# 4) Reordenar
# ==============================================================================

@pytest.mark.django_db
def test_columna_reordenar_up_intercambia_orden_con_vecina(admin_director_client, proyecto):
    cerramiento = ColumnaConfigurable.objects.get(
        proyecto=proyecto, capitulo=ColumnaConfigurable.CAPITULO_OBRA_CIVIL, clave='cerramiento',
    )
    excavacion = ColumnaConfigurable.objects.get(
        proyecto=proyecto, capitulo=ColumnaConfigurable.CAPITULO_OBRA_CIVIL, clave='excavacion',
    )
    assert cerramiento.orden == 0
    assert excavacion.orden == 1

    url = reverse('construccion:columna_reordenar', kwargs={'proyecto_id': proyecto.id, 'columna_id': excavacion.id})
    resp = admin_director_client.post(url, {'direccion': 'up'})
    assert resp.status_code == 200
    assert resp.json()['ok'] is True

    cerramiento.refresh_from_db()
    excavacion.refresh_from_db()
    assert excavacion.orden == 0
    assert cerramiento.orden == 1


@pytest.mark.django_db
def test_columna_reordenar_en_extremo_es_no_op(admin_director_client, proyecto):
    """La primera columna (orden=0) no puede subir más — no debe fallar,
    devuelve sin_cambio=True."""
    cerramiento = ColumnaConfigurable.objects.get(
        proyecto=proyecto, capitulo=ColumnaConfigurable.CAPITULO_OBRA_CIVIL, clave='cerramiento',
    )
    url = reverse('construccion:columna_reordenar', kwargs={'proyecto_id': proyecto.id, 'columna_id': cerramiento.id})
    resp = admin_director_client.post(url, {'direccion': 'up'})
    assert resp.status_code == 200
    assert resp.json().get('sin_cambio') is True

    cerramiento.refresh_from_db()
    assert cerramiento.orden == 0


# ==============================================================================
# 5) Role-gated — admin/director pasan; un rol operario REAL de construccion
#    (operario_construccion, NIVEL_OPERARIO en RBAC v2, con acceso al módulo
#    CONSTRUCCION) NO (403).
#
# IMPORTANTE (hallazgo durante B3): `RoleRequiredMixin.test_func` tiene un
# bypass de RBAC v2 — CUALQUIER rol con `nivel=NIVEL_ADMIN` (ver
# apps/core/rbac_seed_data.py ROL_NIVEL) pasa TODAS las vistas
# `RoleRequiredMixin`, sin importar el `allowed_roles` legacy que declaren
# — 'coordinador' es NIVEL_ADMIN en RBAC v2 (aunque no está en la lista
# literal `['admin','director']` de B6), así que SÍ pasa (sección positiva
# abajo, no es un bug de B6). El test negativo real necesita un rol
# NIVEL_OPERARIO con acceso al módulo CONSTRUCCION — 'liniero' NO tiene
# acceso al módulo CONSTRUCCION en el seed RBAC (queda redirigido 302 por
# el middleware ANTES de llegar a la vista, no es un 403 de esta vista) —
# se usa 'operario_construccion' (NIVEL_OPERARIO, módulo CONSTRUCCION sí)
# para que el 403 sea el de RoleRequiredMixin.allowed_roles de B6, no un
# 302 del middleware de módulo (ver
# feedback_validar_role_gated_con_rol_real_no_superuser: nunca con
# superuser, que pasa todo y produce falso positivo).
# ==============================================================================

@pytest.fixture
def operario_construccion_client(client, user_password, django_user_model):
    user = django_user_model.objects.create_user(
        email='operario_b6@test.com', password=user_password,
        first_name='Operario', last_name='Construccion', rol='operario_construccion',
    )
    client.login(username=user.email, password=user_password)
    return client


@pytest.mark.django_db
def test_columnas_configurables_operario_construccion_403(operario_construccion_client, proyecto):
    """'operario_construccion' SÍ tiene acceso al módulo CONSTRUCCION (pasa
    el middleware RBAC) pero es NIVEL_OPERARIO (no bypassea vía
    user_es_admin) y no está en el allowed_roles angosto de B6 — 403
    genuino de RoleRequiredMixin."""
    url = reverse('construccion:columnas_configurables', kwargs={'proyecto_id': proyecto.id})
    resp = operario_construccion_client.get(url)
    assert resp.status_code == 403


@pytest.mark.django_db
def test_columnas_configurables_coordinador_pasa_via_rbac_v2_nivel_admin(
    client, coordinador_user, user_password, proyecto,
):
    """Positivo documentado (NO es un bug de B6): 'coordinador' es
    NIVEL_ADMIN en RBAC v2 (rbac_seed_data.py) y por tanto bypassea
    CUALQUIER allowed_roles legacy vía RoleRequiredMixin.test_func →
    user_es_admin(). B6 no puede restringir por debajo del nivel RBAC v2
    con el mecanismo legacy — documentado acá para que no se confunda con
    un hueco de seguridad."""
    client.login(username=coordinador_user.email, password=user_password)
    url = reverse('construccion:columnas_configurables', kwargs={'proyecto_id': proyecto.id})
    resp = client.get(url)
    assert resp.status_code == 200


@pytest.mark.django_db
def test_columnas_configurables_director_200(admin_director_client, proyecto):
    """Sanity positivo: 'director' SÍ está en el allowed_roles angosto."""
    url = reverse('construccion:columnas_configurables', kwargs={'proyecto_id': proyecto.id})
    resp = admin_director_client.get(url)
    assert resp.status_code == 200


@pytest.mark.django_db
def test_columna_toggle_operario_construccion_403(operario_construccion_client, proyecto):
    columna = ColumnaConfigurable.objects.get(
        proyecto=proyecto, capitulo=ColumnaConfigurable.CAPITULO_OBRA_CIVIL, clave='cerramiento',
    )
    url = reverse('construccion:columna_toggle', kwargs={'proyecto_id': proyecto.id, 'columna_id': columna.id})
    resp = operario_construccion_client.post(url, {'activa': '0'})
    assert resp.status_code == 403
    columna.refresh_from_db()
    assert columna.activa is True, "El toggle NO debió aplicarse — el usuario no tiene rol."
