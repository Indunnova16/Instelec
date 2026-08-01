"""Issue #187 — Mantenimiento: navbar mas completo (Programacion Semanal y
Vanos sin acceso directo) + freeze rows/columns.

Cubre los 2 sub-pedidos implementados en modo --no-deploy (F1-F3, sin
comentario/cierre de issue -- eso queda fuera de este RUN):

1. Accesos directos nuevos en el sidebar de Mantenimiento (rama NO
   ``request.user.is_campo``), siguiendo la spec final confirmada por
   Alcides en los comentarios del issue (reemplaza cualquier ambiguedad de
   comentarios anteriores):
   - "Actividades" gana "Programacion Semanal" (renombrado desde el link
     plano "Cuadrillas", MISMA url ``cuadrillas:lista`` -- confirmado por
     Alcides: la pantalla "Cuadrillas - TransMaint" ES, en el uso real,
     la programacion semanal).
   - "Campo" pasa de link plano ("Registros Campo") a submenu con acceso
     directo a "Avances" (pantalla "Avances de Vanos" =
     ``campo:avance_registrar`` -- el hallazgo central del issue, cero
     referencias en el sidebar antes de este fix) y "Anomalia" (renombrado
     desde "Danos" = ``campo:reportar_dano``). "Registros Campo" se
     conserva como 3er item para no retirar acceso existente en silencio.
   - "Procedimientos" nuevo grupo (antes solo en el menu de campo) con 2
     hijos "Guias de Mantenimiento" / "Fichas Tecnicas" -- ambos apuntan
     hoy al mismo ``campo:procedimientos`` porque el modelo `Procedimiento`
     aun no tiene el campo `categoria` que separaria el contenido real
     (issue #24, fuera de alcance de #187 -- no se inventa el campo aca).

2. Freeze de filas/columnas (mismo patron que #183) en las 3 grillas que
   el issue nombra explicitamente:
   - Listado de Colaboradores (``cuadrillas/colaboradores_lista.html``):
     tabla real -> patron identico a #183 (wrapper ``overflow-auto
     max-h-[70vh]`` + ``thead sticky top-0 z-20`` + primera columna
     ``sticky left-0``).
   - Listado de Cuadrillas / "Programacion Semanal" (``cuadrillas/
     lista.html``): NO es una <table> (es un acordeon de tarjetas
     agrupadas por semana) -- se adapta el patron: contenedor con altura
     acotada + overflow-auto real, encabezado de cada grupo de semana
     sticky top-0. No hay "primera columna" que congelar (no es tabular).
   - Grilla "Avances de Vanos" (``campo/avance_registrar.html``, seccion
     "Vanos Grid"): tampoco es una <table> (CSS grid de tarjetas por
     vano) -- se adapta igual: contenedor acotado + overflow-auto,
     encabezado "Vanos (N)" sticky top-0.

Nota de colision con #201: el checkout principal (sucio, fuera de este
worktree) tiene trabajo en curso sobre este MISMO archivo
``templates/components/sidebar.html`` (unificacion Lista Operativa /
Programacion Mensual). Este worktree partio de ``origin/main`` limpio, asi
que los cambios de #187 y #201 van a requerir reconciliacion manual al
momento del merge real -- fuera de alcance de este RUN.

Ejecutar con:
    pytest tests/unit/test_issue_187_navbar_freeze.py -v
"""

import pytest
from django.urls import reverse

from apps.lineas.models import Vano

# ==============================================================================
# 1. Sidebar -- accesos directos nuevos
# ==============================================================================

# (url_name, label visible en el sidebar)
SIDEBAR_LINKS_NUEVOS_187 = [
    ("cuadrillas:lista", "Programacion Semanal"),
    ("campo:avance_registrar", "Avances"),
    ("campo:reportar_dano", "Anomalia"),
    ("campo:procedimientos", "Guias de Mantenimiento"),
    ("campo:procedimientos", "Fichas Tecnicas"),
]


@pytest.mark.django_db
class TestSidebarUrlsNuevas187:
    """Las urls que el sidebar referencia para #187 existen y resuelven."""

    @pytest.mark.parametrize("url_name,_label", SIDEBAR_LINKS_NUEVOS_187)
    def test_url_resuelve(self, url_name, _label):
        url = reverse(url_name)
        assert url, f"{url_name} no resuelve"

    def test_urls_actividades_siguen_resolviendo(self):
        """Programacion Mensual / Lista Operativa / Calendario -- sin cambio."""
        for name in ["actividades:programacion", "actividades:lista", "actividades:calendario"]:
            assert reverse(name)


@pytest.mark.django_db
class TestSidebarRenderMantenimiento187:
    """El sidebar de Mantenimiento (rama administrativos) expone los accesos
    directos nuevos del issue #187."""

    def _render_sidebar(self, authenticated_client):
        """core:home usa base.html -> incluye templates/components/sidebar.html."""
        resp = authenticated_client.get(reverse("core:home"))
        assert resp.status_code == 200, f"render de core:home fallo: {resp.status_code}"
        return resp.content.decode("utf-8")

    @pytest.mark.parametrize("url_name,label", SIDEBAR_LINKS_NUEVOS_187)
    def test_sidebar_tiene_labels_nuevos(self, url_name, label, authenticated_client):
        body = self._render_sidebar(authenticated_client)
        assert label in body, f"Falta el label {label!r} en el sidebar (issue #187)"

    def test_sidebar_ya_no_tiene_link_plano_cuadrillas(self, authenticated_client):
        """El item de menu plano "Cuadrillas" (top-level, fuera del submenu
        Actividades) desaparece -- se renombra a "Programacion Semanal"
        dentro de "Actividades" (spec confirmada por Alcides)."""
        body = self._render_sidebar(authenticated_client)
        assert ">Cuadrillas<" not in body, (
            "El link plano 'Cuadrillas' sigue presente; debia renombrarse a "
            "'Programacion Semanal' dentro del submenu Actividades (issue #187)"
        )

    def test_sidebar_conserva_registros_campo(self, authenticated_client):
        """'Registros Campo' se preserva dentro del nuevo submenu Campo (no
        se retira acceso existente en silencio, aunque la spec final del
        cliente solo declaro Avances + Anomalia explicitamente)."""
        body = self._render_sidebar(authenticated_client)
        assert "Registros Campo" in body

    def test_sidebar_campo_es_submenu_expandible(self, authenticated_client):
        """'Campo' ahora es un boton de submenu (aria-label), no un <a> plano."""
        body = self._render_sidebar(authenticated_client)
        assert 'aria-label="Submenu Campo"' in body

    def test_sidebar_procedimientos_es_submenu_expandible(self, authenticated_client):
        body = self._render_sidebar(authenticated_client)
        assert 'aria-label="Submenu Procedimientos"' in body

    def test_sidebar_actividades_submenu_orden(self, authenticated_client):
        """Programacion Semanal queda entre Programacion Mensual y Lista
        Operativa, dentro del submenu Actividades (orden de la spec)."""
        body = self._render_sidebar(authenticated_client)
        submenu_start = body.index('aria-label="Submenu Actividades"')
        submenu_html = body[submenu_start : submenu_start + 2000]
        assert "Programacion Mensual" in submenu_html
        assert "Programacion Semanal" in submenu_html
        assert "Lista Operativa" in submenu_html
        assert submenu_html.index("Programacion Mensual") < submenu_html.index(
            "Programacion Semanal"
        )
        assert submenu_html.index("Programacion Semanal") < submenu_html.index("Lista Operativa")


# ==============================================================================
# 2. Acceso real (status 200) a las pantallas destino de los links nuevos
# ==============================================================================


@pytest.mark.django_db
class TestAccesoUrlsNuevas187:
    """Los links nuevos del navbar apuntan a URLs que responden 200 para un
    usuario autenticado con permisos (admin)."""

    def test_programacion_semanal_200(self, authenticated_client):
        resp = authenticated_client.get(reverse("cuadrillas:lista"))
        assert resp.status_code == 200

    def test_avances_de_vanos_sin_linea_200(self, authenticated_client):
        """Avances de Vanos sin ?linea_id= muestra el selector de lineas."""
        resp = authenticated_client.get(reverse("campo:avance_registrar"))
        assert resp.status_code == 200
        assert "Avances de Vanos" in resp.content.decode("utf-8")

    def test_avances_de_vanos_con_linea_200(self, authenticated_client, linea):
        Vano.objects.create(linea=linea, numero="1")
        Vano.objects.create(linea=linea, numero="2")
        resp = authenticated_client.get(
            reverse("campo:avance_registrar"), {"linea_id": str(linea.id)}
        )
        assert resp.status_code == 200
        body = resp.content.decode("utf-8")
        assert "Vano 1" in body
        assert "Vano 2" in body

    def test_anomalia_reportar_dano_200(self, authenticated_client):
        resp = authenticated_client.get(reverse("campo:reportar_dano"))
        assert resp.status_code == 200

    def test_procedimientos_200(self, authenticated_client):
        resp = authenticated_client.get(reverse("campo:procedimientos"))
        assert resp.status_code == 200

    def test_registros_campo_200(self, authenticated_client):
        """El 3er item preservado del submenu Campo tambien responde 200."""
        resp = authenticated_client.get(reverse("campo:lista"))
        assert resp.status_code == 200


# ==============================================================================
# 3. Freeze rows/columns
# ==============================================================================


@pytest.mark.django_db
class TestFreezeColaboradores187:
    """Listado de Colaboradores: tabla real -> patron identico a #183."""

    def test_wrapper_altura_acotada_y_overflow_auto(self, authenticated_client):
        resp = authenticated_client.get(reverse("cuadrillas:colaboradores_lista"))
        assert resp.status_code == 200
        body = resp.content.decode("utf-8")
        assert "overflow-auto max-h-[70vh]" in body

    def test_thead_sticky(self, authenticated_client):
        resp = authenticated_client.get(reverse("cuadrillas:colaboradores_lista"))
        body = resp.content.decode("utf-8")
        assert "sticky top-0 z-20" in body

    def test_primera_columna_sticky(self, authenticated_client):
        """El <td> de la primera columna solo se renderiza si hay >=1 fila --
        se necesita >=1 PersonalCuadrilla real (rol_cuadrilla FK Cargo PROTECT,
        default 'LINIERO_I' -- se siembra igual que test_issue_186_m4_area.py)."""
        from apps.cuadrillas.models import Cargo
        from apps.cuadrillas.models_base import PersonalCuadrilla

        Cargo.objects.get_or_create(
            codigo="LINIERO_I", defaults={"nombre": "Liniero I", "activo": True}
        )
        PersonalCuadrilla.objects.create(
            nombre="Colaborador Freeze 187",
            documento="qa-e2e-187-freeze",
        )

        resp = authenticated_client.get(reverse("cuadrillas:colaboradores_lista"))
        body = resp.content.decode("utf-8")
        assert "sticky left-0 bg-gray-50 dark:bg-gray-900 z-10" in body, (
            "Falta sticky left-0 en el <th> de la columna Nombre"
        )
        assert "sticky left-0 bg-white dark:bg-gray-800 z-10" in body, (
            "Falta sticky left-0 en los <td> de la columna Nombre"
        )


@pytest.mark.django_db
class TestFreezeCuadrillasLista187:
    """Programacion Semanal / Listado de Cuadrillas: acordeon (no tabla) --
    freeze adaptado (contenedor acotado + header de semana sticky)."""

    def test_wrapper_altura_acotada_y_overflow_auto(self, authenticated_client, cuadrilla):
        resp = authenticated_client.get(reverse("cuadrillas:lista"))
        assert resp.status_code == 200
        body = resp.content.decode("utf-8")
        assert "overflow-auto max-h-[70vh]" in body

    def test_header_de_semana_sticky(self, authenticated_client, cuadrilla):
        resp = authenticated_client.get(reverse("cuadrillas:lista"))
        body = resp.content.decode("utf-8")
        assert "sticky top-0 z-10" in body
        # La cuadrilla de la fixture debe aparecer en el listado renderizado.
        assert cuadrilla.codigo in body


@pytest.mark.django_db
class TestFreezeVanosGrid187:
    """Grilla de Avances de Vanos: CSS grid de tarjetas (no tabla) -- freeze
    adaptado (contenedor acotado + encabezado 'Vanos (N)' sticky)."""

    def test_wrapper_y_header_sticky(self, authenticated_client, linea):
        Vano.objects.create(linea=linea, numero="1")
        Vano.objects.create(linea=linea, numero="2")
        Vano.objects.create(linea=linea, numero="3")
        resp = authenticated_client.get(
            reverse("campo:avance_registrar"), {"linea_id": str(linea.id)}
        )
        assert resp.status_code == 200
        body = resp.content.decode("utf-8")
        assert "overflow-auto max-h-[70vh]" in body
        assert "sticky top-0 z-10" in body
        assert "Vanos (3)" in body
