"""B3 (#123) — Tests de los 5 modelos financieros de Construcción.

ESCRITOS pero NO corridos en F3 (no hay Django local en este entorno) —
"tests_passing": "deferred_to_f4_docker". F4 los corre dentro del contenedor.

Cobertura:
- Los 5 modelos instancian (happy path).
- ``CostosConstruccion.costo_total`` se computa en save().
- ``CostosActividadConstruccion.costo_total`` (property) suma los 5 componentes.
- ``IndicadorANSConstruccion.estado`` clasifica cumplido/parcial/incumplido en save().
- ``FacturacionConstruccion.saldo_pendiente``.
- Edge cases: meta=0, valor en frontera del umbral parcial, cantidad cero.
- Dato legacy: un ``ProyectoConstruccion`` preexistente sigue funcionando.
"""
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.contratos.models import Contrato
from apps.construccion.models import ProyectoConstruccion, TorreConstruccion
from apps.construccion.models_b1_actividades_finales import ActividadFinalTorre
from apps.construccion.models_fin import (
    PresupuestoDetalladoConstruccion,
    CostosConstruccion,
    CostosActividadConstruccion,
    FacturacionConstruccion,
    IndicadorANSConstruccion,
)


def _crear_proyecto():
    """Crea un Contrato CONSTRUCCION + ProyectoConstruccion mínimo."""
    contrato = Contrato.objects.create(
        codigo=f"CONS-{timezone.now().timestamp()}",
        nombre='Contrato test construcción',
        unidad_negocio='CONSTRUCCION',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto LT 230kV test',
    )


class TestB3ModelosMigranOk(TestCase):
    """tests_e2e: b3_modelos_migran_ok — los 5 modelos instancian + cómputos."""

    def setUp(self):
        self.proyecto = _crear_proyecto()

    # --- 1. PresupuestoDetalladoConstruccion -----------------------------
    def test_presupuesto_detallado_instancia(self):
        p = PresupuestoDetalladoConstruccion.objects.create(
            proyecto=self.proyecto, anio=2026,
            tipo=PresupuestoDetalladoConstruccion.Tipo.PLANEADO,
            datos={'enero': {'material': 1000}},
        )
        self.assertEqual(p.tipo, 'PLANEADO')
        self.assertEqual(p.datos['enero']['material'], 1000)

    def test_presupuesto_default_datos_dict(self):
        p = PresupuestoDetalladoConstruccion.objects.create(
            proyecto=self.proyecto, anio=2027, tipo='REAL',
        )
        self.assertEqual(p.datos, {})

    def test_presupuesto_unique_together(self):
        from django.db import IntegrityError, transaction
        PresupuestoDetalladoConstruccion.objects.create(
            proyecto=self.proyecto, anio=2026, tipo='PLANEADO',
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PresupuestoDetalladoConstruccion.objects.create(
                    proyecto=self.proyecto, anio=2026, tipo='PLANEADO',
                )

    # --- 2. CostosConstruccion ------------------------------------------
    def test_costos_costo_total_auto(self):
        c = CostosConstruccion.objects.create(
            proyecto=self.proyecto, concepto='Cemento',
            tipo_recurso='MATERIAL',
            cantidad=Decimal('10'), costo_unitario=Decimal('2500.50'),
        )
        self.assertEqual(c.costo_total, Decimal('25005.00'))

    def test_costos_edge_cantidad_cero(self):
        """Edge: cantidad cero → costo_total cero (no None / no error)."""
        c = CostosConstruccion.objects.create(
            proyecto=self.proyecto, concepto='Sin consumo',
            cantidad=Decimal('0'), costo_unitario=Decimal('999'),
        )
        self.assertEqual(c.costo_total, Decimal('0.00'))

    def test_costos_actividad_nullable(self):
        """Edge: un costo puede no estar atado a una actividad."""
        c = CostosConstruccion.objects.create(
            proyecto=self.proyecto, concepto='Costo general',
            cantidad=Decimal('1'), costo_unitario=Decimal('100'),
        )
        self.assertIsNone(c.actividad)

    def test_costos_con_actividad_fk(self):
        torre = TorreConstruccion.objects.create(
            proyecto=self.proyecto, numero='T-001',
        )
        act = ActividadFinalTorre.objects.create(torre=torre)
        c = CostosConstruccion.objects.create(
            proyecto=self.proyecto, actividad=act, concepto='MO empalme',
            tipo_recurso='MANO_OBRA',
            cantidad=Decimal('3'), costo_unitario=Decimal('1000'),
        )
        self.assertEqual(c.actividad_id, act.id)
        self.assertEqual(c.costo_total, Decimal('3000.00'))

    # --- 3. CostosActividadConstruccion ---------------------------------
    def test_costos_actividad_total_property(self):
        torre = TorreConstruccion.objects.create(
            proyecto=self.proyecto, numero='T-002',
        )
        act = ActividadFinalTorre.objects.create(torre=torre)
        ca = CostosActividadConstruccion.objects.create(
            actividad=act,
            costo_materiales=Decimal('100'),
            costo_mano_obra=Decimal('200'),
            costo_equipos=Decimal('50'),
            costo_subcontratos=Decimal('300'),
            costo_otros=Decimal('25'),
        )
        self.assertEqual(ca.costo_total, Decimal('675'))

    def test_costos_actividad_defaults_cero(self):
        torre = TorreConstruccion.objects.create(
            proyecto=self.proyecto, numero='T-003',
        )
        act = ActividadFinalTorre.objects.create(torre=torre)
        ca = CostosActividadConstruccion.objects.create(actividad=act)
        self.assertEqual(ca.costo_total, Decimal('0'))

    # --- 4. FacturacionConstruccion -------------------------------------
    def test_facturacion_instancia_y_saldo(self):
        f = FacturacionConstruccion.objects.create(
            proyecto=self.proyecto, numero_factura='FC-001',
            monto_facturado=Decimal('1000000'),
            monto_pagado=Decimal('400000'),
            estado='EN_VALIDACION',
        )
        self.assertEqual(f.saldo_pendiente, Decimal('600000'))
        self.assertEqual(f.estado, 'EN_VALIDACION')

    def test_facturacion_default_pagado_cero(self):
        f = FacturacionConstruccion.objects.create(
            proyecto=self.proyecto, numero_factura='FC-002',
            monto_facturado=Decimal('500'),
        )
        self.assertEqual(f.monto_pagado, Decimal('0'))
        self.assertEqual(f.saldo_pendiente, Decimal('500'))
        self.assertEqual(f.estado, 'EMITIDA')

    # --- 5. IndicadorANSConstruccion ------------------------------------
    def test_ans_estado_cumplido(self):
        ind = IndicadorANSConstruccion.objects.create(
            proyecto=self.proyecto, nombre='% Cumplimiento Programación',
            meta_porcentaje=Decimal('95'), valor_actual=Decimal('98'),
            periodo_anio=2026, periodo_mes=6,
        )
        self.assertEqual(ind.estado, 'cumplido')

    def test_ans_estado_parcial(self):
        """Edge: valor en banda [meta*0.9, meta) → parcial."""
        ind = IndicadorANSConstruccion.objects.create(
            proyecto=self.proyecto, nombre='ANS parcial',
            meta_porcentaje=Decimal('100'), valor_actual=Decimal('92'),
            periodo_anio=2026, periodo_mes=6,
        )
        self.assertEqual(ind.estado, 'parcial')

    def test_ans_estado_incumplido(self):
        ind = IndicadorANSConstruccion.objects.create(
            proyecto=self.proyecto, nombre='ANS incumplido',
            meta_porcentaje=Decimal('100'), valor_actual=Decimal('50'),
            periodo_anio=2026, periodo_mes=6,
        )
        self.assertEqual(ind.estado, 'incumplido')

    def test_ans_edge_frontera_parcial(self):
        """Edge: valor exactamente en el umbral parcial (meta*0.9) → parcial."""
        ind = IndicadorANSConstruccion.objects.create(
            proyecto=self.proyecto, nombre='ANS frontera',
            meta_porcentaje=Decimal('100'), valor_actual=Decimal('90'),
            periodo_anio=2026, periodo_mes=6,
        )
        self.assertEqual(ind.estado, 'parcial')

    def test_ans_edge_meta_cero(self):
        """Edge: meta=0 → cualquier valor cuenta como cumplido (no división por cero)."""
        ind = IndicadorANSConstruccion.objects.create(
            proyecto=self.proyecto, nombre='ANS sin meta',
            meta_porcentaje=Decimal('0'), valor_actual=Decimal('0'),
            periodo_anio=2026, periodo_mes=6,
        )
        self.assertEqual(ind.estado, 'cumplido')

    def test_ans_estado_recalcula_en_update(self):
        ind = IndicadorANSConstruccion.objects.create(
            proyecto=self.proyecto, nombre='ANS recalc',
            meta_porcentaje=Decimal('90'), valor_actual=Decimal('50'),
            periodo_anio=2026, periodo_mes=6,
        )
        self.assertEqual(ind.estado, 'incumplido')
        ind.valor_actual = Decimal('95')
        ind.save()
        ind.refresh_from_db()
        self.assertEqual(ind.estado, 'cumplido')


class TestB3DatoLegacy(TestCase):
    """Dato legacy: un ProyectoConstruccion preexistente sigue OK tras 0023."""

    def test_proyecto_construccion_legacy_intacto(self):
        proyecto = _crear_proyecto()
        proyecto.refresh_from_db()
        # El proyecto legacy existe y conserva sus campos sin tocar.
        self.assertTrue(ProyectoConstruccion.objects.filter(id=proyecto.id).exists())
        self.assertEqual(proyecto.estado, 'PLANIFICACION')
        # Y los nuevos related_name están disponibles, vacíos por defecto.
        self.assertEqual(proyecto.costos.count(), 0)
        self.assertEqual(proyecto.facturacion.count(), 0)
        self.assertEqual(proyecto.indicadores_ans.count(), 0)
        self.assertEqual(proyecto.presupuestos_detallados.count(), 0)
