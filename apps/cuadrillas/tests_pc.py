"""
Tests del módulo Programación y seguimiento de cuadrillas (B5, #155).

Cubren el bloque COMPLETO contra los CONTRATOS del BLUEPRINT:

- Modelos `models_pc` (importables en este worktree base):
  `ProgramacionSemanalCuadrilla`, `EjecucionSemanalCuadrilla`,
  `rendimiento_pct`, `unique_together`, OneToOne.
- Vistas B1 (índice), B2 (crear/editar/detalle), B3 (ejecución AJAX),
  B4 (dashboard) por sus URL names del contrato (NO se hardcodean paths;
  se usa `reverse('construccion:...')`).

NOTA F4: los archivos de B1–B4 (views_pc_index / views_pc_programacion /
views_pc_ejecucion / views_pc_dashboard + urls_pc) viven en sus propias
branches y NO están en el worktree base de B5. Por eso estos tests se
EJECUTAN en F4 sobre el árbol integrado, no aquí. En este worktree solo
``manage.py check`` (admin_pc) corre limpio. Los tests están escritos
contra el contrato de nombres/JSON del BLUEPRINT para que F4 los corra
verdes una vez integrado.

Discovery: pytest está limitado a ``tests/`` por pyproject.toml; ejecutar
vía path explícito:

    python3.12 -m pytest apps/cuadrillas/tests_pc.py -v
"""
import json

import pytest
from django.test import Client
from django.urls import NoReverseMatch, reverse

from apps.cuadrillas.models import Cuadrilla
from apps.cuadrillas.models_pc import (
    EjecucionSemanalCuadrilla,
    ProgramacionSemanalCuadrilla,
)
from apps.usuarios.models import Usuario


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _crear_cuadrilla(codigo='CUA-PC-001', nombre='Cuadrilla PC'):
    return Cuadrilla.objects.create(codigo=codigo, nombre=nombre, activa=True)


def _crear_usuario_admin(email='admin_pc@test.local'):
    """Usuario rol admin (RBAC v2) — pasa el RoleRequiredMixin de las vistas."""
    return Usuario.objects.create_user(
        email=email,
        password='ClaudeQA2026!',
        first_name='Admin',
        last_name='PC',
        rol=Usuario.Rol.ADMIN_CONSTRUCCION,
        is_active=True,
    )


def _crear_programacion(cuadrilla=None, anio=2026, semana=18, torres=10):
    if cuadrilla is None:
        cuadrilla = _crear_cuadrilla()
    return ProgramacionSemanalCuadrilla.objects.create(
        cuadrilla=cuadrilla,
        anio=anio,
        semana=semana,
        torres_programadas=torres,
        actividades_programadas='Tendido de torres',
    )


def _login(client, usuario):
    """Login por email (USERNAME_FIELD='email')."""
    ok = client.login(email=usuario.email, password='ClaudeQA2026!')
    assert ok, 'login del usuario admin falló (revisar credenciales/backend)'


# ===========================================================================
# 1. Modelos (models_pc) — importables en el worktree base
# ===========================================================================

@pytest.mark.django_db
class TestRendimientoPct:
    """rendimiento_pct = torres_ejecutadas / torres_programadas × 100."""

    def test_rendimiento_pct_7_sobre_10_es_70(self):
        """Happy path del contrato: 7/10 → 70.0."""
        prog = _crear_programacion(torres=10)
        eje = EjecucionSemanalCuadrilla.objects.create(
            programacion=prog, torres_ejecutadas=7,
        )
        assert eje.rendimiento_pct == 70.0

    def test_rendimiento_pct_division_por_cero_es_cero(self):
        """Edge — torres_programadas=0 → guard div/0 → 0.0 (no excepción)."""
        prog = _crear_programacion(torres=0)
        eje = EjecucionSemanalCuadrilla.objects.create(
            programacion=prog, torres_ejecutadas=5,
        )
        assert eje.rendimiento_pct == 0.0

    def test_rendimiento_pct_fraccionario(self):
        """Edge — 1/3 × 100 ≈ 33.33 (la propiedad del modelo NO redondea;
        el redondeo a 1 decimal del contrato lo hace la vista B3 en su JSON)."""
        prog = _crear_programacion(torres=3)
        eje = EjecucionSemanalCuadrilla.objects.create(
            programacion=prog, torres_ejecutadas=1,
        )
        assert eje.rendimiento_pct == pytest.approx(33.333, abs=0.01)

    def test_rendimiento_pct_sobre_cumplimiento_mayor_100(self):
        """Edge — ejecutado > programado → rendimiento > 100 (no se capa)."""
        prog = _crear_programacion(torres=10)
        eje = EjecucionSemanalCuadrilla.objects.create(
            programacion=prog, torres_ejecutadas=12,
        )
        assert eje.rendimiento_pct == 120.0


@pytest.mark.django_db
class TestModelosConstraints:
    """Constraints del contrato: unique_together + OneToOne."""

    def test_unique_together_cuadrilla_anio_semana(self):
        """unique_together(cuadrilla, anio, semana): segunda programación
        idéntica para la misma cuadrilla/semana/año debe fallar a nivel BD."""
        from django.db import IntegrityError, transaction

        cuadrilla = _crear_cuadrilla()
        _crear_programacion(cuadrilla=cuadrilla, anio=2026, semana=20)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                ProgramacionSemanalCuadrilla.objects.create(
                    cuadrilla=cuadrilla, anio=2026, semana=20, torres_programadas=5,
                )

    def test_unique_together_distinta_semana_ok(self):
        """Misma cuadrilla, distinta semana → permitido."""
        cuadrilla = _crear_cuadrilla()
        _crear_programacion(cuadrilla=cuadrilla, anio=2026, semana=20)
        otra = _crear_programacion(cuadrilla=cuadrilla, anio=2026, semana=21)
        assert otra.pk is not None
        assert ProgramacionSemanalCuadrilla.objects.filter(cuadrilla=cuadrilla).count() == 2

    def test_ejecucion_one_to_one(self):
        """OneToOne ejecución: una segunda ejecución para la misma
        programación debe fallar."""
        from django.db import IntegrityError, transaction

        prog = _crear_programacion()
        EjecucionSemanalCuadrilla.objects.create(programacion=prog, torres_ejecutadas=3)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                EjecucionSemanalCuadrilla.objects.create(
                    programacion=prog, torres_ejecutadas=4,
                )

    def test_ejecucion_accesible_via_related_name(self):
        """related_name='ejecucion' — acceso inverso 1:1."""
        prog = _crear_programacion(torres=10)
        EjecucionSemanalCuadrilla.objects.create(programacion=prog, torres_ejecutadas=8)
        prog.refresh_from_db()
        assert prog.ejecucion.torres_ejecutadas == 8
        assert prog.ejecucion.rendimiento_pct == 80.0


# ===========================================================================
# 2. Dato legacy — cuadrilla del maestro pre-existente
# ===========================================================================

@pytest.mark.django_db
class TestDatoLegacy:
    """El módulo de programación se monta SOBRE el maestro de cuadrillas que
    YA existe. Una cuadrilla "legacy" (creada sin saber del módulo nuevo)
    debe poder programarse sin tocar el maestro."""

    def test_programar_cuadrilla_legacy_no_altera_maestro(self):
        # Cuadrilla creada "como legacy": solo campos del maestro original.
        legacy = Cuadrilla.objects.create(
            codigo='CUA-LEGACY-77', nombre='Cuadrilla histórica', activa=True,
        )
        codigo_original = legacy.codigo

        prog = ProgramacionSemanalCuadrilla.objects.create(
            cuadrilla=legacy, anio=2026, semana=15, torres_programadas=20,
        )
        EjecucionSemanalCuadrilla.objects.create(
            programacion=prog, torres_ejecutadas=18,
        )

        legacy.refresh_from_db()
        # Maestro intacto.
        assert legacy.codigo == codigo_original
        assert legacy.activa is True
        # La programación cuelga del maestro vía related_name.
        assert legacy.programaciones_semanales.count() == 1
        assert prog.ejecucion.rendimiento_pct == 90.0


# ===========================================================================
# 3. Vistas (B1–B4) — por URL name del contrato. Corren en F4 (árbol integrado).
# ===========================================================================

@pytest.mark.django_db
class TestVistasSmoke:
    """Smoke de las vistas del módulo por su URL name del contrato
    (namespace ``construccion:``). NO se hardcodean paths."""

    def setUp(self):  # pragma: no cover - pytest no llama setUp en clases plain
        pass

    def test_b1_indice_render_200_con_login(self):
        """B1 ProgramacionCuadrillaIndexView — índice render 200 autenticado."""
        client = Client()
        admin = _crear_usuario_admin()
        _login(client, admin)
        url = reverse('construccion:programacion_cuadrillas_index')
        resp = client.get(url)
        assert resp.status_code == 200

    def test_b1_indice_role_gate_anonimo_redirige_login(self):
        """Role gate — anónimo NO accede; redirige a login (302)."""
        client = Client()
        url = reverse('construccion:programacion_cuadrillas_index')
        resp = client.get(url)
        assert resp.status_code in (302, 403)
        if resp.status_code == 302:
            assert '/login' in resp.url or 'login' in resp.url

    def test_b2_crear_render_200(self):
        """B2 ProgramacionCuadrillaCreateView — form crear render 200."""
        client = Client()
        admin = _crear_usuario_admin()
        _login(client, admin)
        url = reverse('construccion:programacion_cuadrilla_crear')
        resp = client.get(url)
        assert resp.status_code == 200

    def test_b2_detalle_render_200(self):
        """B2 ProgramacionCuadrillaDetailView — detalle render 200 (pk UUID)."""
        client = Client()
        admin = _crear_usuario_admin()
        _login(client, admin)
        prog = _crear_programacion()
        url = reverse('construccion:programacion_cuadrilla_detalle', args=[prog.pk])
        resp = client.get(url)
        assert resp.status_code == 200

    def test_b2_editar_render_200(self):
        """B2 ProgramacionCuadrillaUpdateView — editar render 200 (pk UUID)."""
        client = Client()
        admin = _crear_usuario_admin()
        _login(client, admin)
        prog = _crear_programacion()
        url = reverse('construccion:programacion_cuadrilla_editar', args=[prog.pk])
        resp = client.get(url)
        assert resp.status_code == 200

    def test_b4_dashboard_render_200(self):
        """B4 dashboard — render 200 autenticado."""
        client = Client()
        admin = _crear_usuario_admin()
        _login(client, admin)
        url = reverse('construccion:programacion_cuadrillas_dashboard')
        resp = client.get(url)
        assert resp.status_code == 200


@pytest.mark.django_db
class TestEjecucionAjax:
    """B3 EjecucionSemanalUpdateView — POST AJAX upsert (pk = UUID de la
    PROGRAMACIÓN), devuelve JSON {ok, rendimiento_pct}."""

    def test_b3_ejecucion_save_post_calcula_rendimiento(self):
        """Mutativo m2: crear programación (torres=10) → POST ejecución
        (torres_ejecutadas=7) → JSON ok + rendimiento_pct=70.0 y BD
        persiste torres_ejecutadas=7."""
        client = Client()
        admin = _crear_usuario_admin()
        _login(client, admin)
        prog = _crear_programacion(torres=10)
        url = reverse('construccion:programacion_cuadrilla_ejecucion_save', args=[prog.pk])
        resp = client.post(
            url,
            data={'torres_ejecutadas': 7, 'observaciones': 'cierre semana'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        assert resp.status_code == 200
        payload = json.loads(resp.content)
        assert payload.get('ok') is True
        assert float(payload.get('rendimiento_pct')) == 70.0

        # BD: la ejecución 1:1 quedó persistida.
        prog.refresh_from_db()
        assert prog.ejecucion.torres_ejecutadas == 7
        assert prog.ejecucion.rendimiento_pct == 70.0

    def test_b3_ejecucion_save_upsert_actualiza_existente(self):
        """Edge — el endpoint es upsert: un segundo POST actualiza la misma
        ejecución (no crea otra, respetando el OneToOne)."""
        client = Client()
        admin = _crear_usuario_admin()
        _login(client, admin)
        prog = _crear_programacion(torres=10)
        url = reverse('construccion:programacion_cuadrilla_ejecucion_save', args=[prog.pk])

        client.post(url, data={'torres_ejecutadas': 5},
                    HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        resp2 = client.post(url, data={'torres_ejecutadas': 9},
                            HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        assert resp2.status_code == 200
        payload = json.loads(resp2.content)
        assert float(payload.get('rendimiento_pct')) == 90.0
        # Sigue habiendo UNA sola ejecución para esta programación.
        assert EjecucionSemanalCuadrilla.objects.filter(programacion=prog).count() == 1


# ===========================================================================
# 4. Calculator de agregación (B4) — rendimiento_por_cuadrilla(qs)
# ===========================================================================

@pytest.mark.django_db
class TestCalculatorRendimiento:
    """calculators_pc.rendimiento_por_cuadrilla(qs) -> list[dict].

    Función pura testeable (B4 la define). Se importa de forma diferida
    porque el módulo calculators_pc vive en la branch de B4 y solo está
    presente en el árbol integrado de F4."""

    def _calc(self):
        try:
            from apps.cuadrillas.calculators_pc import rendimiento_por_cuadrilla
        except ImportError:
            pytest.skip('calculators_pc (B4) no integrado todavía — corre en F4')
        return rendimiento_por_cuadrilla

    def test_calculator_rendimiento_agrega_por_cuadrilla(self):
        rendimiento_por_cuadrilla = self._calc()
        cuadrilla = _crear_cuadrilla(codigo='CUA-CALC-1')
        prog = _crear_programacion(cuadrilla=cuadrilla, semana=10, torres=10)
        EjecucionSemanalCuadrilla.objects.create(programacion=prog, torres_ejecutadas=7)

        resultado = rendimiento_por_cuadrilla(
            ProgramacionSemanalCuadrilla.objects.all()
        )
        assert isinstance(resultado, list)
        assert len(resultado) >= 1
        fila = resultado[0]
        assert isinstance(fila, dict)
        # El contrato no fija las keys exactas; sí que la agregación expone
        # programadas/ejecutadas/rendimiento de alguna forma reconocible.
        valores = list(fila.values())
        assert 70.0 in [round(float(v), 1) for v in valores if isinstance(v, (int, float))]

    def test_calculator_qs_vacio_no_falla(self):
        rendimiento_por_cuadrilla = self._calc()
        resultado = rendimiento_por_cuadrilla(
            ProgramacionSemanalCuadrilla.objects.none()
        )
        assert resultado == [] or list(resultado) == []
