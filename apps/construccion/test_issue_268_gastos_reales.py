"""Instelec#268 — Presupuesto Real (Ejecutado): carga de gastos reales (Excel de
18 columnas) y comparación contra el Presupuesto Planeado (#267).

Cobertura: validaciones de la carga (encabezados, NIT vs maestro #262,
proveedor inactivo, Periodo, Neto, Fecha, Docto duplicado), UPSERT por
período, semáforo con los umbrales exactos del issue, comparativo contra un
planeado con la estructura REAL de prod (rubros → cuentas equivalentes con
meses por nombre), vista (GET/POST/filtros), plantilla, reportes, API y el
dato legacy: el historial del planeado no se mezcla con las cargas reales.
"""

import uuid
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import Http404
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from openpyxl import Workbook

from apps.construccion import gastos_real
from apps.construccion.api import presupuesto_real_periodo
from apps.construccion.models import ProyectoConstruccion
from apps.construccion.models_fin import (
    GastoRealConstruccion,
    HistorialCargaPresupuestoConstruccion,
    PresupuestoDetalladoConstruccion,
)
from apps.contratos.models import Contrato
from apps.financiero.models_finv2_facturas import Proveedor

User = get_user_model()
COLS = gastos_real.COLUMNAS_GASTOS_REALES


def _fila(
    neto=1000000,
    nit="900111222",
    periodo="202602",
    fecha="15/02/2026",
    docto="NC-1",
    cuenta="Prestaciones Sociales",
    auxiliar="5105",
    fijo="Si",
    cc="300102",
):
    return [
        auxiliar,
        "CESANTIAS",
        neto,
        fecha,
        docto,
        periodo,
        nit,
        "PROVEEDOR UNO SAS",
        "OBRA",
        "janet@instelec.com.co",
        "67",
        "",
        cc,
        "ADMINISTRACION",
        cuenta,
        "TRANSELCA",
        "Auxiliar",
        fijo,
    ]


def _excel(filas, encabezado=None):
    wb = Workbook()
    ws = wb.active
    ws.append(encabezado or COLS)
    for f in filas:
        ws.append(f)
    buf = BytesIO()
    wb.save(buf)
    return SimpleUploadedFile(
        "gastos_reales.xlsx",
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _proyecto():
    contrato = Contrato.objects.create(
        codigo=f"CONS-{uuid.uuid4().hex[:10]}",
        nombre="Contrato #268",
        unidad_negocio="CONSTRUCCION",
    )
    return ProyectoConstruccion.objects.create(contrato=contrato, nombre="Proyecto #268")


def _planeado(proyecto, anio=2026):
    """Estructura real de prod: finv2_bd.rubros[rubro].cuentas[cta_equivalente].meses{nombre}."""
    return PresupuestoDetalladoConstruccion.objects.create(
        proyecto=proyecto,
        anio=anio,
        tipo=PresupuestoDetalladoConstruccion.Tipo.PLANEADO,
        datos={
            "finv2_bd": {
                "total": 0,
                "rubros": {
                    "Personal": {
                        "meses": {"febrero": 1300000.0, "marzo": 900000.0},
                        "cuentas": [
                            {
                                "cta_equivalente": "Prestaciones Sociales",
                                "descripcion": "CESANTIAS",
                                "meses": {"febrero": 1000000.0, "marzo": 900000.0},
                            },
                            {
                                "cta_equivalente": "Seguridad Social",
                                "descripcion": "APORTES ARP",
                                "meses": {"febrero": 300000.0},
                            },
                        ],
                    },
                    "Ingresos Operacionales": {
                        "meses": {"febrero": -5000000.0},
                        "cuentas": [
                            {
                                "cta_equivalente": "Ingresos Operacionales",
                                "meses": {"febrero": -5000000.0},
                            }
                        ],
                    },
                },
            }
        },
    )


class SemaforoTests(SimpleTestCase):
    def test_umbrales_exactos_del_issue(self):
        self.assertEqual(gastos_real.semaforo(Decimal("99"), Decimal("100")), "verde")
        self.assertEqual(gastos_real.semaforo(Decimal("100"), Decimal("100")), "amarillo")
        self.assertEqual(gastos_real.semaforo(Decimal("110"), Decimal("100")), "amarillo")
        self.assertEqual(gastos_real.semaforo(Decimal("110.01"), Decimal("100")), "rojo")
        self.assertEqual(gastos_real.semaforo(Decimal("5"), Decimal("0")), "sin_presupuesto")

    def test_variacion_pct_ejemplo_del_issue(self):
        # Seguridad Social: real 9.101.203 vs presupuesto 8.500.000 → +7,07 % (🟡)
        self.assertEqual(
            gastos_real.variacion_pct(Decimal("9101203"), Decimal("8500000")), Decimal("7.07")
        )
        self.assertEqual(gastos_real.semaforo(Decimal("9101203"), Decimal("8500000")), "amarillo")

    def test_fijo_a_clasificacion_y_nit(self):
        self.assertEqual(gastos_real.clasificacion_desde_fijo("SI"), "Fijo")
        self.assertEqual(gastos_real.clasificacion_desde_fijo(""), "Variable")
        self.assertEqual(gastos_real.normalizar_nit(900111222.0), "900111222")
        self.assertEqual(gastos_real.normalizar_nit(" 900.111.222 "), "900111222")


class CargaGastosRealesTests(TestCase):
    def setUp(self):
        self.proyecto = _proyecto()
        self.prov = Proveedor.objects.create(
            nombre="Proveedor Uno SAS", nit="900111222", activo=True
        )
        self.inactivo = Proveedor.objects.create(
            nombre="Colfondos", nit="800227940-1", activo=False
        )

    def test_carga_feliz_con_varias_lineas_y_proveedor_inactivo(self):
        filas = [_fila(docto=f"NC-{i}", neto=100000 + i) for i in range(5)]
        filas.append(_fila(nit="800227940", docto="AP-1", cuenta="Seguridad Social", fijo=""))
        res = gastos_real.procesar_carga_gastos_reales(self.proyecto, _excel(filas))
        self.assertTrue(res.exito, res.errores)
        self.assertEqual(res.filas, 6)
        self.assertEqual(res.periodos, ["202602"])
        self.assertEqual(len(res.advertencias), 1)
        self.assertIn("inactivo", res.advertencias[0])
        g = GastoRealConstruccion.objects.get(docto="AP-1")
        self.assertEqual(g.proveedor, self.inactivo)  # NIT sin DV casa con el maestro con DV
        self.assertEqual(g.rubro, "Personal")
        self.assertEqual(g.clasificacion, "Variable")
        self.assertEqual(g.fecha, date(2026, 2, 15))
        h = res.historial
        self.assertEqual(
            (h.tipo, h.estado, h.filas_procesadas, h.mes, h.anio), ("REAL", "PROCESADA", 6, 2, 2026)
        )

    def test_upsert_reemplaza_el_periodo_sin_duplicar(self):
        gastos_real.procesar_carga_gastos_reales(
            self.proyecto, _excel([_fila(docto="A"), _fila(docto="B")])
        )
        gastos_real.procesar_carga_gastos_reales(
            self.proyecto, _excel([_fila(docto="C", periodo="202603", fecha="10/03/2026")])
        )
        res = gastos_real.procesar_carga_gastos_reales(
            self.proyecto, _excel([_fila(docto="A", neto=777)])
        )
        self.assertTrue(res.exito)
        feb = GastoRealConstruccion.objects.filter(proyecto=self.proyecto, periodo="202602")
        self.assertEqual(list(feb.values_list("docto", "neto")), [("A", Decimal("777.00"))])
        self.assertTrue(
            GastoRealConstruccion.objects.filter(periodo="202603").exists()
        )  # otro período intacto

    def test_nit_inexistente_bloquea_toda_la_carga(self):
        res = gastos_real.procesar_carga_gastos_reales(
            self.proyecto, _excel([_fila(docto="OK"), _fila(nit="98687561", docto="X")])
        )
        self.assertFalse(res.exito)
        self.assertIn("Proveedor 98687561 no registrado", " ".join(res.errores))
        self.assertFalse(GastoRealConstruccion.objects.exists())
        self.assertEqual(res.historial.estado, "ERROR")
        self.assertEqual(res.historial.detalle_errores["total_errores"], 1)

    def test_validaciones_de_fila(self):
        filas = [
            _fila(periodo="2026-02", docto="P"),
            _fila(neto=-5000, docto="N"),
            _fila(fecha="01/12/2025", docto="F"),  # >30 días antes de feb-2026
            _fila(fecha="texto", docto="T"),
            _fila(docto="D"),
            _fila(docto="D"),  # misma línea repetida
        ]
        res = gastos_real.procesar_carga_gastos_reales(self.proyecto, _excel(filas))
        texto = " ".join(res.errores)
        self.assertFalse(res.exito)
        for esperado in (
            'Periodo "2026-02" inválido',
            "debe ser positivo",
            "más de 30 días",
            'Fecha "texto" inválida',
            "Docto. D duplicado",
        ):
            self.assertIn(esperado, texto)

    def test_fecha_dentro_de_30_dias_antes_del_periodo_es_valida(self):
        res = gastos_real.procesar_carga_gastos_reales(
            self.proyecto, _excel([_fila(fecha="10/01/2026")])
        )
        self.assertTrue(res.exito, res.errores)

    def test_mismo_docto_con_otra_cuenta_no_es_duplicado(self):
        res = gastos_real.procesar_carga_gastos_reales(
            self.proyecto,
            _excel([_fila(docto="NOM-1", auxiliar="5105"), _fila(docto="NOM-1", auxiliar="5110")]),
        )
        self.assertTrue(res.exito, res.errores)

    def test_encabezados_en_otro_orden_se_rechazan(self):
        cols = list(COLS)
        cols[2], cols[3] = cols[3], cols[2]
        res = gastos_real.procesar_carga_gastos_reales(
            self.proyecto, _excel([_fila()], encabezado=cols)
        )
        self.assertFalse(res.exito)
        self.assertIn('columna 3: se esperaba "Neto"', res.errores[0])

    def test_encabezados_con_puntos_y_mayusculas_de_la_exportacion_contable(self):
        cols = [c.upper() + "." for c in COLS]
        res = gastos_real.procesar_carga_gastos_reales(
            self.proyecto, _excel([_fila()], encabezado=cols)
        )
        self.assertTrue(res.exito, res.errores)

    def test_archivo_no_excel(self):
        archivo = SimpleUploadedFile("x.xlsx", b"no soy excel")
        res = gastos_real.procesar_carga_gastos_reales(self.proyecto, archivo)
        self.assertFalse(res.exito)
        self.assertIn(".xlsx", res.errores[0])


class ComparativoTests(TestCase):
    def setUp(self):
        self.proyecto = _proyecto()
        _planeado(self.proyecto)
        Proveedor.objects.create(nombre="Proveedor Uno SAS", nit="900111222", activo=True)
        gastos_real.procesar_carga_gastos_reales(
            self.proyecto,
            _excel(
                [
                    _fila(neto=800000, docto="A"),  # Prestaciones: 800k vs 1.000k
                    _fila(
                        neto=320000, docto="B", cuenta="Seguridad Social"
                    ),  # 320k vs 300k (+6,67 %)
                    _fila(
                        neto=50000, docto="C", cuenta="CIF", fijo=""
                    ),  # sin presupuesto de cuenta
                ]
            ),
        )

    def test_compara_contra_el_presupuesto_de_los_meses_con_ejecucion(self):
        comp = gastos_real.construir_comparativo(self.proyecto, 2026)
        self.assertEqual(comp["meses_alcance"], [2])
        filas = {f["nombre"]: f for f in comp["filas"]}
        self.assertEqual(
            filas["Prestaciones Sociales"]["presupuesto"], Decimal("1000000")
        )  # marzo NO suma
        self.assertEqual(filas["Prestaciones Sociales"]["semaforo"], "verde")
        self.assertEqual(filas["Seguridad Social"]["variacion_pct"], Decimal("6.67"))
        self.assertEqual(filas["Seguridad Social"]["semaforo"], "amarillo")
        self.assertIsNone(filas["CIF"]["presupuesto"])
        self.assertEqual(filas["Personal"]["total_real"], Decimal("1120000"))
        self.assertEqual(filas["Personal"]["presupuesto"], Decimal("1300000"))
        self.assertTrue(filas["Personal"]["es_subtotal"])
        self.assertEqual(filas["Personal"]["meses"][1], Decimal("1120000"))  # columna Feb
        self.assertNotIn("Ingresos Operacionales", filas)  # ingresos fuera del comparativo de gasto
        kpi = comp["kpi"]
        self.assertEqual(kpi["real"], Decimal("1170000"))
        self.assertEqual(kpi["planeado"], Decimal("1300000"))
        self.assertEqual(kpi["cumplimiento_pct"], Decimal("90.0"))

    def test_filtros_y_proveedores(self):
        comp = gastos_real.construir_comparativo(self.proyecto, 2026, {"clasificacion": "Variable"})
        self.assertEqual(comp["kpi"]["real"], Decimal("50000"))
        comp = gastos_real.construir_comparativo(self.proyecto, 2026, {"proveedor": "900111222"})
        prov = comp["proveedores"][0]
        self.assertEqual(
            (prov["nombre"], prov["activo"], prov["total"]),
            ("Proveedor Uno SAS", True, Decimal("1170000")),
        )
        comp = gastos_real.construir_comparativo(self.proyecto, 2026, {"periodo": "202603"})
        self.assertEqual(comp["kpi"]["real"], Decimal("0"))
        self.assertEqual(
            comp["kpi"]["planeado"], Decimal("900000")
        )  # presupuesto de marzo sin ejecución

    def test_api_para_indicadores_246(self):
        data = presupuesto_real_periodo(None, self.proyecto.id, 2, 2026)
        self.assertEqual(data["periodo"], "02/2026")
        self.assertEqual(data["gasto_real_total"], 1170000.0)
        self.assertEqual(data["presupuesto_total"], 1300000.0)
        rubros = {r["rubro"]: r for r in data["por_rubro"]}
        self.assertEqual(rubros["Seguridad Social"]["variacion_porcentaje"], 6.67)
        with self.assertRaises(Http404):
            presupuesto_real_periodo(None, self.proyecto.id, 5, 2026)


class VistaPresupuestoRealTests(TestCase):
    def setUp(self):
        self.proyecto = _proyecto()
        _planeado(self.proyecto)
        Proveedor.objects.create(nombre="Proveedor Uno SAS", nit="900111222", activo=True)
        self.user = User.objects.create_superuser(
            email=f"qa268_{uuid.uuid4().hex[:6]}@instelec.com", password="x"
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse("construccion:fin_presupuesto_real", args=[self.proyecto.id])
        # Dato legacy: una carga del PLANEADO previa a #268.
        HistorialCargaPresupuestoConstruccion.objects.create(
            proyecto=self.proyecto,
            anio=2026,
            mes=9,
            filas_procesadas=18,
            estado="PROCESADA",
            archivo_nombre="planeado_sep.xlsx",
        )

    def test_sin_datos_muestra_la_carga(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Cargar Excel de gastos reales")
        self.assertNotContains(resp, "planeado_sep.xlsx")  # historial del planeado no se mezcla

    def test_post_carga_y_muestra_comparativo(self):
        resp = self.client.post(
            self.url,
            {"archivo": _excel([_fila(neto=800000), _fila(docto="B", cuenta="Seguridad Social")])},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("periodo=202602", resp["Location"])
        resp = self.client.get(resp["Location"])
        for texto in (
            "Prestaciones Sociales",
            "Seguridad Social",
            "Proveedor Uno SAS",
            "Total Real",
            "Presupuesto",
            "Cumplimiento",
            "gastos_reales.xlsx",
            'data-semaforo="verde"',
        ):
            self.assertContains(resp, texto)
        # El historial del planeado sigue mostrando solo lo suyo.
        planeado = self.client.get(
            reverse("construccion:fin_presupuesto_planeado", args=[self.proyecto.id])
        )
        self.assertEqual(planeado.status_code, 200)
        self.assertNotContains(planeado, "gastos_reales.xlsx")

    def test_post_con_errores_no_guarda_y_lo_dice(self):
        resp = self.client.post(self.url, {"archivo": _excel([_fila(nit="111")])}, follow=True)
        self.assertContains(resp, "no registrado en el maestro de proveedores")
        self.assertFalse(GastoRealConstruccion.objects.exists())

    def test_filtros_plantilla_y_reportes(self):
        gastos_real.procesar_carga_gastos_reales(self.proyecto, _excel([_fila()]))
        resp = self.client.get(
            self.url, {"anio": 2026, "clasificacion": "Fijo", "centro_costo": "300102"}
        )
        self.assertContains(resp, "Prestaciones Sociales")
        plantilla = self.client.get(
            reverse("construccion:fin_presupuesto_real_plantilla", args=[self.proyecto.id])
        )
        self.assertEqual(plantilla.status_code, 200)
        excel = self.client.get(
            reverse("construccion:fin_presupuesto_real_excel", args=[self.proyecto.id]),
            {"anio": 2026},
        )
        self.assertEqual(excel.status_code, 200)
        self.assertTrue(excel.content.startswith(b"PK"))
        csv_resp = self.client.get(
            reverse("construccion:fin_presupuesto_real_csv", args=[self.proyecto.id]),
            {"periodo": "202602"},
        )
        self.assertIn("Prestaciones Sociales", csv_resp.content.decode("utf-8"))
        from apps.construccion.reportes_gastos_real import construir_html_pdf_gastos_real

        html = construir_html_pdf_gastos_real(
            self.proyecto,
            2026,
            {"periodo": "", "clasificacion": "", "proveedor": "", "centro_costo": ""},
        )
        self.assertIn("Prestaciones Sociales", html)
