"""Tests #154 — Resumen de materiales del proyecto (total + por torre).

Cubre el método de agregación ``ProyectoConstruccion.resumen_materiales()`` y la
vista ``ResumenMaterialesView``. Sin migración (solo lectura/agregación).

Reglas de negocio bajo prueba (PLAN_2026-06-20_resumen_materiales_154.md + fix #154):
  - Cemento de trinchos se captura en bultos de 50K → se normaliza a kg (×50).
  - Arena/Grava de trinchos se reportan en cuñetes (NO m³).
  - ``ObraCivilTorreDetalle`` (CANT OOCC #74) aporta los materiales reales por
    torre×pata (se suman las 4 patas): Solado/Vaciado calc Y real, Excavación,
    Acero, Cerramiento, Compactación. El cemento de Obra Civil va SEPARADO del
    de trinchos (unidades/fuente distintas — NO se suman).
  - Las columnas legacy de PataObra (solado_m3/concreto_m3/relleno_m3) se
    retiraron: el modelo está vacío en prod y siempre salía en 0.
  - Tras el fix #154, Agua y Madera SÍ existen (Obra Civil) → no hay N/D.
  - Solo torres con ``aplica=True`` entran.
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


def _oc_detalle(proyecto, torre, pata="A", **campos):
    """Crea un ObraCivilTorreDetalle (CANT OOCC #74) — una pata de la torre."""
    from apps.construccion.models_b3_oc_detalle import ObraCivilTorreDetalle

    return ObraCivilTorreDetalle.objects.create(
        proyecto=proyecto,
        torre=torre,
        pata=pata,
        **campos,
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
def test_oc_detalle_suma_las_4_patas_por_torre(proyecto_i154):
    """ObraCivilTorreDetalle (#74) aporta materiales reales sumando las 4 patas.

    Solado/Vaciado traen calc Y real; Excavación/Acero traen su cantidad.
    """
    t = _torre(proyecto_i154, "E-1")
    # Dos patas con materiales de Obra Civil; el resumen las suma por torre.
    _oc_detalle(
        proyecto_i154,
        t,
        pata="A",
        sol_cemento_calc=Decimal("100"),
        sol_cemento_real=Decimal("90"),
        sol_arena_calc=Decimal("2"),
        sol_arena_real=Decimal("1.5"),
        vac_cemento_calc=Decimal("300"),
        vac_cemento_real=Decimal("320"),
        exc_metros_m3=Decimal("12"),
        ace_instalado_kg=Decimal("500"),
        ace_solicitado_kg=Decimal("480"),
        cerr_madera_un=4,
        cerr_lona_m=Decimal("20"),
        com_volumen_m3=Decimal("8"),
    )
    _oc_detalle(
        proyecto_i154,
        t,
        pata="B",
        sol_cemento_calc=Decimal("100"),
        sol_cemento_real=Decimal("95"),
        vac_cemento_real=Decimal("280"),
        exc_metros_m3=Decimal("10"),
        ace_instalado_kg=Decimal("450"),
    )

    resumen = proyecto_i154.resumen_materiales()
    fila = resumen["torres"][0]
    # Solado cemento: calc 100+100=200, real 90+95=185
    assert fila["oc_sol_cemento_calc"] == Decimal("200")
    assert fila["oc_sol_cemento_real"] == Decimal("185")
    # Solado arena: solo pata A → calc 2, real 1.5
    assert fila["oc_sol_arena_calc"] == Decimal("2")
    assert fila["oc_sol_arena_real"] == Decimal("1.5")
    # Vaciado cemento: calc 300 (solo A), real 320+280=600
    assert fila["oc_vac_cemento_calc"] == Decimal("300")
    assert fila["oc_vac_cemento_real"] == Decimal("600")
    # Excavación m³: 12+10=22
    assert fila["oc_exc_m3"] == Decimal("22")
    # Acero: instalado 500+450=950, solicitado 480 (solo A)
    assert fila["oc_ace_instalado_kg"] == Decimal("950")
    assert fila["oc_ace_solicitado_kg"] == Decimal("480")
    # Cerramiento/Compactación: solo pata A
    assert fila["oc_cerr_madera_un"] == Decimal("4")
    assert fila["oc_cerr_lona_m"] == Decimal("20")
    assert fila["oc_com_volumen_m3"] == Decimal("8")
    assert resumen["hay_datos"] is True


@pytest.mark.django_db
def test_oc_detalle_resumen_trae_valores_mayores_a_cero(proyecto_i154):
    """Con datos de oc_detalle el resumen NO queda en 0 (regresión del bug #154).

    Antes del fix, Solado/Vaciado salían en 0 porque el método leía de PataObra
    (vacío en prod) y no de ObraCivilTorreDetalle.
    """
    t = _torre(proyecto_i154, "E-64")
    _oc_detalle(
        proyecto_i154,
        t,
        pata="A",
        sol_cemento_real=Decimal("4600"),
        vac_cemento_real=Decimal("4603"),
        vac_agua_real=Decimal("3.2"),
    )

    resumen = proyecto_i154.resumen_materiales()
    fila = next(f for f in resumen["torres"] if f["torre"] == "T-64")
    # Suma de cemento real de Obra Civil (solado + vaciado) > 0
    cemento_oc_real = fila["oc_sol_cemento_real"] + fila["oc_vac_cemento_real"]
    assert cemento_oc_real == Decimal("9203")
    assert fila["oc_vac_agua_real"] == Decimal("3.2")  # Agua YA existe (#154)
    assert resumen["hay_datos"] is True
    # El total del proyecto refleja los mismos valores (1 torre).
    assert resumen["total"]["oc_sol_cemento_real"] == Decimal("4600")
    assert resumen["total"]["oc_vac_cemento_real"] == Decimal("4603")


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
def test_columnas_incluyen_trincho_y_obra_civil(proyecto_i154):
    """Las columnas declaradas cubren trinchos + Obra Civil (calc/real)."""
    resumen = proyecto_i154.resumen_materiales()
    keys = [c["key"] for c in resumen["columnas"]]
    # Columnas de trincho conservadas
    assert "cemento_kg" in keys
    assert "arena" in keys
    assert "geotextil" in keys
    # Columnas legacy de PataObra retiradas (siempre salían 0 en prod)
    assert "solado_m3" not in keys
    assert "concreto_m3" not in keys
    assert "relleno_m3" not in keys
    # Columnas nuevas de Obra Civil: calc Y real + Excavación/Acero
    assert "oc_sol_cemento_calc" in keys
    assert "oc_sol_cemento_real" in keys
    assert "oc_vac_cemento_calc" in keys
    assert "oc_vac_cemento_real" in keys
    assert "oc_exc_m3" in keys
    assert "oc_ace_instalado_kg" in keys
    # Agua y Madera YA existen (Obra Civil) → ya no hay N/D
    assert "oc_sol_agua_calc" in keys
    assert "oc_cerr_madera_un" in keys
    assert resumen["materiales_nd"] == []
    # Header lleva la unidad real: arena en cuñetes, cemento de trincho en kg.
    arena_col = next(c for c in resumen["columnas"] if c["key"] == "arena")
    cemento_col = next(c for c in resumen["columnas"] if c["key"] == "cemento_kg")
    assert arena_col["unidad"] == "cuñetes"
    assert cemento_col["unidad"] == "kg"
    # El cemento de Obra Civil va en kg pero en columna SEPARADA del de trinchos.
    oc_sol_cem = next(c for c in resumen["columnas"] if c["key"] == "oc_sol_cemento_real")
    assert oc_sol_cem["unidad"] == "kg"
    assert oc_sol_cem["key"] != cemento_col["key"]


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
    # Materiales de Obra Civil sin dato → 0 (no crash por columnas nuevas)
    assert fila["oc_sol_cemento_real"] == Decimal("0")
    assert fila["oc_exc_m3"] == Decimal("0")
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
