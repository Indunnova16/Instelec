"""
Tests del issue #269 — selector real de torres en Programación de Cuadrillas.

Antes de este fix, "Torres programadas" (`ProgramacionSemanalCuadrilla.
torres_programadas`) era un `PositiveIntegerField` -- un CONTEO manual, sin
ninguna relación a las torres reales del proyecto (`TorreConstruccion`). Este
fix agrega un M2M ADITIVO (`torres`) puramente informativo/trazabilidad; el
conteo manual se mantiene 100% intacto (así lo exige el corpus de goldens de
``journeys/Instelec.yaml``: b2_crear_form_render_200, m1_crear_programacion_
semanal, m2_registrar_ejecucion_rendimiento -- ninguno setea `proyecto` ni
`torres`, todos fillean `torres_programadas` directo).

Cubre:
  1. Modelo: el M2M existe, es opcional, no afecta `torres_programadas` ni
     `rendimiento_pct` (los goldens del corpus siguen intactos).
  2. Form: el queryset de `torres` depende de `proyecto` (vacío sin proyecto,
     filtrado a `aplica=True, anulada=False` con proyecto) y valida un POST
     real con torres elegidas.
  3. Endpoint `TorresActivasFragmentoView`: fragmento HTML de <option> con
     las torres activas del proyecto vía querystring `?proyecto=<uuid>`;
     excluye anuladas y no-aplica; robusto a proyecto ausente/uuid inválido
     (siempre HTTP 200, nunca 500).
  4. E2E: crear una programación vía POST eligiendo proyecto + torres reales
     -> se persiste el M2M y `torres_programadas` queda con el valor manual
     tecleado (no derivado de las torres elegidas).
  5. Dato "legacy": una `ProgramacionSemanalCuadrilla` creada ANTES de este
     fix (sin tocar `torres`, que nace vacío por ser M2M nuevo) sigue
     cargando y editándose sin error -- el M2M vacío no rompe nada aguas
     abajo (detalle, form de edición, rendimiento_pct).

Discovery (igual que tests_pc.py/tests_issue_209.py): pytest está limitado a
``tests/`` por pyproject.toml; ejecutar vía path explícito:

    ./venv/bin/python3 -m pytest apps/cuadrillas/tests_issue_269.py -v
"""
import pytest
from django.urls import reverse

from apps.contratos.models import Contrato
from apps.construccion.models import ProyectoConstruccion, TorreConstruccion
from apps.cuadrillas.models import Cuadrilla
from apps.cuadrillas.models_pc import ProgramacionSemanalCuadrilla
from apps.cuadrillas.forms_pc import ProgramacionSemanalCuadrillaForm
from apps.usuarios.models import Usuario


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _crear_cuadrilla(codigo='CUA-269-001'):
    return Cuadrilla.objects.create(codigo=codigo, nombre='Cuadrilla #269', activa=True)


def _crear_proyecto(codigo='TEST-269-001'):
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo=codigo,
        nombre='Contrato test #269',
        cliente='Test Cliente #269',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto #269 test',
        estado='EJECUCION',
    )


def _crear_torre(proyecto, numero, aplica=True, anulada=False):
    return TorreConstruccion.objects.create(
        proyecto=proyecto, numero=numero, aplica=aplica, anulada=anulada,
    )


def _crear_usuario_admin(email='admin_269@test.local'):
    return Usuario.objects.create_user(
        email=email,
        password='ClaudeQA2026!',
        first_name='Admin',
        last_name='269',
        rol=Usuario.Rol.ADMIN_CONSTRUCCION,
        is_active=True,
    )


def _login(client, usuario):
    ok = client.login(username=usuario.email, password='ClaudeQA2026!')
    assert ok, 'login del usuario admin falló (revisar credenciales/backend)'


# ===========================================================================
# 1. Modelo — M2M aditivo, no toca torres_programadas/rendimiento_pct
# ===========================================================================

@pytest.mark.django_db
class TestModeloTorresM2M:

    def test_torres_m2m_existe_y_es_opcional(self):
        """Crear una programación SIN tocar 'torres' no falla (blank=True)."""
        cuadrilla = _crear_cuadrilla()
        prog = ProgramacionSemanalCuadrilla.objects.create(
            cuadrilla=cuadrilla, anio=2026, semana=21, torres_programadas=10,
        )
        assert prog.torres.count() == 0

    def test_agregar_torres_no_altera_torres_programadas(self):
        """El M2M es ADITIVO/informativo: agregar torres reales NO cambia
        el conteo manual `torres_programadas` (contrato del fix_propuesto
        de F2 -- invierte_comportamiento=False)."""
        proyecto = _crear_proyecto()
        t1 = _crear_torre(proyecto, 'T-1')
        t2 = _crear_torre(proyecto, 'T-2')
        cuadrilla = _crear_cuadrilla()
        prog = ProgramacionSemanalCuadrilla.objects.create(
            cuadrilla=cuadrilla, proyecto=proyecto, anio=2026, semana=22,
            torres_programadas=10,
        )
        prog.torres.set([t1, t2])
        prog.refresh_from_db()
        assert prog.torres.count() == 2
        assert prog.torres_programadas == 10  # intacto, NO derivado del M2M

    def test_rendimiento_pct_no_se_ve_afectado_por_torres_m2m(self):
        """El cálculo de rendimiento sigue gobernado 100% por
        torres_programadas/torres_ejecutadas -- el M2M nuevo no participa."""
        from apps.cuadrillas.models_pc import EjecucionSemanalCuadrilla

        proyecto = _crear_proyecto()
        t1 = _crear_torre(proyecto, 'T-1')
        cuadrilla = _crear_cuadrilla()
        prog = ProgramacionSemanalCuadrilla.objects.create(
            cuadrilla=cuadrilla, proyecto=proyecto, anio=2026, semana=23,
            torres_programadas=10,
        )
        prog.torres.set([t1])  # solo 1 torre "real" elegida
        eje = EjecucionSemanalCuadrilla.objects.create(programacion=prog, torres_ejecutadas=7)
        assert eje.rendimiento_pct == 70.0  # 7/10, NO 7/1


# ===========================================================================
# 2. Form — queryset dependiente de 'proyecto' + validación de POST real
# ===========================================================================

@pytest.mark.django_db
class TestFormTorresQueryset:

    def test_sin_proyecto_queryset_torres_vacio(self):
        """Form sin datos (create GET): 'torres' nace con queryset vacío --
        el select no debe ofrecer torres de NINGÚN proyecto hasta elegir uno
        (issue #269: 'campo torres oculto/vacío hasta elegir proyecto')."""
        form = ProgramacionSemanalCuadrillaForm()
        assert form.fields['torres'].queryset.count() == 0

    def test_con_proyecto_en_data_queryset_filtra_aplica_true_anulada_false(self):
        """Bound form (POST) con 'proyecto' en los datos: el queryset de
        'torres' se resuelve DESDE el POST (no solo desde instance), y
        excluye torres no-aplica y anuladas -- filtro confirmado por F2
        (aplica=True AND anulada=False, más estricto que ambas fuentes
        legacy por separado)."""
        proyecto = _crear_proyecto()
        t_ok = _crear_torre(proyecto, 'T-1', aplica=True, anulada=False)
        _crear_torre(proyecto, 'T-2', aplica=False, anulada=False)  # no aplica
        _crear_torre(proyecto, 'T-3', aplica=True, anulada=True)    # anulada
        cuadrilla = _crear_cuadrilla()

        form = ProgramacionSemanalCuadrillaForm(data={
            'cuadrilla': str(cuadrilla.pk),
            'proyecto': str(proyecto.pk),
            'anio': '2026', 'semana': '24', 'torres_programadas': '5',
        })
        qs_ids = set(form.fields['torres'].queryset.values_list('pk', flat=True))
        assert qs_ids == {t_ok.pk}

    def test_post_con_torres_reales_valida_y_guarda(self):
        """Submit real con torres elegidas: el ModelMultipleChoiceField
        valida los ids contra el queryset resuelto desde el POST -- NO debe
        fallar con 'esa opción no es una de las disponibles' (bug que
        ocurriría si el queryset quedara en .none() a secas)."""
        proyecto = _crear_proyecto()
        t1 = _crear_torre(proyecto, 'T-1')
        t2 = _crear_torre(proyecto, 'T-2')
        cuadrilla = _crear_cuadrilla()

        form = ProgramacionSemanalCuadrillaForm(data={
            'cuadrilla': str(cuadrilla.pk),
            'proyecto': str(proyecto.pk),
            'anio': '2026', 'semana': '25', 'torres_programadas': '8',
            'torres': [str(t1.pk), str(t2.pk)],
        })
        assert form.is_valid(), form.errors
        prog = form.save()
        assert set(prog.torres.values_list('pk', flat=True)) == {t1.pk, t2.pk}
        assert prog.torres_programadas == 8


# ===========================================================================
# 3. Endpoint TorresActivasFragmentoView — fragmento HTML para HTMX
# ===========================================================================

@pytest.mark.django_db
class TestTorresActivasFragmentoView:

    def test_sin_proyecto_devuelve_fragmento_vacio_200(self):
        usuario = _crear_usuario_admin()
        from django.test import Client
        client = Client()
        _login(client, usuario)
        url = reverse('construccion:torres_activas_fragmento')
        resp = client.get(url)
        assert resp.status_code == 200
        assert resp.content.decode() == ''

    def test_proyecto_uuid_invalido_devuelve_200_no_500(self):
        """Robustez (#269 F3, mismo criterio que DashboardGraficasDataView):
        un valor manipulado/stale en el querystring nunca debe tumbar la
        vista con un 500."""
        usuario = _crear_usuario_admin()
        from django.test import Client
        client = Client()
        _login(client, usuario)
        url = reverse('construccion:torres_activas_fragmento')
        resp = client.get(url, {'proyecto': 'no-es-un-uuid'})
        assert resp.status_code == 200
        assert resp.content.decode() == ''

    def test_proyecto_real_devuelve_options_solo_activas(self):
        proyecto = _crear_proyecto()
        t_ok1 = _crear_torre(proyecto, 'T-1', aplica=True, anulada=False)
        t_ok2 = _crear_torre(proyecto, 'T-2', aplica=True, anulada=False)
        t_no_aplica = _crear_torre(proyecto, 'T-3', aplica=False, anulada=False)
        t_anulada = _crear_torre(proyecto, 'T-4', aplica=True, anulada=True)

        usuario = _crear_usuario_admin()
        from django.test import Client
        client = Client()
        _login(client, usuario)
        url = reverse('construccion:torres_activas_fragmento')
        resp = client.get(url, {'proyecto': str(proyecto.pk)})

        assert resp.status_code == 200
        body = resp.content.decode()
        assert f'value="{t_ok1.pk}"' in body
        assert f'value="{t_ok2.pk}"' in body
        assert f'value="{t_no_aplica.pk}"' not in body
        assert f'value="{t_anulada.pk}"' not in body
        assert 'T-1' in body and 'T-2' in body

    def test_otro_proyecto_no_mezcla_torres(self):
        """Edge case de scoping: torres de OTRO proyecto no aparecen."""
        proyecto_a = _crear_proyecto(codigo='TEST-269-A')
        proyecto_b = _crear_proyecto(codigo='TEST-269-B')
        t_a = _crear_torre(proyecto_a, 'T-1')
        t_b = _crear_torre(proyecto_b, 'T-1')  # mismo numero, otro proyecto

        usuario = _crear_usuario_admin()
        from django.test import Client
        client = Client()
        _login(client, usuario)
        url = reverse('construccion:torres_activas_fragmento')
        resp = client.get(url, {'proyecto': str(proyecto_a.pk)})
        body = resp.content.decode()
        assert f'value="{t_a.pk}"' in body
        assert f'value="{t_b.pk}"' not in body


# ===========================================================================
# 4. E2E — flujo completo de creación con proyecto + torres reales
# ===========================================================================

@pytest.mark.django_db
class TestCrearProgramacionConTorres:

    def test_crear_via_post_persiste_torres_y_conserva_conteo_manual(self):
        proyecto = _crear_proyecto()
        t1 = _crear_torre(proyecto, 'T-1')
        t2 = _crear_torre(proyecto, 'T-2')
        cuadrilla = _crear_cuadrilla()
        usuario = _crear_usuario_admin()

        from django.test import Client
        client = Client()
        _login(client, usuario)

        url = reverse('construccion:programacion_cuadrilla_crear')
        resp = client.post(url, {
            'cuadrilla': str(cuadrilla.pk),
            'proyecto': str(proyecto.pk),
            'anio': '2026', 'semana': '26',
            'torres_programadas': '15',
            'torres': [str(t1.pk), str(t2.pk)],
        })
        assert resp.status_code == 302, getattr(resp, 'context', None) and resp.context['form'].errors

        prog = ProgramacionSemanalCuadrilla.objects.get(cuadrilla=cuadrilla, anio=2026, semana=26)
        assert prog.torres_programadas == 15  # conteo manual intacto
        assert set(prog.torres.values_list('pk', flat=True)) == {t1.pk, t2.pk}

    def test_crear_sin_proyecto_ni_torres_sigue_funcionando(self):
        """Camino ORIGINAL (goldens del corpus: m1_crear_programacion_semanal
        NO setea proyecto ni torres) -- debe seguir funcionando exactamente
        igual que antes del fix."""
        cuadrilla = _crear_cuadrilla()
        usuario = _crear_usuario_admin()

        from django.test import Client
        client = Client()
        _login(client, usuario)

        url = reverse('construccion:programacion_cuadrilla_crear')
        resp = client.post(url, {
            'cuadrilla': str(cuadrilla.pk),
            'anio': '2026', 'semana': '27',
            'torres_programadas': '10',
        })
        assert resp.status_code == 302

        prog = ProgramacionSemanalCuadrilla.objects.get(cuadrilla=cuadrilla, anio=2026, semana=27)
        assert prog.torres_programadas == 10
        assert prog.torres.count() == 0
        assert prog.proyecto is None


# ===========================================================================
# 5. Dato "legacy" — registro creado ANTES del fix (M2M vacío por diseño)
# ===========================================================================

@pytest.mark.django_db
class TestRegistroLegacySinTorresM2M:
    """Simula una `ProgramacionSemanalCuadrilla` que existía en prod ANTES
    de este fix: se creó sin ningún dato en el M2M nuevo (imposible que lo
    tuviera -- el campo no existía). El fix debe ser 100% retrocompatible
    con esas filas."""

    def test_registro_legacy_carga_en_detalle_sin_error(self):
        proyecto = _crear_proyecto()
        cuadrilla = _crear_cuadrilla()
        prog_legacy = ProgramacionSemanalCuadrilla.objects.create(
            cuadrilla=cuadrilla, proyecto=proyecto, anio=2025, semana=40,
            torres_programadas=6,
            actividades_programadas='Programación histórica pre-#269',
        )
        # Nunca se tocó 'torres' -- exactamente el estado de un registro legacy.
        assert prog_legacy.torres.count() == 0

        usuario = _crear_usuario_admin()
        from django.test import Client
        client = Client()
        _login(client, usuario)

        url = reverse('construccion:programacion_cuadrilla_detalle', kwargs={'pk': prog_legacy.pk})
        resp = client.get(url)
        assert resp.status_code == 200

    def test_registro_legacy_se_puede_editar_sin_error_y_preselecciona_torres_vacio(self):
        proyecto = _crear_proyecto()
        _crear_torre(proyecto, 'T-1')  # torre existe pero el legacy no la tiene asociada
        cuadrilla = _crear_cuadrilla()
        prog_legacy = ProgramacionSemanalCuadrilla.objects.create(
            cuadrilla=cuadrilla, proyecto=proyecto, anio=2025, semana=41,
            torres_programadas=4,
        )
        usuario = _crear_usuario_admin()
        from django.test import Client
        client = Client()
        _login(client, usuario)

        url = reverse('construccion:programacion_cuadrilla_editar', kwargs={'pk': prog_legacy.pk})
        resp = client.get(url)
        assert resp.status_code == 200
        # El form de edición debe traer el queryset de torres del proyecto ya
        # asociado (vía instance.proyecto_id), no vacío -- el usuario SÍ puede
        # empezar a poblar el M2M en un registro legacy.
        assert resp.context['form'].fields['torres'].queryset.count() == 1
        # Pero nada preseleccionado (initial vacío -- el M2M legacy está vacío).
        assert list(resp.context['form'].initial.get('torres', [])) == []
