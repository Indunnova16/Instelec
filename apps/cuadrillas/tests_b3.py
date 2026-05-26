"""
B3 — Tests para filtro cuadrillas desactivadas + auditoría.

Issue: Indunnova16/Instelec#104.

Cubre:
  * b3_filtrar_cuadrillas_inactivas — filtro ?filtro=inactivas
  * b3_reactivar_cuadrilla — POST a CuadrillaReactivateView
  * Edge cases: save() auto-asigna fecha_desactivacion en transición True→False;
    reactivar limpia motivo/fecha; dato legacy sin auditoría se preserva;
    permisos RBAC bloquean liniero.
"""
import pytest
from django.urls import reverse
from django.utils import timezone

from apps.cuadrillas.models import Cuadrilla


pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures locales
# ---------------------------------------------------------------------------

@pytest.fixture
def cuadrilla_activa(db, liniero_user):
    """Cuadrilla activa con un miembro."""
    from tests.factories import CuadrillaFactory, CuadrillaMiembroFactory
    c = CuadrillaFactory(codigo='18-2026-001', nombre='Cuadrilla Activa Test', activa=True)
    CuadrillaMiembroFactory(cuadrilla=c, usuario=liniero_user, activo=True)
    return c


@pytest.fixture
def cuadrilla_inactiva(db, admin_user):
    """Cuadrilla previamente desactivada (con auditoría completa)."""
    from tests.factories import CuadrillaFactory
    c = CuadrillaFactory(codigo='18-2026-002', nombre='Cuadrilla Inactiva Test', activa=True)
    c.desactivar(usuario=admin_user, motivo='Equipo reasignado al cliente Y')
    return c


@pytest.fixture
def cuadrilla_legacy_inactiva(db):
    """Cuadrilla inactiva sin auditoría (registro pre-B3)."""
    from tests.factories import CuadrillaFactory
    # Crear activa primero, luego forzar update directo sin pasar por save()
    # para simular dato legacy.
    c = CuadrillaFactory(codigo='17-2026-999', nombre='Legacy Inactiva', activa=True)
    Cuadrilla.objects.filter(pk=c.pk).update(activa=False)
    c.refresh_from_db()
    return c


# ---------------------------------------------------------------------------
# Tests de modelo — save() override + helpers desactivar/reactivar
# ---------------------------------------------------------------------------

class TestB3ModelAuditoria:
    """Auditoría a nivel modelo Cuadrilla."""

    def test_save_transicion_activa_a_inactiva_setea_fecha(self, cuadrilla_activa):
        """En transición activa True→False, save() rellena fecha_desactivacion."""
        antes = timezone.now()
        cuadrilla_activa.activa = False
        cuadrilla_activa.save()
        cuadrilla_activa.refresh_from_db()

        assert cuadrilla_activa.activa is False
        assert cuadrilla_activa.fecha_desactivacion is not None
        assert cuadrilla_activa.fecha_desactivacion >= antes

    def test_desactivar_helper_setea_los_tres_campos(self, cuadrilla_activa, admin_user):
        """`Cuadrilla.desactivar(usuario, motivo)` rellena los 3 campos."""
        cuadrilla_activa.desactivar(usuario=admin_user, motivo='Cliente canceló operación')
        cuadrilla_activa.refresh_from_db()

        assert cuadrilla_activa.activa is False
        assert cuadrilla_activa.motivo_desactivacion == 'Cliente canceló operación'
        assert cuadrilla_activa.fecha_desactivacion is not None
        assert cuadrilla_activa.desactivado_por_id == admin_user.id

    def test_reactivar_limpia_motivo_y_fecha(self, cuadrilla_inactiva):
        """`Cuadrilla.reactivar()` limpia motivo+fecha y deja activa=True."""
        cuadrilla_inactiva.reactivar()
        cuadrilla_inactiva.refresh_from_db()

        assert cuadrilla_inactiva.activa is True
        assert cuadrilla_inactiva.motivo_desactivacion == ''
        assert cuadrilla_inactiva.fecha_desactivacion is None
        # desactivado_por se conserva como rastro histórico
        # (la firma del último que la desactivó)

    def test_motivo_max_length_255_truncado(self, cuadrilla_activa, admin_user):
        """Edge case: motivo >255 chars se trunca para respetar CharField."""
        motivo_largo = 'X' * 300
        cuadrilla_activa.desactivar(usuario=admin_user, motivo=motivo_largo)
        cuadrilla_activa.refresh_from_db()

        assert len(cuadrilla_activa.motivo_desactivacion) == 255

    def test_dato_legacy_preservado(self, cuadrilla_legacy_inactiva):
        """Edge case: registro inactivo pre-B3 (sin auditoría) sigue funcionando."""
        assert cuadrilla_legacy_inactiva.activa is False
        assert cuadrilla_legacy_inactiva.motivo_desactivacion == ''
        assert cuadrilla_legacy_inactiva.fecha_desactivacion is None
        assert cuadrilla_legacy_inactiva.desactivado_por is None
        # Y el queryset por inactiva sigue retornándolo
        assert cuadrilla_legacy_inactiva in Cuadrilla.objects.filter(activa=False)


# ---------------------------------------------------------------------------
# Tests E2E — filtros y view reactivar (nombre exacto del BLUEPRINT)
# ---------------------------------------------------------------------------

class TestB3FiltroEReactivar:
    """E2E: lista con filtros + reactivar via POST."""

    def test_b3_filtrar_cuadrillas_inactivas(
        self, client, admin_user, user_password,
        cuadrilla_activa, cuadrilla_inactiva, cuadrilla_legacy_inactiva,
    ):
        """GET /cuadrillas/?filtro=inactivas → solo retorna inactivas."""
        client.login(username=admin_user.email, password=user_password)

        # filtro=inactivas
        resp = client.get(reverse('cuadrillas:lista') + '?filtro=inactivas')
        assert resp.status_code == 200
        cuadrillas_en_contexto = list(resp.context['cuadrillas'])
        ids = {c.id for c in cuadrillas_en_contexto}
        assert cuadrilla_inactiva.id in ids
        assert cuadrilla_legacy_inactiva.id in ids
        assert cuadrilla_activa.id not in ids

        # Contadores en context
        assert resp.context['b3_total_activas'] == 1
        assert resp.context['b3_total_inactivas'] == 2
        assert resp.context['b3_total_todas'] == 3
        assert resp.context['b3_filtro_actual'] == 'inactivas'

    def test_b3_filtrar_activas_default(
        self, client, admin_user, user_password,
        cuadrilla_activa, cuadrilla_inactiva,
    ):
        """Sin parámetro → comportamiento legacy (solo activas)."""
        client.login(username=admin_user.email, password=user_password)
        resp = client.get(reverse('cuadrillas:lista'))
        assert resp.status_code == 200
        ids = {c.id for c in resp.context['cuadrillas']}
        assert cuadrilla_activa.id in ids
        assert cuadrilla_inactiva.id not in ids
        assert resp.context['b3_filtro_actual'] == 'activas'

    def test_b3_filtrar_todas(
        self, client, admin_user, user_password,
        cuadrilla_activa, cuadrilla_inactiva,
    ):
        """filtro=todas → activas + inactivas."""
        client.login(username=admin_user.email, password=user_password)
        resp = client.get(reverse('cuadrillas:lista') + '?filtro=todas')
        assert resp.status_code == 200
        ids = {c.id for c in resp.context['cuadrillas']}
        assert cuadrilla_activa.id in ids
        assert cuadrilla_inactiva.id in ids
        assert resp.context['b3_filtro_actual'] == 'todas'

    def test_b3_filtrar_invalido_cae_a_activas(
        self, client, admin_user, user_password, cuadrilla_activa, cuadrilla_inactiva,
    ):
        """Edge case: ?filtro=randombasura → fallback a activas (no 500)."""
        client.login(username=admin_user.email, password=user_password)
        resp = client.get(reverse('cuadrillas:lista') + '?filtro=basura')
        assert resp.status_code == 200
        assert resp.context['b3_filtro_actual'] == 'activas'

    def test_b3_reactivar_cuadrilla(
        self, client, admin_user, user_password, cuadrilla_inactiva,
    ):
        """POST /cuadrillas/<uuid>/reactivar/ → cuadrilla queda activa=True."""
        client.login(username=admin_user.email, password=user_password)
        url = reverse('cuadrillas:reactivar', kwargs={'pk': cuadrilla_inactiva.pk})

        resp = client.post(url)

        # Redirect a lista (302) o success
        assert resp.status_code in (200, 302)
        cuadrilla_inactiva.refresh_from_db()
        assert cuadrilla_inactiva.activa is True
        assert cuadrilla_inactiva.motivo_desactivacion == ''
        assert cuadrilla_inactiva.fecha_desactivacion is None

    def test_b3_reactivar_idempotente(
        self, client, admin_user, user_password, cuadrilla_activa,
    ):
        """Edge case: reactivar una cuadrilla ya activa → no-op idempotente."""
        client.login(username=admin_user.email, password=user_password)
        url = reverse('cuadrillas:reactivar', kwargs={'pk': cuadrilla_activa.pk})

        resp = client.post(url)
        assert resp.status_code in (200, 302)
        cuadrilla_activa.refresh_from_db()
        assert cuadrilla_activa.activa is True

    def test_b3_reactivar_no_autenticado_redirect(
        self, client, cuadrilla_inactiva,
    ):
        """Sin login → redirect al login (no 200)."""
        url = reverse('cuadrillas:reactivar', kwargs={'pk': cuadrilla_inactiva.pk})
        resp = client.post(url)
        # 302 a /login o 403; cualquiera distinto de 200 OK con cuadrilla reactivada
        cuadrilla_inactiva.refresh_from_db()
        assert cuadrilla_inactiva.activa is False  # NO se reactivó

    def test_b3_reactivar_permisos_rbac_liniero_negado(
        self, client, liniero_user, user_password, cuadrilla_inactiva,
    ):
        """RBAC: liniero NO puede reactivar (403)."""
        client.login(username=liniero_user.email, password=user_password)
        url = reverse('cuadrillas:reactivar', kwargs={'pk': cuadrilla_inactiva.pk})
        resp = client.post(url)
        assert resp.status_code in (302, 403)
        cuadrilla_inactiva.refresh_from_db()
        assert cuadrilla_inactiva.activa is False

    def test_b3_desactivar_via_view(
        self, client, admin_user, user_password, cuadrilla_activa,
    ):
        """POST /cuadrillas/<uuid>/desactivar/ con motivo → cuadrilla queda inactiva."""
        client.login(username=admin_user.email, password=user_password)
        url = reverse('cuadrillas:desactivar', kwargs={'pk': cuadrilla_activa.pk})
        resp = client.post(url, {'motivo': 'Test motivo'})
        assert resp.status_code in (200, 302)
        cuadrilla_activa.refresh_from_db()
        assert cuadrilla_activa.activa is False
        assert cuadrilla_activa.motivo_desactivacion == 'Test motivo'
        assert cuadrilla_activa.fecha_desactivacion is not None
        assert cuadrilla_activa.desactivado_por_id == admin_user.id
