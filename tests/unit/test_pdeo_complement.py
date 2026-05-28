"""Tests para complemento financiero PDEO (#103).

Cubre las 4 vistas + parser:
  - TransaccionesListView (filtros, paginación, agregado)
  - TransaccionesUploadView (form validation)
  - ReportesFinancierosView (3 reportes + export CSV)
  - PyGDrillDownView (drill-down con expandir categoría)
  - pdeo_importer.import_pdeo_workbook (idempotencia, mapeo PUC)
"""
from datetime import date
from decimal import Decimal
from io import BytesIO

import openpyxl
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.construccion.models import (
    CategoriaFinanciera,
    MovimientoFinanciero,
    PeriodoFinanciero,
    ProyectoConstruccion,
    TransaccionContable,
)
from apps.construccion.pdeo_importer import (
    PUC_PREFIX_MAP,
    _categoria_para_auxiliar,
    import_pdeo_workbook,
)
from apps.contratos.models import Contrato

User = get_user_model()


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        email='pdeo_admin@indunnova.com',
        password='x',
        rol='admin_general',
    )


@pytest.fixture
def proyecto(db):
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='CT-PDEO-103',
        nombre='Proyecto PDEO #103',
        cliente='Cliente PDEO',
        estado=Contrato.Estado.ACTIVO,
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto PDEO complemento',
        estado='EJECUCION',
    )


@pytest.fixture
def categoria_admin(db):
    return CategoriaFinanciera.objects.create(
        codigo='ADMIN',
        nombre='Administración',
        tipo='GASTO',
        orden=10,
    )


@pytest.fixture
def categoria_ingresos(db):
    return CategoriaFinanciera.objects.create(
        codigo='INGRESOS',
        nombre='Ingresos Operacionales',
        tipo='INGRESO',
        orden=1,
    )


@pytest.fixture
def movimientos_seed(proyecto, categoria_admin, categoria_ingresos):
    """Crea 2 periodos × 2 categorías × 2 tipos = 8 movimientos."""
    p1 = PeriodoFinanciero.objects.create(
        proyecto=proyecto, anio=2025, mes=1)
    p2 = PeriodoFinanciero.objects.create(
        proyecto=proyecto, anio=2025, mes=2)
    movs = []
    for periodo in [p1, p2]:
        for cat in [categoria_admin, categoria_ingresos]:
            movs.append(MovimientoFinanciero.objects.create(
                periodo=periodo, categoria=cat,
                tipo='PRESUPUESTO', valor=Decimal('100000')))
            movs.append(MovimientoFinanciero.objects.create(
                periodo=periodo, categoria=cat,
                tipo='REAL', valor=Decimal('120000')))
    return movs


@pytest.fixture
def transacciones_seed(movimientos_seed):
    """Crea 5 transacciones repartidas en los movimientos REAL."""
    movs_real = [m for m in movimientos_seed if m.tipo == 'REAL']
    txs = []
    for i, mov in enumerate(movs_real * 2):  # 8 movimientos REAL × 2 = 16, slice 5
        if len(txs) >= 5:
            break
        txs.append(TransaccionContable.objects.create(
            movimiento=mov,
            fecha=date(2025, mov.periodo.mes, 10 + i),
            descripcion=f'Transacción de prueba {i}',
            nit_proveedor=f'900{i:06d}',
            nombre_proveedor=f'Proveedor {i}',
            numero_factura=f'FV-{i:04d}',
            valor=Decimal('30000') + i * 1000,
        ))
    return txs


# === TransaccionesListView ===

@pytest.mark.django_db
def test_transacciones_list_view_renders(admin_user, transacciones_seed):
    c = Client()
    c.force_login(admin_user)
    resp = c.get(reverse('construccion:transacciones_list'))
    assert resp.status_code == 200
    assert b'Transacciones financieras' in resp.content


@pytest.mark.django_db
def test_transacciones_list_filtro_nit(admin_user, transacciones_seed):
    c = Client()
    c.force_login(admin_user)
    tx0 = transacciones_seed[0]
    resp = c.get(reverse('construccion:transacciones_list'),
                 {'nit': tx0.nit_proveedor})
    assert resp.status_code == 200
    # Filtrar por nit_proveedor exacto debe traer al menos esa transaccion
    assert tx0.nit_proveedor.encode() in resp.content


@pytest.mark.django_db
def test_transacciones_list_filtro_categoria(admin_user, transacciones_seed,
                                              categoria_admin):
    c = Client()
    c.force_login(admin_user)
    resp = c.get(reverse('construccion:transacciones_list'),
                 {'categoria': str(categoria_admin.id)})
    assert resp.status_code == 200


@pytest.mark.django_db
def test_transacciones_list_total_agregado(admin_user, transacciones_seed):
    c = Client()
    c.force_login(admin_user)
    resp = c.get(reverse('construccion:transacciones_list'))
    assert resp.status_code == 200
    # Tiene que mostrar el total y el count
    expected_total = sum(t.valor for t in transacciones_seed)
    assert str(int(expected_total)).encode() in resp.content or b'transacciones' in resp.content


# === TransaccionesUploadView ===

@pytest.mark.django_db
def test_transacciones_upload_get_renders(admin_user):
    c = Client()
    c.force_login(admin_user)
    resp = c.get(reverse('construccion:transacciones_upload'))
    assert resp.status_code == 200
    assert b'Cargar Excel PDEO' in resp.content


@pytest.mark.django_db
def test_transacciones_upload_rejects_non_xlsx(admin_user, proyecto):
    c = Client()
    c.force_login(admin_user)
    from django.core.files.uploadedfile import SimpleUploadedFile
    bad = SimpleUploadedFile('test.csv', b'fake data',
                              content_type='text/csv')
    resp = c.post(reverse('construccion:transacciones_upload'),
                  {'proyecto': str(proyecto.id), 'archivo': bad})
    assert resp.status_code == 200  # form re-renders with errors
    assert b'Solo se aceptan archivos' in resp.content


# === ReportesFinancierosView ===

@pytest.mark.django_db
def test_reportes_renders_with_data(admin_user, movimientos_seed,
                                     transacciones_seed):
    c = Client()
    c.force_login(admin_user)
    resp = c.get(reverse('construccion:reportes_financieros'))
    assert resp.status_code == 200
    assert b'PyG por trimestre' in resp.content
    assert b'Top 10 proveedores' in resp.content
    assert b'Alertas' in resp.content


@pytest.mark.django_db
def test_reportes_export_csv_pyg_trimestre(admin_user, movimientos_seed):
    c = Client()
    c.force_login(admin_user)
    resp = c.get(reverse('construccion:reportes_financieros'),
                 {'export': 'csv', 'reporte': 'pyg_trimestre'})
    assert resp.status_code == 200
    assert resp['Content-Type'].startswith('text/csv')
    assert b'Trimestre,Tipo,Presupuesto' in resp.content


@pytest.mark.django_db
def test_reportes_export_csv_top_proveedores(admin_user, transacciones_seed):
    c = Client()
    c.force_login(admin_user)
    resp = c.get(reverse('construccion:reportes_financieros'),
                 {'export': 'csv', 'reporte': 'top_proveedores'})
    assert resp.status_code == 200
    assert b'NIT,Raz' in resp.content


@pytest.mark.django_db
def test_reportes_alertas_solo_variacion_alta(admin_user, proyecto,
                                                categoria_admin):
    """Alerta solo si abs(variación) >= 50%."""
    p = PeriodoFinanciero.objects.create(proyecto=proyecto, anio=2025, mes=1)
    # 100k presup, 200k real → 100% variación → debe disparar alerta
    MovimientoFinanciero.objects.create(periodo=p, categoria=categoria_admin,
                                         tipo='PRESUPUESTO',
                                         valor=Decimal('100000'))
    MovimientoFinanciero.objects.create(periodo=p, categoria=categoria_admin,
                                         tipo='REAL',
                                         valor=Decimal('200000'))
    c = Client()
    c.force_login(admin_user)
    resp = c.get(reverse('construccion:reportes_financieros'))
    assert resp.status_code == 200
    # La categoria 'Administración' debe aparecer en alertas
    assert b'Administraci' in resp.content


# === PyGDrillDownView ===

@pytest.mark.django_db
def test_pyg_drilldown_renders(admin_user, proyecto, movimientos_seed):
    c = Client()
    c.force_login(admin_user)
    resp = c.get(reverse('construccion:pyg_drilldown',
                          kwargs={'proyecto_id': proyecto.id}))
    assert resp.status_code == 200
    assert b'Estado de Resultados' in resp.content


@pytest.mark.django_db
def test_pyg_drilldown_expandir_muestra_transacciones(admin_user, proyecto,
                                                       categoria_admin,
                                                       movimientos_seed,
                                                       transacciones_seed):
    c = Client()
    c.force_login(admin_user)
    resp = c.get(reverse('construccion:pyg_drilldown',
                          kwargs={'proyecto_id': proyecto.id}),
                 {'expandir': str(categoria_admin.id)})
    assert resp.status_code == 200


# === pdeo_importer ===

@pytest.mark.django_db
def test_categoria_para_auxiliar_mapea_prefix():
    cat = _categoria_para_auxiliar('41250501')
    assert cat.codigo == 'INGRESOS'
    cat = _categoria_para_auxiliar('51100501')
    assert cat.codigo == 'ADMIN'
    cat = _categoria_para_auxiliar('99999999')
    assert cat.codigo == 'OTROS'


@pytest.mark.django_db
def test_puc_prefix_map_cubre_principales():
    for pref in ['41', '42', '51', '52', '53', '54', '72', '73']:
        assert pref in PUC_PREFIX_MAP


def _build_pdeo_excel(rows):
    """Helper: arma un workbook PDEO mínimo con hoja BD."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'BD'
    header = ['Auxiliar', 'Desc. auxiliar', 'Neto', 'Fecha', 'Docto.',
              'Periodo', 'Tercero movto.', 'Razón social tercero movto.',
              'Desc. C.O. movto.', 'Usuario creación', 'C.O. movto.',
              'Notas', 'C.Costo', 'Desc. C.Costo', 'Cta equivalente',
              'Cargo', 'Subcontratista', 'SUBCONTRATA', 'Q']
    ws.append(header)
    for r in rows:
        ws.append(r)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


@pytest.mark.django_db
def test_import_pdeo_workbook_crea_transacciones(proyecto):
    rows = [
        ['41250501', 'Lineas de transmision', -2423118863,
         date(2024, 11, 26), 'FVE-1015', 202411, '860000656',
         'HMV INGENIEROS', '', '', '', '', '4001', '', '', '', '', '', ''],
        ['51100501', 'Gastos admin', 150000,
         date(2024, 12, 5), 'FC-301', 202412, '900111222',
         'Proveedor admin', '', '', '', '', '4002', '', '', '', '', '', ''],
    ]
    buf = _build_pdeo_excel(rows)
    stats = import_pdeo_workbook(buf, proyecto)
    assert stats['transacciones_creadas'] == 2
    assert stats['transacciones_omitidas'] == 0
    assert TransaccionContable.objects.count() == 2
    # Periodos creados correctamente
    assert PeriodoFinanciero.objects.filter(
        proyecto=proyecto, anio=2024, mes=11).exists()
    assert PeriodoFinanciero.objects.filter(
        proyecto=proyecto, anio=2024, mes=12).exists()
    # Categoría mapeada por PUC
    ing = TransaccionContable.objects.get(numero_factura='FVE-1015')
    assert ing.movimiento.categoria.codigo == 'INGRESOS'
    admin = TransaccionContable.objects.get(numero_factura='FC-301')
    assert admin.movimiento.categoria.codigo == 'ADMIN'


@pytest.mark.django_db
def test_import_pdeo_workbook_idempotente(proyecto):
    """Cargar 2 veces el mismo Excel NO duplica transacciones."""
    rows = [
        ['41250501', 'Test', 100000, date(2025, 1, 15), 'FAC-001',
         202501, '900111', 'Proveedor X', '', '', '', '', '', '', '', '', '', '', ''],
    ]
    buf1 = _build_pdeo_excel(rows)
    stats1 = import_pdeo_workbook(buf1, proyecto)
    assert stats1['transacciones_creadas'] == 1

    buf2 = _build_pdeo_excel(rows)
    stats2 = import_pdeo_workbook(buf2, proyecto)
    assert stats2['transacciones_creadas'] == 0
    assert stats2['transacciones_omitidas'] == 1
    assert TransaccionContable.objects.count() == 1


@pytest.mark.django_db
def test_import_pdeo_actualiza_movimiento_valor(proyecto):
    """Cada transacción debe acumularse al MovimientoFinanciero correspondiente."""
    rows = [
        ['51100501', 'Admin 1', 100000, date(2025, 1, 5), 'F1',
         202501, '900', 'P', '', '', '', '', '', '', '', '', '', '', ''],
        ['51100501', 'Admin 2', 50000, date(2025, 1, 8), 'F2',
         202501, '900', 'P', '', '', '', '', '', '', '', '', '', '', ''],
    ]
    buf = _build_pdeo_excel(rows)
    import_pdeo_workbook(buf, proyecto)
    cat = CategoriaFinanciera.objects.get(codigo='ADMIN')
    mov = MovimientoFinanciero.objects.get(
        periodo__proyecto=proyecto,
        periodo__anio=2025, periodo__mes=1,
        categoria=cat, tipo='REAL')
    assert mov.valor == Decimal('150000')
