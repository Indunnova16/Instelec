"""Tests B2 — Indicadores de Construcción (#98).

Cubre:
- Test happy: IndicadorFinancieroConstruccion auto-calcula margen + desviacion en save()
- Test técnico: IndicadorTecnicoConstruccion auto-calcula 5 fórmulas
- Test ANS-style estado clasificado en IndicadorDesempenoLinea
- Test E2E b2_indicador_financiero_crear_y_calcular (HTTP POST view → DB)
- Edge cases: división por cero, valores negativos, datos legacy
"""
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.contratos.models import Contrato
from apps.construccion.models import ProyectoConstruccion
from apps.construccion.models_b2_indicadores import (
    IndicadorFinancieroConstruccion,
    IndicadorTecnicoConstruccion,
    IndicadorDesempenoLinea,
)
from apps.construccion import calculators


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def proyecto_b2(db):
    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo='TEST-B2-001',
        nombre='Proyecto B2 indicadores',
        cliente='Cliente Test',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre='Proyecto B2',
        estado='EJECUCION',
    )


@pytest.fixture
def linea_test(db):
    from apps.lineas.models import Linea
    return Linea.objects.create(
        nombre='Línea Test B2',
        codigo='LN-B2-001',
    )


# ===========================================================================
# CALCULATORS — funciones puras
# ===========================================================================

class TestCalculadoresFinancieros:
    def test_margen_operativo_happy(self):
        # IE=1000, CD=600, G=150 → margen = (1000 - 750) / 1000 * 100 = 25%
        result = calculators.calcular_margen_operativo(1000, 600, 150)
        assert result == pytest.approx(25.0)

    def test_margen_operativo_ingresos_cero(self):
        # División por cero → None
        assert calculators.calcular_margen_operativo(0, 100, 50) is None

    def test_margen_operativo_negativo(self):
        # Pérdidas: CD+G > IE → margen negativo
        result = calculators.calcular_margen_operativo(1000, 800, 400)
        assert result == pytest.approx(-20.0)

    def test_desviacion_presupuestal_happy(self):
        # CR=1200, CP=1000 → desv = (1200-1000)/1000 * 100 = 20%
        result = calculators.calcular_desviacion_presupuestal(1200, 1000)
        assert result == pytest.approx(20.0)

    def test_desviacion_presupuestado_cero(self):
        assert calculators.calcular_desviacion_presupuestal(1000, 0) is None


class TestCalculadoresTecnicos:
    def test_ejecucion_presupuestal(self):
        # PE=80, PP=90 → 80/90*100 = 88.88...
        assert calculators.calcular_ejecucion_presupuestal(80, 90) == pytest.approx(88.8888, abs=0.01)

    def test_avance_obra_meta_cero(self):
        assert calculators.calcular_avance_obra(100, 0) is None

    def test_cumplimiento_cronograma(self):
        # 19/20 = 95%
        assert calculators.calcular_cumplimiento_cronograma(19, 20) == pytest.approx(95.0)

    def test_productividad_horas_cero(self):
        assert calculators.calcular_productividad(100, 0) is None


class TestClasificarEstadoDesempeno:
    def test_en_meta_exacto(self):
        assert calculators.clasificar_estado_desempeno(100, 100) == 'EN_META'

    def test_en_meta_tolerancia(self):
        # 96/100 = 0.96 → diff 4% < 5% tolerancia
        assert calculators.clasificar_estado_desempeno(96, 100) == 'EN_META'

    def test_bajo_meta(self):
        # 80/100 = 0.8 → diff 20% → BAJO_META
        assert calculators.clasificar_estado_desempeno(80, 100) == 'BAJO_META'

    def test_sobre_meta(self):
        # 120/100 = 1.2 → diff 20% sobre meta
        assert calculators.clasificar_estado_desempeno(120, 100) == 'SOBRE_META'

    def test_sin_datos_meta_cero(self):
        assert calculators.clasificar_estado_desempeno(50, 0) == 'SIN_DATOS'


# ===========================================================================
# MODELOS — auto-cálculo en save()
# ===========================================================================

@pytest.mark.django_db
class TestIndicadorFinancieroConstruccion:
    def test_crear_y_calcular_happy(self, proyecto_b2):
        """Test happy: crear → margen y desviacion auto-calculados."""
        ind = IndicadorFinancieroConstruccion.objects.create(
            proyecto=proyecto_b2,
            ingresos_ejecutados=Decimal('1000000'),
            costos_directos=Decimal('600000'),
            gastos=Decimal('150000'),
            costo_real=Decimal('1100000'),
            costo_presupuestado=Decimal('1000000'),
        )
        # margen = (1M - 750k) / 1M * 100 = 25%
        assert ind.margen_operativo == pytest.approx(25.0)
        # desviacion = (1.1M - 1M) / 1M * 100 = 10%
        assert ind.desviacion_presupuestal == pytest.approx(10.0)

    def test_edge_ingresos_cero(self, proyecto_b2):
        """Edge: ingresos=0 → margen None (no crashea)."""
        ind = IndicadorFinancieroConstruccion.objects.create(
            proyecto=proyecto_b2,
            ingresos_ejecutados=Decimal('0'),
            costos_directos=Decimal('100'),
            gastos=Decimal('50'),
            costo_real=Decimal('100'),
            costo_presupuestado=Decimal('100'),
        )
        assert ind.margen_operativo is None
        # desviacion sigue calculándose: (100-100)/100*100 = 0%
        assert ind.desviacion_presupuestal == pytest.approx(0.0)

    def test_recalcular_tras_update(self, proyecto_b2):
        """Edge: editar y guardar → recalcula derivados."""
        ind = IndicadorFinancieroConstruccion.objects.create(
            proyecto=proyecto_b2,
            ingresos_ejecutados=Decimal('1000'),
            costos_directos=Decimal('500'),
            gastos=Decimal('100'),
            costo_real=Decimal('1000'),
            costo_presupuestado=Decimal('1000'),
        )
        assert ind.margen_operativo == pytest.approx(40.0)
        ind.costos_directos = Decimal('800')
        ind.save()
        # margen = (1000 - 900)/1000 = 10%
        assert ind.margen_operativo == pytest.approx(10.0)

    def test_estado_margen_property(self, proyecto_b2):
        ind = IndicadorFinancieroConstruccion.objects.create(
            proyecto=proyecto_b2,
            ingresos_ejecutados=Decimal('1000'),
            costos_directos=Decimal('800'),
            gastos=Decimal('50'),
        )
        # margen = 15% exacto → EN_META
        assert ind.estado_margen == 'EN_META'


@pytest.mark.django_db
class TestIndicadorTecnicoConstruccion:
    def test_crear_calcula_5_formulas(self, proyecto_b2):
        """Test técnico: las 5 fórmulas auto-llenan al save()."""
        ind = IndicadorTecnicoConstruccion.objects.create(
            proyecto=proyecto_b2,
            presupuesto_ejecutado_pct=80.0,
            presupuesto_planeado_pct=85.0,
            obra_ejecutada=Decimal('800'),
            obra_programada=Decimal('1000'),
            actividades_completadas=19,
            actividades_planificadas=20,
            cantidad_ejecutada=400.0,
            horas_hombre=100.0,
        )
        assert ind.ejecucion_presupuestal == pytest.approx(94.117, abs=0.01)
        assert ind.avance_obra == pytest.approx(80.0)
        assert ind.cumplimiento_cronograma == pytest.approx(95.0)
        assert ind.productividad == pytest.approx(400.0)
        assert ind.rendimiento_cuadrillas == pytest.approx(400.0)

    def test_edge_division_cero_no_crashea(self, proyecto_b2):
        ind = IndicadorTecnicoConstruccion.objects.create(
            proyecto=proyecto_b2,
            presupuesto_ejecutado_pct=80.0,
            presupuesto_planeado_pct=0.0,
            obra_ejecutada=Decimal('100'),
            obra_programada=Decimal('0'),
            actividades_completadas=0,
            actividades_planificadas=0,
            cantidad_ejecutada=10.0,
            horas_hombre=0.0,
        )
        assert ind.ejecucion_presupuestal is None
        assert ind.avance_obra is None
        assert ind.cumplimiento_cronograma is None
        assert ind.productividad is None


@pytest.mark.django_db
class TestIndicadorDesempenoLinea:
    def test_estado_clasificado_en_meta(self, proyecto_b2, linea_test):
        """ANS-style: estado se auto-clasifica al save()."""
        ind = IndicadorDesempenoLinea.objects.create(
            proyecto=proyecto_b2,
            linea=linea_test,
            tipo_trabajo='MONTAJE',
            unidad='torres/semana',
            meta=50.0,
            actual=48.0,  # 96% → diff 4% < 5% tolerancia → EN_META
        )
        assert ind.estado == 'EN_META'

    def test_estado_clasificado_bajo_meta(self, proyecto_b2, linea_test):
        ind = IndicadorDesempenoLinea.objects.create(
            proyecto=proyecto_b2,
            linea=linea_test,
            tipo_trabajo='TENDIDO',
            unidad='km/semana',
            meta=100.0,
            actual=80.0,  # 80% → BAJO_META
        )
        assert ind.estado == 'BAJO_META'

    def test_estado_clasificado_sobre_meta(self, proyecto_b2, linea_test):
        ind = IndicadorDesempenoLinea.objects.create(
            proyecto=proyecto_b2,
            linea=linea_test,
            tipo_trabajo='OBRA_CIVIL',
            unidad='und/día',
            meta=10.0,
            actual=15.0,  # 150% → SOBRE_META
        )
        assert ind.estado == 'SOBRE_META'

    def test_estado_sin_datos_meta_cero(self, proyecto_b2, linea_test):
        ind = IndicadorDesempenoLinea.objects.create(
            proyecto=proyecto_b2,
            linea=linea_test,
            tipo_trabajo='OBRA_CIVIL',
            unidad='und/día',
            meta=0.0,
            actual=10.0,
        )
        assert ind.estado == 'SIN_DATOS'

    def test_pct_cumplimiento_meta_cero(self, proyecto_b2, linea_test):
        ind = IndicadorDesempenoLinea.objects.create(
            proyecto=proyecto_b2,
            linea=linea_test,
            tipo_trabajo='OBRA_CIVIL',
            unidad='und/día',
            meta=0.0,
            actual=10.0,
        )
        assert ind.pct_cumplimiento is None


# ===========================================================================
# E2E — view crear funciona end-to-end
# ===========================================================================

@pytest.mark.django_db
class TestB2E2E:
    def test_b2_indicador_financiero_crear_y_calcular(
        self, client, admin_user, user_password, proyecto_b2
    ):
        """E2E: POST a crear → DB tiene record con margen calculado."""
        client.login(username=admin_user.email, password=user_password)
        url = reverse(
            'construccion:b2_indicador_financiero_crear',
            kwargs={'proyecto_id': proyecto_b2.id},
        )
        response = client.post(url, data={
            'fecha': '2026-05-25',
            'ingresos_ejecutados': '1000000',
            'costos_directos': '600000',
            'gastos': '150000',
            'costo_real': '1100000',
            'costo_presupuestado': '1000000',
            'observaciones': 'Test E2E',
        }, follow=False)
        # Redirect a lista al éxito
        assert response.status_code in (302, 303), response.content[:500]
        # Verifica que se creó y el margen está bien
        ind = IndicadorFinancieroConstruccion.objects.get(proyecto=proyecto_b2)
        assert ind.margen_operativo == pytest.approx(25.0)
        assert ind.desviacion_presupuestal == pytest.approx(10.0)
        assert ind.actualizado_por == admin_user

    def test_b2_recalcular_endpoint(
        self, client, admin_user, user_password, proyecto_b2
    ):
        """POST /indicadores/recalcular/ re-aplica fórmulas."""
        ind = IndicadorFinancieroConstruccion.objects.create(
            proyecto=proyecto_b2,
            ingresos_ejecutados=Decimal('1000'),
            costos_directos=Decimal('500'),
            gastos=Decimal('100'),
        )
        # Forzar inconsistencia: poner margen viejo manualmente
        IndicadorFinancieroConstruccion.objects.filter(pk=ind.pk).update(margen_operativo=999.0)
        ind.refresh_from_db()
        assert ind.margen_operativo == 999.0  # estado inconsistente

        client.login(username=admin_user.email, password=user_password)
        url = reverse('construccion:b2_indicadores_recalcular',
                     kwargs={'proyecto_id': proyecto_b2.id})
        response = client.post(url, HTTP_ACCEPT='application/json')
        assert response.status_code == 200
        data = response.json()
        assert data['ok'] is True
        assert data['financieros'] == 1
        ind.refresh_from_db()
        # Recalculado: margen = (1000-600)/1000 = 40%
        assert ind.margen_operativo == pytest.approx(40.0)


# ===========================================================================
# Test contra dato legacy: indicador previo con campos nuevos None
# ===========================================================================

@pytest.mark.django_db
class TestDatoLegacy:
    def test_indicador_financiero_legacy_no_crashea(self, proyecto_b2):
        """Modelos nuevos no afectan datos existentes (no hay legacy aún)."""
        # No hay datos prod aún (modelo nuevo). Verificación: el modelo
        # tolera valores 0 en todos los campos numéricos (sin crashear).
        ind = IndicadorFinancieroConstruccion.objects.create(
            proyecto=proyecto_b2,
            # Todos los inputs en su default (Decimal('0'))
        )
        assert ind.margen_operativo is None  # IE=0 → None
        assert ind.desviacion_presupuestal is None  # CP=0 → None

    def test_indicador_desempeno_sin_cuadrilla_ok(self, proyecto_b2, linea_test):
        """cuadrilla es nullable: legacy puede no tener cuadrilla asociada."""
        ind = IndicadorDesempenoLinea.objects.create(
            proyecto=proyecto_b2,
            linea=linea_test,
            tipo_trabajo='OBRA_CIVIL',
            unidad='und/día',
            meta=10.0,
            actual=10.0,
            # cuadrilla omitido
        )
        assert ind.cuadrilla is None
        assert ind.estado == 'EN_META'
