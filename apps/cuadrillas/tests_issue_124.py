"""
Tests #124 (reproceso bounce=1) — ProgramacionS18CuadrillaImporter:
idempotencia con estrategia SALTAR + RESUMEN.

Issue: Indunnova16/Instelec#124

Contexto del rebote: la intervención previa agregó un pre-check
`filter(codigo).first()`, pero el lote corría en UN solo `transaction.atomic()`
sin savepoints. Cuando un INSERT colisionaba con la UNIQUE `cuadrillas_codigo_key`
(código que YA existe en prod), el IntegrityError envenenaba la transacción
completa, abortaba todo el lote y el str crudo de psycopg2 se fugaba a la UI.

Este archivo valida el fix:
- (reproduce) subir un S18 cuyo código YA existe → esa cuadrilla se OMITE
  (no duplica: COUNT(codigo)=1), el resto del lote SÍ se crea, y NO se lanza
  excepción ni se fuga el error técnico.
- (dato legacy) se siembra primero una Cuadrilla pre-existente con el código
  realista del cliente (18-2026-0001-SER), no solo fixtures del propio import.
- `cuadrillas_omitidas` contiene el código colisionado.

Se usa TransactionTestCase para ejercitar el rollback REAL del savepoint
anidado (un TestCase envuelto en atomic enmascararía la semántica del
savepoint sobre una txn ya "rota").

Ejecutar:  pytest apps/cuadrillas/tests_issue_124.py -v
"""
from datetime import date
from io import BytesIO

from django.test import TransactionTestCase
from openpyxl import Workbook

from apps.cuadrillas.importers import ProgramacionS18CuadrillaImporter
from apps.cuadrillas.models import Cuadrilla
from apps.usuarios.models import Usuario


S18_HEADERS = [
    '#', 'ACTIVIDAD', 'LINEA', 'TRAMO', 'INICIO', 'FIN', 'PERSONAL',
    'CEDULA', 'CELULAR', 'CARGO', 'ROL', 'PLACA', 'AVISOS', 'ORDEN',
    'PT SAP', 'Comentarios',
]


def _build_s18_excel(filas, sheet_name='18'):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append(['INSTELEC SAS - NIT 890911324'])  # banner
    ws.append(S18_HEADERS)                        # headers
    for f in filas:
        ws.append(f)
    out = BytesIO()
    wb.save(out)
    out.seek(0)
    return out


def _act(numero, actividad, linea, inicio, fin, personal, cedula, cargo,
         rol=None, placa=None):
    # [#, ACTIVIDAD, LINEA, TRAMO, INICIO, FIN, PERSONAL, CEDULA, CELULAR,
    #  CARGO, ROL, PLACA, AVISOS, ORDEN, PT SAP, Comentarios]
    return [numero, actividad, linea, '', inicio, fin, personal, cedula,
            '', cargo, rol, placa, '', '', '', '']


def _crear_usuario(documento, nombre='OPERARIO TEST'):
    partes = nombre.split(maxsplit=1)
    return Usuario.objects.create(
        email=f'{documento}@test.local',
        documento=documento,
        first_name=partes[0],
        last_name=partes[1] if len(partes) > 1 else '',
        rol='operario_general',
        is_active=True,
    )


class TestImportS18Idempotencia(TransactionTestCase):
    """Issue #124: SALTAR + RESUMEN, sin envenenar el lote ni fugar el error."""

    # Código realista del cliente: WW-YYYY-NNNN-AAA → 18 + 2026 + 0001 + SER
    # (de actividad 'Servidumbre ...', numero 1, semana 18, año 2026).
    CODIGO_LEGACY = '18-2026-0001-SER'

    def test_codigo_existente_se_omite_y_resto_del_lote_se_crea(self):
        # --- dato legacy: cuadrilla pre-existente con el código del cliente ---
        Cuadrilla.objects.create(
            codigo=self.CODIGO_LEGACY,
            nombre='Servidumbre (PRE-EXISTENTE)',
            activa=True,
        )
        assert Cuadrilla.objects.filter(codigo=self.CODIGO_LEGACY).count() == 1

        _crear_usuario('1143246675', 'JHON JAIRO JIMENEZ')
        _crear_usuario('9999000111', 'PEDRO NUEVO')

        # Lote: bloque 1 colisiona (mismo código legacy); bloque 2 es NUEVO.
        excel = _build_s18_excel([
            _act(1, 'Servidumbre Completa', '817', date(2026, 4, 27),
                 date(2026, 5, 3), 'JHON JAIRO JIMENEZ', '1143246675',
                 'LINIERO I', 'JT/CTA'),
            _act(2, 'Despeje Mecanico', '817', date(2026, 4, 27),
                 date(2026, 5, 3), 'PEDRO NUEVO', '9999000111',
                 'AYUDANTE', 'JT/CTA'),
        ])

        # (a) NO debe propagar excepción a la vista — el import retorna un dict.
        res = ProgramacionS18CuadrillaImporter().importar(excel)

        # (b) el código colisionado se OMITIÓ → sigue habiendo exactamente 1.
        self.assertEqual(
            Cuadrilla.objects.filter(codigo=self.CODIGO_LEGACY).count(), 1,
            'la cuadrilla pre-existente no debe duplicarse',
        )

        # (c) el resto del lote SÍ se creó (bloque 2, código distinto).
        nuevo = Cuadrilla.objects.exclude(codigo=self.CODIGO_LEGACY)
        self.assertEqual(nuevo.count(), 1, 'el bloque nuevo debe haberse creado')
        self.assertEqual(res['cuadrillas_creadas'], 1)

        # (d) cuadrillas_omitidas contiene el código colisionado.
        self.assertIn(self.CODIGO_LEGACY, res['cuadrillas_omitidas'])
        self.assertEqual(res['cuadrillas_omitidas_count'], 1)

        # (e) NUNCA se fuga el error técnico de Postgres.
        self.assertTrue(res.get('exito', False))
        self.assertIsNone(res.get('error'))
        for adv in res.get('advertencias', []):
            self.assertNotIn('duplicate key', adv.lower())
            self.assertNotIn('cuadrillas_codigo_key', adv)

    def test_resumen_amigable_no_fuga_error_tecnico_en_error_inesperado(self):
        """Aunque algo inesperado reviente, el mensaje a la UI es amigable."""
        importer = ProgramacionS18CuadrillaImporter()
        msg = importer._resultado_error(
            'Ocurrió un error inesperado al procesar el archivo. '
            'Revisa el formato e inténtalo de nuevo; si persiste, contacta a soporte.'
        )
        self.assertFalse(msg['exito'])
        self.assertIn('inesperado', msg['error'].lower())
        self.assertNotIn('duplicate key', msg['error'].lower())
        self.assertNotIn('psycopg2', msg['error'].lower())
        # las claves nuevas de resumen están presentes incluso en error.
        self.assertIn('cuadrillas_omitidas', msg)
        self.assertIn('cuadrillas_omitidas_count', msg)
