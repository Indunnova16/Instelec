"""Tests Dashboards Curva S (issues #75 #77)."""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.contratos.models import Contrato
from apps.construccion.models import (
    DashboardAvanceSemanal, ProyectoConstruccion, TorreConstruccion,
    recalcular_dashboard_acumulados,
)


@pytest.fixture
def proyecto(db):
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo="CT-DASH", nombre="Dash", cliente="C", estado=Contrato.Estado.ACTIVO,
    )
    p = ProyectoConstruccion.objects.create(
        contrato=contrato, nombre="Dash", estado="EJECUCION",
    )
    # 64 torres como en el ejemplo del issue
    for i in range(1, 65):
        TorreConstruccion.objects.create(proyecto=p, numero=f"T-{i:03d}", tipo="A")
    return p


@pytest.fixture
def admin_client(client, admin_user, user_password):
    client.login(username=admin_user.email, password=user_password)
    return client


@pytest.mark.django_db
class TestRecalcularAcumulados:
    """Issue #75: acumulados se recalculan correctamente."""

    def test_serie_simple(self, proyecto):
        # 3 semanas con 2, 2, 1 programadas y 1, 2, 0 ejecutadas
        for sem, prog, cons in [(date(2026, 1, 5), 2, 1),
                                 (date(2026, 1, 12), 2, 2),
                                 (date(2026, 1, 19), 1, 0)]:
            DashboardAvanceSemanal.objects.create(
                proyecto=proyecto, fase='OOCC', semana=sem,
                torres_programadas_semana=prog,
                torres_construidas_semana=cons,
            )
        recalcular_dashboard_acumulados(proyecto, 'OOCC')
        semanas = list(DashboardAvanceSemanal.objects
                       .filter(proyecto=proyecto, fase='OOCC').order_by('semana'))
        assert [s.torres_programadas_acum for s in semanas] == [2, 4, 5]
        assert [s.torres_construidas_acum for s in semanas] == [1, 3, 3]
        # % sobre 64 torres
        assert semanas[1].pct_programado == pytest.approx(Decimal('6.25'), abs=Decimal('0.01'))
        assert semanas[2].pct_construido == pytest.approx(Decimal('4.6875'), abs=Decimal('0.01'))

    def test_varianza(self, proyecto):
        s = DashboardAvanceSemanal.objects.create(
            proyecto=proyecto, fase='OOCC', semana=date(2026, 1, 5),
            torres_programadas_semana=4, torres_construidas_semana=2,
        )
        recalcular_dashboard_acumulados(proyecto, 'OOCC')
        s.refresh_from_db()
        assert s.varianza_semana == -2
        assert s.varianza_acum == -2


@pytest.mark.django_db
class TestDashboardObraCivilView:
    def test_get_200(self, admin_client, proyecto):
        url = reverse("construccion:dashboard_obra_civil", kwargs={"proyecto_id": proyecto.id})
        resp = admin_client.get(url)
        assert resp.status_code == 200
        assert resp.context["fase_activa"] == "OOCC"

    def test_get_con_fase_query(self, admin_client, proyecto):
        url = reverse("construccion:dashboard_obra_civil", kwargs={"proyecto_id": proyecto.id})
        resp = admin_client.get(url + "?fase=TENDIDO")
        assert resp.context["fase_activa"] == "TENDIDO"

    def test_fase_invalida_default(self, admin_client, proyecto):
        url = reverse("construccion:dashboard_obra_civil", kwargs={"proyecto_id": proyecto.id})
        resp = admin_client.get(url + "?fase=XXX")
        assert resp.context["fase_activa"] == "OOCC"

    def test_indicadores_con_datos(self, admin_client, proyecto):
        DashboardAvanceSemanal.objects.create(
            proyecto=proyecto, fase='OOCC', semana=date(2026, 1, 5),
            torres_programadas_semana=2, torres_construidas_semana=1,
        )
        recalcular_dashboard_acumulados(proyecto, 'OOCC')
        url = reverse("construccion:dashboard_obra_civil", kwargs={"proyecto_id": proyecto.id})
        resp = admin_client.get(url)
        ctx = resp.context
        assert ctx["varianza_acum"] == -1


@pytest.mark.django_db
class TestDashboardMontajeView:
    def test_get_200(self, admin_client, proyecto):
        url = reverse("construccion:dashboard_montaje", kwargs={"proyecto_id": proyecto.id})
        resp = admin_client.get(url)
        assert resp.status_code == 200
        assert resp.context["fase_activa"] == "MONTAJE"


@pytest.mark.django_db
class TestDashboardSemanaUpsert:
    def _url(self, p):
        return reverse("construccion:dashboard_semana_upsert", kwargs={"proyecto_id": p.id})

    def test_crear_actualiza_acumulados(self, admin_client, proyecto):
        resp = admin_client.post(self._url(proyecto), {
            "fase": "OOCC", "semana": "2026-01-05",
            "torres_programadas_semana": "4", "torres_construidas_semana": "2",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["created"] is True
        assert data["prog_acum"] == 4
        assert data["cons_acum"] == 2

    def test_actualizar_recalcula(self, admin_client, proyecto):
        # 2 semanas
        admin_client.post(self._url(proyecto), {
            "fase": "OOCC", "semana": "2026-01-05",
            "torres_programadas_semana": "2", "torres_construidas_semana": "1",
        })
        admin_client.post(self._url(proyecto), {
            "fase": "OOCC", "semana": "2026-01-12",
            "torres_programadas_semana": "3", "torres_construidas_semana": "2",
        })
        # Update primera semana: acumulados deben recalcularse
        resp = admin_client.post(self._url(proyecto), {
            "fase": "OOCC", "semana": "2026-01-05",
            "torres_programadas_semana": "5", "torres_construidas_semana": "3",
        })
        assert resp.status_code == 200
        # Segunda semana ahora debe tener prog_acum=8 (5+3) y cons_acum=5 (3+2)
        s2 = DashboardAvanceSemanal.objects.get(
            proyecto=proyecto, fase='OOCC', semana=date(2026, 1, 12))
        assert int(s2.torres_programadas_acum) == 8
        assert int(s2.torres_construidas_acum) == 5

    def test_fase_invalida(self, admin_client, proyecto):
        resp = admin_client.post(self._url(proyecto), {
            "fase": "XXX", "semana": "2026-01-05",
            "torres_programadas_semana": "1",
        })
        assert resp.status_code == 400

    def test_fecha_invalida(self, admin_client, proyecto):
        resp = admin_client.post(self._url(proyecto), {
            "fase": "OOCC", "semana": "no-fecha",
            "torres_programadas_semana": "1",
        })
        assert resp.status_code == 400

    def test_valor_excede_total_torres(self, admin_client, proyecto):
        resp = admin_client.post(self._url(proyecto), {
            "fase": "OOCC", "semana": "2026-01-05",
            "torres_programadas_semana": "100",  # > 64
        })
        assert resp.status_code == 400

    def test_pendientes_se_persiste_y_se_muestra(self, admin_client, proyecto):
        """Refs #75 #77 — campo pendientes texto libre por semana."""
        resp = admin_client.post(self._url(proyecto), {
            "fase": "OOCC", "semana": "2026-01-05",
            "torres_programadas_semana": "2", "torres_construidas_semana": "1",
            "pendientes": "Clima desfavorable, falta permisos",
        })
        assert resp.status_code == 200
        obj = DashboardAvanceSemanal.objects.get(
            proyecto=proyecto, fase='OOCC', semana=date(2026, 1, 5),
        )
        assert obj.pendientes == "Clima desfavorable, falta permisos"
        # La vista del dashboard debe renderizar el texto
        url_dashboard = reverse("construccion:dashboard_obra_civil",
                                kwargs={"proyecto_id": proyecto.id})
        page = admin_client.get(url_dashboard)
        assert page.status_code == 200
        assert b"Clima desfavorable" in page.content
        # Símbolo Obra Civil debe aparecer en el header (no el genérico 📊)
        assert "🏗️ Dashboard Obra Civil".encode() in page.content


@pytest.mark.django_db
class TestDashboardSemanaDelete:
    def test_delete_recalcula(self, admin_client, proyecto):
        admin_client.post(
            reverse("construccion:dashboard_semana_upsert", kwargs={"proyecto_id": proyecto.id}),
            {"fase": "OOCC", "semana": "2026-01-05",
             "torres_programadas_semana": "2", "torres_construidas_semana": "1"},
        )
        admin_client.post(
            reverse("construccion:dashboard_semana_upsert", kwargs={"proyecto_id": proyecto.id}),
            {"fase": "OOCC", "semana": "2026-01-12",
             "torres_programadas_semana": "3", "torres_construidas_semana": "2"},
        )
        s1 = DashboardAvanceSemanal.objects.get(semana=date(2026, 1, 5))
        url = reverse("construccion:dashboard_semana_delete",
                      kwargs={"proyecto_id": proyecto.id, "pk": s1.id})
        resp = admin_client.post(url)
        assert resp.status_code == 200
        assert not DashboardAvanceSemanal.objects.filter(id=s1.id).exists()
        # La semana sobreviviente ahora tiene prog_acum=3 (solo ella)
        s2 = DashboardAvanceSemanal.objects.get(semana=date(2026, 1, 12))
        assert int(s2.torres_programadas_acum) == 3


@pytest.mark.django_db
class TestDashboardChartData:
    def test_devuelve_3_arrays(self, admin_client, proyecto):
        DashboardAvanceSemanal.objects.create(
            proyecto=proyecto, fase='OOCC', semana=date(2026, 1, 5),
            torres_programadas_semana=2, torres_construidas_semana=1,
        )
        DashboardAvanceSemanal.objects.create(
            proyecto=proyecto, fase='OOCC', semana=date(2026, 1, 12),
            torres_programadas_semana=2, torres_construidas_semana=2,
        )
        recalcular_dashboard_acumulados(proyecto, 'OOCC')
        url = reverse("construccion:dashboard_chart_data", kwargs={"proyecto_id": proyecto.id})
        resp = admin_client.get(url + "?fase=OOCC")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["labels"]) == 2
        assert len(data["planeado"]) == 2
        assert len(data["ejecutado"]) == 2
        assert data["planeado"][0] == pytest.approx(3.125, abs=0.01)  # 2/64*100

    def test_fase_invalida(self, admin_client, proyecto):
        url = reverse("construccion:dashboard_chart_data", kwargs={"proyecto_id": proyecto.id})
        resp = admin_client.get(url + "?fase=XX")
        assert resp.status_code == 400
