"""
B2.1 — Tests E2E para Segmentación de Vanos por Semestre.

Cubre:
- happy path filtrar S1
- aislamiento: cambiar estado de vano S1 no afecta S2
- importer/datafix parsea la tabla del issue #102 y crea VanoSemestres
- avance_consolidado calcula porcentajes correctos
- legacy: Vano pre-existente sin VanoSemestre rows queda preservado
- permisos: liniero no puede mutar; observaciones inválido devuelve 400
- modal config: desmarcar S2 cuando estaba PENDIENTE → eliminar; cuando ya tiene
  seguimiento → marcar NO_EJECUTADO en vez de borrar
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from apps.lineas.models import Linea, Vano
from apps.lineas.models_b21 import (
    VanoSemestre,
    SeguimientoVanoSemestre,
    filter_vanos_by_semestre,
)
from apps.lineas.importers_b21 import (
    parse_tabla,
    importar_tabla,
    TABLA_ISSUE_102,
)


User = get_user_model()


def _crear_linea_con_vanos(codigo='L-805', codigo_transelca='805', cantidad=10):
    linea = Linea.objects.create(
        codigo=codigo,
        codigo_transelca=codigo_transelca,
        nombre='Test Sabanalarga',
        cliente=Linea.Cliente.TRANSELCA,
    )
    vanos = [
        Vano.objects.create(linea=linea, numero=str(i + 1))
        for i in range(cantidad)
    ]
    return linea, vanos


class TestB21FiltrarVanosSemestreS1(TestCase):
    """
    Happy path: crear 10 vanos, 5 en S1 y 5 en S2, filtrar por S1 trae 5.
    Test cubre el método `b21_filtrar_vanos_semestre_s1` del BLUEPRINT.
    """

    def setUp(self):
        self.linea, self.vanos = _crear_linea_con_vanos(cantidad=10)
        for v in self.vanos[:5]:
            VanoSemestre.objects.create(vano=v, semestre='S1')
        for v in self.vanos[5:]:
            VanoSemestre.objects.create(vano=v, semestre='S2')

    def test_b21_filtrar_vanos_semestre_s1(self):
        qs = filter_vanos_by_semestre(Vano.objects.filter(linea=self.linea), 'S1')
        self.assertEqual(qs.count(), 5)
        self.assertSetEqual(
            set(qs.values_list('numero', flat=True)),
            {'1', '2', '3', '4', '5'},
        )

    def test_b21_filtrar_vanos_semestre_s1_lowercase_aceptado(self):
        # Edge: filtro case-insensitive
        qs = filter_vanos_by_semestre(Vano.objects.filter(linea=self.linea), 's1')
        self.assertEqual(qs.count(), 5)

    def test_b21_filtrar_vanos_semestre_invalido_devuelve_original(self):
        # Edge: semestre inválido → queryset sin filtrar
        qs = filter_vanos_by_semestre(Vano.objects.filter(linea=self.linea), 'XX')
        self.assertEqual(qs.count(), 10)

    def test_b21_filtrar_vanos_semestre_vacio_devuelve_original(self):
        qs = filter_vanos_by_semestre(Vano.objects.filter(linea=self.linea), '')
        self.assertEqual(qs.count(), 10)

    def test_b21_filtrar_vanos_semestre_ta(self):
        # Cambiar 1 vano a TA y filtrarlo
        VanoSemestre.objects.create(vano=self.vanos[0], semestre='TA')
        qs = filter_vanos_by_semestre(Vano.objects.filter(linea=self.linea), 'TA')
        self.assertEqual(qs.count(), 1)


class TestB21CambiarEstadoVanoS1NoAfectaS2(TestCase):
    """
    Aislamiento crítico: cambiar estado en S1 NO debe propagar a S2.
    Test cubre `b21_cambiar_estado_vano_s1_no_afecta_s2` del BLUEPRINT.
    """

    def setUp(self):
        self.linea, vanos = _crear_linea_con_vanos(cantidad=1)
        self.vano = vanos[0]
        self.vs1 = VanoSemestre.objects.create(vano=self.vano, semestre='S1')
        self.vs2 = VanoSemestre.objects.create(vano=self.vano, semestre='S2')
        self.admin = User.objects.create_user(
            email='admin@b21.test', password='x', rol='admin', is_superuser=True, is_staff=True,
        )

    def test_b21_cambiar_estado_vano_s1_no_afecta_s2(self):
        # Cambiar S1 a EJECUTADO via método marcar()
        self.vs1.marcar(VanoSemestre.Estado.EJECUTADO, usuario=self.admin)

        self.vs1.refresh_from_db()
        self.vs2.refresh_from_db()
        self.assertEqual(self.vs1.estado, VanoSemestre.Estado.EJECUTADO)
        self.assertEqual(self.vs2.estado, VanoSemestre.Estado.PENDIENTE)
        self.assertEqual(self.vs1.actualizado_por, self.admin)

    def test_b21_cambiar_estado_via_endpoint_admin(self):
        client = Client()
        client.force_login(self.admin)
        url = reverse('lineas:vano_semestre_estado', kwargs={'pk': self.vs1.pk})
        resp = client.post(url, {'estado': 'ejecutado', 'observaciones': 'Hecho 15-jun'})
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['estado'], 'ejecutado')

        self.vs1.refresh_from_db()
        self.vs2.refresh_from_db()
        self.assertEqual(self.vs1.estado, 'ejecutado')
        self.assertEqual(self.vs2.estado, 'pendiente')  # ← aislamiento

        # Seguimiento creado automáticamente
        seguimientos = SeguimientoVanoSemestre.objects.filter(vano_semestre=self.vs1)
        self.assertEqual(seguimientos.count(), 1)
        self.assertEqual(seguimientos.first().porcentaje_avance, 100.0)

    def test_b21_estado_invalido_devuelve_400(self):
        # Edge: estado inválido
        client = Client()
        client.force_login(self.admin)
        url = reverse('lineas:vano_semestre_estado', kwargs={'pk': self.vs1.pk})
        resp = client.post(url, {'estado': 'inventado'})
        self.assertEqual(resp.status_code, 400)

    def test_b21_marcar_estado_invalido_levanta(self):
        with self.assertRaises(ValueError):
            self.vs1.marcar('estado_falso')


class TestB21AvanceConsolidado(TestCase):
    """Cálculo de porcentajes por semestre y consolidado."""

    def setUp(self):
        self.linea, vanos = _crear_linea_con_vanos(cantidad=10)
        # S1: 6 vanos, 3 ejecutados
        for v in vanos[:6]:
            VanoSemestre.objects.create(vano=v, semestre='S1')
        VanoSemestre.objects.filter(vano__in=vanos[:3], semestre='S1').update(estado='ejecutado')
        # S2: 4 vanos, 2 ejecutados
        for v in vanos[6:]:
            VanoSemestre.objects.create(vano=v, semestre='S2')
        VanoSemestre.objects.filter(vano__in=vanos[6:8], semestre='S2').update(estado='ejecutado')

    def test_avance_consolidado_por_semestre(self):
        res = VanoSemestre.objects.avance_consolidado(self.linea)
        self.assertEqual(res['s1']['total'], 6)
        self.assertEqual(res['s1']['ejecutados'], 3)
        self.assertEqual(res['s1']['porcentaje'], 50.0)
        self.assertEqual(res['s2']['total'], 4)
        self.assertEqual(res['s2']['ejecutados'], 2)
        self.assertEqual(res['s2']['porcentaje'], 50.0)
        self.assertEqual(res['ta']['total'], 0)
        self.assertEqual(res['ta']['porcentaje'], 0.0)
        self.assertEqual(res['total']['total'], 10)
        self.assertEqual(res['total']['ejecutados'], 5)
        self.assertEqual(res['total']['porcentaje'], 50.0)

    def test_avance_consolidado_linea_sin_vano_semestres(self):
        # Edge: línea limpia → porcentajes en 0 sin dividir por cero
        linea2 = Linea.objects.create(codigo='L-999', nombre='Vacia')
        res = VanoSemestre.objects.avance_consolidado(linea2)
        self.assertEqual(res['total']['porcentaje'], 0.0)
        self.assertEqual(res['s1']['porcentaje'], 0.0)


class TestB21DatoLegacyPreservado(TestCase):
    """
    Test obligatorio (modelo Vano tiene datos prod): un Vano legacy sin
    VanoSemestre rows debe seguir funcionando, y queryset por_linea() lo
    ignora cuando no tiene semestres.
    """

    def setUp(self):
        self.linea, vanos = _crear_linea_con_vanos(cantidad=3)
        self.vano_legacy = vanos[0]
        # Otros 2 vanos sí tienen VanoSemestre
        for v in vanos[1:]:
            VanoSemestre.objects.create(vano=v, semestre='S1')

    def test_dato_legacy_vano_sin_semestres_no_aparece_filtrado(self):
        qs = filter_vanos_by_semestre(Vano.objects.filter(linea=self.linea), 'S1')
        ids = set(qs.values_list('id', flat=True))
        self.assertNotIn(self.vano_legacy.id, ids)
        self.assertEqual(len(ids), 2)

    def test_dato_legacy_vano_sin_semestres_aparece_sin_filtro(self):
        qs = filter_vanos_by_semestre(Vano.objects.filter(linea=self.linea), None)
        self.assertEqual(qs.count(), 3)

    def test_dato_legacy_vano_sin_semestres_consolidado(self):
        # avance_consolidado no debe romper aunque haya vanos sin VanoSemestre
        res = VanoSemestre.objects.avance_consolidado(self.linea)
        self.assertEqual(res['s1']['total'], 2)


class TestB21Importer(TestCase):
    """El importer parsea la tabla del issue #102 y crea VanoSemestres."""

    def test_parse_tabla_extrae_filas(self):
        filas = parse_tabla(TABLA_ISSUE_102)
        # 23 líneas en la tabla del issue
        self.assertGreaterEqual(len(filas), 20)
        ln_805 = [f for f in filas if '805' in f.codigo_linea and '806' not in f.codigo_linea]
        self.assertEqual(len(ln_805), 1)
        self.assertEqual(ln_805[0].s1, 246)
        self.assertEqual(ln_805[0].s2, 129)
        self.assertEqual(ln_805[0].ta, 0)

    def test_parse_tabla_dash_como_cero(self):
        filas = parse_tabla(TABLA_ISSUE_102)
        ln_5156 = [f for f in filas if '5156' in f.codigo_linea]
        self.assertEqual(len(ln_5156), 1)
        # "- " en S2/TA → 0
        self.assertEqual(ln_5156[0].s2, 0)
        self.assertEqual(ln_5156[0].ta, 0)
        self.assertEqual(ln_5156[0].s1, 264)

    def test_importar_tabla_crea_vano_semestres(self):
        # Crear linea LN 805 con suficientes vanos para que el importer
        # asigne todos los de S1+S2
        linea, _ = _crear_linea_con_vanos(codigo='L-805', codigo_transelca='805', cantidad=246)

        texto_mini = """
LÍNEA          | S1 Total | S2 Total | Todo Año | Total
LN 805         |   246    |   129    |    0     |  246
"""
        res = importar_tabla(texto_mini, dry_run=False)
        self.assertEqual(res.filas_parseadas, 1)
        self.assertGreater(res.vano_semestres_creados, 0)

        s1_count = VanoSemestre.objects.filter(vano__linea=linea, semestre='S1').count()
        s2_count = VanoSemestre.objects.filter(vano__linea=linea, semestre='S2').count()
        self.assertEqual(s1_count, 246)
        self.assertEqual(s2_count, 129)

    def test_importar_tabla_linea_no_encontrada_reportada(self):
        # Edge: línea inexistente
        texto_mini = """
LÍNEA          | S1 Total | S2 Total | Todo Año | Total
LN 9999        |    10    |     5    |    0     |   15
"""
        res = importar_tabla(texto_mini, dry_run=False)
        self.assertEqual(res.filas_parseadas, 1)
        self.assertIn('LN 9999', res.lineas_no_encontradas)
        self.assertEqual(res.vano_semestres_creados, 0)

    def test_importar_tabla_vanos_faltantes_reportados(self):
        # Edge: línea con menos vanos que la tabla pide → warning, no error
        linea, _ = _crear_linea_con_vanos(codigo='L-733', codigo_transelca='733', cantidad=5)
        texto_mini = """
LÍNEA          | S1 Total | S2 Total | Todo Año | Total
LN 733         |    18    |     8    |    0     |   18
"""
        res = importar_tabla(texto_mini, dry_run=False)
        self.assertIn(linea.codigo, res.vanos_faltantes_por_linea)

    def test_importar_tabla_dry_run_no_persiste(self):
        linea, _ = _crear_linea_con_vanos(codigo='L-805', codigo_transelca='805', cantidad=10)
        texto_mini = """
LÍNEA          | S1 Total | S2 Total | Todo Año | Total
LN 805         |    10    |     0    |    0     |   10
"""
        res = importar_tabla(texto_mini, dry_run=True)
        self.assertEqual(res.filas_parseadas, 1)
        # En dry-run no debe persistir
        count = VanoSemestre.objects.filter(vano__linea=linea).count()
        self.assertEqual(count, 0)


class TestB21ConfigurarSemestresEndpoint(TestCase):
    """Endpoint del modal: configurar qué semestres aplica un vano."""

    def setUp(self):
        self.linea, vanos = _crear_linea_con_vanos(cantidad=1)
        self.vano = vanos[0]
        self.admin = User.objects.create_user(
            email='admin2@b21.test', password='x', rol='admin', is_superuser=True, is_staff=True,
        )
        self.liniero = User.objects.create_user(
            email='liniero@b21.test', password='x', rol='liniero',
        )

    def test_configurar_semestres_crea_filas(self):
        client = Client()
        client.force_login(self.admin)
        url = reverse('lineas:vano_semestres_configurar', kwargs={'vano_id': self.vano.id})
        resp = client.post(url, {'semestres': ['S1', 'S2']})
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertSetEqual(set(data['creados']), {'S1', 'S2'})
        self.assertEqual(VanoSemestre.objects.filter(vano=self.vano).count(), 2)

    def test_desmarcar_pendiente_elimina(self):
        VanoSemestre.objects.create(vano=self.vano, semestre='S1')
        VanoSemestre.objects.create(vano=self.vano, semestre='S2')

        client = Client()
        client.force_login(self.admin)
        url = reverse('lineas:vano_semestres_configurar', kwargs={'vano_id': self.vano.id})
        # Solo S1 marcado → S2 debe desaparecer (pendiente sin seguimiento)
        resp = client.post(url, {'semestres': ['S1']})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(VanoSemestre.objects.filter(vano=self.vano).count(), 1)
        self.assertEqual(
            VanoSemestre.objects.filter(vano=self.vano).first().semestre, 'S1',
        )

    def test_desmarcar_con_seguimiento_se_marca_no_ejecutado(self):
        # Edge: S2 con histórico no se borra, queda NO_EJECUTADO
        vs1 = VanoSemestre.objects.create(vano=self.vano, semestre='S1')
        vs2 = VanoSemestre.objects.create(vano=self.vano, semestre='S2')
        SeguimientoVanoSemestre.objects.create(
            vano_semestre=vs2,
            fecha='2026-04-01',
            porcentaje_avance=50,
            horas=2,
        )

        client = Client()
        client.force_login(self.admin)
        url = reverse('lineas:vano_semestres_configurar', kwargs={'vano_id': self.vano.id})
        resp = client.post(url, {'semestres': ['S1']})
        self.assertEqual(resp.status_code, 200)
        # S2 sigue existiendo pero como NO_EJECUTADO
        vs2.refresh_from_db()
        self.assertEqual(vs2.estado, 'no_ejecutado')
        self.assertEqual(VanoSemestre.objects.filter(vano=self.vano).count(), 2)

    def test_semestre_invalido_devuelve_400(self):
        client = Client()
        client.force_login(self.admin)
        url = reverse('lineas:vano_semestres_configurar', kwargs={'vano_id': self.vano.id})
        resp = client.post(url, {'semestres': ['XX']})
        self.assertEqual(resp.status_code, 400)

    def test_liniero_no_puede_configurar(self):
        # Permisos
        client = Client()
        client.force_login(self.liniero)
        url = reverse('lineas:vano_semestres_configurar', kwargs={'vano_id': self.vano.id})
        resp = client.post(url, {'semestres': ['S1']})
        # RoleRequiredMixin denega (403/302 según implementación)
        self.assertIn(resp.status_code, (302, 403))


class TestB21LineaDetailSemestreEndpoint(TestCase):
    """GET /lineas/<uuid>/semestre/?semestre=S1 devuelve JSON con stats + rows."""

    def setUp(self):
        self.linea, vanos = _crear_linea_con_vanos(cantidad=4)
        for v in vanos[:3]:
            VanoSemestre.objects.create(vano=v, semestre='S1')
        VanoSemestre.objects.create(vano=vanos[3], semestre='S2')
        self.admin = User.objects.create_user(
            email='admin3@b21.test', password='x', rol='admin', is_superuser=True, is_staff=True,
        )

    def test_detalle_semestre_filtra_y_devuelve_stats(self):
        client = Client()
        client.force_login(self.admin)
        url = reverse('lineas:detalle_semestre', kwargs={'linea_id': self.linea.id})
        resp = client.get(url + '?semestre=S1')
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(data['semestre_filtro'], 'S1')
        self.assertEqual(data['count'], 3)
        self.assertEqual(data['avance_consolidado']['s1']['total'], 3)
        self.assertEqual(data['avance_consolidado']['s2']['total'], 1)

    def test_detalle_semestre_sin_filtro_devuelve_todos(self):
        client = Client()
        client.force_login(self.admin)
        url = reverse('lineas:detalle_semestre', kwargs={'linea_id': self.linea.id})
        resp = client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNone(data['semestre_filtro'])
        # 4 vanos en total (incluso el legacy sin VanoSemestre — ah espera, todos tienen 1)
        self.assertEqual(data['count'], 4)
