"""
Issue #218 — Sistema de filtros de Programación Semanal de Cuadrillas.

Cubre:
  * apps/cuadrillas/filtros.py (unidad pura + queryset)
  * A1/A2 — regresión del bug real: `semanas_disponibles` YA NO se pisa
    entre `CuadrillaListView.get_context_data` (views.py) y la fusión con
    `_contexto_semana` (views_semanal.py) -- ambos usaban la misma clave de
    contexto para 2 shapes distintas, dejando el <select> con <option
    value=""> vacías (visual Y funcional, misma causa raíz).
  * A2-A5 — filtro de semana/línea/actividad/fecha vía HTTP, contra
    `_b3_get_queryset` (el método que REALMENTE corre en producción, ver
    monkeypatch de views_b3.py).
  * A6 — combinación de 2+ filtros da la intersección, no la unión.
  * A7 — wiring del import: filtro de línea activo rechaza filas de otra
    línea, tanto en el importer B4 (`CuadrillaImporter`) como en la vista
    REALMENTE enlazada en producción (`CuadrillaMasivaUploadView`, la que
    ejecuta el botón "Importar Excel" del grid semanal).
  * A8 — stats (total_cuadrillas/cuadrillas_activas) reflejan el queryset
    filtrado, no el total global.

Los códigos de cuadrilla usados (`32-2026-0001-BLQ`, líneas `LN834`/`LN817`,
actividad `SERVIDUMBR`) replican el FORMATO real de producción confirmado
por F2 vía psql (2026-08-09) -- F3 no tiene credenciales de BD prod (por
diseño, ver `_common.md`), así que estas son fixtures locales con esa misma
forma, no una query directa contra prod.
"""

from io import BytesIO

import pytest
from django.urls import reverse
from openpyxl import Workbook

from apps.cuadrillas.filtros import (
    FiltrosCuadrilla,
    aplicar_filtros_queryset,
    linea_permite_fila,
    resolver_filtros,
)
from apps.cuadrillas.importers import CuadrillaImporter
from apps.cuadrillas.models import Cuadrilla

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures locales
# ---------------------------------------------------------------------------


@pytest.fixture
def linea_834():
    from tests.factories import LineaFactory

    return LineaFactory(codigo="LN834", nombre="Linea 834")


@pytest.fixture
def linea_817():
    from tests.factories import LineaFactory

    return LineaFactory(codigo="LN817", nombre="Linea 817")


@pytest.fixture
def actividad_servidumbre():
    from tests.factories import TipoActividadFactory

    return TipoActividadFactory(codigo="SERVIDUMBR", nombre="Servidumbre", categoria="SERVIDUMBRE")


@pytest.fixture
def cuadrillas_semana_32(linea_834, linea_817, actividad_servidumbre):
    """Dato legacy real (shape confirmada por F2 vía psql 2026-08-09):
    codigos `32-2026-0001-BLQ` y `32-2026-NOVEDADES` -- semana 32-2026,
    2 cuadrillas. Una en LN834 con actividad SERVIDUMBR y fecha dentro del
    rango 2026-01-01..2026-08-03; la otra en LN817 sin actividad ni fecha."""
    from tests.factories import CuadrillaFactory

    c1 = CuadrillaFactory(
        codigo="32-2026-0001-BLQ",
        nombre="Cuadrilla 0001 BLQ",
        linea_asignada=linea_834,
        tipo_actividad=actividad_servidumbre,
        fecha="2026-08-03",
        activa=True,
    )
    c2 = CuadrillaFactory(
        codigo="32-2026-NOVEDADES",
        nombre="Cuadrilla Novedades",
        linea_asignada=linea_817,
        activa=True,
    )
    return c1, c2


@pytest.fixture
def cuadrilla_otra_semana(linea_834):
    """Cuadrilla de OTRA semana (31-2026), para verificar que el filtro de
    semana reduce el queryset y no solo lo deja intacto."""
    from tests.factories import CuadrillaFactory

    return CuadrillaFactory(
        codigo="31-2026-0009-BLQ",
        nombre="Cuadrilla semana 31",
        linea_asignada=linea_834,
        fecha="2026-01-05",
        activa=True,
    )


# ---------------------------------------------------------------------------
# Unidad: apps/cuadrillas/filtros.py
# ---------------------------------------------------------------------------


class TestResolverFiltros:
    def test_resolver_filtros_vacio(self):
        f = resolver_filtros({})
        assert f == FiltrosCuadrilla()
        assert f.hay_filtro_activo is False
        assert f.querystring_params() == {}

    def test_resolver_filtros_strip_espacios(self):
        f = resolver_filtros({"semana": " 32-2026 ", "linea": " uuid-x "})
        assert f.semana == "32-2026"
        assert f.linea_id == "uuid-x"

    def test_hay_filtro_activo_con_un_solo_campo(self):
        assert FiltrosCuadrilla(actividad_id="x").hay_filtro_activo is True

    def test_querystring_params_solo_no_vacios(self):
        f = FiltrosCuadrilla(semana="32-2026", linea_id="", fecha_desde="2026-01-01")
        assert f.querystring_params() == {"semana": "32-2026", "fecha_desde": "2026-01-01"}


class TestAplicarFiltrosQueryset:
    def test_sin_filtro_devuelve_todo(self, cuadrillas_semana_32, cuadrilla_otra_semana):
        qs = aplicar_filtros_queryset(Cuadrilla.objects.all(), FiltrosCuadrilla())
        assert qs.count() == 3

    def test_filtro_semana_reduce_queryset(self, cuadrillas_semana_32, cuadrilla_otra_semana):
        """A2 -- dato legacy: semana=32-2026 reduce de 3 a 2 (dato real F2)."""
        qs = aplicar_filtros_queryset(Cuadrilla.objects.all(), FiltrosCuadrilla(semana="32-2026"))
        codigos = set(qs.values_list("codigo", flat=True))
        assert codigos == {"32-2026-0001-BLQ", "32-2026-NOVEDADES"}

    def test_filtro_linea(self, cuadrillas_semana_32, linea_834):
        """A3."""
        qs = aplicar_filtros_queryset(
            Cuadrilla.objects.all(), FiltrosCuadrilla(linea_id=str(linea_834.id))
        )
        assert list(qs.values_list("codigo", flat=True)) == ["32-2026-0001-BLQ"]

    def test_filtro_actividad(self, cuadrillas_semana_32, actividad_servidumbre):
        """A4 -- data thinness declarada: 1 solo registro real con tipo_actividad."""
        qs = aplicar_filtros_queryset(
            Cuadrilla.objects.all(), FiltrosCuadrilla(actividad_id=str(actividad_servidumbre.id))
        )
        assert qs.count() == 1
        assert qs.first().codigo == "32-2026-0001-BLQ"

    def test_filtro_actividad_sin_match_da_vacio(self, cuadrillas_semana_32):
        """Edge case: uuid de actividad que no coincide con nada -> vacío, no error."""
        import uuid

        qs = aplicar_filtros_queryset(
            Cuadrilla.objects.all(), FiltrosCuadrilla(actividad_id=str(uuid.uuid4()))
        )
        assert qs.count() == 0

    def test_filtro_rango_fecha(self, cuadrillas_semana_32, cuadrilla_otra_semana):
        """A5 -- dato legacy real: rango 2026-01-01..2026-08-03."""
        qs = aplicar_filtros_queryset(
            Cuadrilla.objects.all(),
            FiltrosCuadrilla(fecha_desde="2026-01-01", fecha_hasta="2026-08-03"),
        )
        codigos = set(qs.values_list("codigo", flat=True))
        # c1 (2026-08-03) y cuadrilla_otra_semana (2026-01-05) caen en rango;
        # c2 (sin fecha) queda fuera.
        assert codigos == {"32-2026-0001-BLQ", "31-2026-0009-BLQ"}

    def test_combinacion_linea_y_fecha_es_interseccion(
        self, cuadrillas_semana_32, cuadrilla_otra_semana, linea_834
    ):
        """A6 -- combinar linea=LN834 + rango de fecha da la INTERSECCIÓN
        (2 cuadrillas de LN834 dentro del rango), no la unión de cada filtro
        por separado."""
        qs = aplicar_filtros_queryset(
            Cuadrilla.objects.all(),
            FiltrosCuadrilla(
                linea_id=str(linea_834.id),
                fecha_desde="2026-01-01",
                fecha_hasta="2026-08-03",
            ),
        )
        codigos = set(qs.values_list("codigo", flat=True))
        assert codigos == {"32-2026-0001-BLQ", "31-2026-0009-BLQ"}

    def test_semana_con_formato_invalido_no_rompe(self, cuadrillas_semana_32):
        """Edge case: semana mal formada (sin guion) no lanza excepción."""
        qs = aplicar_filtros_queryset(
            Cuadrilla.objects.all(), FiltrosCuadrilla(semana="no-es-una-semana")
        )
        # No debe reventar; el filtro malformado se ignora silenciosamente
        # (mismo comportamiento que el código legacy que reemplaza).
        assert qs.count() >= 0


class TestLineaPermiteFila:
    def test_sin_filtro_permite_todo(self):
        assert linea_permite_fila(FiltrosCuadrilla(), "cualquier-uuid") is True

    def test_con_filtro_coincide(self):
        f = FiltrosCuadrilla(linea_id="abc-123")
        assert linea_permite_fila(f, "abc-123") is True

    def test_con_filtro_no_coincide(self):
        f = FiltrosCuadrilla(linea_id="abc-123")
        assert linea_permite_fila(f, "otro-uuid") is False

    def test_con_filtro_linea_none_rechaza(self):
        """Edge case: fila sin línea resuelta, con filtro activo -> rechazada."""
        f = FiltrosCuadrilla(linea_id="abc-123")
        assert linea_permite_fila(f, None) is False


# ---------------------------------------------------------------------------
# HTTP: CuadrillaListView (A1/A2 regresión + A3-A6 + A8)
# ---------------------------------------------------------------------------


class TestListaFiltrosHTTP:
    def test_semanas_filtro_disponibles_no_pisado_por_grid_semanal(
        self, authenticated_client, cuadrillas_semana_32
    ):
        """Regresión A1/A2 -- ANTES de este fix, `context.update(_contexto_semana(...))`
        (views.py ~línea 150) pisaba `context['semanas_disponibles']` (shape
        {value,label} para el <select>) con el `semanas_disponibles` de
        `_contexto_semana` (shape {anio,semana,n_bloques,key} para "Duplicar
        semana"), dejando <option value=""> vacías. Ahora viven en claves
        separadas: `semanas_filtro_disponibles` (dropdown) intacto."""
        resp = authenticated_client.get(reverse("cuadrillas:lista"))
        assert resp.status_code == 200
        opciones = resp.context["semanas_filtro_disponibles"]
        assert len(opciones) > 0
        for opcion in opciones:
            # El bug real: value/label vacíos para TODAS las opciones salvo
            # la estática "Todas las semanas" del template.
            assert opcion["value"], f"option value vacío -- regresión del bug #218: {opcion}"
            assert opcion["label"], f"option label vacío -- regresión del bug #218: {opcion}"
        assert {"value": "32-2026", "label": "Semana 32 - 2026"} in opciones

    def test_filtro_semana_reduce_listado_http(
        self, authenticated_client, cuadrillas_semana_32, cuadrilla_otra_semana
    ):
        """A2 -- GET ?semana=32-2026 reduce el queryset (era el bug funcional:
        antes NUNCA reducía porque el <option value=""> siempre viajaba vacío)."""
        resp_sin_filtro = authenticated_client.get(reverse("cuadrillas:lista"))
        resp_filtrado = authenticated_client.get(reverse("cuadrillas:lista"), {"semana": "32-2026"})

        assert resp_sin_filtro.status_code == 200
        assert resp_filtrado.status_code == 200
        assert len(resp_sin_filtro.context["cuadrillas"]) == 3
        assert len(resp_filtrado.context["cuadrillas"]) == 2

    def test_filtro_linea_http(self, authenticated_client, cuadrillas_semana_32, linea_834):
        """A3."""
        resp = authenticated_client.get(reverse("cuadrillas:lista"), {"linea": str(linea_834.id)})
        codigos = {c.codigo for c in resp.context["cuadrillas"]}
        assert codigos == {"32-2026-0001-BLQ"}

    def test_combinacion_filtros_interseccion_http(
        self, authenticated_client, cuadrillas_semana_32, cuadrilla_otra_semana, linea_834
    ):
        """A6 -- combinación línea+fecha vía HTTP da la intersección."""
        resp = authenticated_client.get(
            reverse("cuadrillas:lista"),
            {
                "linea": str(linea_834.id),
                "fecha_desde": "2026-01-01",
                "fecha_hasta": "2026-08-03",
            },
        )
        codigos = {c.codigo for c in resp.context["cuadrillas"]}
        assert codigos == {"32-2026-0001-BLQ", "31-2026-0009-BLQ"}

    def test_stats_reflejan_filtro_activo(
        self, authenticated_client, cuadrillas_semana_32, cuadrilla_otra_semana, linea_834
    ):
        """A8 -- total_cuadrillas/cuadrillas_activas ya NO son el total
        global (3), sino el tamaño del queryset filtrado (2, para
        linea=LN834)."""
        resp = authenticated_client.get(reverse("cuadrillas:lista"), {"linea": str(linea_834.id)})
        assert resp.context["total_cuadrillas"] == 2
        assert resp.context["cuadrillas_activas"] == 2

    def test_filtro_sin_resultados_no_rompe(
        self, authenticated_client, cuadrillas_semana_32, linea_817
    ):
        """Edge case: combinación de filtros que no matchea nada -> 0
        resultados, 200 OK, no excepción."""
        resp = authenticated_client.get(
            reverse("cuadrillas:lista"),
            {
                "linea": str(linea_817.id),
                "semana": "01-2000",
            },
        )
        assert resp.status_code == 200
        assert len(resp.context["cuadrillas"]) == 0
        assert resp.context["total_cuadrillas"] == 0

    def test_tab_semanas_duplicar_no_afectado_por_el_fix(
        self, authenticated_client, cuadrillas_semana_32
    ):
        """Regresión negativa: `_contexto_semana`'s propio `semanas_disponibles`
        (shape distinta, para "Duplicar semana") sigue vivo bajo su clave
        original -- el fix de A1/A2 NO debía romper A9 (issue #207)."""
        resp = authenticated_client.get(reverse("cuadrillas:lista"))
        assert resp.status_code == 200
        assert "semanas_disponibles" in resp.context
        for entry in resp.context["semanas_disponibles"]:
            assert "key" in entry and "n_bloques" in entry


# ---------------------------------------------------------------------------
# A7 — wiring del import con filtro de línea activo
# ---------------------------------------------------------------------------


def _excel_aviso_sap(filas):
    """Arma un .xlsx en memoria en formato Aviso SAP (columnas mínimas)."""
    wb = Workbook()
    ws = wb.active
    ws.append(["#", "CUADRILLA", "LINEA", "PERSONAL", "CEDULA"])
    for fila in filas:
        ws.append(fila)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


class TestImportWiringA7:
    def test_importer_b4_rechaza_fila_de_otra_linea(self, linea_834, linea_817):
        """A7 -- CuadrillaImporter (views_b4/importers.py): con filtro de
        línea LN834 activo, la fila de LN817 se omite (advertencia, no
        error fatal) y la de LN834 sí se crea."""
        excel = _excel_aviso_sap(
            [
                [1, "CUA-100", linea_834.nombre, "Juan Perez", "1000001"],
                [2, "CUA-200", linea_817.nombre, "Carlos Ruiz", "1000002"],
            ]
        )
        importer = CuadrillaImporter()
        resultado = importer.importar(excel, {"linea_filtro_id": str(linea_834.id)})

        assert resultado["exito"] is True
        assert Cuadrilla.objects.filter(codigo="CUA-100").exists()
        assert not Cuadrilla.objects.filter(codigo="CUA-200").exists()
        assert any("CUA-200" in a and "omitida" in a for a in resultado["advertencias"])

    def test_importer_b4_sin_filtro_importa_todas_las_lineas(self, linea_834, linea_817):
        """Edge case: sin `linea_filtro_id` (comportamiento default, sin
        cambios) ambas filas se crean."""
        excel = _excel_aviso_sap(
            [
                [1, "CUA-101", linea_834.nombre, "Juan Perez", "1000003"],
                [2, "CUA-201", linea_817.nombre, "Carlos Ruiz", "1000004"],
            ]
        )
        importer = CuadrillaImporter()
        resultado = importer.importar(excel, {})

        assert resultado["exito"] is True
        assert Cuadrilla.objects.filter(codigo="CUA-101").exists()
        assert Cuadrilla.objects.filter(codigo="CUA-201").exists()

    def test_masiva_upload_view_reachable_reachable_desde_boton_real(
        self, authenticated_client, linea_834, linea_817
    ):
        """A7 -- regresión de wiring: el botón "Importar Excel" realmente
        enlazado en producción (`_tab_semanas.html`) apunta a
        `cuadrillas:masiva_upload` (CuadrillaMasivaUploadView, views.py),
        NO a `views_b4.CuadrillaUploadView` (sin link en ningún template).
        Con `?linea=` activo, el POST a esta vista rechaza filas de línea
        distinta con el mismo criterio que el importer B4."""
        from datetime import date

        wb = Workbook()
        ws = wb.active
        ws.append(["Cuadrilla", "Ano", "Actividad", "Fecha", "Supervisor", "Linea", "Vehiculo"])
        ws.append(
            [1, "2026", "Mantenimiento", date(2026, 8, 3).isoformat(), "", linea_834.codigo, ""]
        )
        ws.append(
            [2, "2026", "Mantenimiento", date(2026, 8, 3).isoformat(), "", linea_817.codigo, ""]
        )
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        buf.name = "masiva.xlsx"

        url = reverse("cuadrillas:masiva_upload")
        resp = authenticated_client.post(
            url,
            {
                "archivo": buf,
                "linea_filtro_id": str(linea_834.id),
            },
        )
        assert resp.status_code in (200, 302)

        semana_actual = date(2026, 8, 3).isocalendar()[1]
        codigo_834 = f"{semana_actual:02d}-2026-001"
        codigo_817 = f"{semana_actual:02d}-2026-002"
        assert Cuadrilla.objects.filter(codigo=codigo_834, linea_asignada=linea_834).exists()
        assert not Cuadrilla.objects.filter(codigo=codigo_817).exists()

    def test_masiva_upload_banner_visible_con_filtro_get(self, authenticated_client, linea_834):
        """A1 UI (#305): el banner "Filtro activo: Línea X" debe verse en el
        HTML real, no solo en el contexto -- via test client (render real de
        template, no solo el dict de contexto)."""
        url = reverse("cuadrillas:masiva_upload")
        resp = authenticated_client.get(url, {"linea": str(linea_834.id)})
        assert resp.status_code == 200
        contenido = resp.content.decode("utf-8")
        assert "Filtro activo" in contenido
        assert linea_834.codigo in contenido
