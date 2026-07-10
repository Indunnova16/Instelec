"""#174: la actividad creada desde `/actividades/crear/` "desaparecía" del
listado que el usuario esperaba porque `fecha_programada` no era `required`
ni venía prepoblada -- el server hacía fallback silencioso a `date.today()`
(comportamiento invisible en la UI). Además, 5 vistas de `apps/actividades/
views.py` (`ActividadListView`, `CalendarioView`, `ProgramacionListView`,
`EventosAPIView`, `ListaOperativaView`) aplicaban
`qs.filter(linea__contrato__unidad_negocio=X)` -- un INNER JOIN excluyente --
cuando el filtro de unidad de negocio estaba activo.

Causa raíz confirmada en F2 (ver agents/Instelec_174_f2.json): el 100% de las
líneas (40/40) y actividades (243/243) en prod tienen `linea.contrato_id=NULL`.
El INNER JOIN excluyente no es un caso legacy raro -- es el estado real de
TODO el dataset. Cualquier filtro de unidad de negocio activo ocultaba el
dataset completo.

REPROCESO (bounce=1): el fix anterior (commit `d9d2c19`) sólo tocó
`EventosAPIView` -- y encima **replicó** el JOIN excluyente ahí en vez de
corregirlo -- y su test (`test_eventos_filtro_unidad_negocio_contra_actividad_
legacy`) usó un contrato explícito (`contrato=contrato_constr`) en vez de
`contrato=None` real, por lo que nunca ejecutó el camino que falla. Esta
ronda corrige las 5 vistas (`Q(linea__contrato__isnull=True) |
Q(linea__contrato__unidad_negocio=unidad_negocio)`) y los tests usan
`LineaFactory(contrato=None)` -- el estado REAL de prod -- además de un caso
de regresión con contrato explícito de la unidad de negocio CONTRARIA (que
debe seguir excluido; el fix no debe relajar el filtro para el caso normal).
"""

from datetime import date, timedelta

import pytest
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from apps.actividades.models import Actividad, HistorialIntervencion
from apps.actividades.views import ListaOperativaView
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
        """Test contra dato LEGACY REAL: en prod el 100% de las líneas tienen
        `contrato_id=NULL` (confirmado F2, 40/40 líneas + 243/243
        actividades) -- no `contrato=<unidad contraria>` como probaba el fix
        anterior (bounce=1), que nunca ejercitó el camino que falla. Una
        actividad cuya línea NO tiene contrato asignado debe seguir
        apareciendo sin importar cuál unidad de negocio se filtre."""
        client.force_login(admin_user)

        linea_legacy = LineaFactory(contrato=None, codigo="LT-LEGACY-174")
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
            observaciones_programacion="Actividad legacy pre-existente #174 sin contrato",
        )

        resp_mant = client.get(
            reverse("actividades:api_eventos"),
            {"unidad": "MANTENIMIENTO"},
        )
        assert resp_mant.status_code == 200
        ids_mant = {evento["id"] for evento in resp_mant.json()}
        assert str(actividad_legacy.id) in ids_mant

        resp_constr = client.get(
            reverse("actividades:api_eventos"),
            {"unidad": "CONSTRUCCION"},
        )
        assert resp_constr.status_code == 200
        ids_constr = {evento["id"] for evento in resp_constr.json()}
        assert str(actividad_legacy.id) in ids_constr

    def test_eventos_regresion_excluye_contrato_unidad_contraria(self, client, admin_user):
        """Regresión: el fix NO debe relajar el filtro para el caso normal --
        una actividad cuya línea SÍ tiene un contrato explícito de la unidad
        de negocio CONTRARIA debe seguir excluida (ya cubierto arriba en
        test_eventos_filtra_por_unidad_negocio_explicita, reforzado aquí como
        caso de regresión explícito post-fix)."""
        client.force_login(admin_user)

        contrato_constr = _crear_contrato("CONSTRUCCION", "CONSTR-174D")
        linea_constr = LineaFactory(contrato=contrato_constr, codigo="LT-CONSTR-174D")
        torre_constr = TorreFactory(linea=linea_constr)
        tipo = TipoActividadFactory()
        cuadrilla = CuadrillaFactory()

        actividad_constr = Actividad.objects.create(
            linea=linea_constr,
            torre=torre_constr,
            tipo_actividad=tipo,
            cuadrilla=cuadrilla,
            fecha_programada=date.today() - timedelta(days=30),
            estado="COMPLETADA",
            prioridad="NORMAL",
            observaciones_programacion="Actividad construccion contraria #174 eventos",
        )

        resp = client.get(
            reverse("actividades:api_eventos"),
            {"unidad": "MANTENIMIENTO"},
        )
        assert resp.status_code == 200
        ids = {evento["id"] for evento in resp.json()}
        assert str(actividad_constr.id) not in ids


@pytest.mark.django_db
class TestActividadListViewFiltroUnidadNegocio:
    """Mismo fix aplicado en ActividadListView.get_queryset (L41) -- el
    listado principal de actividades es la vista más visible del bug: con
    unidad de negocio activa, ocultaba el 100% de las actividades reales."""

    def test_lista_incluye_linea_sin_contrato(self, client, admin_user):
        client.force_login(admin_user)

        linea_sin_contrato = LineaFactory(contrato=None, codigo="LT-SINCONTRATO-174-LISTA")
        act_sin_contrato = ActividadFactory(
            linea=linea_sin_contrato,
            torre=TorreFactory(linea=linea_sin_contrato),
            observaciones_programacion="Actividad linea sin contrato #174 lista",
        )

        resp = client.get(reverse("actividades:lista"), {"unidad": "MANTENIMIENTO"})
        assert resp.status_code == 200
        ids = {str(a.id) for a in resp.context["actividades"]}
        assert str(act_sin_contrato.id) in ids

    def test_lista_regresion_excluye_contrato_unidad_contraria(self, client, admin_user):
        """Regresión: NO relajar el filtro para el caso normal."""
        client.force_login(admin_user)

        contrato_constr = _crear_contrato("CONSTRUCCION", "CONSTR-174-LISTA")
        linea_constr = LineaFactory(contrato=contrato_constr, codigo="LT-CONSTR-174-LISTA")
        act_constr = ActividadFactory(
            linea=linea_constr,
            torre=TorreFactory(linea=linea_constr),
            observaciones_programacion="Actividad construccion contraria #174 lista",
        )

        resp = client.get(reverse("actividades:lista"), {"unidad": "MANTENIMIENTO"})
        assert resp.status_code == 200
        ids = {str(a.id) for a in resp.context["actividades"]}
        assert str(act_constr.id) not in ids


@pytest.mark.django_db
class TestCalendarioViewFiltroUnidadNegocio:
    """Mismo fix aplicado en CalendarioView.get_context_data (L183-186), más
    el fallback de sesión alineado con las otras 4 vistas
    (`self.request.GET.get('unidad') or get_unidad_negocio(self.request)`)."""

    def test_calendario_incluye_linea_sin_contrato(self, client, admin_user):
        client.force_login(admin_user)

        linea_sin_contrato = LineaFactory(contrato=None, codigo="LT-SINCONTRATO-174-CAL")
        act = ActividadFactory(
            linea=linea_sin_contrato,
            torre=TorreFactory(linea=linea_sin_contrato),
            fecha_programada=date.today(),
            observaciones_programacion="Actividad sin contrato #174 calendario",
        )

        resp = client.get(reverse("actividades:calendario"), {"unidad": "MANTENIMIENTO"})
        assert resp.status_code == 200
        actividades_dia = resp.context["actividades_por_fecha"].get(date.today().day, [])
        ids = {str(a.id) for a in actividades_dia}
        assert str(act.id) in ids

    def test_calendario_regresion_excluye_contrato_unidad_contraria(self, client, admin_user):
        client.force_login(admin_user)

        contrato_constr = _crear_contrato("CONSTRUCCION", "CONSTR-174-CAL")
        linea_constr = LineaFactory(contrato=contrato_constr, codigo="LT-CONSTR-174-CAL")
        act = ActividadFactory(
            linea=linea_constr,
            torre=TorreFactory(linea=linea_constr),
            fecha_programada=date.today(),
            observaciones_programacion="Actividad construccion contraria #174 calendario",
        )

        resp = client.get(reverse("actividades:calendario"), {"unidad": "MANTENIMIENTO"})
        assert resp.status_code == 200
        actividades_dia = resp.context["actividades_por_fecha"].get(date.today().day, [])
        ids = {str(a.id) for a in actividades_dia}
        assert str(act.id) not in ids

    def test_calendario_respeta_unidad_negocio_de_sesion(self, client, admin_user):
        """El fallback de sesión debe funcionar igual que en las otras 4
        vistas: sin ?unidad en la URL pero con unidad_negocio persistida en
        sesión, el filtro de sesión debe aplicarse (antes del fix,
        CalendarioView ignoraba la sesión por completo)."""
        client.force_login(admin_user)
        session = client.session
        session["unidad_negocio"] = "MANTENIMIENTO"
        session.save()

        linea_sin_contrato = LineaFactory(contrato=None, codigo="LT-SINCONTRATO-174-CALSES")
        act_sin_contrato = ActividadFactory(
            linea=linea_sin_contrato,
            torre=TorreFactory(linea=linea_sin_contrato),
            fecha_programada=date.today(),
            observaciones_programacion="Actividad sin contrato #174 calendario sesion",
        )

        contrato_constr = _crear_contrato("CONSTRUCCION", "CONSTR-174-CALSES")
        linea_constr = LineaFactory(contrato=contrato_constr, codigo="LT-CONSTR-174-CALSES")
        act_constr = ActividadFactory(
            linea=linea_constr,
            torre=TorreFactory(linea=linea_constr),
            fecha_programada=date.today(),
            observaciones_programacion="Actividad construccion contraria #174 calendario sesion",
        )

        resp = client.get(reverse("actividades:calendario"))
        assert resp.status_code == 200
        actividades_dia = resp.context["actividades_por_fecha"].get(date.today().day, [])
        ids = {str(a.id) for a in actividades_dia}
        assert str(act_sin_contrato.id) in ids
        assert str(act_constr.id) not in ids


@pytest.mark.django_db
class TestProgramacionListViewFiltroUnidadNegocio:
    """Mismo fix aplicado en ProgramacionListView.get_queryset (L221-225)."""

    def test_programacion_incluye_linea_sin_contrato(self, client, admin_user):
        client.force_login(admin_user)

        linea_sin_contrato = LineaFactory(contrato=None, codigo="LT-SINCONTRATO-174-PROG")
        act = ActividadFactory(
            linea=linea_sin_contrato,
            torre=TorreFactory(linea=linea_sin_contrato),
            observaciones_programacion="Actividad sin contrato #174 programacion",
        )

        resp = client.get(reverse("actividades:programacion"), {"unidad": "MANTENIMIENTO"})
        assert resp.status_code == 200
        ids = {str(a.id) for a in resp.context["actividades"]}
        assert str(act.id) in ids

    def test_programacion_regresion_excluye_contrato_unidad_contraria(self, client, admin_user):
        client.force_login(admin_user)

        contrato_constr = _crear_contrato("CONSTRUCCION", "CONSTR-174-PROG")
        linea_constr = LineaFactory(contrato=contrato_constr, codigo="LT-CONSTR-174-PROG")
        act = ActividadFactory(
            linea=linea_constr,
            torre=TorreFactory(linea=linea_constr),
            observaciones_programacion="Actividad construccion contraria #174 programacion",
        )

        resp = client.get(reverse("actividades:programacion"), {"unidad": "MANTENIMIENTO"})
        assert resp.status_code == 200
        ids = {str(a.id) for a in resp.context["actividades"]}
        assert str(act.id) not in ids


@pytest.mark.django_db
class TestListaOperativaViewFiltroUnidadNegocio:
    """Mismo fix aplicado en ListaOperativaView.get_queryset (L1206-1209).

    Smoke test: esta vista NO tiene URL wireada en `actividades/urls.py`
    (confirmado -- no aparece en el urlconf), así que se ejercita
    get_queryset() directo con un request armado a mano en vez de
    client.get(reverse(...)) como las otras 4."""

    def _build_request(self, admin_user, unidad=None):
        rf = RequestFactory()
        params = {"unidad": unidad} if unidad else {}
        request = rf.get("/actividades/lista-operativa/", params)
        request.user = admin_user
        return request

    def test_lista_operativa_incluye_linea_sin_contrato(self, admin_user, db):
        linea_sin_contrato = LineaFactory(contrato=None, codigo="LT-SINCONTRATO-174-OP")
        torre = TorreFactory(linea=linea_sin_contrato)
        cuadrilla = CuadrillaFactory()
        actividad = ActividadFactory(linea=linea_sin_contrato, torre=torre)

        intervencion = HistorialIntervencion.objects.create(
            linea=linea_sin_contrato,
            actividad=actividad,
            fecha_intervencion=timezone.now(),
            tipo_intervencion="Mantenimiento preventivo",
            cuadrilla=cuadrilla,
        )

        request = self._build_request(admin_user, unidad="MANTENIMIENTO")
        view = ListaOperativaView()
        view.request = request
        view.kwargs = {}

        ids = {str(obj.id) for obj in view.get_queryset()}
        assert str(intervencion.id) in ids

    def test_lista_operativa_regresion_excluye_contrato_unidad_contraria(self, admin_user, db):
        contrato_constr = _crear_contrato("CONSTRUCCION", "CONSTR-174-OP")
        linea_constr = LineaFactory(contrato=contrato_constr, codigo="LT-CONSTR-174-OP")
        torre = TorreFactory(linea=linea_constr)
        cuadrilla = CuadrillaFactory()
        actividad = ActividadFactory(linea=linea_constr, torre=torre)

        intervencion = HistorialIntervencion.objects.create(
            linea=linea_constr,
            actividad=actividad,
            fecha_intervencion=timezone.now(),
            tipo_intervencion="Mantenimiento preventivo",
            cuadrilla=cuadrilla,
        )

        request = self._build_request(admin_user, unidad="MANTENIMIENTO")
        view = ListaOperativaView()
        view.request = request
        view.kwargs = {}

        ids = {str(obj.id) for obj in view.get_queryset()}
        assert str(intervencion.id) not in ids
