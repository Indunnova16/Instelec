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
from datetime import date

import pytest
from django.db import IntegrityError
from django.test import Client
from django.urls import NoReverseMatch, reverse

from apps.core.permissions import AREA_CONSTRUCCION, AREA_MANTENIMIENTO
from apps.cuadrillas.models import Asistencia, Cargo, Cuadrilla, PersonalCuadrilla, Vehiculo
from apps.cuadrillas.models_pc import (
    AsistenciaEjecucionSemanal,
    EjecucionSemanalCuadrilla,
    EjecucionSemanalPersonal,
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


def _crear_vehiculo(placa='PC-VEH-01', estado=None, capacidad=6):
    """#270 (sub-item B): vehículo de prueba. `estado` default ACTIVO (el
    ``save()`` de Vehiculo sincroniza el puente legacy ``activo``)."""
    kwargs = {'placa': placa, 'capacidad_personas': capacidad}
    if estado is not None:
        kwargs['estado'] = estado
    return Vehiculo.objects.create(**kwargs)


def _crear_cargo(codigo='PC-CARGO-01', nombre='Liniero PC', salario_base='60000'):
    """#270 (sub-item C): Cargo dedicado con `salario_base` conocido, para
    poder afirmar el valor exacto de `costo_dia` snapshoteado (el seed
    LINIERO_I de 0019_seed_cargos.py no garantiza un valor estable para el
    test)."""
    cargo, _ = Cargo.objects.get_or_create(
        codigo=codigo,
        defaults={'nombre': nombre, 'salario_base': salario_base, 'activo': True},
    )
    return cargo


def _crear_personal(
    documento, nombre='Colaborador PC', area=AREA_CONSTRUCCION,
    activo=True, cargo=None,
):
    """#270 (sub-item C): PersonalCuadrilla de prueba. `area=''` (blank)
    simula el dato LEGACY pre-#186 (colaboradores sin área asignada) --
    edge case explícito del sub-item."""
    if cargo is None:
        cargo = _crear_cargo()
    return PersonalCuadrilla.objects.create(
        documento=documento,
        nombre=nombre,
        area=area,
        activo=activo,
        rol_cuadrilla_id=cargo.codigo,
    )


def _login(client, usuario):
    """Login vía CedulaOrEmailBackend (espera kwarg ``username``, que el
    backend resuelve a email o cédula); USERNAME_FIELD='email'."""
    ok = client.login(username=usuario.email, password='ClaudeQA2026!')
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

    def test_asignar_vehiculo_a_ejecucion_legacy_no_rompe_dato_pre_existente(self):
        """#270 sub-item B: un vehículo creado ANTES de esta feature (solo
        con el puente legacy `activo=True`, sin `estado` explícito -- dato
        legacy real del maestro de vehículos) debe poder asignarse a una
        ejecución sin migrarlo ni tocarlo."""
        vehiculo_legacy = Vehiculo.objects.create(
            placa='LEGACY-VEH-01', activo=True,
        )
        placa_original = vehiculo_legacy.placa
        prog = _crear_programacion(torres=10)

        EjecucionSemanalCuadrilla.objects.create(
            programacion=prog, torres_ejecutadas=9, vehiculo=vehiculo_legacy,
        )

        vehiculo_legacy.refresh_from_db()
        # El vehículo legacy queda intacto (save() sincronizó estado=ACTIVO
        # vía el puente activo->estado, ya existente desde #226).
        assert vehiculo_legacy.placa == placa_original
        assert vehiculo_legacy.estado == Vehiculo.Estado.ACTIVO

        prog.refresh_from_db()
        assert prog.ejecucion.vehiculo_id == vehiculo_legacy.pk
        assert prog.ejecucion.vehiculo.placa == 'LEGACY-VEH-01'


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
# 3.5 Asignación de vehículo a la ejecución (#270, sub-item B)
# ===========================================================================

@pytest.mark.django_db
class TestEjecucionVehiculoAjax:
    """B3 EjecucionSemanalUpdateView — asignación/reasignación de vehículo vía
    el mismo POST AJAX (upsert) de la ejecución."""

    def test_happy_asignar_vehiculo_activo_devuelve_placa_tipo_capacidad(self):
        """Happy: asignar un vehículo ACTIVO -> JSON.vehiculo con
        placa/tipo/capacidad, y queda persistido en BD."""
        client = Client()
        admin = _crear_usuario_admin()
        _login(client, admin)
        prog = _crear_programacion(torres=10)
        vehiculo = _crear_vehiculo(
            placa='ABC-123', capacidad=8,
        )
        url = reverse('construccion:programacion_cuadrilla_ejecucion_save', args=[prog.pk])
        resp = client.post(
            url,
            data={
                'torres_ejecutadas': 7,
                'vehiculo': str(vehiculo.pk),
                'observaciones': '',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        assert resp.status_code == 200
        payload = json.loads(resp.content)
        assert payload['ok'] is True
        assert payload['vehiculo'] is not None
        assert payload['vehiculo']['placa'] == 'ABC-123'
        assert payload['vehiculo']['capacidad_personas'] == 8
        assert payload['vehiculo']['tipo']  # get_tipo_display() no vacío

        prog.refresh_from_db()
        assert prog.ejecucion.vehiculo_id == vehiculo.pk

    def test_edge_vehiculo_en_mantenimiento_rechaza_asignacion_nueva(self):
        """Edge — un vehículo EN_MANTENIMIENTO/INACTIVO NO se puede asignar
        de nuevo (400 con mensaje de dominio), sin romper la ejecución ya
        guardada (torres_ejecutadas no se pierde)."""
        client = Client()
        admin = _crear_usuario_admin()
        _login(client, admin)
        prog = _crear_programacion(torres=10)
        vehiculo_mant = _crear_vehiculo(
            placa='MANT-01', estado=Vehiculo.Estado.EN_MANTENIMIENTO,
        )
        # Primero, un guardado válido sin vehículo (para que exista la
        # ejecución 1:1 y confirmar que el rechazo no la corrompe).
        url = reverse('construccion:programacion_cuadrilla_ejecucion_save', args=[prog.pk])
        client.post(url, data={'torres_ejecutadas': 5, 'vehiculo': ''},
                    HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        resp = client.post(
            url,
            data={'torres_ejecutadas': 6, 'vehiculo': str(vehiculo_mant.pk)},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        assert resp.status_code == 400
        payload = json.loads(resp.content)
        assert 'vehículo' in payload['error'].lower()
        assert 'activo' in payload['error'].lower()

        # La ejecución previa sigue intacta (no se sobre-escribió con el POST
        # rechazado).
        prog.refresh_from_db()
        assert prog.ejecucion.torres_ejecutadas == 5
        assert prog.ejecucion.vehiculo_id is None

    def test_edge_reasignar_vehiculo_upsert_reemplaza_el_anterior(self):
        """Edge — reasignar: un segundo POST con OTRO vehículo ACTIVO
        reemplaza al primero (upsert, no acumula ni falla)."""
        client = Client()
        admin = _crear_usuario_admin()
        _login(client, admin)
        prog = _crear_programacion(torres=10)
        vehiculo_1 = _crear_vehiculo(placa='V1-001')
        vehiculo_2 = _crear_vehiculo(placa='V2-002')
        url = reverse('construccion:programacion_cuadrilla_ejecucion_save', args=[prog.pk])

        client.post(url, data={'torres_ejecutadas': 3, 'vehiculo': str(vehiculo_1.pk)},
                    HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        resp2 = client.post(
            url, data={'torres_ejecutadas': 3, 'vehiculo': str(vehiculo_2.pk)},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        assert resp2.status_code == 200
        payload = json.loads(resp2.content)
        assert payload['vehiculo']['placa'] == 'V2-002'

        prog.refresh_from_db()
        assert prog.ejecucion.vehiculo_id == vehiculo_2.pk
        # Sigue habiendo UNA sola ejecución (OneToOne respetado).
        assert EjecucionSemanalCuadrilla.objects.filter(programacion=prog).count() == 1

    def test_edge_reenviar_el_mismo_vehiculo_ya_en_mantenimiento_no_lo_bloquea(self):
        """Edge (contrato del docstring de la vista) — si el vehículo YA
        asignado pasa a EN_MANTENIMIENTO después, reenviar el MISMO id (sin
        cambiarlo) no debe rechazarse -- solo se bloquea asignar uno NUEVO
        que no esté activo."""
        client = Client()
        admin = _crear_usuario_admin()
        _login(client, admin)
        prog = _crear_programacion(torres=10)
        vehiculo = _crear_vehiculo(placa='YA-ASIG-01')
        url = reverse('construccion:programacion_cuadrilla_ejecucion_save', args=[prog.pk])
        client.post(url, data={'torres_ejecutadas': 4, 'vehiculo': str(vehiculo.pk)},
                    HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        # El vehículo pasa a mantenimiento DESPUÉS de asignado.
        vehiculo.estado = Vehiculo.Estado.EN_MANTENIMIENTO
        vehiculo.save(update_fields=['estado'])

        resp = client.post(
            url, data={'torres_ejecutadas': 4, 'vehiculo': str(vehiculo.pk)},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        assert resp.status_code == 200
        payload = json.loads(resp.content)
        assert payload['ok'] is True
        assert payload['vehiculo']['placa'] == 'YA-ASIG-01'

    def test_edge_vacio_desasigna_vehiculo(self):
        """Edge — enviar 'vehiculo' vacío desasigna (vehiculo=None), no es
        un error."""
        client = Client()
        admin = _crear_usuario_admin()
        _login(client, admin)
        prog = _crear_programacion(torres=10)
        vehiculo = _crear_vehiculo(placa='DESASIG-01')
        url = reverse('construccion:programacion_cuadrilla_ejecucion_save', args=[prog.pk])
        client.post(url, data={'torres_ejecutadas': 2, 'vehiculo': str(vehiculo.pk)},
                    HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        resp = client.post(url, data={'torres_ejecutadas': 2, 'vehiculo': ''},
                            HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert resp.status_code == 200
        payload = json.loads(resp.content)
        assert payload['vehiculo'] is None

        prog.refresh_from_db()
        assert prog.ejecucion.vehiculo_id is None

    def test_edge_vehiculo_id_inexistente_400(self):
        """Edge — un uuid de vehículo que no existe en absoluto -> 400."""
        import uuid as uuid_module

        client = Client()
        admin = _crear_usuario_admin()
        _login(client, admin)
        prog = _crear_programacion(torres=10)
        url = reverse('construccion:programacion_cuadrilla_ejecucion_save', args=[prog.pk])
        resp = client.post(
            url,
            data={'torres_ejecutadas': 1, 'vehiculo': str(uuid_module.uuid4())},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        assert resp.status_code == 400


@pytest.mark.django_db
class TestEjecucionSemanalCuadrillaFormVehiculo:
    """`forms_pc.EjecucionSemanalCuadrillaForm` — queryset y validación del
    campo `vehiculo` (#270 sub-item B)."""

    def test_queryset_excluye_vehiculo_inactivo_no_asignado(self):
        from apps.cuadrillas.forms_pc import EjecucionSemanalCuadrillaForm

        _crear_vehiculo(placa='FORM-ACTIVO')
        inactivo = _crear_vehiculo(placa='FORM-INACTIVO', estado=Vehiculo.Estado.INACTIVO)
        form = EjecucionSemanalCuadrillaForm()
        ids = set(form.fields['vehiculo'].queryset.values_list('pk', flat=True))
        assert inactivo.pk not in ids

    def test_clean_vehiculo_rechaza_no_activo_si_no_es_el_ya_asignado(self):
        from apps.cuadrillas.forms_pc import EjecucionSemanalCuadrillaForm

        prog = _crear_programacion(torres=5)
        vehiculo_mant = _crear_vehiculo(
            placa='FORM-MANT', estado=Vehiculo.Estado.EN_MANTENIMIENTO,
        )
        form = EjecucionSemanalCuadrillaForm(
            data={'torres_ejecutadas': 1, 'vehiculo': str(vehiculo_mant.pk), 'observaciones': ''},
            instance=EjecucionSemanalCuadrilla(programacion=prog),
        )
        # queryset por defecto no incluye el vehículo en mantenimiento (no
        # está asignado a esta instancia todavía) -> el form lo rechaza a
        # nivel de ModelChoiceField antes de llegar a clean_vehiculo.
        assert not form.is_valid()
        assert 'vehiculo' in form.errors


# ===========================================================================
# 3.6 Gestión de personal en la ejecución (#270, sub-item C)
# ===========================================================================

@pytest.mark.django_db
class TestEjecucionSemanalPersonalModel:
    """Modelo `EjecucionSemanalPersonal` (through FK+FK, #270 sub-item C)."""

    def test_str_y_creacion_basica(self):
        prog = _crear_programacion(torres=5)
        ejecucion = EjecucionSemanalCuadrilla.objects.create(programacion=prog)
        personal = _crear_personal('PC-C-001', nombre='Juan Pérez')
        ep = EjecucionSemanalPersonal.objects.create(
            ejecucion=ejecucion, personal=personal, costo_dia='60000',
        )
        assert 'Juan Pérez' in str(ep)
        ep.refresh_from_db()
        assert ep.costo_dia == 60000

    def test_unique_together_rechaza_persona_duplicada_en_la_misma_ejecucion(self):
        """Edge — constraint de BD: la MISMA persona no puede estar dos veces
        en la misma ejecución (respaldo del chequeo de aplicación en la
        vista)."""
        prog = _crear_programacion(torres=5)
        ejecucion = EjecucionSemanalCuadrilla.objects.create(programacion=prog)
        personal = _crear_personal('PC-C-002', nombre='Duplicado Test')
        EjecucionSemanalPersonal.objects.create(ejecucion=ejecucion, personal=personal)
        with pytest.raises(IntegrityError):
            EjecucionSemanalPersonal.objects.create(ejecucion=ejecucion, personal=personal)


@pytest.mark.django_db
class TestEjecucionSemanalPersonalAgregarForm:
    """`forms_pc.EjecucionSemanalPersonalAgregarForm` — queryset filtrado
    (#270 sub-item C)."""

    def test_queryset_excluye_area_vacia_y_otra_area(self):
        from apps.cuadrillas.forms_pc import EjecucionSemanalPersonalAgregarForm

        construccion = _crear_personal('PC-FORM-001', nombre='De Construcción')
        legacy = _crear_personal('PC-FORM-002', nombre='Legacy Sin Area', area='')
        mantenimiento = _crear_personal(
            'PC-FORM-003', nombre='De Mantenimiento', area=AREA_MANTENIMIENTO,
        )
        inactivo = _crear_personal('PC-FORM-004', nombre='Inactivo', activo=False)

        form = EjecucionSemanalPersonalAgregarForm()
        ids = set(form.fields['personal'].queryset.values_list('pk', flat=True))
        assert construccion.pk in ids
        assert legacy.pk not in ids
        assert mantenimiento.pk not in ids
        assert inactivo.pk not in ids


@pytest.mark.django_db
class TestEjecucionPersonalAjax:
    """Vistas AJAX de `views_pc_ejecucion_personal.py` (#270 sub-item C):
    agregar (alta múltiple) / editar (costo_dia) / remover."""

    def test_happy_agregar_multiple_crea_ejecucion_y_filas_con_costo_snapshot(self):
        """Happy: la ejecución NO existe todavía (nadie guardó torres/vehículo
        primero) -> agregar personal la crea (upsert) y la tabla refleja
        nombre/documento/cargo/costo_dia tomado del Cargo."""
        client = Client()
        admin = _crear_usuario_admin()
        _login(client, admin)
        prog = _crear_programacion(torres=8)
        cargo = _crear_cargo(codigo='PC-CARGO-HAPPY', salario_base='75000')
        p1 = _crear_personal('PC-H-001', nombre='Ana Torres', cargo=cargo)
        p2 = _crear_personal('PC-H-002', nombre='Luis Peña', cargo=cargo)

        assert not EjecucionSemanalCuadrilla.objects.filter(programacion=prog).exists()

        url = reverse(
            'construccion:programacion_cuadrilla_ejecucion_personal_agregar',
            args=[prog.pk],
        )
        resp = client.post(
            url, data={'personal': [str(p1.pk), str(p2.pk)]},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        assert resp.status_code == 200
        payload = json.loads(resp.content)
        assert payload['ok'] is True
        assert len(payload['agregados']) == 2
        nombres = {fila['nombre'] for fila in payload['agregados']}
        assert nombres == {'Ana Torres', 'Luis Peña'}
        fila_ana = next(f for f in payload['agregados'] if f['nombre'] == 'Ana Torres')
        assert fila_ana['documento'] == 'PC-H-001'
        assert float(fila_ana['costo_dia']) == 75000.0

        # BD: la ejecución se creó (upsert) y tiene 2 filas de personal.
        ejecucion = EjecucionSemanalCuadrilla.objects.get(programacion=prog)
        assert ejecucion.personal_asignado.count() == 2

    def test_edge_agregar_persona_duplicada_no_crea_fila_extra(self):
        """Edge — agregar la MISMA persona dos veces (llamadas separadas):
        la segunda va a `duplicados`, no crea una segunda fila."""
        client = Client()
        admin = _crear_usuario_admin()
        _login(client, admin)
        prog = _crear_programacion(torres=8)
        personal = _crear_personal('PC-DUP-001', nombre='Repetido')
        url = reverse(
            'construccion:programacion_cuadrilla_ejecucion_personal_agregar',
            args=[prog.pk],
        )
        client.post(url, data={'personal': [str(personal.pk)]},
                    HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        resp2 = client.post(url, data={'personal': [str(personal.pk)]},
                             HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        assert resp2.status_code == 200
        payload = json.loads(resp2.content)
        assert payload['agregados'] == []
        assert payload['duplicados'] == [str(personal.pk)]

        ejecucion = EjecucionSemanalCuadrilla.objects.get(programacion=prog)
        assert ejecucion.personal_asignado.count() == 1

    def test_edge_area_vacia_dato_legacy_no_se_puede_agregar(self):
        """Edge — dato legacy: un `PersonalCuadrilla` con `area=''` (colaborador
        pre-#186 sin área asignada) NO se puede agregar -> va a `no_validos`,
        400 si es el ÚNICO id enviado."""
        client = Client()
        admin = _crear_usuario_admin()
        _login(client, admin)
        prog = _crear_programacion(torres=8)
        legacy = _crear_personal('PC-LEGACY-001', nombre='Legacy Sin Area', area='')
        url = reverse(
            'construccion:programacion_cuadrilla_ejecucion_personal_agregar',
            args=[prog.pk],
        )
        resp = client.post(url, data={'personal': [str(legacy.pk)]},
                            HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert resp.status_code == 400

    def test_edge_remover_el_unico_miembro_deja_ejecucion_sin_personal(self):
        """Edge — remover el único miembro asignado: la ejecución sigue
        existiendo, solo queda sin personal (no se borra la ejecución)."""
        client = Client()
        admin = _crear_usuario_admin()
        _login(client, admin)
        prog = _crear_programacion(torres=8)
        ejecucion = EjecucionSemanalCuadrilla.objects.create(
            programacion=prog, torres_ejecutadas=3,
        )
        personal = _crear_personal('PC-REM-001', nombre='Único Miembro')
        ep = EjecucionSemanalPersonal.objects.create(
            ejecucion=ejecucion, personal=personal, costo_dia='50000',
        )
        url = reverse(
            'construccion:programacion_cuadrilla_ejecucion_personal_remover',
            args=[ep.pk],
        )
        resp = client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert resp.status_code == 200
        payload = json.loads(resp.content)
        assert payload['ok'] is True

        ejecucion.refresh_from_db()
        assert ejecucion.personal_asignado.count() == 0
        # La ejecución (y sus otros datos) sigue intacta.
        assert ejecucion.torres_ejecutadas == 3

    def test_happy_editar_costo_dia_persiste_el_nuevo_valor(self):
        client = Client()
        admin = _crear_usuario_admin()
        _login(client, admin)
        prog = _crear_programacion(torres=8)
        ejecucion = EjecucionSemanalCuadrilla.objects.create(programacion=prog)
        personal = _crear_personal('PC-EDIT-001', nombre='A Editar')
        ep = EjecucionSemanalPersonal.objects.create(
            ejecucion=ejecucion, personal=personal, costo_dia='50000',
        )
        url = reverse(
            'construccion:programacion_cuadrilla_ejecucion_personal_editar',
            args=[ep.pk],
        )
        resp = client.post(url, data={'costo_dia': '65000.50'},
                            HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert resp.status_code == 200
        payload = json.loads(resp.content)
        assert payload['ok'] is True
        assert float(payload['fila']['costo_dia']) == 65000.50

        ep.refresh_from_db()
        assert ep.costo_dia == pytest.approx(65000.50)

    def test_edge_editar_costo_dia_negativo_400(self):
        """Edge — costo_dia negativo se rechaza (400), no se persiste."""
        client = Client()
        admin = _crear_usuario_admin()
        _login(client, admin)
        prog = _crear_programacion(torres=8)
        ejecucion = EjecucionSemanalCuadrilla.objects.create(programacion=prog)
        personal = _crear_personal('PC-EDIT-NEG-001', nombre='Costo Negativo')
        ep = EjecucionSemanalPersonal.objects.create(
            ejecucion=ejecucion, personal=personal, costo_dia='50000',
        )
        url = reverse(
            'construccion:programacion_cuadrilla_ejecucion_personal_editar',
            args=[ep.pk],
        )
        resp = client.post(url, data={'costo_dia': '-100'},
                            HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert resp.status_code == 400
        ep.refresh_from_db()
        assert ep.costo_dia == 50000


# ===========================================================================
# 3.5. Asistencia semanal por persona/día (#270, sub-item D) — DEPENDE del
# roster de C (`EjecucionSemanalPersonal`).
# ===========================================================================

def _crear_fila_roster(personal=None, ejecucion=None, prog=None):
    """Helper D — arma una fila `EjecucionSemanalPersonal` (roster de C)
    lista para colgarle asistencia. Si no se pasa `ejecucion`/`prog`, crea
    ambos."""
    if ejecucion is None:
        if prog is None:
            prog = _crear_programacion(torres=8)
        ejecucion = EjecucionSemanalCuadrilla.objects.create(programacion=prog)
    if personal is None:
        personal = _crear_personal('PC-D-DEFAULT', nombre='Default Asistencia')
    return EjecucionSemanalPersonal.objects.create(ejecucion=ejecucion, personal=personal)


@pytest.mark.django_db
class TestAsistenciaEjecucionSemanalModel:
    """Modelo `AsistenciaEjecucionSemanal` (#270 sub-item D)."""

    def test_str_y_creacion_basica(self):
        ep = _crear_fila_roster()
        registro = AsistenciaEjecucionSemanal.objects.create(
            ejecucion=ep.ejecucion, personal=ep.personal,
            fecha='2026-04-27', tipo_novedad=Asistencia.TipoNovedad.PRESENTE,
            horas_trabajadas='8.0',
        )
        assert 'Default Asistencia' in str(registro)
        assert '2026-04-27' in str(registro)

    def test_unique_together_rechaza_mismo_dia_dos_veces(self):
        """Edge — constraint de BD: (ejecucion, personal, fecha) es único."""
        ep = _crear_fila_roster()
        AsistenciaEjecucionSemanal.objects.create(
            ejecucion=ep.ejecucion, personal=ep.personal, fecha='2026-04-27',
        )
        with pytest.raises(IntegrityError):
            AsistenciaEjecucionSemanal.objects.create(
                ejecucion=ep.ejecucion, personal=ep.personal, fecha='2026-04-27',
            )

    def test_reusa_choices_de_asistencia_no_las_redefine(self):
        """El enum de tipo_novedad ES el mismo objeto que Asistencia.TipoNovedad
        (issue explícito: reusar, no redefinir)."""
        field = AsistenciaEjecucionSemanal._meta.get_field('tipo_novedad')
        assert dict(field.choices) == dict(Asistencia.TipoNovedad.choices)


@pytest.mark.django_db
class TestAsistenciaEjecucionSemanalForm:
    """`forms_pc.AsistenciaEjecucionSemanalForm` (#270 sub-item D)."""

    def test_clean_fuerza_horas_trabajadas_a_cero_si_tipo_no_es_presente(self):
        """Edge del dominio: tipo_novedad != PRESENTE con horas_trabajadas > 0
        enviado -- SE LIMPIA (no es error, se normaliza a 0)."""
        from apps.cuadrillas.forms_pc import AsistenciaEjecucionSemanalForm

        form = AsistenciaEjecucionSemanalForm(data={
            'tipo_novedad': Asistencia.TipoNovedad.VACACIONES,
            'horas_trabajadas': '8.0',
            'horas_extra': '0',
        })
        assert form.is_valid(), form.errors
        assert form.cleaned_data['horas_trabajadas'] == 0

    def test_horas_extra_sin_horas_trabajadas_se_permite(self):
        """Edge — horas_extra > 0 con horas_trabajadas = 0: PERMITIDO
        (ej. llamado de emergencia un día de descanso)."""
        from apps.cuadrillas.forms_pc import AsistenciaEjecucionSemanalForm

        form = AsistenciaEjecucionSemanalForm(data={
            'tipo_novedad': Asistencia.TipoNovedad.PRESENTE,
            'horas_trabajadas': '0',
            'horas_extra': '3.0',
        })
        assert form.is_valid(), form.errors
        assert form.cleaned_data['horas_trabajadas'] == 0
        assert form.cleaned_data['horas_extra'] == 3.0

    def test_horas_negativas_rechazadas(self):
        from apps.cuadrillas.forms_pc import AsistenciaEjecucionSemanalForm

        form = AsistenciaEjecucionSemanalForm(data={
            'tipo_novedad': Asistencia.TipoNovedad.PRESENTE,
            'horas_trabajadas': '-1',
            'horas_extra': '0',
        })
        assert not form.is_valid()
        assert 'horas_trabajadas' in form.errors


@pytest.mark.django_db
class TestAsistenciaEjecucionAjax:
    """Vista AJAX `views_pc_ejecucion_asistencia.
    AsistenciaEjecucionSemanalGuardarView` (#270 sub-item D)."""

    def _url(self, ep, fecha):
        return reverse(
            'construccion:programacion_cuadrilla_ejecucion_asistencia_guardar',
            args=[ep.pk, fecha],
        )

    def test_happy_7_dias_x_2_personas_default_presente_horas_visibles(self):
        """Happy: 7 días × 2 personas, tipo_novedad por defecto PRESENTE,
        horas visibles en la respuesta y persistidas."""
        client = Client()
        admin = _crear_usuario_admin()
        _login(client, admin)
        prog = _crear_programacion(anio=2026, semana=18, torres=8)
        ejecucion = EjecucionSemanalCuadrilla.objects.create(programacion=prog)
        p1 = _crear_personal('PC-D-H-001', nombre='Persona Uno')
        p2 = _crear_personal('PC-D-H-002', nombre='Persona Dos')
        ep1 = EjecucionSemanalPersonal.objects.create(ejecucion=ejecucion, personal=p1)
        ep2 = EjecucionSemanalPersonal.objects.create(ejecucion=ejecucion, personal=p2)

        # Semana ISO 2026-S18 = 2026-04-27 (lunes) a 2026-05-03 (domingo).
        dias = [date.fromisocalendar(2026, 18, d) for d in range(1, 8)]
        for ep in (ep1, ep2):
            for dia in dias:
                resp = client.post(
                    self._url(ep, dia.isoformat()),
                    data={'tipo_novedad': 'PRESENTE', 'horas_trabajadas': '8.0', 'horas_extra': '0'},
                    HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                )
                assert resp.status_code == 200, resp.content
                payload = json.loads(resp.content)
                assert payload['ok'] is True
                assert payload['registro']['tipo_novedad'] == 'PRESENTE'
                assert float(payload['registro']['horas_trabajadas']) == 8.0

        assert AsistenciaEjecucionSemanal.objects.filter(ejecucion=ejecucion).count() == 14

    def test_edge_persona_agregada_a_mitad_de_semana_sin_backfill(self):
        """Edge — agregar una persona al roster (C) NO crea automáticamente
        registros de asistencia para los días previos: quedan sin fila hasta
        que alguien guarda explícitamente."""
        ep = _crear_fila_roster()
        assert AsistenciaEjecucionSemanal.objects.filter(
            ejecucion=ep.ejecucion, personal=ep.personal,
        ).count() == 0

    def test_edge_tipo_novedad_no_presente_limpia_horas_trabajadas(self):
        """Edge — tipo_novedad != PRESENTE con horas_trabajadas enviado > 0:
        se limpia (fuerza a 0) en vez de rechazar con 400."""
        client = Client()
        admin = _crear_usuario_admin()
        _login(client, admin)
        ep = _crear_fila_roster()
        prog = ep.ejecucion.programacion
        fecha = date.fromisocalendar(prog.anio, prog.semana, 3)
        resp = client.post(
            self._url(ep, fecha.isoformat()),
            data={'tipo_novedad': 'INCAPACIDAD', 'horas_trabajadas': '8.0', 'horas_extra': '0'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        assert resp.status_code == 200, resp.content
        payload = json.loads(resp.content)
        assert payload['registro']['tipo_novedad'] == 'INCAPACIDAD'
        assert float(payload['registro']['horas_trabajadas']) == 0.0

        registro = AsistenciaEjecucionSemanal.objects.get(
            ejecucion=ep.ejecucion, personal=ep.personal, fecha=fecha,
        )
        assert registro.horas_trabajadas == 0

    def test_edge_horas_extra_sin_horas_trabajadas_se_guarda(self):
        """Edge — horas_extra > 0 con horas_trabajadas = 0: se persiste tal
        cual, sin error (ver docstring del modelo)."""
        client = Client()
        admin = _crear_usuario_admin()
        _login(client, admin)
        ep = _crear_fila_roster()
        prog = ep.ejecucion.programacion
        fecha = date.fromisocalendar(prog.anio, prog.semana, 6)
        resp = client.post(
            self._url(ep, fecha.isoformat()),
            data={'tipo_novedad': 'PRESENTE', 'horas_trabajadas': '0', 'horas_extra': '4.0'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        assert resp.status_code == 200, resp.content
        payload = json.loads(resp.content)
        assert float(payload['registro']['horas_trabajadas']) == 0.0
        assert float(payload['registro']['horas_extra']) == 4.0

    def test_edge_fecha_fuera_de_la_semana_iso_400(self):
        """Edge — una fecha que NO pertenece a la semana ISO de la
        programación se rechaza con 400 (no se persiste nada)."""
        client = Client()
        admin = _crear_usuario_admin()
        _login(client, admin)
        prog = _crear_programacion(anio=2026, semana=18, torres=8)
        ep = _crear_fila_roster(prog=prog)
        fecha_fuera = date.fromisocalendar(2026, 19, 1)  # semana SIGUIENTE
        resp = client.post(
            self._url(ep, fecha_fuera.isoformat()),
            data={'tipo_novedad': 'PRESENTE', 'horas_trabajadas': '8.0', 'horas_extra': '0'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        assert resp.status_code == 400
        assert not AsistenciaEjecucionSemanal.objects.filter(ejecucion=ep.ejecucion).exists()

    def test_guardar_dos_veces_el_mismo_dia_actualiza_no_duplica(self):
        """Upsert: guardar la MISMA celda dos veces actualiza el registro
        existente, no crea un segundo (respalda el unique_together)."""
        client = Client()
        admin = _crear_usuario_admin()
        _login(client, admin)
        ep = _crear_fila_roster()
        prog = ep.ejecucion.programacion
        fecha = date.fromisocalendar(prog.anio, prog.semana, 2)
        url = self._url(ep, fecha.isoformat())
        client.post(url, data={'tipo_novedad': 'PRESENTE', 'horas_trabajadas': '8.0', 'horas_extra': '0'},
                    HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        resp2 = client.post(url, data={'tipo_novedad': 'PRESENTE', 'horas_trabajadas': '4.0', 'horas_extra': '1.0'},
                             HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert resp2.status_code == 200
        assert AsistenciaEjecucionSemanal.objects.filter(
            ejecucion=ep.ejecucion, personal=ep.personal, fecha=fecha,
        ).count() == 1
        registro = AsistenciaEjecucionSemanal.objects.get(
            ejecucion=ep.ejecucion, personal=ep.personal, fecha=fecha,
        )
        assert float(registro.horas_trabajadas) == 4.0
        assert float(registro.horas_extra) == 1.0

    def test_dato_legacy_personal_area_vacia_ya_en_roster_puede_registrar_asistencia(self):
        """Dato legacy (mismo criterio que TestDatoLegacy del módulo): un
        `PersonalCuadrilla` con `area=''` (colaborador pre-#186) que YA
        estaba en el roster de una ejecución -- agregado antes de que #270
        existiera, vía fixture/admin -- debe poder registrar asistencia sin
        romperse, aunque hoy quedaría excluido del Select2 de alta de C."""
        client = Client()
        admin = _crear_usuario_admin()
        _login(client, admin)
        legacy = _crear_personal('PC-D-LEGACY-001', nombre='Legacy Sin Area', area='')
        ep = _crear_fila_roster(personal=legacy)
        prog = ep.ejecucion.programacion
        fecha = date.fromisocalendar(prog.anio, prog.semana, 4)
        resp = client.post(
            self._url(ep, fecha.isoformat()),
            data={'tipo_novedad': 'PRESENTE', 'horas_trabajadas': '8.0', 'horas_extra': '0'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        assert resp.status_code == 200, resp.content
        assert AsistenciaEjecucionSemanal.objects.filter(
            ejecucion=ep.ejecucion, personal=legacy, fecha=fecha,
        ).exists()


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
