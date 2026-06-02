"""Tests B1 — Importador contable + carga BD en Presupuesto Planeado (#120).

Cubre:
- b1_cargar_bd_form_200: GET de la página de carga responde 200 autenticado.
- b1_presupuesto_planeado_render: importer + render de rubros con datos reales.
- b1_mapeo_crud: CRUD inline de MapeoCtaRubro (crear / editar / eliminar).
- Edge cases del importer: archivo sin columna O, archivo vacío, no-.xlsx.
- Mapeo: cuentas no mapeadas caen en "Otros / No Clasificado".
- Dato legacy: PresupuestoDetallado.datos legacy preservado al cargar BD.

Sub-feature: B1 (issue #120)

NOTA (entorno /modulo): estos tests NO se corren en la máquina de desarrollo
(sin Django). Se difieren a F4 con Docker+PostGIS. Solo py_compile aquí.
"""
import io

import pytest
from openpyxl import Workbook

from django.urls import reverse

from apps.financiero.importers_finv2 import (
    ContableCompleteImporter,
    build_rubro_display_rows,
)
from apps.financiero.models import MapeoCtaRubro, PresupuestoDetallado


# --------------------------------------------------------------------------- #
# Helpers de fixtures Excel en memoria
# --------------------------------------------------------------------------- #
def _excel_bytes(rows, sheet_name='BD', headers=None, name='bd.xlsx'):
    """Construye un .xlsx en memoria con encabezados estilo BD contable."""
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    hdr = headers or [
        'Auxiliar', 'Desc. auxiliar', 'Neto', 'Fecha', 'Docto.', 'Periodo',
        'Tercero movto.', 'Razón social', 'Desc. C.O.', 'Usuario',
        'C.O. movto.', 'Notas', 'C.Costo', 'Desc. C.Costo', 'Cta equivalente',
    ]
    ws.append(hdr)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    buf.name = name
    buf.size = len(buf.getvalue())
    return buf


def _row(auxiliar, desc, neto, cta_equiv):
    """Fila BD con A,B,C poblados y O (índice 15) = cta_equiv."""
    r = [auxiliar, desc, neto, None, None, None, None, None, None, None,
         None, None, None, None, cta_equiv]
    return r


# --------------------------------------------------------------------------- #
# Importer — happy path + edge cases
# --------------------------------------------------------------------------- #
class TestB1Importer:

    def test_b1_importer_happy_agrupa_y_mapea(self):
        """Agrupa por col O sumando col C; mapea a rubro."""
        rows = [
            _row('41250501', 'LINEAS DE TRANSMISION', -100, 'Ingresos Operacionales'),
            _row('41250501', 'LINEAS DE TRANSMISION', -50, 'Ingresos Operacionales'),
            _row('42100501', 'INTERESES', -30, 'Intereses'),
        ]
        archivo = _excel_bytes(rows)
        res = ContableCompleteImporter().procesar_bd_completa(archivo)

        assert res['exito'] is True
        assert res['cuentas'] == 2  # dos cuentas equivalentes distintas
        bloque = res['datos']['finv2_bd']
        rubros = bloque['rubros']
        # Ingresos Operacionales sumó -150
        assert rubros['Ingresos Operacionales']['total'] == -150
        assert rubros['Intereses']['total'] == -30
        assert 'cuentas procesadas' in res['mensaje']

    def test_b1_importer_cuenta_no_mapeada_a_otros(self):
        """Cuenta equivalente sin mapeo cae en 'Otros / No Clasificado'."""
        rows = [_row('99999', 'CUENTA RARA', -10, 'Cuenta Inexistente XYZ')]
        archivo = _excel_bytes(rows)
        res = ContableCompleteImporter().procesar_bd_completa(archivo)

        assert res['exito'] is True
        assert 'Otros / No Clasificado' in res['datos']['finv2_bd']['rubros']
        assert res['no_mapeadas'] == ['Cuenta Inexistente XYZ']

    def test_b1_importer_edge_sin_columna_o(self):
        """Edge case: archivo sin columna 'Cta equivalente' → advertencia."""
        headers = ['Auxiliar', 'Desc. auxiliar', 'Neto', 'Fecha']
        rows = [['41250501', 'X', -10, None]]
        archivo = _excel_bytes(rows, headers=headers)
        res = ContableCompleteImporter().procesar_bd_completa(archivo)

        assert res['exito'] is False
        assert res['advertencia'] is not None
        assert 'Cta equivalente' in res['advertencia']

    def test_b1_importer_edge_archivo_vacio(self):
        """Edge case: archivo sin filas de datos → advertencia."""
        archivo = _excel_bytes([])
        res = ContableCompleteImporter().procesar_bd_completa(archivo)

        assert res['exito'] is False
        assert res['advertencia'] is not None

    def test_b1_importer_edge_no_xlsx(self):
        """Edge case: extensión no .xlsx → error."""
        fake = io.BytesIO(b'not an excel')
        fake.name = 'datos.csv'
        fake.size = 12
        res = ContableCompleteImporter().procesar_bd_completa(fake)

        assert res['exito'] is False
        assert res['error'] is not None

    def test_b1_build_rubro_display_rows(self):
        """build_rubro_display_rows produce filas con pct correcto."""
        datos = {
            'finv2_bd': {
                'rubros': {
                    'A': {'total': 75.0, 'cuentas': []},
                    'B': {'total': 25.0, 'cuentas': []},
                },
                'total': 100.0,
            }
        }
        rows, total = build_rubro_display_rows(datos)
        assert total == 100.0
        # Ordenado desc por total → A primero
        assert rows[0]['rubro'] == 'A'
        assert rows[0]['pct'] == 75.0

    def test_b1_build_rubro_display_rows_legacy_sin_finv2(self):
        """datos legacy sin finv2_bd no rompe (devuelve vacío)."""
        rows, total = build_rubro_display_rows({'ingreso_proyectado': {}})
        assert rows == []
        assert total == 0


# --------------------------------------------------------------------------- #
# Vistas
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestB1Views:

    def test_b1_cargar_bd_form_200(self, client, admin_user):
        """GET de la página de carga responde 200 autenticado."""
        client.force_login(admin_user)
        resp = client.get(reverse('financiero:cargar_bd_contable'))
        assert resp.status_code == 200
        assert b'Cargar Base de Datos Contable' in resp.content

    def test_b1_cargar_bd_no_autenticado_redirect(self, client):
        """Sin login → redirect a login."""
        resp = client.get(reverse('financiero:cargar_bd_contable'))
        assert resp.status_code in (301, 302)

    def test_b1_presupuesto_planeado_render(self, client, admin_user):
        """POST de carga guarda en .datos y la pestaña planeado renderiza rubros."""
        client.force_login(admin_user)
        rows = [
            _row('41250501', 'LINEAS', -200, 'Ingresos Operacionales'),
            _row('42100501', 'INTERESES', -50, 'Intereses'),
        ]
        archivo = _excel_bytes(rows)
        url = reverse('financiero:cargar_bd_contable') + '?anio=2026'
        resp = client.post(url, {
            'action': 'cargar_bd', 'anio': 2026, 'archivo': archivo,
        }, follow=True)
        assert resp.status_code == 200

        obj = PresupuestoDetallado.objects.get(anio=2026, tipo='PLANEADO', contrato=None)
        assert 'finv2_bd' in obj.datos
        assert obj.datos['finv2_bd']['rubros']['Ingresos Operacionales']['total'] == -200
        # El render de la pestaña planeado muestra el rubro
        assert b'Ingresos Operacionales' in resp.content

    def test_b1_mapeo_crud(self, client, admin_user):
        """CRUD inline de MapeoCtaRubro: crear, editar, eliminar."""
        client.force_login(admin_user)
        url = reverse('financiero:editar_mapeo')

        # Crear
        resp = client.post(url, {
            'accion': 'crear',
            'cta_equivalente': 'Servicios Publicos',
            'rubro_presupuestal': 'Servicios',
            'activo': 'on',
        })
        assert resp.status_code == 200
        m = MapeoCtaRubro.objects.get(cta_equivalente='Servicios Publicos')
        assert m.rubro_presupuestal == 'Servicios'

        # Editar
        resp = client.post(url, {
            'accion': 'editar', 'pk': str(m.pk),
            'cta_equivalente': 'Servicios Publicos',
            'rubro_presupuestal': 'Servicios Generales',
            'activo': 'on',
        })
        assert resp.status_code == 200
        m.refresh_from_db()
        assert m.rubro_presupuestal == 'Servicios Generales'

        # Eliminar
        resp = client.post(url, {'accion': 'eliminar', 'pk': str(m.pk)})
        assert resp.status_code == 200
        assert not MapeoCtaRubro.objects.filter(pk=m.pk).exists()

    def test_b1_mapeo_crud_aplica_al_importer(self, client, admin_user):
        """Un MapeoCtaRubro activo reclasifica una cuenta antes No Clasificada."""
        MapeoCtaRubro.objects.create(
            cta_equivalente='Mi Cuenta Especial',
            rubro_presupuestal='Rubro Custom',
            activo=True,
        )
        rows = [_row('555', 'X', -77, 'Mi Cuenta Especial')]
        archivo = _excel_bytes(rows)
        res = ContableCompleteImporter().procesar_bd_completa(archivo)
        assert 'Rubro Custom' in res['datos']['finv2_bd']['rubros']

    def test_b1_dato_legacy_preservado(self, client, admin_user):
        """Cargar BD preserva otras llaves legacy de PresupuestoDetallado.datos."""
        client.force_login(admin_user)
        legacy = PresupuestoDetallado.objects.create(
            anio=2026, tipo='PLANEADO', contrato=None,
            datos={'ingreso_proyectado': {'enero': 999}},
        )
        rows = [_row('41250501', 'LINEAS', -200, 'Ingresos Operacionales')]
        archivo = _excel_bytes(rows)
        url = reverse('financiero:cargar_bd_contable') + '?anio=2026'
        client.post(url, {'action': 'cargar_bd', 'anio': 2026, 'archivo': archivo}, follow=True)

        legacy.refresh_from_db()
        # La llave legacy sigue presente y el nuevo bloque también
        assert legacy.datos['ingreso_proyectado']['enero'] == 999
        assert 'finv2_bd' in legacy.datos
