import io

import pytest
from django.core.cache import cache
from openpyxl import Workbook, load_workbook

from apps.core.models_roles import Role, RoleModuloPermiso
from apps.financiero.models_finv2_carga import HomologacionProjectsContable


def _homologacion(**overrides):
    data = dict(tipo='REAL', grupo='QA', concepto='QA_E2E_247 legacy', rubro='R', codigo_contable='5100', centro_costo='CC-01')
    data.update(overrides)
    return HomologacionProjectsContable.objects.create(**data)


@pytest.mark.django_db
def test_247_c_crud_archiva_filtra_y_exporta_sin_borrado(client, admin_user):
    client.force_login(admin_user)
    vigente, archivada = _homologacion(), _homologacion(concepto='QA_E2E_247 archivar', codigo_contable='6100')
    response = client.post('/financiero/carga-financiera/', {'accion': 'archivar_homologacion', 'pk': archivada.pk}, follow=True)
    assert 'archivada' in response.content.decode().lower()
    archivada.refresh_from_db()
    assert not archivada.activo and HomologacionProjectsContable.objects.filter(pk=archivada.pk).exists()
    response = client.get('/financiero/carga-financiera/?buscar=legacy')
    assert vigente.concepto in response.content.decode()
    response = client.get('/financiero/carga-financiera/homologacion/xlsx/')
    book = load_workbook(io.BytesIO(response.content), read_only=True)
    rows = list(book.active.values)
    assert any(row[2] == vigente.concepto for row in rows)
    assert not any(row[2] == archivada.concepto for row in rows)


@pytest.mark.django_db
def test_247_c_rbac_granular_consulta_pero_no_muta(client, django_user_model):
    role = Role.objects.create(codigo='qa_janet_247', nombre='Janet QA', nivel='operario')
    RoleModuloPermiso.objects.create(role=role, modulo='MANTENIMIENTO', submodulo='FIN_HOMOLOGACION', nivel_acceso='ver')
    user = django_user_model.objects.create_user(email='janet-247@example.test', password='x', rol=role.codigo)
    cache.clear()
    client.force_login(user)
    assert client.get('/financiero/carga-financiera/').status_code == 200
    assert client.post('/financiero/carga-financiera/', {'accion': 'homologar'}).status_code == 403


@pytest.mark.django_db
def test_247_c_edicion_requiere_permiso_y_conserva_registro(client, admin_user):
    client.force_login(admin_user)
    fila = _homologacion()
    response = client.post('/financiero/carga-financiera/', {'accion': 'editar_homologacion', 'pk': fila.pk, 'codigo_contable': '6101', 'centro_costo': 'CC-77'}, follow=True)
    assert response.status_code == 200
    fila.refresh_from_db()
    assert fila.codigo_contable == '6101' and fila.centro_costo == 'CC-77'
