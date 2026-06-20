"""
Instelec#120 — La URL vieja del Presupuesto Planeado debe redirigir a la v2.

El cliente seguía aterrizando en la pantalla vieja
(``/financiero/presupuesto-planeado/``, filtros "Unidad de Negocio"/"Contrato")
porque la entrega previa (#126) agregó la v2 (``/financiero/cargar-bd-contable/``)
pero NO retiró ni redirigió la ruta vieja. Estos tests fijan el contrato:

  1. ``GET /financiero/presupuesto-planeado/`` autenticado devuelve 302 hacia
     ``/financiero/cargar-bd-contable/`` (preservando el query string).
  2. La vista destino v2 (``financiero:cargar_bd_contable``) existe y resuelve.
"""
import pytest
from django.urls import resolve, reverse


URL_VIEJA = "/financiero/presupuesto-planeado/"
URL_V2 = "/financiero/cargar-bd-contable/"


def test_url_vieja_resuelve_a_redirectview():
    """La ruta vieja resuelve a un RedirectView apuntando a la v2."""
    match = resolve(URL_VIEJA)
    # RedirectView se instancia como función-vista vía as_view(); su nombre de
    # url debe seguir siendo el mismo para no romper templates/reverse.
    assert match.url_name == "presupuesto_planeado"
    assert match.func.view_class.__name__ == "RedirectView"
    assert match.func.view_initkwargs.get("pattern_name") == "financiero:cargar_bd_contable"


def test_vista_destino_v2_existe():
    """El name destino de la v2 está registrado y reverse-able a la URL esperada."""
    assert reverse("financiero:cargar_bd_contable") == URL_V2


@pytest.mark.django_db
def test_get_url_vieja_redirige_302_a_v2(client, admin_user):
    """GET autenticado a la ruta vieja devuelve 302 hacia la v2 (carga BD contable)."""
    client.force_login(admin_user)

    resp = client.get(URL_VIEJA)
    assert resp.status_code == 302
    assert resp.url.split("?")[0] == URL_V2


@pytest.mark.django_db
def test_redirect_preserva_query_string(client, admin_user):
    """query_string=True: los params del request viejo se preservan en el destino."""
    client.force_login(admin_user)

    resp = client.get(URL_VIEJA + "?proyecto=42&mes=03")
    assert resp.status_code == 302
    assert resp.url.startswith(URL_V2)
    assert "proyecto=42" in resp.url
    assert "mes=03" in resp.url
