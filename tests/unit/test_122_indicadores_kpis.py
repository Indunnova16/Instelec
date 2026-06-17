"""#122 (rebote): los 6 KPIs técnico-financieros + ANS deben aparecer en el
Dashboard de Indicadores (/indicadores/), no solo en /financiero/."""
import pytest
from django.urls import reverse


@pytest.mark.django_db
class Test122IndicadoresKPIs:
    def test_helper_devuelve_6_kpis_y_ans(self):
        from apps.financiero.indicadores_finv2 import contexto_indicadores_finv2
        ctx = contexto_indicadores_finv2(anio=2026, mes=0)
        assert len(ctx['indicadores_tecnico_financieros']) == 6
        assert len(ctx['indicadores_ans']) == 9
        assert 'resumen_ans' in ctx

    def test_dashboard_indicadores_expone_kpis(self, client, admin_user, user_password):
        client.force_login(admin_user)
        resp = client.get(reverse('indicadores:dashboard'))
        assert resp.status_code == 200
        # #122: el dashboard que ve el cliente ahora trae las 2 tablas nuevas.
        assert len(resp.context['indicadores_tecnico_financieros']) == 6
        assert len(resp.context['indicadores_ans']) == 9
