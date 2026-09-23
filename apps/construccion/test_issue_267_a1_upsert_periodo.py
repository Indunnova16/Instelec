"""Instelec#267 — A1: UPSERT por período (deep-merge rubro+mes).

Causa raíz: ``PresupuestoPlaneadoConstruccionView.post()`` hacía
``merged.update(res['datos'])`` a nivel RAÍZ del JSON — reemplazaba la llave
``finv2_bd`` COMPLETA en cada carga. Si Janet cargaba Septiembre y luego
Octubre, Octubre borraba los rubros/meses de Septiembre que no reaparecieran
en el archivo nuevo. El issue #267 (Fase 1.2) exige lo contrario:
"UPSERT: Reemplaza período, no duplica".

Cobertura:
- Unit (sin BD): los 3 helpers de merge (``_merge_seccion_mensual``,
  ``_merge_finv2_bd``, ``_merge_presupuesto_datos``) directo sobre dicts.
- Integración (con BD, vía POST real): 2 cargas de meses distintos coexisten;
  recarga del MISMO mes reemplaza solo ese mes sin duplicar cuentas.
- Dato legacy: un ``PresupuestoDetalladoConstruccion`` con datos PRE-existentes
  (simulando lo que ya vive en prod, cargado antes de este fix) sobrevive
  intacto a una carga nueva de un período distinto.
"""
import io
import uuid

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from openpyxl import Workbook

from apps.construccion.models import ProyectoConstruccion
from apps.construccion.models_fin import PresupuestoDetalladoConstruccion
from apps.construccion.views_fin import (
    _merge_finv2_bd,
    _merge_presupuesto_datos,
    _merge_seccion_mensual,
)
from apps.contratos.models import Contrato
from apps.financiero.models_finv2_mapeo import RUBRO_NO_CLASIFICADO

User = get_user_model()


# ===========================================================================
# Unit — helpers de merge (sin BD)
# ===========================================================================
class MergeSeccionMensualTests(SimpleTestCase):
    """Sección legacy {concepto: {mes: valor}} (ingreso/variables/fijos)."""

    def test_meses_distintos_coexisten(self):
        existente = {'Arriendo': {'enero': 100.0}}
        nuevo = {'Arriendo': {'febrero': 200.0}}
        resultado = _merge_seccion_mensual(existente, nuevo)
        self.assertEqual(resultado, {'Arriendo': {'enero': 100.0, 'febrero': 200.0}})

    def test_mismo_mes_reemplaza_no_duplica(self):
        existente = {'Arriendo': {'enero': 100.0}}
        nuevo = {'Arriendo': {'enero': 999.0}}
        resultado = _merge_seccion_mensual(existente, nuevo)
        self.assertEqual(resultado, {'Arriendo': {'enero': 999.0}})

    def test_concepto_nuevo_no_pisa_existentes(self):
        existente = {'Arriendo': {'enero': 100.0}}
        nuevo = {'Nomina': {'enero': 50.0}}
        resultado = _merge_seccion_mensual(existente, nuevo)
        self.assertEqual(resultado, {
            'Arriendo': {'enero': 100.0},
            'Nomina': {'enero': 50.0},
        })


class MergeFinv2BdTests(SimpleTestCase):
    """Bloque ``finv2_bd`` (BD contable) — merge por (rubro, cuenta, mes)."""

    def _bloque(self, rubro, cta, meses):
        total = round(sum(meses.values()), 2)
        return {
            'rubros': {
                rubro: {
                    'total': total,
                    'meses': dict(meses),
                    'cuentas': [{
                        'cta_equivalente': cta,
                        'descripcion': 'mov',
                        'total': total,
                        'meses': dict(meses),
                    }],
                }
            },
            'total': total,
            'cuentas_count': 1,
            'cuentas_no_mapeadas': [] if rubro != RUBRO_NO_CLASIFICADO else [cta],
            'filas_sin_mes': 0,
        }

    def test_meses_distintos_coexisten(self):
        existente = self._bloque('Gastos de Personal', 'CTA-1', {'septiembre': 100.0})
        nuevo = self._bloque('Gastos de Personal', 'CTA-1', {'octubre': 50.0})
        resultado = _merge_finv2_bd(existente, nuevo)

        rubro = resultado['rubros']['Gastos de Personal']
        self.assertEqual(rubro['meses'], {'septiembre': 100.0, 'octubre': 50.0})
        self.assertEqual(rubro['total'], 150.0)
        self.assertEqual(len(rubro['cuentas']), 1, 'NO debe duplicar la cuenta')
        self.assertEqual(
            rubro['cuentas'][0]['meses'],
            {'septiembre': 100.0, 'octubre': 50.0},
        )
        self.assertEqual(resultado['total'], 150.0)
        self.assertEqual(resultado['cuentas_count'], 1)

    def test_recarga_mismo_mes_reemplaza_no_duplica(self):
        existente = self._bloque('Gastos de Personal', 'CTA-1', {'septiembre': 100.0})
        nuevo = self._bloque('Gastos de Personal', 'CTA-1', {'septiembre': 999.0})
        resultado = _merge_finv2_bd(existente, nuevo)

        rubro = resultado['rubros']['Gastos de Personal']
        self.assertEqual(rubro['meses'], {'septiembre': 999.0}, 'reemplaza, no suma')
        self.assertEqual(rubro['total'], 999.0)
        self.assertEqual(len(rubro['cuentas']), 1, 'NO debe duplicar la cuenta')

    def test_rubro_nuevo_no_borra_rubros_previos(self):
        existente = self._bloque('Gastos de Personal', 'CTA-1', {'septiembre': 100.0})
        nuevo = self._bloque('Servicios Publicos', 'CTA-2', {'septiembre': 40.0})
        resultado = _merge_finv2_bd(existente, nuevo)

        self.assertIn('Gastos de Personal', resultado['rubros'])
        self.assertIn('Servicios Publicos', resultado['rubros'])
        self.assertEqual(resultado['total'], 140.0)

    def test_sin_existente_devuelve_nuevo_tal_cual(self):
        nuevo = self._bloque('Gastos de Personal', 'CTA-1', {'septiembre': 100.0})
        resultado = _merge_finv2_bd(None, nuevo)
        self.assertEqual(resultado, nuevo)

    def test_sin_nuevo_preserva_existente(self):
        existente = self._bloque('Gastos de Personal', 'CTA-1', {'septiembre': 100.0})
        resultado = _merge_finv2_bd(existente, None)
        self.assertEqual(resultado, existente)


class MergePresupuestoDatosTests(SimpleTestCase):
    """Orquestador raíz — despacha por llave, NUNCA reemplaza a nivel raíz."""

    def test_finv2_bd_se_mergea_no_se_reemplaza(self):
        existente = {'finv2_bd': {
            'rubros': {'Personal': {'total': 100.0, 'meses': {'septiembre': 100.0},
                                     'cuentas': [{'cta_equivalente': 'C1', 'descripcion': '',
                                                  'total': 100.0, 'meses': {'septiembre': 100.0}}]}},
            'total': 100.0, 'cuentas_count': 1, 'cuentas_no_mapeadas': [], 'filas_sin_mes': 0,
        }}
        nuevo = {'finv2_bd': {
            'rubros': {'Personal': {'total': 50.0, 'meses': {'octubre': 50.0},
                                     'cuentas': [{'cta_equivalente': 'C1', 'descripcion': '',
                                                  'total': 50.0, 'meses': {'octubre': 50.0}}]}},
            'total': 50.0, 'cuentas_count': 1, 'cuentas_no_mapeadas': [], 'filas_sin_mes': 0,
        }}
        resultado = _merge_presupuesto_datos(existente, nuevo)
        meses = resultado['finv2_bd']['rubros']['Personal']['meses']
        self.assertEqual(meses, {'septiembre': 100.0, 'octubre': 50.0})

    def test_dato_legacy_preservado_si_archivo_no_lo_toca(self):
        """Simula ``datos`` real de prod cargado ANTES de este fix: una llave
        arbitraria del JSONField que el importador nuevo no conoce/produce
        debe sobrevivir intacta (no debe desaparecer del merge raíz)."""
        existente = {'finv2_bd': {'rubros': {}, 'total': 0.0, 'cuentas_count': 0,
                                   'cuentas_no_mapeadas': [], 'filas_sin_mes': 0},
                     'nota_legacy': 'dato preexistente sin relacion con el importer'}
        nuevo = {'ingreso': {'Ventas': {'enero': 10.0}}}
        resultado = _merge_presupuesto_datos(existente, nuevo)
        self.assertEqual(resultado['nota_legacy'],
                          'dato preexistente sin relacion con el importer')
        self.assertEqual(resultado['ingreso'], {'Ventas': {'enero': 10.0}})


# ===========================================================================
# Integración — POST real contra la vista (con BD)
# ===========================================================================
def _crear_proyecto(nombre='Proyecto UPSERT test #267'):
    contrato = Contrato.objects.create(
        codigo=f"CONS-{uuid.uuid4().hex[:10]}",
        nombre='Contrato test construcción #267',
        unidad_negocio='CONSTRUCCION',
    )
    return ProyectoConstruccion.objects.create(contrato=contrato, nombre=nombre)


def _crear_usuario_admin():
    kwargs = {'is_superuser': True, 'is_staff': True}
    try:
        return User.objects.create_superuser(
            username=f'qa_267_{uuid.uuid4().hex[:6]}',
            email=f'qa_267_{uuid.uuid4().hex[:6]}@instelec.com', password='x',
        )
    except TypeError:
        user = User(**kwargs)
        if hasattr(user, 'email'):
            user.email = f'qa_267_{uuid.uuid4().hex[:6]}@instelec.com'
        user.set_password('x')
        user.save()
        return user


def _xlsx_contable_bytes(cta, neto, fecha):
    """BD contable mínima: 1 movimiento de ``cta`` por ``neto`` en ``fecha``."""
    wb = Workbook()
    ws = wb.active
    ws.title = 'BD'
    ws.append(['Desc auxiliar', 'Neto', 'Cta equivalente', 'Fecha'])
    ws.append(['mov', neto, cta, fecha])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


class UpsertPeriodoPostTests(TestCase):
    """B4 POST real: 2 cargas consecutivas de meses distintos + recarga."""

    def setUp(self):
        self.proyecto = _crear_proyecto()
        self.user = _crear_usuario_admin()
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse('construccion:fin_presupuesto_planeado',
                            kwargs={'proyecto_id': self.proyecto.pk})

    def _post_archivo(self, cta, neto, fecha, anio=2026):
        import datetime
        archivo = SimpleUploadedFile(
            'BASE DE DATOS.xlsx',
            _xlsx_contable_bytes(cta, neto, datetime.date(*fecha)),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        return self.client.post(
            self.url, {'action': 'cargar_bd', 'anio': anio, 'archivo': archivo})

    def _rubro_de(self, obj, cta):
        """Encuentra el rubro donde cayó ``cta`` (mapeado o NO_CLASIFICADO)."""
        obj.refresh_from_db()
        rubros = (obj.datos or {}).get('finv2_bd', {}).get('rubros', {})
        for nombre, info in rubros.items():
            for cuenta in info.get('cuentas', []):
                if cuenta.get('cta_equivalente') == cta:
                    return nombre, info
        return None, None

    def test_dos_cargas_meses_distintos_coexisten(self):
        """tests_requeridos #1: Sept + Oct → ambos meses viven en finv2_bd."""
        resp1 = self._post_archivo('MOV-267-A', 100, (2026, 9, 15))
        self.assertEqual(resp1.status_code, 302)
        resp2 = self._post_archivo('MOV-267-A', 50, (2026, 10, 15))
        self.assertEqual(resp2.status_code, 302)

        obj = PresupuestoDetalladoConstruccion.objects.get(
            proyecto=self.proyecto, anio=2026,
            tipo=PresupuestoDetalladoConstruccion.Tipo.PLANEADO,
        )
        _, info = self._rubro_de(obj, 'MOV-267-A')
        self.assertIsNotNone(info, 'la cuenta debe existir en algún rubro tras 2 cargas')
        self.assertEqual(info['meses'].get('septiembre'), 100.0,
                          'Septiembre NO debe desaparecer al cargar Octubre (bug #267)')
        self.assertEqual(info['meses'].get('octubre'), 50.0)
        cuentas = [c for c in info['cuentas'] if c['cta_equivalente'] == 'MOV-267-A']
        self.assertEqual(len(cuentas), 1, 'no debe duplicar la cuenta entre cargas')

    def test_recarga_mismo_mes_reemplaza_no_duplica(self):
        """tests_requeridos #2: recargar Septiembre reemplaza solo Septiembre."""
        self._post_archivo('MOV-267-B', 100, (2026, 9, 10))
        self._post_archivo('MOV-267-B', 777, (2026, 9, 20))  # mismo mes, otro valor

        obj = PresupuestoDetalladoConstruccion.objects.get(
            proyecto=self.proyecto, anio=2026,
            tipo=PresupuestoDetalladoConstruccion.Tipo.PLANEADO,
        )
        _, info = self._rubro_de(obj, 'MOV-267-B')
        self.assertEqual(info['meses'], {'septiembre': 777.0},
                          'la recarga del mismo mes reemplaza, no acumula ni duplica')
        cuentas = [c for c in info['cuentas'] if c['cta_equivalente'] == 'MOV-267-B']
        self.assertEqual(len(cuentas), 1)

    def test_dato_legacy_preexistente_sobrevive_a_carga_nueva(self):
        """Dato ya persistido en prod (formato pre-fix, ≥1 registro legacy)
        no debe borrarse al procesar una carga de un período distinto."""
        legacy_datos = {
            'finv2_bd': {
                'rubros': {
                    'Gastos de Personal': {
                        'total': 500.0,
                        'meses': {'julio': 500.0},
                        'cuentas': [{
                            'cta_equivalente': 'LEGACY-267',
                            'descripcion': 'movimiento legacy pre-fix',
                            'total': 500.0,
                            'meses': {'julio': 500.0},
                        }],
                    }
                },
                'total': 500.0,
                'cuentas_count': 1,
                'cuentas_no_mapeadas': [],
                'filas_sin_mes': 0,
            }
        }
        obj = PresupuestoDetalladoConstruccion.objects.create(
            proyecto=self.proyecto, anio=2026,
            tipo=PresupuestoDetalladoConstruccion.Tipo.PLANEADO,
            datos=legacy_datos,
        )

        resp = self._post_archivo('MOV-267-C', 33, (2026, 11, 5))
        self.assertEqual(resp.status_code, 302)

        obj.refresh_from_db()
        rubro_legacy = obj.datos['finv2_bd']['rubros'].get('Gastos de Personal')
        self.assertIsNotNone(rubro_legacy, 'el rubro legacy no debe desaparecer')
        self.assertEqual(rubro_legacy['meses'].get('julio'), 500.0,
                          'el mes legacy (julio) debe sobrevivir intacto')
        cuentas_legacy = [c for c in rubro_legacy['cuentas']
                           if c['cta_equivalente'] == 'LEGACY-267']
        self.assertEqual(len(cuentas_legacy), 1)
