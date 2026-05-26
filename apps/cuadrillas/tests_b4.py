"""
Tests B4 — CuadrillaImporter (carga masiva con formato Aviso SAP).

Issue: Indunnova16/Instelec#105

NOTA: pytest discovery está limitado a ``tests/`` por pyproject.toml; ejecutar
estos tests vía path explícito:

    pytest apps/cuadrillas/tests_b4.py -v
"""
from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import Workbook

from apps.cuadrillas.importers import CuadrillaImporter
from apps.cuadrillas.models import Cuadrilla, CuadrillaMiembro, Vehiculo
from apps.lineas.models import Linea
from apps.usuarios.models import Usuario


HEADERS = [
    '#', 'CUADRILLA', 'LÍNEA', 'SUPERVISOR', 'PERSONAL',
    'CEDULA', 'CARGO', 'CELULAR', 'PLACA', 'ESTADO', 'OBSERVACIONES',
]


def _build_excel(rows):
    """Construye un Excel in-memory con HEADERS + las filas dadas."""
    wb = Workbook()
    ws = wb.active
    ws.append(HEADERS)
    for r in rows:
        ws.append(r)
    out = BytesIO()
    wb.save(out)
    out.seek(0)
    return out


def _crear_linea(nombre='L1', codigo='LINEA-001'):
    return Linea.objects.create(
        codigo=codigo,
        nombre=nombre,
        cliente='TRANSELCA',
    )


def _crear_cuadrilla_b3_safe(**kwargs):
    """Crea Cuadrilla manejando schema con B3 audit fields NOT NULL.

    Pre-merge B3, el modelo Python no expone motivo_desactivacion/etc.,
    pero el schema de BD sí los tiene como NOT NULL. Insertamos via raw
    SQL para esquivar la restricción.
    """
    from django.db import connection
    import uuid
    from django.utils import timezone

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'cuadrillas'"
        )
        cols = {row[0] for row in cursor.fetchall()}

    if 'motivo_desactivacion' not in cols:
        return Cuadrilla.objects.create(**kwargs)

    new_id = uuid.uuid4()
    now = timezone.now()
    linea = kwargs.get('linea_asignada')
    vehiculo = kwargs.get('vehiculo')
    supervisor = kwargs.get('supervisor')
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO cuadrillas
                (id, created_at, updated_at, codigo, nombre, activa,
                 observaciones, linea_asignada_id, supervisor_id,
                 vehiculo_id, fecha, motivo_desactivacion,
                 fecha_desactivacion, desactivado_por_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                str(new_id), now, now,
                kwargs['codigo'], kwargs.get('nombre', kwargs['codigo']),
                kwargs.get('activa', True),
                kwargs.get('observaciones', ''),
                linea.id if linea else None,
                supervisor.id if supervisor else None,
                vehiculo.id if vehiculo else None,
                None, '', None, None,
            ],
        )
    return Cuadrilla.objects.get(id=new_id)


def _crear_usuario(documento, nombre='Carlos González'):
    partes = nombre.split(maxsplit=1)
    return Usuario.objects.create(
        email=f'{documento}@test.local',
        documento=documento,
        first_name=partes[0],
        last_name=partes[1] if len(partes) > 1 else '',
        rol='liniero',
        is_active=True,
    )


@pytest.mark.django_db
class TestB4UploadExcelCuadrillas:
    """Tests E2E del importer B4 (matching tests_e2e del BLUEPRINT)."""

    def test_b4_upload_excel_cuadrillas_crea_2_cuadrillas(self):
        """Happy path — Excel con 2 cuadrillas + 5 miembros + 1 vehículo.

        - Cuadrilla 1: 3 miembros, vehículo JAK-520.
        - Cuadrilla 2: 2 miembros, sin vehículo.
        Resultado esperado: 2 cuadrillas creadas, 5 miembros agregados, 0
        errores fatales.
        """
        # Setup BD.
        linea1 = _crear_linea(nombre='L1', codigo='L1-001')
        linea2 = _crear_linea(nombre='L2', codigo='L2-002')
        Vehiculo.objects.create(placa='JAK-520', activo=True)
        _crear_usuario('1055688', 'Carlos González')
        _crear_usuario('1098765', 'María Rodríguez')
        _crear_usuario('1076543', 'Pedro Sánchez')
        _crear_usuario('1033333', 'Luis Martínez')
        _crear_usuario('1044444', 'Ana Torres')

        # Excel: 2 cuadrillas con 3 + 2 miembros.
        rows = [
            [1, 'CUA-001', 'L1', 'Juan', 'Carlos González', '1055688', 'Liniero', '3161234567', 'JAK-520', 'Activa', 'Sector norte'],
            ['', '', '', '', 'María Rodríguez', '1098765', 'Ayudante', '3167654321', '', '', ''],
            ['', '', '', '', 'Pedro Sánchez', '1076543', 'Liniero', '3169876543', '', '', ''],
            [2, 'CUA-002', 'L2', 'Carlos', 'Luis Martínez', '1033333', 'Supervisor', '3197654321', '', 'Activa', ''],
            ['', '', '', '', 'Ana Torres', '1044444', 'Ayudante', '3198765432', '', '', ''],
        ]
        excel = _build_excel(rows)

        importer = CuadrillaImporter()
        resultado = importer.importar(excel)

        assert resultado['exito'] is True, f'Resultado: {resultado}'
        assert resultado['cuadrillas_creadas'] == 2
        assert resultado['cuadrillas_actualizadas'] == 0
        assert resultado['miembros_agregados'] == 5
        assert resultado['errores'] == []

        # Verificar BD.
        cua1 = Cuadrilla.objects.get(codigo='CUA-001')
        assert cua1.linea_asignada == linea1
        assert cua1.vehiculo is not None
        assert cua1.vehiculo.placa == 'JAK-520'
        assert cua1.activa is True
        assert cua1.observaciones == 'Sector norte'
        assert CuadrillaMiembro.objects.filter(cuadrilla=cua1, activo=True).count() == 3

        cua2 = Cuadrilla.objects.get(codigo='CUA-002')
        assert cua2.linea_asignada == linea2
        assert cua2.vehiculo is None  # sin placa en Excel
        assert CuadrillaMiembro.objects.filter(cuadrilla=cua2, activo=True).count() == 2

        # Verificar mapeo de rol_cuadrilla.
        miembro_carlos = CuadrillaMiembro.objects.get(usuario__documento='1055688')
        assert miembro_carlos.rol_cuadrilla == 'LINIERO_I'
        miembro_luis = CuadrillaMiembro.objects.get(usuario__documento='1033333')
        assert miembro_luis.rol_cuadrilla == 'SUPERVISOR'

    def test_b4_upload_excel_cuadrilla_existente_actualiza(self):
        """Edge — cuadrilla ya existe; con ``actualizar_existentes=True``
        se actualiza la línea, supervisor y vehículo; los miembros se
        agregan a la cuadrilla existente.
        """
        linea_vieja = _crear_linea(nombre='LX', codigo='LX-OLD')
        linea_nueva = _crear_linea(nombre='L1', codigo='L1-NEW')
        Vehiculo.objects.create(placa='OLD-111', activo=True)
        Vehiculo.objects.create(placa='NEW-222', activo=True)
        _crear_usuario('2055688', 'Diego Ramírez')

        # Cuadrilla pre-existente con línea X y vehículo OLD-111.
        cua_existente = _crear_cuadrilla_b3_safe(
            codigo='CUA-100',
            nombre='Cuadrilla original',
            linea_asignada=linea_vieja,
            vehiculo=Vehiculo.objects.get(placa='OLD-111'),
            activa=True,
            observaciones='Original',
        )
        assert cua_existente.linea_asignada == linea_vieja

        rows = [
            [1, 'CUA-100', 'L1', '', 'Diego Ramírez', '2055688', 'Liniero', '3160000000', 'NEW-222', 'Activa', 'Actualizada'],
        ]
        excel = _build_excel(rows)

        importer = CuadrillaImporter()
        resultado = importer.importar(excel, {'actualizar_existentes': True})

        assert resultado['exito'] is True, f'Resultado: {resultado}'
        assert resultado['cuadrillas_creadas'] == 0
        assert resultado['cuadrillas_actualizadas'] == 1
        assert resultado['miembros_agregados'] == 1

        cua_existente.refresh_from_db()
        assert cua_existente.linea_asignada == linea_nueva
        assert cua_existente.vehiculo.placa == 'NEW-222'
        assert cua_existente.observaciones == 'Actualizada'
        assert CuadrillaMiembro.objects.filter(cuadrilla=cua_existente, activo=True).count() == 1

    def test_b4_cuadrilla_existente_sin_flag_no_se_actualiza(self):
        """Edge — sin ``actualizar_existentes`` la cuadrilla se preserva."""
        linea_vieja = _crear_linea(nombre='LX', codigo='LX-OLD-2')
        _crear_linea(nombre='L1', codigo='L1-NEW-2')
        _crear_usuario('3055688', 'Diego Ramírez')

        cua_existente = _crear_cuadrilla_b3_safe(
            codigo='CUA-200',
            nombre='Cuadrilla original',
            linea_asignada=linea_vieja,
            observaciones='Original',
        )

        rows = [
            [1, 'CUA-200', 'L1', '', 'Diego Ramírez', '3055688', 'Liniero', '', '', 'Activa', 'Cambiada'],
        ]
        excel = _build_excel(rows)

        importer = CuadrillaImporter()
        resultado = importer.importar(excel, {'actualizar_existentes': False})

        assert resultado['exito'] is True
        assert resultado['cuadrillas_creadas'] == 0
        assert resultado['cuadrillas_actualizadas'] == 0
        # Miembro sí se agrega aunque la cuadrilla no se actualice.
        assert resultado['miembros_agregados'] == 1

        cua_existente.refresh_from_db()
        assert cua_existente.linea_asignada == linea_vieja  # NO actualizada
        assert cua_existente.observaciones == 'Original'

    def test_b4_cedula_inexistente_warning_no_fatal(self):
        """Edge — cédula del miembro no existe en Usuario → warning, no
        error fatal. La cuadrilla SÍ se crea.
        """
        _crear_linea(nombre='L1', codigo='L1-WARN')
        _crear_usuario('4055688', 'Carlos Real')  # solo este existe

        rows = [
            [1, 'CUA-300', 'L1', '', 'Carlos Real', '4055688', 'Liniero', '', '', 'Activa', ''],
            ['', '', '', '', 'Fantasma', '9999999', 'Ayudante', '', '', '', ''],
        ]
        excel = _build_excel(rows)

        importer = CuadrillaImporter()
        resultado = importer.importar(excel)

        assert resultado['exito'] is True
        assert resultado['cuadrillas_creadas'] == 1
        assert resultado['miembros_agregados'] == 1  # solo Carlos
        assert len(resultado['advertencias']) >= 1
        assert any('9999999' in adv for adv in resultado['advertencias'])
        # Cuadrilla creada correctamente con 1 miembro.
        cua = Cuadrilla.objects.get(codigo='CUA-300')
        assert CuadrillaMiembro.objects.filter(cuadrilla=cua, activo=True).count() == 1

    def test_b4_linea_inexistente_es_error_fatal(self):
        """Edge — línea no existe → error fatal y rollback completo.

        Si la línea de la fila 1 no existe, NINGUNA cuadrilla del Excel
        debe persistir (transacción atómica).
        """
        _crear_linea(nombre='L_OK', codigo='L1-OK')
        _crear_usuario('5055688', 'X Y')

        rows = [
            [1, 'CUA-400', 'LINEA_QUE_NO_EXISTE', '', 'X Y', '5055688', 'Liniero', '', '', 'Activa', ''],
            [2, 'CUA-401', 'L_OK', '', 'X Y', '5055688', 'Liniero', '', '', 'Activa', ''],
        ]
        excel = _build_excel(rows)

        importer = CuadrillaImporter()
        resultado = importer.importar(excel)

        assert resultado['exito'] is False
        assert resultado['cuadrillas_creadas'] == 0
        assert resultado['cuadrillas_actualizadas'] == 0
        assert len(resultado['errores']) >= 1
        # Rollback: ninguna cuadrilla debe existir.
        assert Cuadrilla.objects.filter(codigo__in=['CUA-400', 'CUA-401']).count() == 0

    def test_b4_archivo_invalido_devuelve_error(self):
        """Edge — archivo no es Excel válido."""
        importer = CuadrillaImporter()
        bad = BytesIO(b'esto no es excel')
        resultado = importer.importar(bad)
        assert resultado['exito'] is False
        assert 'error' in resultado
        assert resultado['cuadrillas_creadas'] == 0

    def test_b4_archivo_vacio_devuelve_error(self):
        """Edge — archivo sin filas de datos (solo encabezado)."""
        excel = _build_excel([])
        importer = CuadrillaImporter()
        resultado = importer.importar(excel)
        assert resultado['exito'] is False
        assert resultado['cuadrillas_creadas'] == 0

    def test_b4_archivo_sin_columna_cuadrilla_devuelve_error(self):
        """Edge — encabezado sin columna CUADRILLA → error de detección."""
        wb = Workbook()
        ws = wb.active
        ws.append(['#', 'LÍNEA', 'PERSONAL', 'CEDULA'])
        ws.append([1, 'L1', 'Juan', '111'])
        out = BytesIO()
        wb.save(out)
        out.seek(0)

        importer = CuadrillaImporter()
        resultado = importer.importar(out)
        assert resultado['exito'] is False
        assert 'CUADRILLA' in resultado.get('error', '').upper() or 'cuadrilla' in resultado.get('error', '').lower()
