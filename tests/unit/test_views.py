"""
Tests for Django views.

These tests cover all major views in the application with:
- Response codes (200, 302, 403, 404)
- Redirections for unauthenticated users
- Template verification
- Basic context validation
"""

import pytest
from django.urls import reverse
from django.test import Client

from tests.factories import (
    LineaFactory,
    TorreFactory,
    CuadrillaFactory,
    CuadrillaMiembroFactory,
    ActividadFactory,
    ActividadEnCursoFactory,
    ProgramacionMensualFactory,
    RegistroCampoFactory,
    EvidenciaFactory,
    PresupuestoFactory,
    PresupuestoEnEjecucionFactory,
    CicloFacturacionFactory,
    IndicadorFactory,
    MedicionIndicadorFactory,
    ActaSeguimientoFactory,
    AdminFactory,
    CoordinadorFactory,
    IngenieroResidenteFactory,
    LinieroFactory,
)


# ==============================================================================
# Authentication Views Tests
# ==============================================================================

@pytest.mark.django_db
class TestAuthenticationViews:
    """Tests for authentication views (login, logout)."""

    def test_login_view_get(self, client):
        """Test that login page is accessible."""
        url = reverse('usuarios:login')
        response = client.get(url)

        assert response.status_code == 200
        assert 'usuarios/login.html' in [t.name for t in response.templates]

    def test_login_view_post_valid_credentials(self, client, user_password):
        """Test login with valid credentials redirects to home."""
        user = AdminFactory()
        url = reverse('usuarios:login')

        response = client.post(url, {
            'username': user.email,
            'password': user_password,
        })

        assert response.status_code == 302
        assert response.url == reverse('core:home')

    def test_login_view_post_invalid_credentials(self, client):
        """Test login with invalid credentials shows error."""
        url = reverse('usuarios:login')

        response = client.post(url, {
            'username': 'nonexistent@test.com',
            'password': 'wrongpassword',
        })

        assert response.status_code == 200
        # Should stay on login page

    def test_login_view_authenticated_user_redirect(self, client, admin_user, user_password):
        """Test authenticated user is redirected from login."""
        client.login(email=admin_user.email, password=user_password)
        url = reverse('usuarios:login')

        response = client.get(url)

        # redirect_authenticated_user = True in CustomLoginView
        assert response.status_code == 302

    def test_logout_view(self, client, admin_user, user_password):
        """Test logout redirects to login page."""
        client.login(email=admin_user.email, password=user_password)
        url = reverse('usuarios:logout')

        response = client.post(url)

        assert response.status_code == 302
        assert response.url == reverse('usuarios:login')


# ==============================================================================
# Profile Views Tests
# ==============================================================================

@pytest.mark.django_db
class TestProfileViews:
    """Tests for user profile views."""

    def test_perfil_view_requires_login(self, client):
        """Test profile view requires authentication."""
        url = reverse('usuarios:perfil')
        response = client.get(url)

        assert response.status_code == 302
        assert 'login' in response.url

    def test_perfil_view_authenticated(self, client, admin_user, user_password):
        """Test profile view for authenticated user."""
        client.login(email=admin_user.email, password=user_password)
        url = reverse('usuarios:perfil')

        response = client.get(url)

        assert response.status_code == 200
        assert 'usuarios/perfil.html' in [t.name for t in response.templates]
        assert 'usuario' in response.context

    def test_perfil_edit_view_requires_login(self, client):
        """Test profile edit requires authentication."""
        url = reverse('usuarios:perfil_edit')
        response = client.get(url)

        assert response.status_code == 302
        assert 'login' in response.url

    def test_perfil_edit_view_authenticated(self, client, admin_user, user_password):
        """Test profile edit view for authenticated user."""
        client.login(email=admin_user.email, password=user_password)
        url = reverse('usuarios:perfil_edit')

        response = client.get(url)

        assert response.status_code == 200
        assert 'usuarios/perfil_edit.html' in [t.name for t in response.templates]


# ==============================================================================
# Core Views Tests (Dashboard, Health)
# ==============================================================================

@pytest.mark.django_db
class TestCoreViews:
    """Tests for core views (home/dashboard, health check)."""

    def test_home_view_requires_login(self, client):
        """Test home view requires authentication."""
        url = reverse('core:home')
        response = client.get(url)

        assert response.status_code == 302
        assert 'login' in response.url

    def test_home_view_authenticated_admin(self, client, admin_user, user_password):
        """Test home view shows full dashboard for admin."""
        client.login(email=admin_user.email, password=user_password)
        url = reverse('core:home')

        response = client.get(url)

        assert response.status_code == 200
        assert 'core/home.html' in [t.name for t in response.templates]
        assert response.context['show_full_dashboard'] is True

    def test_home_view_authenticated_liniero(self, client, liniero_user, user_password):
        """Test home view shows limited dashboard for liniero."""
        client.login(email=liniero_user.email, password=user_password)
        url = reverse('core:home')

        response = client.get(url)

        assert response.status_code == 200
        assert response.context['show_full_dashboard'] is False

    def test_health_check_simple(self, client):
        """Test simple health check endpoint."""
        url = reverse('core:api_health_simple')
        response = client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'ok'


# ==============================================================================
# Lineas Views Tests
# ==============================================================================

@pytest.mark.django_db
class TestLineasViews:
    """Tests for transmission lines views."""

    def test_linea_list_requires_login(self, client):
        """Test linea list requires authentication."""
        url = reverse('lineas:lista')
        response = client.get(url)

        assert response.status_code == 302
        assert 'login' in response.url

    def test_linea_list_view(self, client, admin_user, user_password):
        """Test linea list view."""
        client.login(email=admin_user.email, password=user_password)
        LineaFactory.create_batch(3)
        url = reverse('lineas:lista')

        response = client.get(url)

        assert response.status_code == 200
        assert 'lineas/lista.html' in [t.name for t in response.templates]
        assert 'lineas' in response.context

    def test_linea_list_with_filter(self, client, admin_user, user_password):
        """Test linea list with search filter."""
        client.login(email=admin_user.email, password=user_password)
        linea = LineaFactory(nombre="Linea Especial Test")
        url = reverse('lineas:lista')

        response = client.get(url, {'buscar': 'Especial'})

        assert response.status_code == 200

    def test_linea_detail_view(self, client, admin_user, user_password, linea):
        """Test linea detail view."""
        client.login(email=admin_user.email, password=user_password)
        url = reverse('lineas:detalle', kwargs={'pk': linea.pk})

        response = client.get(url)

        assert response.status_code == 200
        assert 'lineas/detalle.html' in [t.name for t in response.templates]
        assert response.context['linea'] == linea

    def test_linea_detail_404(self, client, admin_user, user_password):
        """Test linea detail view with non-existent ID."""
        import uuid
        client.login(email=admin_user.email, password=user_password)
        url = reverse('lineas:detalle', kwargs={'pk': uuid.uuid4()})

        response = client.get(url)

        assert response.status_code == 404

    def test_torres_linea_view(self, client, admin_user, user_password, linea):
        """Test torres list for a linea."""
        client.login(email=admin_user.email, password=user_password)
        TorreFactory.create_batch(3, linea=linea)
        url = reverse('lineas:torres', kwargs={'pk': linea.pk})

        response = client.get(url)

        assert response.status_code == 200
        assert 'torres' in response.context
        assert response.context['linea'] == linea

    def test_torre_detail_view(self, client, admin_user, user_password, torre):
        """Test torre detail view."""
        client.login(email=admin_user.email, password=user_password)
        url = reverse('lineas:torre_detalle', kwargs={'pk': torre.pk})

        response = client.get(url)

        assert response.status_code == 200
        assert 'lineas/torre_detalle.html' in [t.name for t in response.templates]
        assert response.context['torre'] == torre

    def test_mapa_lineas_view(self, client, admin_user, user_password):
        """Test map view for lines."""
        client.login(email=admin_user.email, password=user_password)
        linea = LineaFactory()
        TorreFactory.create_batch(3, linea=linea)
        url = reverse('lineas:mapa')

        response = client.get(url)

        assert response.status_code == 200
        assert 'lineas/mapa.html' in [t.name for t in response.templates]
        assert 'lineas' in response.context
        assert 'torres_json' in response.context


# ==============================================================================
# Cuadrillas Views Tests
# ==============================================================================

@pytest.mark.django_db
class TestCuadrillasViews:
    """Tests for crew management views."""

    def test_cuadrilla_list_requires_login(self, client):
        """Test cuadrilla list requires authentication."""
        url = reverse('cuadrillas:lista')
        response = client.get(url)

        assert response.status_code == 302
        assert 'login' in response.url

    def test_cuadrilla_list_view(self, client, admin_user, user_password):
        """Test cuadrilla list view."""
        client.login(email=admin_user.email, password=user_password)
        CuadrillaFactory.create_batch(3)
        url = reverse('cuadrillas:lista')

        response = client.get(url)

        assert response.status_code == 200
        assert 'cuadrillas/lista.html' in [t.name for t in response.templates]
        assert 'cuadrillas' in response.context

    def test_cuadrilla_detail_view(self, client, admin_user, user_password, cuadrilla):
        """Test cuadrilla detail view."""
        client.login(email=admin_user.email, password=user_password)
        url = reverse('cuadrillas:detalle', kwargs={'pk': cuadrilla.pk})

        response = client.get(url)

        assert response.status_code == 200
        assert 'cuadrillas/detalle.html' in [t.name for t in response.templates]
        assert response.context['cuadrilla'] == cuadrilla
        assert 'miembros' in response.context

    def test_mapa_cuadrillas_view(self, client, admin_user, user_password):
        """Test real-time map view for crews."""
        client.login(email=admin_user.email, password=user_password)
        url = reverse('cuadrillas:mapa')

        response = client.get(url)

        assert response.status_code == 200
        assert 'cuadrillas/mapa.html' in [t.name for t in response.templates]


# ==============================================================================
# Actividades Views Tests
# ==============================================================================

@pytest.mark.django_db
class TestActividadesViews:
    """Tests for activity management views."""

    def test_actividad_list_requires_login(self, client):
        """Test actividad list requires authentication."""
        url = reverse('actividades:lista')
        response = client.get(url)

        assert response.status_code == 302
        assert 'login' in response.url

    def test_actividad_list_view(self, client, admin_user, user_password):
        """Test actividad list view."""
        client.login(email=admin_user.email, password=user_password)
        ActividadFactory.create_batch(3)
        url = reverse('actividades:lista')

        response = client.get(url)

        assert response.status_code == 200
        assert 'actividades/lista.html' in [t.name for t in response.templates]
        assert 'actividades' in response.context
        assert 'estados' in response.context
        assert 'tipos' in response.context

    def test_actividad_list_with_estado_filter(self, client, admin_user, user_password):
        """Test actividad list with estado filter."""
        client.login(email=admin_user.email, password=user_password)
        ActividadFactory(estado='PENDIENTE')
        ActividadEnCursoFactory()
        url = reverse('actividades:lista')

        response = client.get(url, {'estado': 'PENDIENTE'})

        assert response.status_code == 200

    def test_actividad_detail_view(self, client, admin_user, user_password, actividad_pendiente):
        """Test actividad detail view."""
        client.login(email=admin_user.email, password=user_password)
        url = reverse('actividades:detalle', kwargs={'pk': actividad_pendiente.pk})

        response = client.get(url)

        assert response.status_code == 200
        assert 'actividades/detalle.html' in [t.name for t in response.templates]
        assert response.context['actividad'] == actividad_pendiente
        assert 'registros' in response.context

    def test_actividad_detail_404(self, client, admin_user, user_password):
        """Test actividad detail view with non-existent ID."""
        import uuid
        client.login(email=admin_user.email, password=user_password)
        url = reverse('actividades:detalle', kwargs={'pk': uuid.uuid4()})

        response = client.get(url)

        assert response.status_code == 404

    def test_calendario_view(self, client, admin_user, user_password):
        """Test calendar view."""
        client.login(email=admin_user.email, password=user_password)
        url = reverse('actividades:calendario')

        response = client.get(url)

        assert response.status_code == 200
        assert 'actividades/calendario.html' in [t.name for t in response.templates]
        assert 'mes' in response.context
        assert 'anio' in response.context
        assert 'semanas' in response.context

    def test_programacion_view_requires_role(self, client, liniero_user, user_password):
        """Test programacion view requires specific roles."""
        client.login(email=liniero_user.email, password=user_password)
        url = reverse('actividades:programacion')

        response = client.get(url)

        # Liniero does not have access - should be 403
        assert response.status_code == 403

    def test_programacion_view_coordinador(self, client, coordinador_user, user_password):
        """Test programacion view for coordinador."""
        client.login(email=coordinador_user.email, password=user_password)
        ProgramacionMensualFactory.create_batch(2)
        url = reverse('actividades:programacion')

        response = client.get(url)

        assert response.status_code == 200
        assert 'actividades/programacion.html' in [t.name for t in response.templates]
        assert 'programaciones' in response.context

    def test_importar_programacion_requires_role(self, client, ingeniero_user, user_password):
        """Test import view requires admin/director/coordinador role."""
        client.login(email=ingeniero_user.email, password=user_password)
        url = reverse('actividades:importar')

        response = client.get(url)

        # Ingeniero residente doesn't have access
        assert response.status_code == 403

    def test_importar_programacion_admin(self, client, admin_user, user_password):
        """Test import view for admin."""
        client.login(email=admin_user.email, password=user_password)
        url = reverse('actividades:importar')

        response = client.get(url)

        assert response.status_code == 200
        assert 'actividades/importar.html' in [t.name for t in response.templates]


# ==============================================================================
# Campo Views Tests
# ==============================================================================

@pytest.mark.django_db
class TestCampoViews:
    """Tests for field record views."""

    def test_registro_list_requires_login(self, client):
        """Test registro list requires authentication."""
        url = reverse('campo:lista')
        response = client.get(url)

        assert response.status_code == 302
        assert 'login' in response.url

    def test_registro_list_view(self, client, admin_user, user_password):
        """Test registro list view."""
        client.login(email=admin_user.email, password=user_password)
        RegistroCampoFactory.create_batch(3)
        url = reverse('campo:lista')

        response = client.get(url)

        assert response.status_code == 200
        assert 'campo/lista.html' in [t.name for t in response.templates]
        assert 'registros' in response.context

    def test_registro_detail_view(self, client, admin_user, user_password, registro_campo):
        """Test registro detail view."""
        client.login(email=admin_user.email, password=user_password)
        url = reverse('campo:detalle', kwargs={'pk': registro_campo.pk})

        response = client.get(url)

        assert response.status_code == 200
        assert 'campo/detalle.html' in [t.name for t in response.templates]
        assert response.context['registro'] == registro_campo
        assert 'evidencias_antes' in response.context
        assert 'evidencias_durante' in response.context
        assert 'evidencias_despues' in response.context

    def test_evidencias_view(self, client, admin_user, user_password, registro_campo):
        """Test evidencias view for a registro."""
        client.login(email=admin_user.email, password=user_password)
        EvidenciaFactory.create_batch(3, registro_campo=registro_campo)
        url = reverse('campo:evidencias', kwargs={'pk': registro_campo.pk})

        response = client.get(url)

        assert response.status_code == 200
        assert 'campo/evidencias.html' in [t.name for t in response.templates]
        assert 'evidencias' in response.context
        assert 'registro' in response.context


# ==============================================================================
# Financiero Views Tests
# ==============================================================================

@pytest.mark.django_db
class TestFinancieroViews:
    """Tests for financial management views."""

    def test_dashboard_financiero_requires_login(self, client):
        """Test financial dashboard requires authentication."""
        url = reverse('financiero:dashboard')
        response = client.get(url)

        assert response.status_code == 302
        assert 'login' in response.url

    def test_dashboard_financiero_requires_role(self, client, liniero_user, user_password):
        """Test financial dashboard requires specific roles."""
        client.login(email=liniero_user.email, password=user_password)
        url = reverse('financiero:dashboard')

        response = client.get(url)

        assert response.status_code == 403

    def test_dashboard_financiero_admin(self, client, admin_user, user_password):
        """Test financial dashboard for admin."""
        client.login(email=admin_user.email, password=user_password)
        PresupuestoFactory.create_batch(2)
        url = reverse('financiero:dashboard')

        response = client.get(url)

        assert response.status_code == 200
        assert 'financiero/dashboard.html' in [t.name for t in response.templates]
        assert 'total_presupuestado' in response.context
        assert 'total_ejecutado' in response.context

    def test_cuadro_costos_view(self, client, admin_user, user_password):
        """Test cuadro de costos view."""
        client.login(email=admin_user.email, password=user_password)
        url = reverse('financiero:cuadro_costos')

        response = client.get(url)

        assert response.status_code == 200
        assert 'financiero/cuadro_costos.html' in [t.name for t in response.templates]

    def test_facturacion_view(self, client, coordinador_user, user_password):
        """Test facturacion view."""
        client.login(email=coordinador_user.email, password=user_password)
        CicloFacturacionFactory.create_batch(2)
        url = reverse('financiero:facturacion')

        response = client.get(url)

        assert response.status_code == 200
        assert 'financiero/facturacion.html' in [t.name for t in response.templates]
        assert 'ciclos' in response.context


# ==============================================================================
# Indicadores Views Tests
# ==============================================================================

@pytest.mark.django_db
class TestIndicadoresViews:
    """Tests for KPI/indicator views."""

    def test_dashboard_indicadores_requires_login(self, client):
        """Test KPI dashboard requires authentication."""
        url = reverse('indicadores:dashboard')
        response = client.get(url)

        assert response.status_code == 302
        assert 'login' in response.url

    def test_dashboard_indicadores_view(self, client, admin_user, user_password):
        """Test KPI dashboard view."""
        client.login(email=admin_user.email, password=user_password)
        indicador = IndicadorFactory()
        MedicionIndicadorFactory(indicador=indicador)
        url = reverse('indicadores:dashboard')

        response = client.get(url)

        assert response.status_code == 200
        assert 'indicadores/dashboard.html' in [t.name for t in response.templates]
        assert 'indicadores' in response.context
        assert 'mediciones' in response.context
        assert 'mes' in response.context
        assert 'anio' in response.context

    def test_indicador_detail_view(self, client, admin_user, user_password):
        """Test indicador detail view."""
        client.login(email=admin_user.email, password=user_password)
        indicador = IndicadorFactory()
        MedicionIndicadorFactory.create_batch(3, indicador=indicador)
        url = reverse('indicadores:detalle', kwargs={'pk': indicador.pk})

        response = client.get(url)

        assert response.status_code == 200
        assert 'indicadores/detalle.html' in [t.name for t in response.templates]
        assert response.context['indicador'] == indicador
        assert 'historial' in response.context

    def test_acta_list_requires_role(self, client, liniero_user, user_password):
        """Test acta list requires specific roles."""
        client.login(email=liniero_user.email, password=user_password)
        url = reverse('indicadores:actas')

        response = client.get(url)

        assert response.status_code == 403

    def test_acta_list_view_coordinador(self, client, coordinador_user, user_password):
        """Test acta list view for coordinador."""
        client.login(email=coordinador_user.email, password=user_password)
        ActaSeguimientoFactory.create_batch(3)
        url = reverse('indicadores:actas')

        response = client.get(url)

        assert response.status_code == 200
        assert 'indicadores/actas.html' in [t.name for t in response.templates]
        assert 'actas' in response.context

    def test_acta_detail_view(self, client, ingeniero_user, user_password):
        """Test acta detail view for ingeniero residente."""
        client.login(email=ingeniero_user.email, password=user_password)
        acta = ActaSeguimientoFactory()
        url = reverse('indicadores:acta_detalle', kwargs={'pk': acta.pk})

        response = client.get(url)

        assert response.status_code == 200
        assert 'indicadores/acta_detalle.html' in [t.name for t in response.templates]
        assert response.context['acta'] == acta


# ==============================================================================
# HTMX Views Tests
# ==============================================================================

@pytest.mark.django_db
class TestHTMXViews:
    """Tests for HTMX partial views."""

    def test_actividad_list_htmx_partial(self, client, admin_user, user_password):
        """Test actividad list returns partial template for HTMX requests."""
        client.login(email=admin_user.email, password=user_password)
        url = reverse('actividades:lista')

        response = client.get(url, HTTP_HX_REQUEST='true')

        assert response.status_code == 200
        # Should use partial template
        template_names = [t.name for t in response.templates]
        assert 'actividades/partials/lista_actividades.html' in template_names

    def test_linea_list_htmx_partial(self, client, admin_user, user_password):
        """Test linea list returns partial template for HTMX requests."""
        client.login(email=admin_user.email, password=user_password)
        url = reverse('lineas:lista')

        response = client.get(url, HTTP_HX_REQUEST='true')

        assert response.status_code == 200
        template_names = [t.name for t in response.templates]
        assert 'lineas/partials/lista_lineas.html' in template_names

    def test_cuadrilla_mapa_partial_json(self, client, admin_user, user_password):
        """Test cuadrilla map partial returns JSON for Accept: application/json."""
        client.login(email=admin_user.email, password=user_password)
        url = reverse('cuadrillas:mapa_partial')

        response = client.get(url, HTTP_ACCEPT='application/json')

        assert response.status_code == 200
        data = response.json()
        assert 'ubicaciones' in data

    def test_actividad_detail_partial(self, client, admin_user, user_password, actividad_pendiente):
        """Test actividad detail partial view."""
        client.login(email=admin_user.email, password=user_password)
        url = reverse('actividades:detalle_partial', kwargs={'pk': actividad_pendiente.pk})

        response = client.get(url)

        assert response.status_code == 200
        template_names = [t.name for t in response.templates]
        assert 'actividades/partials/detalle_actividad.html' in template_names
