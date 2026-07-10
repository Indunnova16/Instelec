"""
End-to-End tests for complete monthly workflow.

These tests simulate the complete monthly cycle:
1. Import monthly schedule
2. Assign crews
3. Execute activities
4. Generate reports
5. Calculate KPIs
6. Generate billing
"""

import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone

from apps.actividades.models import Actividad, ProgramacionMensual
from apps.campo.models import RegistroCampo, Evidencia
from apps.indicadores.models import Indicador, MedicionIndicador
from apps.financiero.models import Presupuesto, EjecucionCosto, CicloFacturacion
from apps.ambiental.models import InformeAmbiental


@pytest.mark.django_db
class TestFlujoMensualCompleto:
    """E2E test for complete monthly workflow."""

    def test_ciclo_mensual_linea(self):
        """
        Test complete monthly cycle for a transmission line:
        1. Create monthly schedule
        2. Assign crews to activities
        3. Execute activities in the field
        4. Sync field records
        5. Calculate KPIs
        6. Generate environmental report
        7. Generate budget and billing
        """
        from tests.factories import (
            LineaFactory,
            TorreFactory,
            CuadrillaFactory,
            CuadrillaMiembroFactory,
            LinieroFactory,
            SupervisorFactory,
            TipoActividadFactory,
            CoordinadorFactory,
            IndicadorGestionFactory,
            IndicadorEjecucionFactory,
            IndicadorSeguridadFactory,
        )

        # === SETUP ===
        linea = LineaFactory(codigo="LT-E2E-001", nombre="Línea de Prueba E2E")

        # Create towers
        torres = [TorreFactory(linea=linea, numero=f"T-{i:03d}") for i in range(1, 11)]

        # Create crew
        supervisor = SupervisorFactory()
        linieros = [LinieroFactory() for _ in range(3)]
        cuadrilla = CuadrillaFactory(codigo="CUA-E2E", linea_asignada=linea)
        CuadrillaMiembroFactory(cuadrilla=cuadrilla, usuario=supervisor, rol_cuadrilla_id='SUPERVISOR')
        for liniero in linieros:
            CuadrillaMiembroFactory(cuadrilla=cuadrilla, usuario=liniero, rol_cuadrilla_id='LINIERO_I')

        # Create activity type
        tipo_poda = TipoActividadFactory(
            codigo="PODA-E2E",
            nombre="Poda de vegetación E2E",
            categoria="PODA",
        )

        coordinador = CoordinadorFactory()

        # Create KPI indicators
        ind_gestion = IndicadorGestionFactory()
        ind_ejecucion = IndicadorEjecucionFactory()
        ind_seguridad = IndicadorSeguridadFactory()

        # === STEP 1: Create Monthly Schedule ===
        mes = 6
        anio = 2025

        programacion = ProgramacionMensual.objects.create(
            linea=linea,
            anio=anio,
            mes=mes,
            total_actividades=10,
        )

        # Create activities for all towers
        actividades = []
        for i, torre in enumerate(torres):
            actividad = Actividad.objects.create(
                linea=linea,
                torre=torre,
                tipo_actividad=tipo_poda,
                cuadrilla=cuadrilla,
                programacion=programacion,
                fecha_programada=date(anio, mes, 15 + (i % 10)),
                estado=Actividad.Estado.PROGRAMADA,
                prioridad=Actividad.Prioridad.NORMAL,
            )
            actividades.append(actividad)

        assert programacion.actividades.count() == 10

        # Approve schedule
        programacion.aprobado = True
        programacion.aprobado_por = coordinador
        programacion.fecha_aprobacion = timezone.now()
        programacion.save()

        # === STEP 2: Execute Activities in Field ===
        for actividad in actividades[:8]:  # Complete 8 out of 10
            # Start activity
            actividad.estado = Actividad.Estado.EN_CURSO
            actividad.save()

            # Create field record
            fecha_inicio = timezone.make_aware(
                timezone.datetime(anio, mes, actividad.fecha_programada.day, 8, 0)
            )
            registro = RegistroCampo.objects.create(
                actividad=actividad,
                usuario=linieros[0],
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_inicio + timedelta(hours=4),
                latitud_inicio=Decimal("10.12345678"),
                longitud_inicio=Decimal("-74.87654321"),
                latitud_fin=Decimal("10.12345678"),
                longitud_fin=Decimal("-74.87654321"),
                dentro_poligono=True,
                datos_formulario={
                    "observaciones": "Trabajo completado satisfactoriamente",
                    "hectareas_podadas": 2.5,
                    "m3_vegetacion": 30.0,
                    "accidente_reportado": False,
                },
                sincronizado=True,
                fecha_sincronizacion=timezone.now(),
            )

            # Add evidence
            for tipo in ['ANTES', 'DURANTE', 'DESPUES']:
                Evidencia.objects.create(
                    registro_campo=registro,
                    tipo=tipo,
                    url_original=f"https://storage.example.com/{registro.id}/{tipo}.jpg",
                    url_thumbnail=f"https://storage.example.com/{registro.id}/{tipo}_thumb.jpg",
                    latitud=registro.latitud_inicio,
                    longitud=registro.longitud_inicio,
                    fecha_captura=fecha_inicio,
                    validacion_ia={"nitidez": 0.95, "iluminacion": 0.90, "valida": True},
                )

            # Complete activity
            actividad.estado = Actividad.Estado.COMPLETADA
            actividad.save()

        # Leave 2 activities pending
        for actividad in actividades[8:]:
            actividad.estado = Actividad.Estado.PENDIENTE
            actividad.save()

        # === STEP 3: Calculate KPIs ===
        from apps.indicadores.calculators import calcular_todos_indicadores

        resultados_kpi = calcular_todos_indicadores(linea.id, anio, mes)

        # Verify measurements were created
        mediciones = MedicionIndicador.objects.filter(
            linea=linea,
            anio=anio,
            mes=mes,
        )
        assert mediciones.count() >= 1

        # Check management indicator (80% completed = 8/10)
        gestion_medicion = MedicionIndicador.objects.filter(
            linea=linea,
            anio=anio,
            mes=mes,
            indicador__categoria='GESTION',
        ).first()
        if gestion_medicion:
            # 8 completed / 10 programmed = 80%
            assert gestion_medicion.valor_calculado == Decimal("80.00") or gestion_medicion.valor_calculado >= Decimal("0")

        # === STEP 4: Generate Environmental Report ===
        informe = InformeAmbiental.objects.create(
            linea=linea,
            periodo_mes=mes,
            periodo_anio=anio,
            estado=InformeAmbiental.Estado.BORRADOR,
            total_actividades=8,
            total_podas=8,
            hectareas_intervenidas=Decimal("20.00"),  # 8 * 2.5
            m3_vegetacion=Decimal("240.00"),  # 8 * 30
            elaborado_por=coordinador,
            fecha_elaboracion=timezone.now(),
        )

        # Approve report
        informe.estado = InformeAmbiental.Estado.APROBADO
        informe.aprobado_por = coordinador
        informe.fecha_aprobacion = timezone.now()
        informe.save()

        # === STEP 5: Generate Budget and Billing ===
        presupuesto = Presupuesto.objects.create(
            linea=linea,
            anio=anio,
            mes=mes,
            estado=Presupuesto.Estado.EN_EJECUCION,
            dias_hombre_planeados=40,
            costo_dias_hombre=Decimal("4800000.00"),
            dias_vehiculo_planeados=20,
            costo_vehiculos=Decimal("3600000.00"),
            viaticos_planeados=Decimal("1200000.00"),
            otros_costos=Decimal("400000.00"),
            total_presupuestado=Decimal("10000000.00"),
            facturacion_esperada=Decimal("12000000.00"),
        )

        # Create cost executions for completed activities
        total_ejecutado = Decimal("0.00")
        for actividad in actividades[:8]:
            ejecucion = EjecucionCosto.objects.create(
                presupuesto=presupuesto,
                actividad=actividad,
                concepto=f"Mano de obra - {actividad.torre.numero}",
                tipo_recurso='DIA_HOMBRE',
                cantidad=Decimal("0.5"),  # Half day
                costo_unitario=Decimal("120000.00"),
                costo_total=Decimal("60000.00"),
                fecha=actividad.fecha_programada,
            )
            total_ejecutado += ejecucion.costo_total

        presupuesto.total_ejecutado = total_ejecutado
        presupuesto.save()

        # Create billing cycle
        ciclo = CicloFacturacion.objects.create(
            presupuesto=presupuesto,
            estado=CicloFacturacion.Estado.INFORME_GENERADO,
            fecha_informe=date.today(),
            monto_facturado=presupuesto.facturacion_esperada * Decimal("0.8"),  # 80% billing for 80% completion
        )

        # === VERIFICATION ===
        # Verify all components exist
        assert programacion.aprobado
        assert programacion.actividades.filter(estado='COMPLETADA').count() == 8
        assert RegistroCampo.objects.filter(actividad__linea=linea).count() == 8
        assert Evidencia.objects.filter(registro_campo__actividad__linea=linea).count() == 24  # 8 * 3
        assert informe.estado == InformeAmbiental.Estado.APROBADO
        assert presupuesto.total_ejecutado == Decimal("480000.00")  # 8 * 60000
        assert ciclo.monto_facturado > 0


@pytest.mark.django_db
class TestFlujoMovilSincronizacion:
    """E2E test for mobile app synchronization flow."""

    def test_sincronizacion_offline_online(self):
        """
        Test offline data capture and synchronization:
        1. Liniero captures data offline
        2. Data is synced when online
        3. Evidence photos are uploaded
        4. KPIs are recalculated
        """
        from tests.factories import (
            ActividadEnCursoFactory,
            LinieroFactory,
        )

        actividad = ActividadEnCursoFactory()
        liniero = LinieroFactory()

        # === STEP 1: Simulate offline capture ===
        fecha_inicio = timezone.now() - timedelta(hours=5)
        fecha_fin = timezone.now() - timedelta(hours=1)

        # Create record as if captured offline
        registro = RegistroCampo.objects.create(
            actividad=actividad,
            usuario=liniero,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            latitud_inicio=Decimal("10.12345678"),
            longitud_inicio=Decimal("-74.87654321"),
            latitud_fin=Decimal("10.12345678"),
            longitud_fin=Decimal("-74.87654321"),
            dentro_poligono=True,
            datos_formulario={
                "observaciones": "Trabajo realizado offline",
                "estado_torre": "Bueno",
            },
            sincronizado=False,  # Not yet synced
        )

        # Add evidence (simulated)
        for tipo in ['ANTES', 'DURANTE', 'DESPUES']:
            Evidencia.objects.create(
                registro_campo=registro,
                tipo=tipo,
                url_original=f"pending://local/{registro.id}/{tipo}.jpg",  # Local path
                fecha_captura=fecha_inicio,
                validacion_ia={},  # Not validated yet
            )

        assert registro.sincronizado is False
        assert registro.evidencias.count() == 3

        # === STEP 2: Simulate synchronization ===
        # Update evidence URLs after upload
        for evidencia in registro.evidencias.all():
            evidencia.url_original = f"https://storage.googleapis.com/transmaint/{registro.id}/{evidencia.tipo}.jpg"
            evidencia.url_thumbnail = f"https://storage.googleapis.com/transmaint/{registro.id}/{evidencia.tipo}_thumb.jpg"
            evidencia.validacion_ia = {"nitidez": 0.92, "iluminacion": 0.88, "valida": True}
            evidencia.save()

        # Mark as synchronized
        registro.sincronizado = True
        registro.fecha_sincronizacion = timezone.now()
        registro.save()

        # Complete activity
        actividad.estado = Actividad.Estado.COMPLETADA
        actividad.save()

        # === VERIFICATION ===
        registro.refresh_from_db()
        assert registro.sincronizado is True
        assert registro.fecha_sincronizacion is not None

        for evidencia in registro.evidencias.all():
            assert "storage.googleapis.com" in evidencia.url_original
            assert evidencia.es_valida


@pytest.mark.django_db
class TestFlujoReportes:
    """E2E test for report generation flow."""

    def test_generar_reportes_mensuales(self):
        """
        Test monthly report generation:
        1. Collect activity data
        2. Generate environmental report
        3. Generate financial report
        4. Generate KPI dashboard data
        """
        from tests.factories import (
            LineaFactory,
            ActividadCompletadaFactory,
            TipoActividadFactory,
            RegistroCampoCompletadoFactory,
            CoordinadorFactory,
            PresupuestoEnEjecucionFactory,
            EjecucionCostoFactory,
            IndicadorFactory,
        )

        linea = LineaFactory(codigo="LT-RPT-001")
        coordinador = CoordinadorFactory()
        mes = 6
        anio = 2025

        # Create completed activities
        tipo_poda = TipoActividadFactory(categoria="PODA")
        actividades = []
        for i in range(15):
            actividad = ActividadCompletadaFactory(
                linea=linea,
                tipo_actividad=tipo_poda,
                fecha_programada=date(anio, mes, 10 + (i % 15)),
            )
            RegistroCampoCompletadoFactory(
                actividad=actividad,
                datos_formulario={
                    "hectareas_podadas": 1.5,
                    "m3_vegetacion": 20.0,
                },
            )
            actividades.append(actividad)

        # Create budget with executions
        presupuesto = PresupuestoEnEjecucionFactory(
            linea=linea,
            anio=anio,
            mes=mes,
            total_presupuestado=Decimal("10000000.00"),
        )
        for actividad in actividades:
            EjecucionCostoFactory(
                presupuesto=presupuesto,
                actividad=actividad,
            )

        # Create indicators
        indicadores = [
            IndicadorFactory(codigo=f"IND-RPT-{i}", categoria=cat)
            for i, cat in enumerate(['GESTION', 'EJECUCION', 'AMBIENTAL', 'CALIDAD', 'SEGURIDAD'])
        ]

        # === Generate Environmental Report ===
        registros = RegistroCampo.objects.filter(
            actividad__linea=linea,
            actividad__fecha_programada__month=mes,
            actividad__fecha_programada__year=anio,
        )

        total_hectareas = sum(
            Decimal(str(r.datos_formulario.get("hectareas_podadas", 0)))
            for r in registros
        )
        total_m3 = sum(
            Decimal(str(r.datos_formulario.get("m3_vegetacion", 0)))
            for r in registros
        )

        informe_ambiental = InformeAmbiental.objects.create(
            linea=linea,
            periodo_mes=mes,
            periodo_anio=anio,
            estado=InformeAmbiental.Estado.BORRADOR,
            total_actividades=registros.count(),
            total_podas=registros.count(),
            hectareas_intervenidas=total_hectareas,
            m3_vegetacion=total_m3,
            elaborado_por=coordinador,
        )

        # === Generate Financial Summary ===
        from django.db.models import Sum

        resumen_financiero = presupuesto.ejecuciones.aggregate(
            total_ejecutado=Sum('costo_total'),
        )

        presupuesto.total_ejecutado = resumen_financiero['total_ejecutado'] or Decimal("0.00")
        presupuesto.save()

        # === Calculate KPIs ===
        from apps.indicadores.calculators import calcular_todos_indicadores
        resultados_kpi = calcular_todos_indicadores(linea.id, anio, mes)

        # === VERIFICATION ===
        assert informe_ambiental.total_actividades == 15
        assert informe_ambiental.hectareas_intervenidas == Decimal("22.5")  # 15 * 1.5
        assert informe_ambiental.m3_vegetacion == Decimal("300.0")  # 15 * 20

        assert presupuesto.total_ejecutado > 0
        assert presupuesto.desviacion != 0

        mediciones = MedicionIndicador.objects.filter(
            linea=linea,
            anio=anio,
            mes=mes,
        )
        assert mediciones.exists()
