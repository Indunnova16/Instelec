"""#150 — el toggle de una casilla "no aplica" por casilla NO debe fallar con 400.

Bounce 2: al desmarcar (o marcar) una casilla `*_no_aplica` sobre una fila con
una regla de progresión activa (dossier / G-F / K-J), `_validar_progresion()`
levantaba ValidationError → `ActividadFinalToggleView` la devolvía como HTTP 400
"error en la solicitud" y NO guardaba el cambio.

Causa raíz: las reglas de progresión corren SIEMPRE en `save()` vía
`full_clean()` y no contemplaban las casillas `*_no_aplica`.

Fix:
- El toggle de un campo administrativo (`aplica` o `<campo>_no_aplica`) guarda
  con `skip_progresion=True` → nunca bloquea con 400.
- Las reglas G-F y K-J contemplan `*_no_aplica` (una previa "no aplica" cuenta
  como cubierta, no como faltante).

Tests:
- Reproduce el caso del cliente (dossier=true + casillas no_aplica; desmarcar
  una no_aplica → 200, NO 400).
- Marcar `*_no_aplica` con una regla activa → 200 (no bloquea).
- G-F y K-J contemplan `*_no_aplica` a nivel modelo.
- Regresión: el toggle de una ACTIVIDAD real (no administrativa) sigue dando
  400 cuando rompe la progresión (G sin F).
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
# Fixtures (locales al issue para no acoplar con el módulo compartido)
# ----------------------------------------------------------------------

@pytest.fixture
def proyecto_i150(db):
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-I150-001',
        nombre='Proyecto test #150 no-aplica casilla',
        cliente='Test',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto LT 230kV — Test #150',
        estado='EJECUCION',
    )


@pytest.fixture
def torre_af_i150(proyecto_i150):
    torre = TorreConstruccion.objects.create(proyecto=proyecto_i150, numero='E5')
    af = ActividadFinalTorre.objects.create(torre=torre)
    return torre, af


def _toggle_url(proyecto, torre):
    return reverse(
        'construccion:actividades_finales_toggle',
        kwargs={'proyecto_id': proyecto.id, 'torre_id': torre.id},
    )


# ----------------------------------------------------------------------
# Reproducción del bug (vista / endpoint del toggle)
# ----------------------------------------------------------------------

@pytest.mark.django_db
class TestI150ToggleNoAplicaNoFalla:

    def test_desmarcar_no_aplica_con_dossier_no_devuelve_400(
        self, authenticated_client, proyecto_i150, torre_af_i150,
    ):
        """Caso EXACTO del cliente: dossier=true porque todas las demás están
        marcadas no_aplica; al desmarcar UNA casilla no_aplica → 200, NO 400."""
        torre, af = torre_af_i150
        # Estado previo: dossier=true + las 12 actividades restantes en no_aplica.
        for campo in ACTIVIDAD_CAMPOS:
            if campo != 'dossier':
                setattr(af, f'{campo}_no_aplica', True)
        af.dossier = True
        # Guardar saltando progresión para montar el estado de partida.
        af.save(skip_progresion=True)
        af.refresh_from_db()
        assert af.dossier is True

        url = _toggle_url(proyecto_i150, torre)
        # Desmarcar una casilla no_aplica (valor=0) — reaparecería un "faltante".
        resp = authenticated_client.post(
            url, {'campo': 'empalmes_subestacion_no_aplica', 'valor': '0'},
        )
        assert resp.status_code == 200, (
            f"El toggle de no_aplica NO debe fallar; recibí {resp.status_code}: "
            f"{resp.content[:300]}"
        )
        af.refresh_from_db()
        assert af.empalmes_subestacion_no_aplica is False

    def test_desmarcar_visita_retie_con_certificado_no_devuelve_400(
        self, authenticated_client, proyecto_i150, torre_af_i150,
    ):
        """2do camino reproducido: visita_retie=t + certificado_retie=t; marcar
        visita_retie_no_aplica y luego (en escenario del cliente) desmarcar la
        actividad rompía. Aquí el toggle del no_aplica nunca debe dar 400."""
        torre, af = torre_af_i150
        af.visita_retie = True
        af.certificado_retie = True
        af.save()  # estado válido de partida (G con F)
        af.refresh_from_db()

        url = _toggle_url(proyecto_i150, torre)
        # Marcar visita_retie_no_aplica con certificado activo: NO debe bloquear.
        resp = authenticated_client.post(
            url, {'campo': 'visita_retie_no_aplica', 'valor': '1'},
        )
        assert resp.status_code == 200, (
            f"Marcar no_aplica con regla activa no debe fallar; "
            f"recibí {resp.status_code}: {resp.content[:300]}"
        )
        af.refresh_from_db()
        assert af.visita_retie_no_aplica is True

    def test_marcar_no_aplica_con_regla_activa_devuelve_200(
        self, authenticated_client, proyecto_i150, torre_af_i150,
    ):
        """Marcar una casilla no_aplica sobre una fila con paz_salvo activo
        (K) sin cierre_actas (J) → 200 (toggle administrativo no bloquea)."""
        torre, af = torre_af_i150
        url = _toggle_url(proyecto_i150, torre)
        resp = authenticated_client.post(
            url, {'campo': 'cierre_actas_no_aplica', 'valor': '1'},
        )
        assert resp.status_code == 200
        af.refresh_from_db()
        assert af.cierre_actas_no_aplica is True

    def test_toggle_actividad_real_sigue_validando_progresion(
        self, authenticated_client, proyecto_i150, torre_af_i150,
    ):
        """Regresión: el toggle de una ACTIVIDAD real (no administrativa) que
        rompe la progresión (G sin F) DEBE seguir devolviendo 400."""
        torre, af = torre_af_i150
        url = _toggle_url(proyecto_i150, torre)
        resp = authenticated_client.post(url, {'campo': 'certificado_retie'})
        assert resp.status_code == 400, (
            f"G sin F debe seguir fallando; recibí {resp.status_code}"
        )
        af.refresh_from_db()
        assert af.certificado_retie is False


# ----------------------------------------------------------------------
# Reglas de progresión a nivel modelo (G-F, K-J contemplan *_no_aplica)
# ----------------------------------------------------------------------

@pytest.mark.django_db
class TestI150ProgresionContemplaNoAplica:

    def test_certificado_con_visita_no_aplica_es_valido(self, torre_af_i150):
        """G (certificado_retie) con F (visita_retie) marcada no_aplica: válido."""
        _, af = torre_af_i150
        af.certificado_retie = True
        af.visita_retie_no_aplica = True  # F no aplica → cuenta como cubierta
        af.save()  # no debe lanzar
        af.refresh_from_db()
        assert af.certificado_retie is True

    def test_certificado_sin_visita_ni_no_aplica_sigue_fallando(self, torre_af_i150):
        """G sin F y sin F no_aplica: sigue siendo inválido."""
        _, af = torre_af_i150
        af.certificado_retie = True
        with pytest.raises(ValidationError):
            af.save()

    def test_paz_salvo_con_actas_no_aplica_es_valido(self, torre_af_i150):
        """K (paz_salvo) con J (cierre_actas) marcada no_aplica: válido."""
        _, af = torre_af_i150
        af.paz_salvo_propietarios = True
        af.cierre_actas_no_aplica = True
        af.save()
        af.refresh_from_db()
        assert af.paz_salvo_propietarios is True

    def test_skip_progresion_no_persiste_entre_saves(self, torre_af_i150):
        """La bandera transitoria skip_progresion no debe quedar pegada: un save
        normal posterior vuelve a validar la progresión."""
        _, af = torre_af_i150
        af.dossier_no_aplica = True
        af.save(skip_progresion=True)  # no valida
        # save normal posterior con G sin F debe fallar
        af.certificado_retie = True
        with pytest.raises(ValidationError):
            af.save()
