"""#174: la actividad creada desde `/actividades/crear/` "desaparecía" del
listado que el usuario esperaba porque `fecha_programada` no era `required`
ni venía prepoblada -- el server hacía fallback silencioso a `date.today()`
(comportamiento invisible en la UI). Además, `EventosAPIView` (el endpoint
que alimenta el calendario) no aplicaba el mismo filtro de `unidad_negocio`
que `ProgramacionListView`, causando discrepancias de conteo entre
Programación y Calendario.

Causa raíz confirmada en F2 (ver agents/Instelec_174_f2.json):
1. `templates/actividades/crear.html` L128-134: input `fecha_programada` sin
   `required` ni `value` prepoblado (a diferencia de
   `partials/form_actividad.html` L85-91 que sí lo exige).
2. `apps/actividades/views.py` `ActividadCreateView.post` L683-686: fallback
   silencioso a `date.today()` ya existía -- se mantiene como defensa en
   profundidad.
3. `apps/actividades/views.py` `EventosAPIView.get`: no aplicaba
   `linea__contrato__unidad_negocio` como sí hacen `ProgramacionListView` y
   `CalendarioView`.

Tests contra dato LEGACY: se crea una actividad directamente vía ORM (no solo
fixtures de factory) simulando un registro ya existente en BD antes del fix,
para confirmar que el fallback y el filtro no rompen datos previos.
"""

from datetime import date, timedelta

import pytest
from django.urls import reverse

from apps.actividades.models import Actividad
from apps.contratos.models import Contrato
from tests.factories import (
    ActividadFactory,
    CuadrillaFactory,
    LineaFactory,
    TipoActividadFactory,
    TorreFactory,
)


def _crear_contrato(unidad_negocio, codigo):
    return Contrato.objects.create(
        unidad_negocio=unidad_negocio,
        codigo=codigo,
        nombre=f"Contrato {codigo}",
    )


@pytest.mark.django_db
class TestCrearActividadFechaProgramada:
    """Fix 1+2: el campo fecha_programada debe ser required + prepoblado en
    el template, y el fallback server-side debe seguir funcionando."""

    def test_template_fecha_programada_required_y_prepoblada_hoy(self, client, admin_user):
        """El input `fecha_programada` en /actividades/crear/ debe traer
        `required` y `value` = fecha de hoy (YYYY-MM-DD), igual que el campo
        gemelo en form_actividad.html (#174)."""
        client.force_login(admin_user)

        resp = client.get(reverse("actividades:crear"))

        assert resp.status_code == 200
        contenido = resp.content.decode()
        hoy_iso = date.today().strftime("%Y-%m-%d")

        # El input debe existir, tener required y el value de hoy.
        assert 'id="fecha_programada"' in contenido
        assert 'required' in contenido
        assert f'value="{hoy_iso}"' in contenido

    def test_post_sin_fecha_programada_usa_fallback_hoy(self, client, admin_user):
        """Defensa en profundidad: si el POST llega sin fecha_programada
        (ej. required bypasseado deshabilitando JS), el server sigue cayendo
        a date.today() -- comportamiento pre-existente que NO debe romperse."""
        client.force_login(admin_user)

        tipo = TipoActividadFactory()
        linea = LineaFactory()
        torre = TorreFactory(linea=linea)
        cuadrilla = CuadrillaFactory()

        resp = client.post(
            reverse("actividades:crear"),
            {
                "tipo_actividad": str(tipo.id),
                "linea": str(linea.id),
                "torre": str(torre.id),
                "cuadrilla": str(cuadrilla.id),
                # fecha_programada omitida a propósito
                "observaciones_programacion": "Actividad sin fecha explícita",
            },
        )

        assert resp.status_code in (200, 302)
        actividad = Actividad.objects.filter(
            observaciones_programacion="Actividad sin fecha explícita"
        ).first()
        assert actividad is not None
        assert actividad.fecha_programada == date.today()

    def test_post_con_fecha_programada_futura_se_persiste_exacta(self, client, admin_user):
        """Si el POST sí manda fecha_programada explícita (caso normal tras
        el fix, con el input prepoblado/editable), esa fecha debe persistirse
        tal cual -- el fallback NO debe pisarla."""
        client.force_login(admin_user)

        tipo = TipoActividadFactory()
        linea = LineaFactory()
        torre = TorreFactory(linea=linea)
        cuadrilla = CuadrillaFactory()
        fecha_futura = date.today() + timedelta(days=15)

        resp = client.post(
            reverse("actividades:crear"),
            {
                "tipo_actividad": str(tipo.id),
                "linea": str(linea.id),
                "torre": str(torre.id),
                "cuadrilla": str(cuadrilla.id),
                "fecha_programada": fecha_futura.strftime("%Y-%m-%d"),
                "observaciones_programacion": "Actividad con fecha futura explícita",
            },
        )

        assert resp.status_code in (200, 302)
        actividad = Actividad.objects.get(
            observaciones_programacion="Actividad con fecha futura explícita"
        )
        assert actividad.fecha_programada == fecha_futura


@pytest.mark.django_db
class TestEventosAPIViewFiltroUnidadNegocio:
    """Fix 3: EventosAPIView debe aplicar el mismo filtro de unidad_negocio
    que ProgramacionListView/CalendarioView para que los conteos coincidan."""

    def test_eventos_filtra_por_unidad_negocio_explicita(self, client, admin_user):
        """Con ?unidad=MANTENIMIENTO, el endpoint de eventos debe excluir
        actividades de líneas cuyo contrato es de otra unidad de negocio,
        igual que ya hace ProgramacionListView (#174)."""
        client.force_login(admin_user)

        contrato_mant = _crear_contrato("MANTENIMIENTO", "MANT-174")
        contrato_constr = _crear_contrato("CONSTRUCCION", "CONSTR-174")

        linea_mant = LineaFactory(contrato=contrato_mant)
        linea_constr = LineaFactory(contrato=contrato_constr)

        act_mant = ActividadFactory(
            linea=linea_mant,
            torre=TorreFactory(linea=linea_mant),
            observaciones_programacion="Actividad de mantenimiento #174",
        )
        act_constr = ActividadFactory(
            linea=linea_constr,
            torre=TorreFactory(linea=linea_constr),
            observaciones_programacion="Actividad de construccion #174",
        )

        resp = client.get(
            reverse("actividades:api_eventos"),
            {"unidad": "MANTENIMIENTO"},
        )
        assert resp.status_code == 200
        data = resp.json()
        ids = {evento["id"] for evento in data}

        assert str(act_mant.id) in ids
        assert str(act_constr.id) not in ids

    def test_eventos_sin_filtro_explicito_devuelve_todas_default_todos(self, client, admin_user):
        """Sin ?unidad y sin unidad en sesión, el default sigue siendo
        'TODOS' (get_unidad_negocio) -- NO debe romper el comportamiento
        preexistente de EventosAPIView (sin filtro alguno)."""
        client.force_login(admin_user)

        contrato_mant = _crear_contrato("MANTENIMIENTO", "MANT-174B")
        contrato_constr = _crear_contrato("CONSTRUCCION", "CONSTR-174B")

        linea_mant = LineaFactory(contrato=contrato_mant)
        linea_constr = LineaFactory(contrato=contrato_constr)

        act_mant = ActividadFactory(
            linea=linea_mant,
            torre=TorreFactory(linea=linea_mant),
            observaciones_programacion="Default mantenimiento #174",
        )
        act_constr = ActividadFactory(
            linea=linea_constr,
            torre=TorreFactory(linea=linea_constr),
            observaciones_programacion="Default construccion #174",
        )

        resp = client.get(reverse("actividades:api_eventos"))
        assert resp.status_code == 200
        ids = {evento["id"] for evento in resp.json()}

        # Default 'TODOS': ambas actividades deben aparecer (no-regresión).
        assert str(act_mant.id) in ids
        assert str(act_constr.id) in ids

    def test_eventos_filtro_unidad_negocio_contra_actividad_legacy(self, client, admin_user):
        """Test contra dato LEGACY: una actividad creada directamente vía ORM
        (simulando un registro ya existente en BD antes del fix, sin pasar
        por el form) también debe respetar el filtro de unidad_negocio."""
        client.force_login(admin_user)

        contrato_constr = _crear_contrato("CONSTRUCCION", "CONSTR-174C")
        linea_legacy = LineaFactory(contrato=contrato_constr, codigo="LT-LEGACY-174")
        torre_legacy = TorreFactory(linea=linea_legacy)
        tipo = TipoActividadFactory()
        cuadrilla = CuadrillaFactory()

        actividad_legacy = Actividad.objects.create(
            linea=linea_legacy,
            torre=torre_legacy,
            tipo_actividad=tipo,
            cuadrilla=cuadrilla,
            fecha_programada=date.today() - timedelta(days=30),
            estado="COMPLETADA",
            prioridad="NORMAL",
            observaciones_programacion="Actividad legacy pre-existente #174",
        )

        resp = client.get(
            reverse("actividades:api_eventos"),
            {"unidad": "MANTENIMIENTO"},
        )
        assert resp.status_code == 200
        ids = {evento["id"] for evento in resp.json()}
        assert str(actividad_legacy.id) not in ids

        resp_constr = client.get(
            reverse("actividades:api_eventos"),
            {"unidad": "CONSTRUCCION"},
        )
        assert resp_constr.status_code == 200
        ids_constr = {evento["id"] for evento in resp_constr.json()}
        assert str(actividad_legacy.id) in ids_constr
