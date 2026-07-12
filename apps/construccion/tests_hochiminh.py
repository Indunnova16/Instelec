"""Tests para #171 Hochiminh Fase 1 (matriz por torre: Marcación/Replanteo +
columnas de solo-lectura reusadas de Obra Civil/Montaje/Tendido/Preliminares).

Archivo dedicado (NO tests_issue_171.py, que es de Sprint A — mismo criterio
que la nota de cabecera de ese archivo: evitar colisión con trabajo en
paralelo sobre el mismo repo). Ver SPRINTS/PLAN_2026-07-12_171_hochiminh_fase1.md
para el contrato completo verificado contra BD prod real (F2).
"""
import pytest
from django.urls import reverse

from apps.construccion.models import (
    HochiminhMarcacionReplanteo,
    MontajeEstructuraTorre,
    ObraCivilTorre,
    ProyectoConstruccion,
    TendidoTorre,
    TorreConstruccion,
)
from apps.construccion.models_hochiminh import cruzar_preliminares
from apps.contratos.models import Contrato
from apps.ingenieria.models import TorreContrato
from apps.preliminares.models import AmbientalTorre, PredialTorre


@pytest.fixture
def contrato_construccion():
    return Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-171-HOCHIMINH',
        nombre='Contrato test #171 Hochiminh',
        cliente='Test',
    )


@pytest.fixture
def proyecto_construccion(contrato_construccion):
    return ProyectoConstruccion.objects.create(
        contrato=contrato_construccion,
        nombre='Proyecto test #171 Hochiminh',
        estado='EJECUCION',
    )


# ====== Unit: color_semaforo (límites 0/39/40/99/100/101) ======
# Umbral LITERAL del cliente (verde>=100, amarillo 40-99, rojo<40) — el caso
# amarillo NO existe en datos reales de prod hoy (único proyecto QA está en
# 100%/0%), así que este es el único lugar donde se valida (decisión F2).

@pytest.mark.parametrize('pct,esperado', [
    (0, 'text-red-600'),
    (39, 'text-red-600'),
    (40, 'text-amber-600'),
    (99, 'text-amber-600'),
    (100, 'text-green-600'),
    (101, 'text-green-600'),
])
def test_color_semaforo_limites(pct, esperado):
    assert HochiminhMarcacionReplanteo.color_semaforo(pct) == esperado


# ====== Unit: tendido_pct (promedio simple) y estado_general_pct (promedio de 3) ======

@pytest.mark.django_db
def test_tendido_pct_promedio_simple_conductor_fibra(proyecto_construccion):
    """#171 2026-07-10: tendido_pct = promedio simple de avance_conductor_pct
    y avance_fibra_pct (NO el SUMPRODUCT ponderado que usa el módulo Tendido)."""
    torre = TorreConstruccion.objects.create(proyecto=proyecto_construccion, numero='E1')
    TendidoTorre.objects.create(
        proyecto=proyecto_construccion, torre=torre,
        # Conductor 100%: las 6 actividades ponderadas en True.
        riega_manila_conductor=True, riega_guaya_conductor=True, tendido_conductor=True,
        grapado_amarre_conductor=True, accesorios_puentes=True, balizas_desviadores=True,
        # Fibra 0%: todas en False (default).
    )
    h, _ = HochiminhMarcacionReplanteo.objects.get_or_create(torre=torre)
    assert h.tendido_pct == 50.0


@pytest.mark.django_db
def test_estado_general_pct_promedio_de_3_bloques(proyecto_construccion):
    """estado_general_pct = promedio simple de obra_civil_pct + montaje_pct + tendido_pct."""
    torre = TorreConstruccion.objects.create(proyecto=proyecto_construccion, numero='E2')
    # Obra Civil 100%: las 6 columnas en 1.
    ObraCivilTorre.objects.create(
        proyecto=proyecto_construccion, torre=torre,
        avance_cerramiento=1, avance_excavacion=1, avance_solado=1,
        avance_acero=1, avance_vaciado=1, avance_compactacion=1,
    )
    # Montaje: sin fila creada → montaje_pct debe caer a 0.0 (fallback getattr None).
    # Tendido conductor 100% / fibra 0% → tendido_pct = 50.0 (ver test anterior).
    TendidoTorre.objects.create(
        proyecto=proyecto_construccion, torre=torre,
        riega_manila_conductor=True, riega_guaya_conductor=True, tendido_conductor=True,
        grapado_amarre_conductor=True, accesorios_puentes=True, balizas_desviadores=True,
    )
    h, _ = HochiminhMarcacionReplanteo.objects.get_or_create(torre=torre)
    assert h.obra_civil_pct == 100.0
    assert h.montaje_pct == 0.0
    assert h.tendido_pct == 50.0
    assert h.estado_general_pct == round((100.0 + 0.0 + 50.0) / 3, 1)


@pytest.mark.django_db
def test_obra_civil_y_montaje_pct_sin_fila_relacionada_cae_a_cero(proyecto_construccion):
    """Torre sin ObraCivilTorre/MontajeEstructuraTorre/TendidoTorre asociada
    (aún no gestionada en esos módulos) → todas las properties caen a 0.0,
    sin AttributeError."""
    torre = TorreConstruccion.objects.create(proyecto=proyecto_construccion, numero='E3')
    h, _ = HochiminhMarcacionReplanteo.objects.get_or_create(torre=torre)
    assert h.obra_civil_pct == 0.0
    assert h.montaje_pct == 0.0
    assert h.tendido_pct == 0.0
    assert h.estado_general_pct == 0.0


# ====== Integration: cruce Predial/Ambiental (match y sin match) ======

@pytest.mark.django_db
def test_cruzar_preliminares_con_match(proyecto_construccion, contrato_construccion):
    """Cruce por sufijo numérico + contrato_id compartido — formato real:
    TorreConstruccion.numero='E1' vs TorreContrato.nombre='T1' (verificado
    65/65 por F2 contra BD prod)."""
    torre = TorreConstruccion.objects.create(proyecto=proyecto_construccion, numero='E1')
    # #171: TorreContrato.save() dispara un post_save (apps/ingenieria/signals.py)
    # que ya crea PredialTorre/AmbientalTorre vacíos — usar get_or_create + update
    # en vez de .objects.create() (violaría el OneToOne único torre_id).
    torre_contrato = TorreContrato.objects.create(contrato=contrato_construccion, nombre='T1')
    predial, _ = PredialTorre.objects.get_or_create(torre=torre_contrato)
    predial.liberacion_predial = True
    predial.save(update_fields=['liberacion_predial'])
    ambiental, _ = AmbientalTorre.objects.get_or_create(torre=torre_contrato)
    ambiental.liberacion_pdo = None
    ambiental.save(update_fields=['liberacion_pdo'])

    resultado = cruzar_preliminares(proyecto_construccion, [torre])

    assert resultado[torre.id]['predial'] is True
    # liberacion_pdo NULL (columna sin poblar aún, caso real en QA) → fallback None.
    assert resultado[torre.id]['ambiental'] is None


@pytest.mark.django_db
def test_cruzar_preliminares_sin_match_fallback_none(proyecto_construccion, contrato_construccion):
    """Torre sin TorreContrato correspondiente en el mismo contrato (sufijo
    numérico sin match) → fallback None (el template lo renderiza '—')."""
    torre = TorreConstruccion.objects.create(proyecto=proyecto_construccion, numero='E99')
    # Ninguna TorreContrato con sufijo '99' en este contrato.
    TorreContrato.objects.create(contrato=contrato_construccion, nombre='T1')

    resultado = cruzar_preliminares(proyecto_construccion, [torre])

    assert resultado[torre.id] == {'predial': None, 'ambiental': None}


@pytest.mark.django_db
def test_cruzar_preliminares_no_cruza_entre_contratos_distintos(proyecto_construccion):
    """Mismo sufijo numérico pero contrato_id distinto → NO debe matchear
    (el cruce exige sufijo Y contrato_id compartido)."""
    otro_contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-171-OTRO',
        nombre='Otro contrato',
        cliente='Test',
    )
    torre = TorreConstruccion.objects.create(proyecto=proyecto_construccion, numero='E1')
    torre_contrato_otro = TorreContrato.objects.create(contrato=otro_contrato, nombre='T1')
    predial, _ = PredialTorre.objects.get_or_create(torre=torre_contrato_otro)
    predial.liberacion_predial = True
    predial.save(update_fields=['liberacion_predial'])

    resultado = cruzar_preliminares(proyecto_construccion, [torre])

    assert resultado[torre.id] == {'predial': None, 'ambiental': None}


# ====== View: matriz renderiza 200, toggle persiste ======

@pytest.mark.django_db
def test_hochiminh_matriz_renderiza_200_con_torres_reales(authenticated_client, proyecto_construccion):
    """Matriz Hochiminh renderiza 200 con torres del proyecto, incluida una
    'No aplica' (modela E25 del proyecto QA real — grisada, no excluida)."""
    torre_aplica = TorreConstruccion.objects.create(
        proyecto=proyecto_construccion, numero='E1', tipo='A', tipo_cimentacion='ZAPATA')
    torre_no_aplica = TorreConstruccion.objects.create(
        proyecto=proyecto_construccion, numero='E25', aplica=False)

    url = reverse('construccion:hochiminh_lista', kwargs={'proyecto_id': proyecto_construccion.id})
    resp = authenticated_client.get(url)

    assert resp.status_code == 200
    assert torre_aplica.numero_display.encode() in resp.content
    # #150/#160: la torre "No aplica" se VE (grisada), no se excluye de la matriz.
    assert torre_no_aplica.numero_display.encode() in resp.content
    # get_or_create automático — cada torre visible tiene su fila Hochiminh.
    assert HochiminhMarcacionReplanteo.objects.filter(torre=torre_aplica).exists()
    assert HochiminhMarcacionReplanteo.objects.filter(torre=torre_no_aplica).exists()


@pytest.mark.django_db
def test_hochiminh_toggle_persiste_marcacion(authenticated_client, proyecto_construccion):
    """POST al endpoint toggle persiste el campo de Marcación/Replanteo indicado."""
    torre = TorreConstruccion.objects.create(proyecto=proyecto_construccion, numero='E1')
    url = reverse('construccion:hochiminh_toggle',
                  kwargs={'proyecto_id': proyecto_construccion.id, 'torre_id': torre.id})

    resp = authenticated_client.post(url, data={'campo': 'marcacion_a', 'valor': '1'})
    assert resp.status_code == 200
    h = HochiminhMarcacionReplanteo.objects.get(torre=torre)
    assert h.marcacion_a is True

    # Toggle de vuelta a False persiste también.
    resp = authenticated_client.post(url, data={'campo': 'marcacion_a', 'valor': '0'})
    assert resp.status_code == 200
    h.refresh_from_db()
    assert h.marcacion_a is False


@pytest.mark.django_db
def test_hochiminh_toggle_campo_invalido_rechaza_400(authenticated_client, proyecto_construccion):
    """Campo fuera de HOCHIMINH_TODOS_BOOL (ej. inyectar otro campo del
    modelo) es rechazado con 400 — mismo guard que TendidoToggleView."""
    torre = TorreConstruccion.objects.create(proyecto=proyecto_construccion, numero='E1')
    url = reverse('construccion:hochiminh_toggle',
                  kwargs={'proyecto_id': proyecto_construccion.id, 'torre_id': torre.id})

    resp = authenticated_client.post(url, data={'campo': 'created_at', 'valor': '1'})
    assert resp.status_code == 400
