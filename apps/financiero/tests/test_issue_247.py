"""Discoverability de Homologación Projects → Contabilidad (#247, reproceso #2).

Causa raíz confirmada por F2 (2026-09-22): NO es un bug funcional ni RBAC — el
módulo (financiero:carga_financiera) ya funciona y ya tiene el permiso correcto.
Lo que faltaba es "discoverability":

1. El cliente adivinó la URL `/financiero/maestros/homologacion/` por analogía
   con otros maestros (Clientes/Proveedores, que sí viven bajo Parametrización)
   — esa URL nunca existió (404 real confirmado en vivo).
2. El link real (`financiero:carga_financiera`) sólo vivía dentro del acordeón
   "Financiero" (colapsado por defecto) y NUNCA bajo Parametrización→Maestros,
   que es donde el cliente lo buscó.

Este test cubre exactamente esos 2 gaps, y valida el segundo contra RBAC del
rol `contador` (#248, sembrado en prod por migraciones core 0008/0009 —
RunPython, dato "legacy" real, no inventado para este test). La suite local
corre con `--nomigrations` (pyproject.toml), que salta esas migraciones de
datos, así que se reproduce acá EXACTAMENTE lo que 0008/0009 siembran en prod
-- mismo patrón que `test_issue_248_gastos_v1.py::
test_rol_contador_ve_menu_gestiona_rol_sin_permiso_no_ve`.
"""

import pytest
from django.core.cache import cache

from apps.core.models import Role, RoleModuloPermiso


def _sembrar_contador_fin_homologacion():
    """Reproduce EXACTAMENTE lo que siembran en prod las migraciones core
    0008 (crea el rol `contador`, ver_editar sobre FIN_HOMOLOGACION incluido
    -- está en SUBMODULOS_FINANCIERO) y 0009 (fila de módulo completo
    `MANTENIMIENTO` que `{% puede_acceder 'MANTENIMIENTO' as ok_mant %}`
    exige para que el sidebar muestre el bloque Financiero)."""
    role_contador, _ = Role.objects.get_or_create(
        codigo='contador', defaults={'nombre': 'Contador', 'nivel': 'operario'}
    )
    RoleModuloPermiso.objects.update_or_create(
        role=role_contador,
        modulo='MANTENIMIENTO',
        submodulo='FIN_HOMOLOGACION',
        defaults={'nivel_acceso': 'ver_editar'},
    )
    RoleModuloPermiso.objects.update_or_create(
        role=role_contador,
        modulo='MANTENIMIENTO',
        submodulo='',
        defaults={'nivel_acceso': 'ver_editar'},
    )
    cache.clear()
    return role_contador


@pytest.mark.django_db
def test_url_adivinada_redirige_a_carga_financiera(client, admin_user):
    """La URL que el cliente adivinó ya no da 404: redirige a la real."""
    client.force_login(admin_user)
    respuesta = client.get('/financiero/maestros/homologacion/')
    assert respuesta.status_code == 302
    assert respuesta.url == '/financiero/carga-financiera/'
    # Sigue el redirect: la pantalla real responde 200 (no quedó roto detrás).
    seguimiento = client.get('/financiero/maestros/homologacion/', follow=True)
    assert seguimiento.status_code == 200


@pytest.mark.django_db
def test_url_adivinada_preserva_querystring(client, admin_user):
    """RedirectView(query_string=True) — mismo patrón que presupuesto-planeado/."""
    client.force_login(admin_user)
    respuesta = client.get('/financiero/maestros/homologacion/?anio=2026&mes=1')
    assert respuesta.status_code == 302
    assert respuesta.url == '/financiero/carga-financiera/?anio=2026&mes=1'


@pytest.mark.django_db
def test_entrada_visible_bajo_parametrizacion_para_admin(client, admin_user):
    """La entrada aparece DOS veces: la original (Financiero) + la nueva
    duplicada bajo Parametrización→Maestros — mismo <li>, mismo href, mismo
    gate `ok_fin_homologacion`, dos ubicaciones para cubrir ambos patrones
    mentales del cliente."""
    client.force_login(admin_user)
    # '/' (core:home) en vez de '/financiero/': el dashboard financiero usa
    # `allowed_roles` legacy propio (no relevante acá) pero SIEMPRE extiende
    # base.html -> sidebar completo, igual que cualquier pantalla autenticada.
    respuesta = client.get('/')
    assert respuesta.status_code == 200
    html = respuesta.content.decode()
    assert html.count('Homologación Projects → Contabilidad') == 2
    # El href real (carga-financiera) debe aparecer al menos 2 veces: una por
    # cada <li> del sidebar que apunta al módulo.
    assert html.count('/financiero/carga-financiera/') >= 2


@pytest.mark.django_db
def test_entrada_visible_para_rol_contador_legacy(client, django_user_model):
    """RBAC real del rol `contador` (#248) — nunca se había smokeado contra
    este rol, y es justo lo que el intento anterior (rebote de hoy) se saltó
    según el F2.

    `contador` SÍ tiene `FIN_HOMOLOGACION=ver_editar` (0008) y SÍ tiene el
    sentinel de módulo completo `MANTENIMIENTO` (0009, necesario para que
    `ok_mant` muestre el bloque "Financiero" completo) — pero NO tiene el
    módulo `CONFIG` completo (0009 sólo cubre `MANTENIMIENTO`). El bloque
    entero "Parametrización" del sidebar está gateado por
    `{% puede_acceder 'CONFIG' as ok_config %}` (línea 641), el MISMO gate
    que ya aplica a Maestro de Clientes/Proveedores. Así que para este rol la
    entrada aparece **una sola vez** (la original, bajo "Financiero") —
    comportamiento correcto e idéntico al de los otros Maestros, no una
    regresión de este fix. `/financiero/` (dashboard) tiene su propio
    `allowed_roles` legacy que NO incluye `contador` (gap ajeno, #248-B1) —
    se usa `/` (core:home, solo LoginRequiredMixin) para aislar el sidebar de
    esa restricción distinta."""
    _sembrar_contador_fin_homologacion()
    contador = django_user_model.objects.create_user(
        email='contador-247@example.test', password='x', rol='contador'
    )
    client.force_login(contador)
    # `contador` sólo tiene sembrado FIN_HOMOLOGACION (no el resto de
    # submódulos Financiero/Actividades) -> HomeView.dispatch (single-módulo,
    # RBAC #44) y actividades:lista pueden redirigir/denegar en cadena para
    # un seed mínimo como este. Se usa directo `/financiero/carga-financiera/`
    # -- la pantalla real a la que apunta el fix, con RBAC granular propio
    # (required_submodulo=FIN_HOMOLOGACION), que SÍ extiende base.html ->
    # mismo sidebar completo.
    respuesta = client.get('/financiero/carga-financiera/')
    assert respuesta.status_code == 200
    html = respuesta.content.decode()
    assert html.count('Homologación Projects → Contabilidad') == 1
    assert html.count('/financiero/carga-financiera/') >= 1

    # Y la URL adivinada también redirige para este rol (no solo para admin) —
    # el redirect es puro RBAC de la vista destino, no depende de ok_config.
    redirect = client.get('/financiero/maestros/homologacion/')
    assert redirect.status_code == 302
    assert redirect.url == '/financiero/carga-financiera/'


@pytest.mark.django_db
def test_rol_sin_permiso_no_ve_la_entrada_duplicada(client, django_user_model):
    """Regla dura del portafolio (scoping): un rol SIN el submódulo
    FIN_HOMOLOGACION no debe ver ninguna de las 2 entradas. Default
    `operario_general` no tiene fila en role_modulo_permisos para
    FIN_HOMOLOGACION (ni bajo `--nomigrations` ni en prod)."""
    operario = django_user_model.objects.create_user(
        email='operario-247@example.test', password='x', rol='operario_general'
    )
    client.force_login(operario)
    respuesta = client.get('/')
    assert respuesta.status_code == 200
    html = respuesta.content.decode()
    assert 'Homologación Projects' not in html
