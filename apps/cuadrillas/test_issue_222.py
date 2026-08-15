"""Access-control regression tests for Instelec issue #222."""

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.test.client import RequestFactory
from django.urls import reverse

from apps.cuadrillas.views_semanal import ProgramacionSemanalExportarRangoView

Usuario = get_user_model()
EXPORT_RANGO_URL = reverse("cuadrillas:semanal_exportar_rango")
RANGO_VALIDO = {"fecha_inicio": "2026-08-01", "fecha_fin": "2026-08-15"}


class TestProgramacionSemanalExportarRangoPermissions(TestCase):
    """The payroll-range export is reserved for RBAC level ``admin`` users."""

    def _usuario(self, *, email, rol, is_superuser=False):
        return Usuario.objects.create_user(
            email=email,
            password="testpass123!",
            first_name="QA",
            last_name="222",
            rol=rol,
            is_superuser=is_superuser,
            is_staff=is_superuser,
        )

    def test_supervisor_recibe_403_para_exportar_rango_nomina(self):
        """Legacy operational role previously passed ROLES_CUADRILLAS."""
        supervisor = self._usuario(email="supervisor_222@test.local", rol="supervisor")
        request = RequestFactory().get(EXPORT_RANGO_URL, RANGO_VALIDO)
        request.user = supervisor

        # ``NivelAdminRequiredMixin`` raises PermissionDenied for an authenticated
        # user; Django maps that exception to the endpoint's HTTP 403 response.
        with self.assertRaises(PermissionDenied):
            ProgramacionSemanalExportarRangoView.as_view()(request)

    def test_admin_conserva_acceso_al_exportar_rango_nomina(self):
        admin = self._usuario(email="admin_222@test.local", rol="admin")
        self.client.force_login(admin)

        response = self.client.get(EXPORT_RANGO_URL, RANGO_VALIDO)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
