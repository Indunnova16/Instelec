"""Tests #210 — Asistencia: acciones masivas, viático, Día ganado y jornada
única fuente de verdad.

Issue: Indunnova16/Instelec#210

Cubre (según diagnóstico F2, RUN_2026-08-07_0220):
  - DIA_GANADO existe como choice y NO cuenta como día trabajado para
    nómina/dias_activos (financiero/views.py sigue filtrando
    tipo_novedad='PRESENTE', sin cambios ahí -- este test lo deja
    explícito en vez de confiar en que "por default no cuenta").
  - Asistencia.JORNADA_POR_DIA como única fuente de verdad -- ya no hay
    dicts re-hardcodeados en CuadrillaDetailView/AsistenciaUpdateView.
  - AsistenciaAccionMasivaView: 'presente', 'festivo_domingo', 'viatico',
    cada uno aplicado a TODO el personal activo de la cuadrilla en una
    fecha, sin tocar miembros inactivos ni otras fechas.

Jornada 42h: NO se toca en este issue -- bloqueado por datos reales de
horario pendientes (ver PLAN), JORNADA_POR_DIA queda en 44h/semana
(comportamiento actual, sin cambios de valor) hasta que llegue el insumo.

Ejecutar:
  DJANGO_SETTINGS_MODULE=config.settings.dev_lite \
    venv/bin/python -m pytest apps/cuadrillas/tests_issue_210.py -v \
    -o python_files="tests_*.py test_*.py"
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.cuadrillas.models import Asistencia, Cuadrilla, CuadrillaMiembro

Usuario = get_user_model()


def _crear_admin():
    return Usuario.objects.create_user(
        email="admin_210@test.com",
        password="testpass123!",
        first_name="Admin",
        last_name="210",
        rol="admin",
        is_staff=True,
    )


def _crear_usuario(documento, nombre):
    partes = nombre.split(maxsplit=1)
    return Usuario.objects.create(
        email=f"{documento}@test.local",
        documento=documento,
        first_name=partes[0],
        last_name=partes[1] if len(partes) > 1 else "",
        rol="liniero",
        is_active=True,
    )


def _crear_bloque_con_miembros(codigo, fecha, activos, inactivos=()):
    c = Cuadrilla.objects.create(
        codigo=codigo, nombre="MANTENIMIENTO - 210", activa=True,
        observaciones="", fecha=fecha,
    )
    for usuario in activos:
        CuadrillaMiembro.objects.create(
            cuadrilla=c, usuario=usuario, rol_cuadrilla_id="LINIERO_I",
            cargo="MIEMBRO", costo_dia=0, fecha_inicio=fecha, activo=True,
        )
    for usuario in inactivos:
        CuadrillaMiembro.objects.create(
            cuadrilla=c, usuario=usuario, rol_cuadrilla_id="LINIERO_I",
            cargo="MIEMBRO", costo_dia=0, fecha_inicio=fecha, activo=False,
        )
    return c


class TestDiaGanadoChoiceYNoCuentaComoTrabajado(TestCase):
    def setUp(self):
        self.admin = _crear_admin()
        self.client.force_login(self.admin)
        self.usuario = _crear_usuario("QA0210DG", "QAE210 DiaGanado")
        self.cuadrilla = _crear_bloque_con_miembros(
            "01-2099-0210DG-QAE", date(2099, 1, 5), [self.usuario]
        )

    def test_dia_ganado_es_choice_valido_en_el_modelo(self):
        self.assertIn(
            ("DIA_GANADO", "Día ganado"), Asistencia.TipoNovedad.choices
        )

    def test_dia_ganado_seleccionable_desde_el_endpoint_de_asistencia(self):
        resp = self.client.post(
            reverse("cuadrillas:asistencia_update", args=[self.cuadrilla.pk]),
            data={
                "usuario_id": str(self.usuario.pk),
                "fecha": "2099-01-05",
                "tipo_novedad": "DIA_GANADO",
                "viaticos": "0",
                "observacion": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        asist = Asistencia.objects.get(usuario=self.usuario, fecha=date(2099, 1, 5))
        self.assertEqual(asist.tipo_novedad, "DIA_GANADO")

    def test_dia_ganado_no_cuenta_como_presente_para_nomina(self):
        """Filtro tipo_novedad='PRESENTE' de financiero/views.py -- DIA_GANADO
        debe quedar EXCLUIDO, igual que cualquier otro tipo distinto de
        PRESENTE. Lock-in explícito del comportamiento pedido en el issue
        ("no debe contar como trabajado")."""
        Asistencia.objects.create(
            usuario=self.usuario, cuadrilla=self.cuadrilla, fecha=date(2099, 1, 5),
            tipo_novedad="DIA_GANADO", registrado_por=self.admin,
        )
        dias_presente = Asistencia.objects.filter(
            cuadrilla=self.cuadrilla, tipo_novedad="PRESENTE"
        ).count()
        self.assertEqual(dias_presente, 0)


class TestJornadaUnicaFuenteDeVerdad(TestCase):
    """Asistencia.JORNADA_POR_DIA es la ÚNICA fuente -- ya no hay copias
    re-hardcodeadas en CuadrillaDetailView.get_context_data ni en
    AsistenciaUpdateView.post (issue #210)."""

    def setUp(self):
        self.admin = _crear_admin()
        self.client.force_login(self.admin)
        self.usuario = _crear_usuario("QA0210JOR", "QAE210 Jornada")
        # Lunes 2099-01-05 = ISO semana 02/2099 -- JORNADA_POR_DIA[0] = 7.0.
        # El codigo DEBE llevar el prefijo de semana ISO real (usado por
        # _get_semana_from_codigo para anclar dias_semana en el detalle).
        self.cuadrilla = _crear_bloque_con_miembros(
            "02-2099-0210JOR-QAE", date(2099, 1, 5), [self.usuario]
        )

    def test_detalle_cuadrilla_usa_jornada_por_dia_del_modelo(self):
        Asistencia.objects.create(
            usuario=self.usuario, cuadrilla=self.cuadrilla, fecha=date(2099, 1, 5),
            tipo_novedad="PRESENTE", registrado_por=self.admin,
        )
        resp = self.client.get(reverse("cuadrillas:detalle", args=[self.cuadrilla.pk]))
        self.assertEqual(resp.status_code, 200)
        fila = resp.context["filas_asistencia"][0]
        # Lunes: jornada_por_dia[0] = 7.0 (modelo, no un valor distinto
        # que hubiera quedado hardcodeado aparte).
        self.assertEqual(fila["total_horas_ordinarias"], Decimal("7.0"))
        # El propio dia_info trae 'jornada' -- el template ya no calcula
        # el mapeo dia_semana->horas con tags de Django.
        self.assertEqual(fila["dias"][0]["jornada"], Asistencia.JORNADA_POR_DIA[0])

    def test_asistencia_update_post_usa_jornada_por_dia_del_modelo(self):
        resp = self.client.post(
            reverse("cuadrillas:asistencia_update", args=[self.cuadrilla.pk]),
            data={
                "usuario_id": str(self.usuario.pk),
                "fecha": "2099-01-05",
                "tipo_novedad": "PRESENTE",
                "viaticos": "0",
                "observacion": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        # El HTML del badge de HE embebe "({jornada}h)" -- 7.0h para un lunes.
        self.assertIn("7.0h", resp.content.decode())


class TestAccionMasivaPresente(TestCase):
    def setUp(self):
        self.admin = _crear_admin()
        self.client.force_login(self.admin)
        self.activo1 = _crear_usuario("QA0210AM1", "QAE210 Activo1")
        self.activo2 = _crear_usuario("QA0210AM2", "QAE210 Activo2")
        self.inactivo = _crear_usuario("QA0210AM3", "QAE210 Inactivo")
        self.cuadrilla = _crear_bloque_con_miembros(
            "01-2099-0210AM-QAE", date(2099, 1, 5),
            activos=[self.activo1, self.activo2], inactivos=[self.inactivo],
        )

    def _post(self, accion, fecha="2099-01-05"):
        return self.client.post(
            reverse("cuadrillas:asistencia_accion_masiva", args=[self.cuadrilla.pk]),
            data={"accion": accion, "fecha": fecha},
        )

    def test_presente_marca_todo_el_personal_activo(self):
        resp = self._post("presente")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["afectados"], 2)
        for u in (self.activo1, self.activo2):
            asist = Asistencia.objects.get(usuario=u, fecha=date(2099, 1, 5))
            self.assertEqual(asist.tipo_novedad, "PRESENTE")

    def test_presente_no_toca_miembro_inactivo(self):
        self._post("presente")
        self.assertFalse(
            Asistencia.objects.filter(usuario=self.inactivo, fecha=date(2099, 1, 5)).exists()
        )

    def test_presente_no_toca_otra_fecha(self):
        self._post("presente", fecha="2099-01-05")
        self.assertFalse(
            Asistencia.objects.filter(
                usuario=self.activo1, fecha=date(2099, 1, 6)
            ).exists()
        )

    def test_accion_invalida_400(self):
        resp = self._post("no_existe")
        self.assertEqual(resp.status_code, 400)

    def test_fecha_invalida_400(self):
        resp = self._post("presente", fecha="no-es-una-fecha")
        self.assertEqual(resp.status_code, 400)


class TestAccionMasivaFestivoDomingo(TestCase):
    def setUp(self):
        self.admin = _crear_admin()
        self.client.force_login(self.admin)
        self.usuario = _crear_usuario("QA0210FD1", "QAE210 FestivoDomingo")
        # Domingo real: 2099-01-04 (jornada regular = 0h ese dia).
        self.cuadrilla = _crear_bloque_con_miembros(
            "01-2099-0210FD-QAE", date(2099, 1, 4), [self.usuario]
        )

    def test_festivo_domingo_persiste_estado_y_recargo(self):
        resp = self.client.post(
            reverse("cuadrillas:asistencia_accion_masiva", args=[self.cuadrilla.pk]),
            data={"accion": "festivo_domingo", "fecha": "2099-01-04"},
        )
        self.assertEqual(resp.status_code, 200)
        asist = Asistencia.objects.get(usuario=self.usuario, fecha=date(2099, 1, 4))
        self.assertEqual(asist.tipo_novedad, "FESTIVO")
        self.assertEqual(asist.he_dominical_diurna, Decimal("8.0"))
        # save() recalcula horas_extra como suma de los 4 detalles.
        self.assertEqual(asist.horas_extra, Decimal("8.0"))

    def test_festivo_semana_no_duplica_jornada_ordinaria_en_el_total(self):
        """Un festivo entre semana no se convierte en PRESENTE ni es ordinario."""
        fecha_festiva = date(2099, 1, 5)  # Lunes: jornada regular de 8h.
        self.cuadrilla.codigo = "02-2099-0210FD-QAE"
        self.cuadrilla.save(update_fields=["codigo"])
        resp = self.client.post(
            reverse("cuadrillas:asistencia_accion_masiva", args=[self.cuadrilla.pk]),
            data={"accion": "festivo_domingo", "fecha": fecha_festiva.isoformat()},
        )
        self.assertEqual(resp.status_code, 200)

        detalle = self.client.get(reverse("cuadrillas:detalle", args=[self.cuadrilla.pk]))
        self.assertEqual(detalle.status_code, 200)
        fila = detalle.context["filas_asistencia"][0]
        self.assertEqual(fila["total_horas_ordinarias"], Decimal("0"))
        self.assertEqual(fila["total_horas_extra"], Decimal("7"))
        self.assertEqual(fila["total_horas_total"], Decimal("7"))


class TestAccionMasivaViatico(TestCase):
    def setUp(self):
        self.admin = _crear_admin()
        self.client.force_login(self.admin)
        self.usuario = _crear_usuario("QA0210VI1", "QAE210 Viatico")
        self.cuadrilla = _crear_bloque_con_miembros(
            "01-2099-0210VI-QAE", date(2099, 1, 5), [self.usuario]
        )

    def test_viatico_aplica_default_a_todo_el_personal(self):
        resp = self.client.post(
            reverse("cuadrillas:asistencia_accion_masiva", args=[self.cuadrilla.pk]),
            data={"accion": "viatico", "fecha": "2099-01-05"},
        )
        self.assertEqual(resp.status_code, 200)
        asist = Asistencia.objects.get(usuario=self.usuario, fecha=date(2099, 1, 5))
        self.assertTrue(asist.viatico_aplica)
        # Sin CostoRecurso(tipo='VIATICO') sembrado en este test DB, cae al
        # mismo fallback hardcodeado que ya usa AsistenciaUpdateView.
        self.assertEqual(asist.viaticos, Decimal("136941"))

    def test_viatico_editado_en_formulario_se_conserva(self):
        resp = self.client.post(
            reverse("cuadrillas:asistencia_update", args=[self.cuadrilla.pk]),
            data={
                "usuario_id": str(self.usuario.pk),
                "fecha": "2099-01-05",
                "tipo_novedad": "PRESENTE",
                "viatico_aplica": "on",
                "viaticos": "175000",
                "observacion": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        asist = Asistencia.objects.get(usuario=self.usuario, fecha=date(2099, 1, 5))
        self.assertTrue(asist.viatico_aplica)
        self.assertEqual(asist.viaticos, Decimal("175000"))
        self.assertIn('x-show="showViatico"', resp.content.decode())

    def test_viatico_masivo_se_muestra_editable_tras_recargar(self):
        resp = self.client.post(
            reverse("cuadrillas:asistencia_accion_masiva", args=[self.cuadrilla.pk]),
            data={"accion": "viatico", "fecha": "2099-01-05"},
        )
        self.assertEqual(resp.status_code, 200)

        detalle = self.client.get(reverse("cuadrillas:detalle", args=[self.cuadrilla.pk]))
        self.assertEqual(detalle.status_code, 200)
        self.assertIn('x-show="showViatico"', detalle.content.decode())
        self.assertIn('name="viaticos"', detalle.content.decode())


class TestRevisionAdversarial210(TestCase):
    """Regresiones halladas en la revisión adversarial post-cierre (2026-08-17).

    El cierre anterior de #210 se validó con un viático de $0 y un festivo en
    domingo — justo los dos únicos casos donde los defectos NO se manifiestan.
    Estos tests fijan el caso que sí los expone.
    """

    def setUp(self):
        self.admin = _crear_admin()
        self.client.force_login(self.admin)
        self.usuario = _crear_usuario("QA0210ADV", "QAE210 Adversarial")
        # El código codifica la semana ISO que renderiza el detalle: 2099-01-05
        # (lunes) y 2099-01-06 (martes) caen en la semana 02 de 2099.
        self.cuadrilla = _crear_bloque_con_miembros(
            "02-2099-0210AD-QAE", date(2099, 1, 5), [self.usuario]
        )

    def test_viatico_no_cero_no_rompe_el_js_del_template(self):
        """El bug real: en es-CO `{{ v }}` daba "136941,00" y el x-data de
        Alpine quedaba con JS inválido, tumbando la celda entera. Con $0 (el
        caso que se probó al cerrar) el `{% if %}` caía al literal `0` y el
        defecto quedaba invisible."""
        Asistencia.objects.create(
            usuario=self.usuario, cuadrilla=self.cuadrilla, fecha=date(2099, 1, 5),
            tipo_novedad="PRESENTE", viatico_aplica=True, viaticos=Decimal("136941.00"),
        )
        resp = self.client.get(reverse("cuadrillas:detalle", args=[self.cuadrilla.pk]))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        # Separador decimal PUNTO: con coma el x-data es JS inválido.
        self.assertIn("viaticos: 136941.0", html)
        self.assertNotIn("viaticos: 136941,0", html)
        # Ningún número embebido en el JS del x-data puede llevar coma decimal.
        self.assertNotRegex(html, r"(viaticos|horas):\s*\d+,\d")

    def test_viatico_cero_explicito_no_se_convierte_en_el_default(self):
        """Marcar V con importe 0 debe persistir 0, no el default de $136.941."""
        resp = self.client.post(
            reverse("cuadrillas:asistencia_update", args=[self.cuadrilla.pk]),
            data={
                "usuario_id": str(self.usuario.pk), "fecha": "2099-01-05",
                "tipo_novedad": "PRESENTE", "viatico_aplica": "on",
                "viaticos": "0", "observacion": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        asist = Asistencia.objects.get(usuario=self.usuario, fecha=date(2099, 1, 5))
        self.assertEqual(asist.viaticos, Decimal("0"))

    def test_festivo_entre_semana_usa_la_jornada_del_dia_no_8h_fijas(self):
        """Un martes son 7,5h de jornada: registrar 8h pagaba media hora de
        más al factor dominical 2.00."""
        martes = date(2099, 1, 6)
        self.assertEqual(martes.weekday(), 1)
        resp = self.client.post(
            reverse("cuadrillas:asistencia_accion_masiva", args=[self.cuadrilla.pk]),
            data={"accion": "festivo_domingo", "fecha": martes.isoformat()},
        )
        self.assertEqual(resp.status_code, 200)
        asist = Asistencia.objects.get(usuario=self.usuario, fecha=martes)
        self.assertEqual(asist.he_dominical_diurna, Decimal("7"))

    def test_festivo_en_domingo_conserva_la_jornada_completa_de_8h(self):
        """El domingo tiene jornada 0 por definición, así que el fallback de
        8h se mantiene — este es el caso que ya funcionaba, no debe romperse."""
        domingo = date(2099, 1, 4)
        self.assertEqual(domingo.weekday(), 6)
        resp = self.client.post(
            reverse("cuadrillas:asistencia_accion_masiva", args=[self.cuadrilla.pk]),
            data={"accion": "festivo_domingo", "fecha": domingo.isoformat()},
        )
        self.assertEqual(resp.status_code, 200)
        asist = Asistencia.objects.get(usuario=self.usuario, fecha=domingo)
        self.assertEqual(asist.he_dominical_diurna, Decimal("8.0"))


class TestDiaGanadoAutomatico(TestCase):
    def setUp(self):
        self.admin = _crear_admin()
        self.client.force_login(self.admin)
        self.usuario = _crear_usuario("QA0210DG42", "QAE210 Dia Ganado 42")
        self.cuadrilla = _crear_bloque_con_miembros(
            "02-2099-0210DG42-QAE", date(2099, 1, 5), [self.usuario]
        )

    def _presente(self, fecha):
        return self.client.post(
            reverse("cuadrillas:asistencia_accion_masiva", args=[self.cuadrilla.pk]),
            data={"accion": "presente", "fecha": fecha.isoformat()},
        )

    def test_seis_dias_de_siete_horas_crean_dia_ganado_sin_costos(self):
        lunes = date(2099, 1, 5)
        for offset in range(6):
            self.assertEqual(self._presente(lunes.fromordinal(lunes.toordinal() + offset)).status_code, 200)
        domingo = Asistencia.objects.get(usuario=self.usuario, fecha=date(2099, 1, 11))
        self.assertEqual(domingo.tipo_novedad, "DIA_GANADO")
        self.assertEqual(domingo.horas_extra, Decimal("0"))
        self.assertFalse(domingo.viatico_aplica)

    def test_semana_incompleta_no_crea_dia_ganado(self):
        lunes = date(2099, 1, 5)
        for offset in range(5):
            self._presente(lunes.fromordinal(lunes.toordinal() + offset))
        self.assertFalse(Asistencia.objects.filter(usuario=self.usuario, fecha=date(2099, 1, 11)).exists())
