"""Instelec#171 (Sprint final, GRUPO A) — B2: modelo `ColumnaConfigurable` +
helper `crear_columnas_configurables_default` (fundamento de columnas
configurables por capítulo, base de B3-B7 futuros).

Convención de colección: este archivo vive en `tests/unit/` (NO
`apps/construccion/tests_issue_171.py`) porque `pyproject.toml` define
`testpaths = ["tests"]` + `python_files = ["test_*.py", "*_test.py"]` — el
patrón legacy `apps/<app>/tests_issue_<N>.py` NO colecta en CI ni en `pytest`
bare (ver `tests/unit/test_issue_185.py`, mismo hallazgo documentado ahí).

Nota sobre la DATA MIGRATION (0044_columna_configurable.py): `pyproject.toml`
corre la suite con `--nomigrations` (schema armado directo desde los modelos,
sin reproducir el historial de migraciones) — por diseño, la RunPython de la
migración NUNCA se ejecuta dentro de este test suite. Por eso los tests de
abajo verifican `crear_columnas_configurables_default()` (la MISMA lógica que
usa la migración y el signal, ver models.py) contra la BD de test de pytest,
Y por separado se verificó MANUALMENTE (fuera del test suite, documentado en
`notas_para_orquestador` del JSON de salida de F3) que la migración 0044
aplicada de punta a punta contra una BD Postgres/PostGIS de test local
produce exactamente 21 filas con los pesos verificados por F2 contra prod
para el proyecto QA real (`ec2a68aa-47fe-4772-89bc-2cd2b1c8b5c7`).
"""
import pytest
from django.db.models.signals import post_save

from apps.construccion.models import (
    COLUMNAS_CONFIGURABLES_ESPEC,
    ColumnaConfigurable,
    ProyectoConstruccion,
    crear_columnas_configurables_default,
)
from apps.construccion.signals import crear_columnas_configurables_proyecto_nuevo
from apps.contratos.models import Contrato

# Pesos EXACTOS verificados por F2 contra BD prod (SOLO SELECT, proxy
# 127.0.0.1:5434, instelec_db) — PLAN_2026-07-19_171_sprint_final.md sección
# "Verificación BD prod". Usados acá literal, sin redondear ni inventar.
_PESOS_PROD_VERIFICADOS = {
    'peso_cerramiento_pct': 5,
    'peso_excavacion_pct': 30,
    'peso_solado_pct': 5,
    'peso_acero_pct': 15,
    'peso_vaciado_pct': 30,
    'peso_compactacion_pct': 15,
    'peso_mont_estructura_sitio_pct': 10,
    'peso_mont_prearamada_pct': 20,
    'peso_mont_torre_montada_pct': 45,
    'peso_mont_revisada_pct': 25,
    'peso_tend_riega_manila_pct': 20,
    'peso_tend_riega_guaya_pct': 20,
    'peso_tend_tendido_conductor_pct': 30,
    'peso_tend_grapado_pct': 10,
    'peso_tend_accesorios_pct': 10,
    'peso_tend_balizas_pct': 10,
    'peso_tend_riega_manila_fibra_pct': 10,
    'peso_tend_riega_guaya_opgw_pct': 20,
    'peso_tend_tendido_opgw_pct': 40,
    'peso_tend_grapado_fibra_pct': 20,
    'peso_tend_empalmes_opgw_pct': 10,
}


@pytest.fixture
def proyecto_qa_pesos_prod(db):
    """Proyecto de test con los pesos EXACTOS verificados en BD prod para el
    proyecto QA real (#49 Puerta de Oro) — reproduce el escenario que la
    migración 0044 debe migrar sin inventar/redondear valores.

    El signal post_save (proyectos NUEVOS, ver más abajo sección 3) se
    desconecta temporalmente para esta creación: reproduce fielmente el
    escenario real de la migración 0044 (un ProyectoConstruccion que YA
    existía en prod ANTES de que este código/signal existiera), y deja el
    llamado explícito a `crear_columnas_configurables_default()` en cada test
    con significado real (no un no-op porque el signal ya lo hizo)."""
    post_save.disconnect(crear_columnas_configurables_proyecto_nuevo, sender=ProyectoConstruccion)
    try:
        contrato = Contrato.objects.create(
            unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
            codigo='TEST-171-B2-001',
            nombre='Proyecto test #171 B2 — pesos prod verificados',
            cliente='Test',
        )
        proyecto = ProyectoConstruccion.objects.create(
            contrato=contrato,
            nombre='QA test #49 - Puerta de Oro (fixture)',
            estado='EJECUCION',
            **_PESOS_PROD_VERIFICADOS,
        )
        assert ColumnaConfigurable.objects.filter(proyecto=proyecto).count() == 0, (
            "Fixture inválida: se esperaba un proyecto SIN columnas configurables "
            "todavía (signal desconectado a propósito)."
        )
    finally:
        post_save.connect(crear_columnas_configurables_proyecto_nuevo, sender=ProyectoConstruccion)
    return proyecto


@pytest.fixture
def proyecto_defaults(db):
    """Proyecto de test SIN pesos custom (usa los default del modelo) — para
    probar el flujo de 'proyecto nuevo' (signal post_save)."""
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-171-B2-002',
        nombre='Proyecto test #171 B2 — defaults',
        cliente='Test',
    )
    return contrato


# ==============================================================================
# 1) Especificación de columnas — 21 columnas, 4 capítulos
# ==============================================================================

def test_columnas_configurables_espec_tiene_21_columnas_en_4_capitulos():
    total = sum(len(cols) for cols in COLUMNAS_CONFIGURABLES_ESPEC.values())
    assert total == 21
    assert set(COLUMNAS_CONFIGURABLES_ESPEC.keys()) == {
        'OBRA_CIVIL', 'MONTAJE', 'TENDIDO_CONDUCTOR', 'TENDIDO_FIBRA',
    }
    assert len(COLUMNAS_CONFIGURABLES_ESPEC['OBRA_CIVIL']) == 6
    assert len(COLUMNAS_CONFIGURABLES_ESPEC['MONTAJE']) == 4
    assert len(COLUMNAS_CONFIGURABLES_ESPEC['TENDIDO_CONDUCTOR']) == 6
    assert len(COLUMNAS_CONFIGURABLES_ESPEC['TENDIDO_FIBRA']) == 5


# ==============================================================================
# 2) crear_columnas_configurables_default — 21 filas, pesos EXACTOS
# ==============================================================================

@pytest.mark.django_db
def test_crear_columnas_default_produce_21_filas_con_pesos_prod_exactos(proyecto_qa_pesos_prod):
    """Reproduce el escenario de la data migration 0044 para el proyecto QA
    real: 21 filas es_sistema=True, activa=True, con peso_pct IDÉNTICO a los
    valores verificados por F2 contra prod (no redondeados/inventados)."""
    creadas = crear_columnas_configurables_default(proyecto_qa_pesos_prod)
    assert len(creadas) == 21

    filas = ColumnaConfigurable.objects.filter(proyecto=proyecto_qa_pesos_prod)
    assert filas.count() == 21
    assert filas.filter(es_sistema=True).count() == 21
    assert filas.filter(activa=True).count() == 21

    pesos_por_clave = {f.clave: f.peso_pct for f in filas}
    # Obra Civil: 5/30/5/15/30/15
    assert pesos_por_clave['cerramiento'] == 5
    assert pesos_por_clave['excavacion'] == 30
    assert pesos_por_clave['solado'] == 5
    assert pesos_por_clave['acero'] == 15
    assert pesos_por_clave['vaciado'] == 30
    assert pesos_por_clave['compactacion'] == 15
    # Montaje: 10/20/45/25
    assert pesos_por_clave['estructura_sitio'] == 10
    assert pesos_por_clave['prearamada'] == 20
    assert pesos_por_clave['torre_montada'] == 45
    assert pesos_por_clave['revisada'] == 25
    # Tendido conductor: 20/20/30/10/10/10
    assert pesos_por_clave['riega_manila_conductor'] == 20
    assert pesos_por_clave['riega_guaya_conductor'] == 20
    assert pesos_por_clave['tendido_conductor'] == 30
    assert pesos_por_clave['grapado_amarre_conductor'] == 10
    assert pesos_por_clave['accesorios_puentes'] == 10
    assert pesos_por_clave['balizas_desviadores'] == 10
    # Tendido fibra: 10/20/40/20/10
    assert pesos_por_clave['riega_manila_fibra'] == 10
    assert pesos_por_clave['riega_guaya_opgw'] == 20
    assert pesos_por_clave['tendido_opgw'] == 40
    assert pesos_por_clave['grapado_amarre_fibra'] == 20
    assert pesos_por_clave['empalmes_opgw'] == 10

    # Suma de pesos por capítulo = 100 (mismo invariante que el legacy peso_*_pct)
    for capitulo in ('OBRA_CIVIL', 'MONTAJE', 'TENDIDO_CONDUCTOR', 'TENDIDO_FIBRA'):
        suma = sum(f.peso_pct for f in filas.filter(capitulo=capitulo))
        assert suma == 100, f"{capitulo}: suma de pesos = {suma}, esperado 100"


@pytest.mark.django_db
def test_crear_columnas_default_tipo_valor_decimal_oc_montaje_boolean_tendido(proyecto_qa_pesos_prod):
    """Obra Civil/Montaje son DECIMAL (avance 0-1 real); Tendido conductor/fibra
    son BOOLEAN (check hecho/no hecho) — reflejando el tipo real de los campos
    hoy en ObraCivilTorre/MontajeEstructuraTorre (Decimal) vs TendidoTorre (bool)."""
    crear_columnas_configurables_default(proyecto_qa_pesos_prod)
    filas = ColumnaConfigurable.objects.filter(proyecto=proyecto_qa_pesos_prod)

    assert set(filas.filter(capitulo='OBRA_CIVIL').values_list('tipo_valor', flat=True)) == {'DECIMAL'}
    assert set(filas.filter(capitulo='MONTAJE').values_list('tipo_valor', flat=True)) == {'DECIMAL'}
    assert set(filas.filter(capitulo='TENDIDO_CONDUCTOR').values_list('tipo_valor', flat=True)) == {'BOOLEAN'}
    assert set(filas.filter(capitulo='TENDIDO_FIBRA').values_list('tipo_valor', flat=True)) == {'BOOLEAN'}


@pytest.mark.django_db
def test_crear_columnas_default_orden_respeta_el_orden_de_las_listas_columnas(proyecto_qa_pesos_prod):
    """El campo `orden` debe reflejar el mismo orden que
    ObraCivilTorre.COLUMNAS (0=cerramiento .. 5=compactacion) — necesario
    para que B7 (matrices dinámicas, fuera de este dispatch) renderice las
    columnas en el mismo orden visual de siempre."""
    crear_columnas_configurables_default(proyecto_qa_pesos_prod)
    ordenadas = list(
        ColumnaConfigurable.objects.filter(
            proyecto=proyecto_qa_pesos_prod, capitulo='OBRA_CIVIL',
        ).order_by('orden').values_list('clave', flat=True)
    )
    assert ordenadas == [
        'cerramiento', 'excavacion', 'solado', 'acero', 'vaciado', 'compactacion',
    ]


@pytest.mark.django_db
def test_crear_columnas_default_es_idempotente(proyecto_qa_pesos_prod):
    """Llamar la función 2 veces sobre el mismo proyecto no duplica filas —
    requisito para que el signal post_save (que puede disparar en cualquier
    save() con created=True, aunque en la práctica solo una vez) y una
    re-ejecución manual del helper sean seguras."""
    primera = crear_columnas_configurables_default(proyecto_qa_pesos_prod)
    segunda = crear_columnas_configurables_default(proyecto_qa_pesos_prod)
    assert len(primera) == 21
    assert len(segunda) == 0  # nada nuevo creado, todo ya existía
    assert ColumnaConfigurable.objects.filter(proyecto=proyecto_qa_pesos_prod).count() == 21


# ==============================================================================
# 3) Signal post_save — proyectos NUEVOS creados post-deploy
# ==============================================================================

@pytest.mark.django_db
def test_proyecto_nuevo_genera_columnas_configurables_automaticamente_via_signal(proyecto_defaults):
    """#171 B2: al crear un ProyectoConstruccion nuevo (sin pasar pesos
    explícitos, o sea con los defaults del modelo), el signal post_save debe
    generar las 21 filas ColumnaConfigurable automáticamente — sin que la
    vista/código que crea el proyecto tenga que llamar nada manualmente."""
    proyecto = ProyectoConstruccion.objects.create(
        contrato=proyecto_defaults,
        nombre='Proyecto nuevo post-deploy #171 B2',
        estado='PLANIFICACION',
    )
    filas = ColumnaConfigurable.objects.filter(proyecto=proyecto)
    assert filas.count() == 21
    # Con los defaults del modelo (sin overrides), Obra Civil sigue siendo 5/30/5/15/30/15
    pesos_oc = dict(filas.filter(capitulo='OBRA_CIVIL').values_list('clave', 'peso_pct'))
    assert pesos_oc == {
        'cerramiento': 5, 'excavacion': 30, 'solado': 5,
        'acero': 15, 'vaciado': 30, 'compactacion': 15,
    }


@pytest.mark.django_db
def test_editar_proyecto_existente_no_duplica_columnas_configurables(proyecto_defaults):
    """El signal solo actúa en creación (created=True) — guardar un proyecto
    YA existente (ej. editar nombre) NO debe re-generar/duplicar filas."""
    proyecto = ProyectoConstruccion.objects.create(
        contrato=proyecto_defaults, nombre='Original', estado='PLANIFICACION',
    )
    assert ColumnaConfigurable.objects.filter(proyecto=proyecto).count() == 21

    proyecto.nombre = 'Renombrado'
    proyecto.save()

    assert ColumnaConfigurable.objects.filter(proyecto=proyecto).count() == 21


# ==============================================================================
# 4) Modelo — constraints básicos
# ==============================================================================

@pytest.mark.django_db
def test_columna_configurable_str_incluye_capitulo_etiqueta_proyecto(proyecto_qa_pesos_prod):
    crear_columnas_configurables_default(proyecto_qa_pesos_prod)
    fila = ColumnaConfigurable.objects.filter(
        proyecto=proyecto_qa_pesos_prod, clave='cerramiento',
    ).first()
    texto = str(fila)
    assert 'Cerramiento' in texto
    assert proyecto_qa_pesos_prod.nombre in texto


@pytest.mark.django_db
def test_columna_configurable_unique_together_proyecto_capitulo_clave(proyecto_qa_pesos_prod):
    """No pueden existir 2 columnas con la misma clave dentro del mismo
    capítulo/proyecto (constraint de BD, no solo aplicativo)."""
    from django.db import IntegrityError, transaction

    ColumnaConfigurable.objects.create(
        proyecto=proyecto_qa_pesos_prod, capitulo='OBRA_CIVIL',
        clave='cerramiento', etiqueta='Cerramiento', orden=0,
        peso_pct=5, tipo_valor='DECIMAL', es_sistema=True, activa=True,
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ColumnaConfigurable.objects.create(
                proyecto=proyecto_qa_pesos_prod, capitulo='OBRA_CIVIL',
                clave='cerramiento', etiqueta='Cerramiento (duplicada)', orden=1,
                peso_pct=99, tipo_valor='DECIMAL', es_sistema=False, activa=True,
            )
