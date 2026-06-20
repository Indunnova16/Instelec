"""Tests #154 — Resumen de materiales del proyecto (total + por torre).

Cubre el método de agregación ``ProyectoConstruccion.resumen_materiales()`` y la
vista ``ResumenMaterialesView``. Sin migración (solo lectura/agregación).

Reglas de negocio bajo prueba (PLAN_2026-06-20_resumen_materiales_154.md):
  - Cemento se captura en bultos de 50K → se normaliza a kg multiplicando por 50.
  - Arena/Grava se reportan en cuñetes (NO m³).
  - PataObra aporta agregados m³ (solado, concreto, relleno).
  - Solo torres con ``aplica=True`` entran; agua/madera NO existen → N/D.
  - El Total del proyecto = Σ de las filas por torre.

Edge cases:
  (b) Proyecto sin materiales → estructura vacía/cero sin crash, hay_datos=False.
  (c) Torre con material parcial (solo cemento) → resto en 0, total correcto.
"""

from decimal import Decimal

import pytest

# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def proyecto_i154(db):
    from apps.construccion.models import ProyectoConstruccion
    from apps.contratos.models import Contrato

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo="TEST-I154-001",
        nombre="Contrato test #154",
        cliente="Cliente #154",
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre="Proyecto resumen materiales #154",
        estado="EJECUCION",
    )


def _torre(proyecto, numero, aplica=True):
    from apps.construccion.models import TorreConstruccion

    return TorreConstruccion.objects.create(
        proyecto=proyecto,
        numero=numero,
        aplica=aplica,
    )


def _trincho(proyecto, torre, **materiales):
    from apps.construccion.models import TrinchoCuneta

    return TrinchoCuneta.objects.create(
        proyecto=proyecto,
        torre=torre,
        medida_manejo=TrinchoCuneta.TipoObra.TRINCHO,
        **materiales,
    )


# ===========================================================================
# A1 — resumen_materiales(): agregación por torre + total
# ===========================================================================


@pytest.mark.django_db
def test_cemento_bultos_a_kg_por_50(proyecto_i154):
    """Cemento se captura en bultos de 50K → kg = bultos × 50."""
    t = _torre(proyecto_i154, "E-33")
    _trincho(proyecto_i154, t, cemento=Decimal("10"))  # 10 bultos

    resumen = proyecto_i154.resumen_materiales()
    fila = resumen["torres"][0]
    assert fila["cemento_kg"] == Decimal("500")  # 10 × 50
    assert resumen["total"]["cemento_kg"] == Decimal("500")
    assert resumen["hay_datos"] is True


@pytest.mark.django_db
def test_total_es_suma_de_filas_dos_torres_reales(proyecto_i154):
    """Total del proyecto = Σ de las filas. Dos torres con datos (E-33, E-54)."""
    t33 = _torre(proyecto_i154, "E-33")
    t54 = _torre(proyecto_i154, "E-54")
    # E-33: 30 bultos cemento (=1500 kg), 5 cuñetes arena, 3 grava
    _trincho(proyecto_i154, t33, cemento=Decimal("30"), arena=Decimal("5"), grava=Decimal("3"))
    # E-54: 50 bultos cemento (=2500 kg), 2 cuñetes arena, 7 alambre
    _trincho(
        proyecto_i154,
        t54,
        cemento=Decimal("50"),
        arena=Decimal("2"),
        alambre_galvanizado=Decimal("7"),
    )

    resumen = proyecto_i154.resumen_materiales()

    # Filas ordenadas por orden_numerico: E-33 antes que E-54.
    assert [f["torre"] for f in resumen["torres"]] == ["T-33", "T-54"]
    f33 = next(f for f in resumen["torres"] if f["torre"] == "T-33")
    f54 = next(f for f in resumen["torres"] if f["torre"] == "T-54")
    assert f33["cemento_kg"] == Decimal("1500")
    assert f54["cemento_kg"] == Decimal("2500")

    total = resumen["total"]
    # cemento_kg total = 1500 + 2500 = 4000; = Σ filas
    assert total["cemento_kg"] == f33["cemento_kg"] + f54["cemento_kg"]
    assert total["cemento_kg"] == Decimal("4000")
    assert total["arena"] == Decimal("7")  # 5 + 2
    assert total["grava"] == Decimal("3")  # 3 + 0
    assert total["alambre_galvanizado"] == Decimal("7")  # 0 + 7


@pytest.mark.django_db
def test_pata_obra_agrega_m3_por_torre(proyecto_i154):
    """PataObra aporta solado/concreto/relleno en m³ sumados por torre.

    concreto = concreto_instalado_m3 ∥ fallback concreto_m3.
    """
    from apps.construccion.models import PataObra

    t = _torre(proyecto_i154, "E-1")
    # Dos patas: una con concreto_instalado, otra solo con concreto_m3 (fallback).
    PataObra.objects.create(
        torre=t, pata="A", solado_m3=2.0, concreto_instalado_m3=4.0, relleno_m3=1.5
    )
    PataObra.objects.create(torre=t, pata="B", solado_m3=3.0, concreto_m3=5.0, relleno_m3=2.5)

    resumen = proyecto_i154.resumen_materiales()
    fila = resumen["torres"][0]
    assert fila["solado_m3"] == Decimal("5.0")  # 2 + 3
    assert fila["concreto_m3"] == Decimal("9.0")  # 4 (instalado) + 5 (fallback)
    assert fila["relleno_m3"] == Decimal("4.0")  # 1.5 + 2.5


@pytest.mark.django_db
def test_torre_no_aplica_se_excluye(proyecto_i154):
    """Una torre con aplica=False NO entra en el resumen ni en el total."""
    t_ok = _torre(proyecto_i154, "E-10", aplica=True)
    t_no = _torre(proyecto_i154, "E-99", aplica=False)
    _trincho(proyecto_i154, t_ok, cemento=Decimal("4"))
    _trincho(proyecto_i154, t_no, cemento=Decimal("100"))  # NO debe contar

    resumen = proyecto_i154.resumen_materiales()
    assert len(resumen["torres"]) == 1
    assert resumen["torres"][0]["torre"] == "T-10"
    assert resumen["total"]["cemento_kg"] == Decimal("200")  # 4×50, sin la no-aplica


@pytest.mark.django_db
def test_columnas_y_materiales_nd(proyecto_i154):
    """Las columnas declaradas y los materiales N/D (Agua, Madera) se exponen."""
    resumen = proyecto_i154.resumen_materiales()
    keys = [c["key"] for c in resumen["columnas"]]
    assert "cemento_kg" in keys
    assert "arena" in keys
    assert "solado_m3" in keys
    # Agua y Madera NO son columnas (no se inventan) pero sí están listadas N/D.
    assert "agua" not in keys
    assert "madera" not in keys
    assert "Agua" in resumen["materiales_nd"]
    assert "Madera" in resumen["materiales_nd"]
    # Header lleva la unidad real: arena en cuñetes, cemento en kg.
    arena_col = next(c for c in resumen["columnas"] if c["key"] == "arena")
    cemento_col = next(c for c in resumen["columnas"] if c["key"] == "cemento_kg")
    assert arena_col["unidad"] == "cuñetes"
    assert cemento_col["unidad"] == "kg"


# ===========================================================================
# Edge cases
# ===========================================================================


@pytest.mark.django_db
def test_edge_proyecto_sin_materiales(proyecto_i154):
    """Edge: proyecto sin torres / sin materiales → estructura vacía sin crash."""
    resumen = proyecto_i154.resumen_materiales()
    assert resumen["torres"] == []
    assert resumen["hay_datos"] is False
    # Total presente pero en cero para cada material declarado.
    for col in resumen["columnas"]:
        assert resumen["total"][col["key"]] == Decimal("0")


@pytest.mark.django_db
def test_edge_torre_sin_materiales_en_cero(proyecto_i154):
    """Edge: torre que aplica pero sin material → fila en cero, hay_datos=False."""
    _torre(proyecto_i154, "E-7")  # torre sin trincho ni pata
    resumen = proyecto_i154.resumen_materiales()
    assert len(resumen["torres"]) == 1
    fila = resumen["torres"][0]
    assert all(fila[c["key"]] == Decimal("0") for c in resumen["columnas"])
    assert resumen["hay_datos"] is False


@pytest.mark.django_db
def test_edge_torre_material_parcial(proyecto_i154):
    """Edge: torre con solo cemento → resto en 0, total coherente."""
    t = _torre(proyecto_i154, "E-5")
    _trincho(proyecto_i154, t, cemento=Decimal("2"))  # solo cemento

    resumen = proyecto_i154.resumen_materiales()
    fila = resumen["torres"][0]
    assert fila["cemento_kg"] == Decimal("100")  # 2 × 50
    assert fila["arena"] == Decimal("0")
    assert fila["geotextil"] == Decimal("0")
    assert fila["solado_m3"] == Decimal("0")
    assert resumen["hay_datos"] is True


# ===========================================================================
# A2 — ResumenMaterialesView (smoke GET 200 autenticado)
# ===========================================================================


@pytest.mark.django_db
def test_view_get_200_autenticado(client, admin_user, proyecto_i154):
    from django.urls import reverse

    t = _torre(proyecto_i154, "E-33")
    _trincho(proyecto_i154, t, cemento=Decimal("10"), arena=Decimal("3"))

    client.force_login(admin_user)
    url = reverse("construccion:resumen_materiales", kwargs={"proyecto_id": proyecto_i154.id})
    resp = client.get(url)
    assert resp.status_code == 200
    # La tabla y el canvas del gráfico deben estar presentes.
    body = resp.content.decode()
    assert "Resumen de Materiales" in body
    assert "chart-materiales" in body
    assert "resumen-materiales-data" in body  # json_script del Chart.js
    # El contexto trae el resumen agregado.
    assert resp.context["resumen"]["total"]["cemento_kg"] == Decimal("500")


@pytest.mark.django_db
def test_view_get_200_proyecto_vacio(client, admin_user, proyecto_i154):
    """La vista no revienta con un proyecto sin materiales (estado vacío)."""
    from django.urls import reverse

    client.force_login(admin_user)
    url = reverse("construccion:resumen_materiales", kwargs={"proyecto_id": proyecto_i154.id})
    resp = client.get(url)
    assert resp.status_code == 200
    assert "sin-materiales" in resp.content.decode()
