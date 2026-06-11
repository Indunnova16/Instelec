"""B1 — tests para ActividadFinalTorre.

Cubre:
- Happy path: crear ActividadFinalTorre, togglear varios bools, pct_avance correcto.
- Validación lógica: G sin F, K sin J, dossier sin todos.
- Dato legacy: torre creada antes de B1 → ActividadFinalTorre vacío funciona.
- E2E del BLUEPRINT: `b1_actividades_finales_matriz_render_y_toggle`.
"""
import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.contratos.models import Contrato
from apps.construccion.models import ProyectoConstruccion, TorreConstruccion
from apps.construccion.models_b1_actividades_finales import (
    ACTIVIDAD_CAMPOS,
    ActividadFinalTorre,
)


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------

@pytest.fixture
def proyecto_construccion(db):
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-B1-AF-001',
        nombre='Proyecto test B1 Actividades Finales',
        cliente='Test',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto LT 230kV — Test B1',
        estado='EJECUCION',
    )


@pytest.fixture
def torre_legacy(proyecto_construccion):
    """Torre creada SIN ActividadFinalTorre — simula dato legacy pre-B1.
    La vista debe auto-crear la instancia defensivamente."""
    return TorreConstruccion.objects.create(
        proyecto=proyecto_construccion,
        numero='E1-LEGACY',
    )


@pytest.fixture
def torre_con_actividades(proyecto_construccion):
    torre = TorreConstruccion.objects.create(
        proyecto=proyecto_construccion, numero='E2',
    )
    af = ActividadFinalTorre.objects.create(torre=torre)
    return torre, af


# ----------------------------------------------------------------------
# Tests modelo
# ----------------------------------------------------------------------

class TestActividadFinalTorreHappy:

    def test_creacion_y_pct_inicial(self, torre_con_actividades):
        _, af = torre_con_actividades
        assert af.actividades_completas == 0
        assert af.pct_avance == 0.0
        assert af.estado_semaforo == 'NO_INICIADO'
        assert af.total_actividades == 13

    def test_toggle_varias_actividades_pct_correcto(self, torre_con_actividades):
        _, af = torre_con_actividades
        # Marcar 4/13 actividades en orden lógico
        af.pruebas_electricas = True
        af.visita_retie = True
        af.certificado_retie = True
        af.empalmes_subestacion = True
        af.save()

        af.refresh_from_db()
        assert af.actividades_completas == 4
        assert af.pct_avance == pytest.approx(4 / 13 * 100)
        assert af.estado_semaforo == 'EN_PROCESO'

    def test_completar_todas_pct_100_y_completado(self, torre_con_actividades):
        _, af = torre_con_actividades
        # Setear todas EXCEPTO dossier primero
        for campo in ACTIVIDAD_CAMPOS:
            if campo != 'dossier':
                setattr(af, campo, True)
        af.save()
        af.refresh_from_db()
        assert af.pct_avance == pytest.approx(12 / 13 * 100)

        # Ahora sí podemos marcar dossier
        af.dossier = True
        af.save()
        af.refresh_from_db()
        assert af.actividades_completas == 13
        assert af.pct_avance == 100.0
        assert af.estado_semaforo == 'COMPLETADO'

    def test_proxima_actividad_pendiente(self, torre_con_actividades):
        _, af = torre_con_actividades
        # Sin nada → debe sugerir pruebas_electricas (primer paso del flujo)
        assert af.proxima_actividad_pendiente() == 'pruebas_electricas'
        af.pruebas_electricas = True
        af.save()
        af.refresh_from_db()
        assert af.proxima_actividad_pendiente() == 'visita_retie'


class TestActividadFinalTorreValidaciones:

    def test_certificado_retie_sin_visita_falla(self, torre_con_actividades):
        """G no puede activarse sin F."""
        _, af = torre_con_actividades
        af.certificado_retie = True
        with pytest.raises(ValidationError) as excinfo:
            af.save()
        assert 'certificado_retie' in excinfo.value.message_dict

    def test_certificado_retie_con_visita_pasa(self, torre_con_actividades):
        _, af = torre_con_actividades
        af.visita_retie = True
        af.certificado_retie = True
        af.save()  # no debe fallar
        af.refresh_from_db()
        assert af.certificado_retie is True

    def test_paz_salvo_propietarios_sin_actas_falla(self, torre_con_actividades):
        """K requiere J."""
        _, af = torre_con_actividades
        af.paz_salvo_propietarios = True
        with pytest.raises(ValidationError) as excinfo:
            af.save()
        assert 'paz_salvo_propietarios' in excinfo.value.message_dict

    def test_dossier_requiere_todos(self, torre_con_actividades):
        """N solo puede marcarse si TODOS los demás están en True."""
        _, af = torre_con_actividades
        # Setear 12 y dejar uno en False
        for campo in ACTIVIDAD_CAMPOS:
            if campo not in ('dossier', 'informe_socioambiental'):
                setattr(af, campo, True)
        af.save()
        af.refresh_from_db()

        # Ahora intentar dossier=True dejando informe_socioambiental=False
        af.dossier = True
        with pytest.raises(ValidationError) as excinfo:
            af.save()
        assert 'dossier' in excinfo.value.message_dict
        # El mensaje debe listar al faltante
        msg = excinfo.value.message_dict['dossier'][0]
        assert 'informe_socioambiental' in msg


class TestActividadFinalTorreLegacy:
    """Test que datos legacy (torres creadas antes de B1) NO se rompen."""

    def test_torre_legacy_get_or_create_funciona(self, torre_legacy):
        # Torre creada sin ActividadFinalTorre asociado
        assert not ActividadFinalTorre.objects.filter(torre=torre_legacy).exists()

        # get_or_create debe crear uno vacío
        af, created = ActividadFinalTorre.objects.get_or_create(torre=torre_legacy)
        assert created is True
        assert af.actividades_completas == 0
        assert af.pct_avance == 0.0
        # Debe poder persistirse sin errores
        af.save()


# ----------------------------------------------------------------------
# Tests E2E (test del BLUEPRINT)
# ----------------------------------------------------------------------

@pytest.mark.django_db
class TestB1ActividadesFinalesMatrizRenderYToggle:
    """E2E test del BLUEPRINT: `b1_actividades_finales_matriz_render_y_toggle`.

    Cubre el render de la matriz + un toggle HTMX completo + verificación de
    persistencia + validación lógica server-side a través del endpoint.
    """

    def test_b1_actividades_finales_matriz_render_y_toggle(
        self, authenticated_client, proyecto_construccion, torre_legacy,
    ):
        # Crear 2 torres más para confirmar render multi-fila
        TorreConstruccion.objects.create(proyecto=proyecto_construccion, numero='E2')
        TorreConstruccion.objects.create(proyecto=proyecto_construccion, numero='E3')

        # --- (1) GET matriz: debe renderizar las 3 estructuras ---
        url = reverse(
            'construccion:actividades_finales',
            kwargs={'proyecto_id': proyecto_construccion.id},
        )
        resp = authenticated_client.get(url)
        assert resp.status_code == 200
        html = resp.content.decode()
        # Headers de las 7 secciones
        for sec_label in (
            'Empalmes F.O.', 'Comunicación', 'Pruebas Eléctricas / RETIE',
            'Seguridad', 'Gestión Social', 'Administrativa', 'Cierre',
        ):
            assert sec_label in html, f"Sección '{sec_label}' no aparece en la matriz"
        # Filas de las 3 torres
        assert 'TE1-LEGACY' in html or 'E1-LEGACY' in html
        assert 'E2' in html
        assert 'E3' in html

        # --- (2) Toggle HTMX de un campo simple (pruebas_electricas) ---
        toggle_url = reverse(
            'construccion:actividades_finales_toggle',
            kwargs={
                'proyecto_id': proyecto_construccion.id,
                'torre_id': torre_legacy.id,
            },
        )
        resp = authenticated_client.post(toggle_url, {'campo': 'pruebas_electricas'})
        assert resp.status_code == 200
        # Debe persistir
        af = ActividadFinalTorre.objects.get(torre=torre_legacy)
        assert af.pruebas_electricas is True
        # El partial devuelve la fila refrescada
        assert b'fila-torre-' in resp.content
        # El % en la fila refleja 1/13
        assert b'1/13' in resp.content

        # --- (3) Toggle con violación lógica (G sin F) debe devolver 400 ---
        torre_e2 = TorreConstruccion.objects.get(
            proyecto=proyecto_construccion, numero='E2',
        )
        toggle_url_e2 = reverse(
            'construccion:actividades_finales_toggle',
            kwargs={'proyecto_id': proyecto_construccion.id, 'torre_id': torre_e2.id},
        )
        # Intentar marcar certificado_retie sin visita_retie
        resp = authenticated_client.post(
            toggle_url_e2, {'campo': 'certificado_retie'},
        )
        assert resp.status_code == 400, (
            f"Esperaba 400 por validación lógica; recibí {resp.status_code}: {resp.content[:200]}"
        )
        # No debe haberse persistido
        af_e2 = ActividadFinalTorre.objects.get(torre=torre_e2)
        assert af_e2.certificado_retie is False

        # --- (4) Filtro por estado ---
        resp = authenticated_client.get(url + '?estado=EN_PROCESO')
        assert resp.status_code == 200
        # Solo debería listarse la torre que tiene 1 actividad (torre_legacy)
        html = resp.content.decode()
        assert 'E1-LEGACY' in html


# ----------------------------------------------------------------------
# Tests #150 — aplicabilidad por torre ("No aplica")
# ----------------------------------------------------------------------

@pytest.mark.django_db
class TestActividadFinalAplica:

    def test_default_aplica_true(self, torre_con_actividades):
        _, af = torre_con_actividades
        assert af.aplica is True

    def test_no_aplica_estado_y_pct(self, torre_con_actividades):
        _, af = torre_con_actividades
        af.aplica = False
        af.save()
        af.refresh_from_db()
        assert af.estado_semaforo == 'NO_APLICA'
        assert af.estado_semaforo_label == 'No aplica'
        # Excluida del cómputo de pendientes → pct_avance 100.
        assert af.pct_avance == 100.0

    def test_no_aplica_salta_validacion_progresion(self, torre_con_actividades):
        """Con aplica=False, marcar certificado sin visita NO debe fallar
        (la matriz queda inactiva, no se valida progresión)."""
        _, af = torre_con_actividades
        af.aplica = False
        af.certificado_retie = True  # normalmente requiere visita_retie
        af.save()  # no debe lanzar ValidationError
        af.refresh_from_db()
        assert af.certificado_retie is True

    def test_aplica_true_sigue_validando(self, torre_con_actividades):
        _, af = torre_con_actividades
        af.certificado_retie = True  # sin visita -> debe fallar
        with pytest.raises(ValidationError):
            af.save()

    def test_toggle_aplica_via_view(self, authenticated_client,
                                    proyecto_construccion, torre_con_actividades):
        torre, af = torre_con_actividades
        assert af.aplica is True
        url = reverse(
            'construccion:actividades_finales_toggle',
            kwargs={'proyecto_id': proyecto_construccion.id, 'torre_id': torre.id},
        )
        resp = authenticated_client.post(url, {'campo': 'aplica'})
        assert resp.status_code == 200
        af.refresh_from_db()
        assert af.aplica is False
        assert b'No aplica' in resp.content
        # Toggle de vuelta a True
        resp = authenticated_client.post(url, {'campo': 'aplica'})
        assert resp.status_code == 200
        af.refresh_from_db()
        assert af.aplica is True

    def test_resumen_excluye_no_aplica(self, proyecto_construccion):
        from apps.construccion.views_b1_actividades_finales import _resumen
        t1 = TorreConstruccion.objects.create(proyecto=proyecto_construccion, numero='R1')
        t2 = TorreConstruccion.objects.create(proyecto=proyecto_construccion, numero='R2')
        af1 = ActividadFinalTorre.objects.create(torre=t1)  # aplica, 0%
        af2 = ActividadFinalTorre.objects.create(torre=t2, aplica=False)
        filas = [
            {'torre': t1, 'af': af1, 'celdas': []},
            {'torre': t2, 'af': af2, 'celdas': []},
        ]
        res = _resumen(filas)
        # pct_global solo cuenta las aplicables (t1 con 0%) -> 0.0, NO inflado por t2=100.
        assert res['pct_global'] == 0.0
        assert res['no_aplica'] == 1
        assert res['total_torres'] == 2
