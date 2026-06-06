"""Tests B1.1 — Renombre torres a formato T-{numero} (canónico Sofi #100).

Cubre:
- Happy path: Torre.__str__ retorna "T{numero}" sin variantes
- Edge case 1: codigo_display preserva linea para casos cross-linea
- Edge case 2: numeros multi-digito (T1, T15, T100) sin padding
- Edge case 3: dato legacy (Torre creada antes del rename) sigue renderizando OK
- Edge case 4: PoligonoServidumbre.__str__ usa T{n} también
- Edge case 5: __str__ con números no numéricos ('A-15', 'TX-3') no rompe

Sub-feature: B1.1 (issue #100)
"""

import pytest
from decimal import Decimal

from apps.lineas.models import Linea, Torre, PoligonoServidumbre


@pytest.fixture
def linea(db):
    """Línea base para los tests."""
    return Linea.objects.create(
        codigo="LN-X",
        nombre="Línea X Test",
        cliente="TRANSELCA",
        longitud_km=Decimal("50.00"),
        tension_kv=220,
        activa=True,
    )


@pytest.fixture
def torre(db, linea):
    """Torre base."""
    return Torre.objects.create(
        linea=linea,
        numero="15",
        tipo="SUSPENSION",
        estado="BUENO",
        latitud=Decimal("5.12345678"),
        longitud=Decimal("-75.12345678"),
    )


class TestB11RenderTorresFormatTNumero:
    """B1.1 — formato uniforme T{numero}."""

    def test_b11_render_torres_format_T_numero(self, torre):
        """Happy path: __str__ retorna 'T{numero}' sin "Torre " ni linea."""
        assert str(torre) == "T-15"
        # No debe contener variantes legacy
        assert "Torre " not in str(torre)
        assert " - " not in str(torre)

    def test_b11_codigo_display_preserva_linea(self, torre):
        """codigo_display retiene la línea para casos cross-línea."""
        assert torre.codigo_display == "T-15 (LN-X)"

    def test_b11_numeros_multi_digito_sin_padding(self, db, linea):
        """T1, T15, T100, T999 — todos sin padding ni zeros."""
        casos = [
            ("1", "T-1"),
            ("15", "T-15"),
            ("100", "T-100"),
            ("999", "T-999"),
        ]
        for n, esperado in casos:
            t = Torre.objects.create(
                linea=linea, numero=n, tipo="SUSPENSION", estado="BUENO",
                latitud=Decimal("5.0"), longitud=Decimal("-75.0"),
            )
            assert str(t) == esperado, f"Falló para numero={n}"

    def test_b11_dato_legacy_preservado(self, db, linea):
        """Torre creada antes del rename (sin migration, solo cambio en __str__)
        sigue renderizando T{numero} sobre datos existentes en BD.

        El campo `numero` es CharField; ningún schema cambió en B1.1, solo el
        método __str__. Verificamos que un objeto cargado desde la BD (no
        construido en memoria) también renderiza el nuevo formato."""
        t = Torre.objects.create(
            linea=linea, numero="042", tipo="ANCLAJE", estado="REGULAR",
            latitud=Decimal("6.0"), longitud=Decimal("-74.0"),
        )
        t.refresh_from_db()
        assert str(t) == "T-42"
        # numero original (legacy) preservado intacto
        assert t.numero == "042"

    def test_b11_alfanumerico_no_rompe(self, db, linea):
        """Algunos clientes usan códigos alfanuméricos ('A-15', 'TX-3').
        El __str__ debe aceptarlos sin error."""
        t = Torre.objects.create(
            linea=linea, numero="TX-3", tipo="SUSPENSION", estado="BUENO",
            latitud=Decimal("5.0"), longitud=Decimal("-75.0"),
        )
        assert str(t) == "TX-3"  # prefijo no-torre se preserva como {PREFIJO}-{n}

    def test_b11_poligono_servidumbre_usa_T_numero(self, db, linea, torre):
        """PoligonoServidumbre.__str__ también usa formato T{n}."""
        from django.contrib.gis.geos import Polygon
        poly = Polygon((
            (-75.0, 5.0), (-74.99, 5.0),
            (-74.99, 5.01), (-75.0, 5.01),
            (-75.0, 5.0),
        ), srid=4326)
        p = PoligonoServidumbre.objects.create(
            linea=linea, torre=torre, nombre="Servidumbre Test",
            geometria=poly,
        )
        assert str(p) == "Servidumbre - T-15"
        assert "Torre " not in str(p)

    def test_b11_poligono_sin_torre_no_rompe(self, db, linea):
        """PoligonoServidumbre sin torre asociada usa el nombre."""
        from django.contrib.gis.geos import Polygon
        poly = Polygon((
            (-75.0, 5.0), (-74.99, 5.0),
            (-74.99, 5.01), (-75.0, 5.01),
            (-75.0, 5.0),
        ), srid=4326)
        p = PoligonoServidumbre.objects.create(
            linea=linea, nombre="Solo Linea",
            geometria=poly,
        )
        assert str(p) == "Servidumbre - Solo Linea"


# ============================================================================
# B1.1 — TorreConstruccion y modelos derivados (apps.construccion)
# ============================================================================

@pytest.fixture
def proyecto_construccion_b11(db):
    """Contrato + Proyecto de construcción para los tests B1.1."""
    from apps.contratos.models import Contrato
    from apps.construccion.models import ProyectoConstruccion
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='B11-OC-001',
        nombre='Proyecto B1.1 test',
        cliente='Test',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto B1.1',
        estado='EJECUCION',
    )


class TestB11TorreConstruccionFormatTNumero:
    """B1.1 — TorreConstruccion y __str__ derivados usan T{numero}."""

    def test_b11_torreconstruccion_str_format_T(self, proyecto_construccion_b11):
        """TorreConstruccion.__str__ retorna 'T{numero}' sin proyecto."""
        from apps.construccion.models import TorreConstruccion
        torre = TorreConstruccion.objects.create(
            proyecto=proyecto_construccion_b11, numero="42",
        )
        assert str(torre) == "T-42"
        assert "Torre " not in str(torre)
        assert "(" not in str(torre)  # proyecto NO en __str__ default

    def test_b11_torreconstruccion_codigo_display(self, proyecto_construccion_b11):
        """codigo_display de TorreConstruccion incluye proyecto."""
        from apps.construccion.models import TorreConstruccion
        torre = TorreConstruccion.objects.create(
            proyecto=proyecto_construccion_b11, numero="7",
        )
        # Formato: "T{numero} ({proyecto.nombre})"
        assert torre.codigo_display.startswith("T-7 (")
        assert proyecto_construccion_b11.nombre in torre.codigo_display

    def test_b11_pataobra_str_format_T(self, proyecto_construccion_b11):
        """PataObra.__str__ usa T{numero} (no 'Torre N')."""
        from apps.construccion.models import TorreConstruccion, PataObra
        torre = TorreConstruccion.objects.create(
            proyecto=proyecto_construccion_b11, numero="10",
        )
        pata = PataObra.objects.create(torre=torre, pata="A")
        assert str(pata) == "T-10 - Pata A"
        assert "Torre " not in str(pata)

    def test_b11_dato_legacy_torreconstruccion(self, proyecto_construccion_b11):
        """Torre legacy en BD (sin migration, solo __str__ cambia) renderiza
        nuevo formato tras refresh_from_db."""
        from apps.construccion.models import TorreConstruccion
        torre = TorreConstruccion.objects.create(
            proyecto=proyecto_construccion_b11, numero="LEGACY-99",
        )
        torre.refresh_from_db()
        assert str(torre) == "LEGACY-99"
        assert torre.numero == "LEGACY-99"  # campo intacto

    def test_b11_no_residuos_torre_n_en_construccion_models(self):
        """Guard test: ningún __str__ de modelos B1.1 hace `f"Torre ..."`.
        Si alguien introduce regresión, este test la atrapa."""
        import inspect
        from apps.construccion import models as cmodels
        # Modelos cuyo __str__ debe usar T{numero} tras B1.1
        objetivos = [
            'TorreConstruccion', 'PataObra', 'FaseTorre',
            'SocialPredial', 'AmbientalTorre', 'ControlLluvia',
            'EntregaElectromecanica', 'CorreccionEntrega', 'ObraProteccion',
        ]
        for nombre in objetivos:
            cls = getattr(cmodels, nombre, None)
            if cls is None:
                continue
            src = inspect.getsource(cls.__str__)
            assert 'Torre {' not in src, (
                f"{nombre}.__str__ aún usa formato legacy 'Torre N': {src!r}"
            )
