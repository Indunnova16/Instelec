"""Instelec#267 — confirmación de la validación dura "Rubro debe existir en
Homologación (#247)" al hacer upload (issue Fase 1.2 / Fase 6.1).

Contexto (aclaración de alcance): el F2 de este sprint asignó esa validación
al sub-item **A2** (``PresupuestoPlanoConstruccionExcelImporter`` en
``apps/construccion/importers.py``, commit 779f79f) — no a A8 (A8 es
"Filtros Clasificación + Ciudad", Fase 2 del issue, cubierto en
``test_issue_267_a8_filtros.py``). A2 ya implementa el rechazo total del
archivo cuando un Rubro no existe en ``HomologacionProjectsContable`` activa
(tipo=PRESUPUESTO), nombrando fila+rubro, con tests dedicados en
``test_issue_267_a2_importador_plano.py::test_rubro_no_homologado_rechaza_archivo_completo_con_fila_y_rubro``.

Este archivo NO reimplementa esa validación (cero código nuevo en
``importers.py``) — la CONFIRMA con tests propios que cubren 4 huecos que la
suite de A2 no cubre explícitamente:

1. Homologación EXISTE pero ``activo=False`` → se rechaza igual que "no
   existe" (``_catalogo_homologaciones`` filtra ``activo=True`` — confirma
   que un registro desactivado no cuela).
2. Catálogo de Homologación COMPLETAMENTE VACÍO (0 filas, no solo sin la
   fila que falta) → rechaza TODA la carga. Confirma en código el riesgo
   operativo que A2 documentó (catálogo real de prod casi vacío): el gate
   es seguro (rechaza) y NUNCA deja pasar por catálogo vacío.
3. Rubro homologado pero bajo OTRA Clasificación (``grupo`` de
   ``HomologacionProjectsContable`` no matchea la ``Clasificacion`` de la
   fila) → rechazado. Confirma que el match es (tipo, grupo=Clasificacion,
   concepto=Rubro, rubro=Rubro), no solo el nombre del Rubro.
4. Con 2 filas de Rubros DISTINTOS no homologados → el mensaje de error
   nombra AMBOS rubros (no solo el primero).
5. Integración end-to-end (POST real): un archivo con un Rubro no
   homologado NO persiste ningún dato parcial en
   ``PresupuestoDetalladoConstruccion`` (rechazo total real, no solo a
   nivel del importer aislado).

Fixtures propias (Homologación creada explícitamente en cada test) — NUNCA
un catálogo real de prod, por instrucción del prompt de este subagente.
"""
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from apps.construccion.importers import PresupuestoPlanoConstruccionExcelImporter
from apps.construccion.models import ProyectoConstruccion
from apps.construccion.models_fin import PresupuestoDetalladoConstruccion
from apps.construccion.test_issue_267_a2_importador_plano import (
    FILA_PERSONAL,
    _FakeUpload,
    _homologacion,
    _xlsx_plano_bytes,
)
from apps.contratos.models import Contrato
from apps.financiero.models_finv2_carga import HomologacionProjectsContable

User = get_user_model()


class HomologacionDuraConfirmacionTests(TestCase):
    """Unit — PresupuestoPlanoConstruccionExcelImporter.procesar() directo."""

    def test_homologacion_inactiva_se_rechaza_igual_que_inexistente(self):
        """Rubro CON registro en Homologación, pero activo=False → rechazado
        (el catálogo solo indexa activo=True, un desactivado no debe colar)."""
        HomologacionProjectsContable.objects.create(
            tipo='PRESUPUESTO', grupo='Fijo', concepto='Gastos de Personal',
            rubro='Gastos de Personal', codigo_contable='5105', activo=False,
        )
        archivo = _FakeUpload(_xlsx_plano_bytes([FILA_PERSONAL]))
        res = PresupuestoPlanoConstruccionExcelImporter().procesar(archivo)

        self.assertFalse(res['exito'])
        self.assertIn('Gastos de Personal', res['error'])
        self.assertIn('Homologación', res['error'])
        self.assertIsNone(res['datos'])

    def test_catalogo_completamente_vacio_rechaza_toda_la_carga(self):
        """0 filas en Homologación (no solo "falta esta fila") → TODO el
        archivo se rechaza. Confirma en código el riesgo operativo que A2
        documentó (catálogo real de prod tiene pocas filas activas): el gate
        es seguro por default, nunca deja pasar nada sin catálogo."""
        self.assertEqual(HomologacionProjectsContable.objects.count(), 0)
        archivo = _FakeUpload(_xlsx_plano_bytes([FILA_PERSONAL]))
        res = PresupuestoPlanoConstruccionExcelImporter().procesar(archivo)

        self.assertFalse(res['exito'])
        self.assertIn('Gastos de Personal', res['error'])
        self.assertIsNone(res['datos'])

    def test_rubro_homologado_bajo_otra_clasificacion_no_matchea(self):
        """Homologación existe para 'Gastos de Personal' pero con
        grupo='Variable' — la fila del Excel trae Clasificacion='Fijo'
        (FILA_PERSONAL). El match es (tipo, grupo=Clasificacion,
        concepto=Rubro, rubro=Rubro): un Rubro homologado bajo la
        Clasificación INCORRECTA debe rechazarse, no colar por nombre."""
        _homologacion('Gastos de Personal', 'Variable', codigo='5199')
        archivo = _FakeUpload(_xlsx_plano_bytes([FILA_PERSONAL]))  # trae Clasificacion='Fijo'
        res = PresupuestoPlanoConstruccionExcelImporter().procesar(archivo)

        self.assertFalse(res['exito'])
        self.assertIn('Gastos de Personal', res['error'])
        self.assertIsNone(res['datos'])

    def test_dos_rubros_distintos_no_homologados_se_nombran_ambos(self):
        """El error no se detiene en el primer Rubro sin homologar — lista
        TODOS los que fallan, no solo el primero (fila+rubro cada uno)."""
        fila_a = ['Presupuesto', 'Transelca', 'Rubro Fantasma A', 'Fijo', 100, 1, 2026, 'Bogota']
        fila_b = ['Presupuesto', 'Transelca', 'Rubro Fantasma B', 'Variable', 200, 1, 2026, 'Bogota']
        archivo = _FakeUpload(_xlsx_plano_bytes([fila_a, fila_b]))
        res = PresupuestoPlanoConstruccionExcelImporter().procesar(archivo)

        self.assertFalse(res['exito'])
        self.assertIn('Rubro Fantasma A', res['error'])
        self.assertIn('Rubro Fantasma B', res['error'])
        self.assertIn('fila 2', res['error'])
        self.assertIn('fila 3', res['error'])


class HomologacionDuraIntegracionPostTests(TestCase):
    """Integración — POST real, rechazo NO deja dato parcial persistido."""

    def setUp(self):
        contrato = Contrato.objects.create(
            codigo='CONS-HOMOL-TEST', nombre='Contrato test #267 confirmación Homologación',
            unidad_negocio='CONSTRUCCION',
        )
        self.proyecto = ProyectoConstruccion.objects.create(contrato=contrato, nombre='Proyecto Homol Test')
        try:
            self.user = User.objects.create_superuser(
                username='qa_267_homol', email='qa_267_homol@instelec.com', password='x')
        except TypeError:
            self.user = User(is_superuser=True, is_staff=True)
            if hasattr(self.user, 'email'):
                self.user.email = 'qa_267_homol@instelec.com'
            self.user.set_password('x')
            self.user.save()
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse('construccion:fin_presupuesto_planeado',
                            kwargs={'proyecto_id': self.proyecto.pk})

    def test_post_con_rubro_no_homologado_no_persiste_nada(self):
        # Catálogo vacío a propósito: cualquier Rubro se rechaza.
        buf = _xlsx_plano_bytes([FILA_PERSONAL])
        archivo = SimpleUploadedFile(
            'presupuesto.xlsx', buf.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        resp = self.client.post(self.url, {'archivo': archivo, 'anio': 2026, 'action': 'cargar_bd'})
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(
            PresupuestoDetalladoConstruccion.objects.filter(
                proyecto=self.proyecto, anio=2026).exists(),
            'rechazo total: el POST no debe crear el presupuesto con datos parciales',
        )
