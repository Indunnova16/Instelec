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

Este test cubre exactamente esos 2 gaps, y valida el segundo contra RBAC real
sembrado por migración (#248: roles `contador`/`gerente_financiero`,
migraciones 0008/0009 — dato "legacy", no un fixture ad-hoc de este test), que
es justo lo que el intento anterior (rebote de hoy) nunca smokeó.
"""

import pytest


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
    """RBAC real sembrado por migración (#248, 0008/0009) — rol `contador`,
    dato PRE-EXISTENTE (no un fixture de este test) — nunca se había smokeado
    contra este rol, y es justo lo que el intento anterior (rebote de hoy)
    se saltó según el F2. `/financiero/` (dashboard) tiene su propio
    `allowed_roles` legacy que NO incluye `contador` (gap ajeno, #248-B1) —
    se usa `/` (core:home, solo LoginRequiredMixin) para aislar el sidebar de
    esa restricción distinta."""
    contador = django_user_model.objects.create_user(
        email='contador-247@example.test', password='x', rol='contador'
    )
    client.force_login(contador)
    respuesta = client.get('/')
    assert respuesta.status_code == 200
    html = respuesta.content.decode()
    assert html.count('Homologación Projects → Contabilidad') == 2
    assert html.count('/financiero/carga-financiera/') >= 2

    # Y el acceso directo a la pantalla real (RBAC granular #248) sigue 200.
    directo = client.get('/financiero/carga-financiera/')
    assert directo.status_code == 200

    # Y la URL adivinada también redirige para este rol (no solo para admin).
    redirect = client.get('/financiero/maestros/homologacion/')
    assert redirect.status_code == 302
    assert redirect.url == '/financiero/carga-financiera/'


@pytest.mark.django_db
def test_rol_sin_permiso_no_ve_la_entrada_duplicada(client, django_user_model):
    """Regla dura del portafolio (scoping): un rol SIN el submódulo
    FIN_HOMOLOGACION no debe ver ninguna de las 2 entradas. Default
    `operario_general` no tiene fila en role_modulo_permisos para
    FIN_HOMOLOGACION."""
    operario = django_user_model.objects.create_user(
        email='operario-247@example.test', password='x', rol='operario_general'
    )
    client.force_login(operario)
    respuesta = client.get('/')
    assert respuesta.status_code == 200
    html = respuesta.content.decode()
    assert 'Homologación Projects' not in html
