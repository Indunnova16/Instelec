"""Instelec#267 — A3: Historial de cargas (modelo + UI)

Issue #267, Fase 1.3 ("Historial de Cargas"): registrar CADA POST de carga de
presupuesto (éxito o error) y mostrar las últimas cargas del proyecto en la
pestaña "Cargar" con el formato Fecha/Usuario/Filas/Valor total/Estado/Período
del ejemplo literal del issue.

Cobertura:
- Integración (POST real): una carga exitosa (formato plano, A2) crea un
  ``HistorialCargaPresupuestoConstruccion`` con estado PROCESADA, filas y
  valor total correctos, usuario y período (mes/año) resueltos.
- Una carga que falla (Rubro no homologado → rechazo total, A2) crea un
  registro ERROR con el detalle del motivo en ``detalle_errores`` — NO se
  pierde silenciosamente.
- Un archivo con formato no reconocible por el detector también crea un
  registro ERROR (tercera vía de fallo, además de la validación dura del
  importer).
- Edge case: sin archivo (validación de formulario, no un intento de carga
  real) NO crea historial.
- UI: la pestaña "Cargar" muestra la tabla de historial con las últimas
  cargas ordenadas por fecha descendente (la más reciente primero) y con las
  6 columnas del issue.
"""
import io
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from openpyxl import Workbook

from apps.construccion.models import ProyectoConstruccion
from apps.construccion.models_fin import HistorialCargaPresupuestoConstruccion
from apps.contratos.models import Contrato
from apps.financiero.models_finv2_carga import HomologacionProjectsContable

User = get_user_model()


# ===========================================================================
# Helpers (espejo de tests_issue_267_a2_importador_plano.py)
# ===========================================================================
_ENCABEZADOS_PLANO = ['Tipo', 'Proyecto', 'Rubro', 'Clasificacion', 'Valor', 'mes', 'año', 'ciudad']


def _xlsx_plano_bytes(filas, encabezados=None):
    wb = Workbook()
    ws = wb.active
    ws.append(encabezados or _ENCABEZADOS_PLANO)
    for fila in filas:
        ws.append(fila)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _homologacion(rubro, clasificacion, codigo='5100', tipo='PRESUPUESTO'):
    return HomologacionProjectsContable.objects.create(
        tipo=tipo, grupo=clasificacion, concepto=rubro, rubro=rubro,
        codigo_contable=codigo, activo=True,
    )


def _crear_proyecto(nombre='Proyecto A3 test #267'):
    contrato = Contrato.objects.create(
        codigo=f"CONS-{uuid.uuid4().hex[:10]}",
        nombre='Contrato test construcción #267 A3',
        unidad_negocio='CONSTRUCCION',
    )
    return ProyectoConstruccion.objects.create(contrato=contrato, nombre=nombre)


def _crear_usuario_admin(prefijo='qa_267a3'):
    sufijo = uuid.uuid4().hex[:6]
    try:
        return User.objects.create_superuser(
            username=f'{prefijo}_{sufijo}',
            email=f'{prefijo}_{sufijo}@instelec.com', password='x',
        )
    except TypeError:
        user = User(is_superuser=True, is_staff=True)
        if hasattr(user, 'email'):
            user.email = f'{prefijo}_{sufijo}@instelec.com'
        user.set_password('x')
        user.save()
        return user


FILA_PERSONAL = ['Presupuesto', 'Transelca', 'Gastos de Personal', 'Fijo', 25625995.04, 9, 2026, 'Barranquilla']


class HistorialCargaPresupuestoTests(TestCase):
    """POST real contra PresupuestoPlaneadoConstruccionView + registro de historial."""

    def setUp(self):
        self.proyecto = _crear_proyecto()
        self.user = _crear_usuario_admin()
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse('construccion:fin_presupuesto_planeado',
                            kwargs={'proyecto_id': self.proyecto.pk})
        _homologacion('Gastos de Personal', 'Fijo', codigo='5105')

    def _post_plano(self, filas, anio=2026, nombre='plano.xlsx'):
        buf = _xlsx_plano_bytes(filas)
        archivo = SimpleUploadedFile(
            nombre, buf.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        return self.client.post(
            self.url, {'action': 'cargar_bd', 'anio': anio, 'archivo': archivo})

    def test_carga_exitosa_crea_registro_procesada(self):
        resp = self._post_plano([FILA_PERSONAL])
        self.assertEqual(resp.status_code, 302)

        historial = HistorialCargaPresupuestoConstruccion.objects.get(proyecto=self.proyecto)
        self.assertEqual(historial.estado, HistorialCargaPresupuestoConstruccion.Estado.PROCESADA)
        self.assertEqual(historial.filas_procesadas, 1)
        self.assertEqual(historial.valor_total, Decimal('25625995.04'))
        self.assertEqual(historial.usuario, self.user)
        self.assertEqual(historial.anio, 2026)
        self.assertEqual(historial.mes, 9, 'archivo de un solo mes → período resuelto (Fase 1.3 del issue)')
        self.assertEqual(historial.archivo_nombre, 'plano.xlsx')
        self.assertEqual(historial.detalle_errores, {})
        self.assertIn('Septiembre 2026 (09/2026)', historial.periodo_display)

    def test_carga_con_rubro_no_homologado_crea_registro_error_con_detalle(self):
        fila_no_homologada = ['Presupuesto', 'Transelca', 'Rubro Inexistente 267 A3', 'Fijo', 1000, 9, 2026, 'Bogota']
        resp = self._post_plano([fila_no_homologada])
        self.assertEqual(resp.status_code, 302)

        historial = HistorialCargaPresupuestoConstruccion.objects.get(proyecto=self.proyecto)
        self.assertEqual(historial.estado, HistorialCargaPresupuestoConstruccion.Estado.ERROR)
        self.assertEqual(historial.filas_procesadas, 0)
        self.assertEqual(historial.valor_total, 0)
        self.assertIn('Rubro Inexistente 267 A3', historial.detalle_errores.get('error', ''))
        self.assertIsNone(historial.detalle_errores.get('advertencia'))

    def test_archivo_formato_no_reconocido_crea_registro_error(self):
        wb = Workbook()
        ws = wb.active
        ws.append(['Columna A', 'Columna B'])
        ws.append(['dato', 1])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        archivo = SimpleUploadedFile(
            'no_reconocido.xlsx', buf.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        resp = self.client.post(
            self.url, {'action': 'cargar_bd', 'anio': 2026, 'archivo': archivo})
        self.assertEqual(resp.status_code, 302)

        historial = HistorialCargaPresupuestoConstruccion.objects.get(proyecto=self.proyecto)
        self.assertEqual(historial.estado, HistorialCargaPresupuestoConstruccion.Estado.ERROR)
        self.assertIn('Formato no reconocido', historial.detalle_errores.get('error', ''))

    def test_sin_archivo_no_crea_historial(self):
        """Edge case: validación de formulario (sin archivo) NO es un intento
        de carga real — no debe ensuciar el historial auditable."""
        resp = self.client.post(self.url, {'action': 'cargar_bd', 'anio': 2026})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(HistorialCargaPresupuestoConstruccion.objects.count(), 0)

    def test_historial_ordenado_por_fecha_descendente(self):
        """2 cargas consecutivas → la más reciente aparece primero en el
        contexto que consume la UI (formato_display / orden -fecha)."""
        self._post_plano([FILA_PERSONAL], nombre='primera.xlsx')
        fila_octubre = ['Presupuesto', 'Transelca', 'Gastos de Personal', 'Fijo', 500, 10, 2026, 'Barranquilla']
        self._post_plano([fila_octubre], nombre='segunda.xlsx')

        self.assertEqual(HistorialCargaPresupuestoConstruccion.objects.count(), 2)
        resp = self.client.get(self.url, {'anio': 2026, 'tab': 'cargar'})
        self.assertEqual(resp.status_code, 200)
        historial_ctx = list(resp.context['historial_cargas'])
        self.assertEqual(len(historial_ctx), 2)
        self.assertEqual(historial_ctx[0].archivo_nombre, 'segunda.xlsx',
                          'la carga más reciente (octubre) debe ir primero')
        self.assertEqual(historial_ctx[1].archivo_nombre, 'primera.xlsx')

        # UI real: ambos nombres de período aparecen en el HTML renderizado.
        contenido = resp.content.decode()
        self.assertIn('Octubre 2026', contenido)
        self.assertIn('Septiembre 2026', contenido)
        self.assertIn('Historial de Cargas', contenido)
        self.assertIn('✅ Procesada', contenido)
