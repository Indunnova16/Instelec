"""Fix round-2 post-validador-cierre (PARCIAL) -- Instelec#247.

Cierra los 4 gaps reales encontrados por el validador adversarial contra el
archivo real del cliente (TRANSELCA.2025.20261.xlsx):

  1. BD Ppto nunca cruzaba con el archivo real porque exigía que la columna
     'Proyecto' del Excel coincidiera EXACTO con Contrato.nombre.
  2. El importador de Tabla Maestra no aceptaba el esquema de columnas
     documentado al cliente (Concepto Projects/Código/Cuenta Contable/
     Tipo/Descripción).
  3. El módulo entero era inalcanzable desde el menú (sin link en sidebar).
  4. El frontend no ocultaba controles (import Tabla Maestra, Restaurar) a
     roles ver-only, aunque el backend ya los rechazaba con 403.
"""
import io
from datetime import datetime

import pytest
from django.core.cache import cache
from openpyxl import Workbook

from apps.contratos.models import Contrato
from apps.core.models_roles import Role, RoleModuloPermiso
from apps.financiero.importers_finv2_carga import (
    previsualizar_tabla_maestra,
    procesar_carga_financiera,
)
from apps.financiero.models_finv2_carga import LineaCargaFinanciera

# ---------------------------------------------------------------------------
# Gap 1 -- BD Ppto debe cruzar con el archivo real (proyecto 'Transelca'
# textual en el Excel, contra un Contrato con OTRO nombre en el sistema).
# ---------------------------------------------------------------------------

def _libro_transelca_real(*, proyecto_excel='Transelca'):
    """Extracto fiel de las 2 hojas del archivo real del cliente: BD Real y
    BD Ppto usan el mismo texto de 'Proyecto' ('Transelca'), pero el
    Contrato real del sistema NO se llama así (ver fixture `proyecto`)."""
    libro = Workbook()
    real = libro.active
    real.title = 'BD Real'
    real.append(['Auxiliar', 'Desc. auxiliar', 'Neto', 'Fecha', 'Docto.', 'Periodo', 'Cuenta Equiv', 'CdeC equiv'])
    real.append([1, 'Compra cable', 100, datetime(2026, 3, 31), 'DOC-1', 202603, 'Materiales', 'TRANSELCA'])
    ppto = libro.create_sheet('BD Ppto')
    ppto.append(['Tipo', 'Proyecto', 'Rubro', 'Clasificacion', 'Valor', 'mes', 'año'])
    ppto.append(['Presupuesto', proyecto_excel, 'Materiales', 'Costos', 120, 3, 2026])
    homologacion = libro.create_sheet('Homologacion')
    homologacion.append(['tipo', 'Grupo', 'Concepto', 'Rubro'])
    homologacion.append(['REAL', 'Materiales', 'Compra cable', 'TRANSELCA'])
    salida = io.BytesIO()
    libro.save(salida)
    salida.seek(0)
    salida.name = 'TRANSELCA.2025.20261.xlsx'
    return salida


@pytest.fixture
def proyecto_real(db):
    """Contrato real de prod: NO se llama 'Transelca' (mismo caso que
    'QA test #49 -- Puerta de Oro' / 'Cambio de OPGW L.T 500 kV')."""
    return Contrato.objects.create(
        codigo='OPGW-500', nombre='Cambio de OPGW L.T 500 kV', unidad_negocio='MANTENIMIENTO',
    )


@pytest.mark.django_db
def test_247_r2_gap1_bd_ppto_cruza_con_archivo_real_aunque_nombre_no_coincida(proyecto_real):
    """Antes: 0 líneas PRESUPUESTO porque 'Transelca' != 'Cambio de OPGW L.T 500 kV'."""
    resultado = procesar_carga_financiera(
        _libro_transelca_real(), proyecto=proyecto_real, anio=2026, mes=3, usuario=None,
    )
    assert resultado.exito, resultado.error
    lineas = LineaCargaFinanciera.objects.filter(carga=resultado.carga)
    assert lineas.filter(tipo=LineaCargaFinanciera.Tipo.PRESUPUESTO).count() == 1
    presupuesto = lineas.get(tipo=LineaCargaFinanciera.Tipo.PRESUPUESTO)
    assert presupuesto.valor == 120
    # Trazabilidad: el texto original del Excel se conserva, sólo deja de
    # usarse como filtro de rechazo.
    assert presupuesto.referencia == 'Transelca'
    assert presupuesto.datos_origen['proyecto'] == 'Transelca'


@pytest.mark.django_db
def test_247_r2_gap1_bd_ppto_persiste_para_cualquier_texto_de_proyecto_en_excel(proyecto_real):
    """La app confía en el Contrato elegido en el formulario -no en texto
    libre-, igual que _lineas_reales."""
    resultado = procesar_carga_financiera(
        _libro_transelca_real(proyecto_excel='Cualquier Otro Texto'),
        proyecto=proyecto_real, anio=2026, mes=3, usuario=None,
    )
    assert resultado.exito, resultado.error
    lineas = LineaCargaFinanciera.objects.filter(carga=resultado.carga)
    assert lineas.filter(tipo=LineaCargaFinanciera.Tipo.PRESUPUESTO).count() == 1


# ---------------------------------------------------------------------------
# Gap 2 -- Tabla Maestra debe aceptar el formato documentado al cliente.
# ---------------------------------------------------------------------------

def _tabla_maestra_formato_cliente(*, con_tipo_ingresos=False):
    """Formato EXACTO documentado al cliente en el issue (2026-09-12):
      INGRESOS (4 cols, SIN Tipo): Concepto Projects | Código | Cuenta Contable | Descripción
      GASTOS   (5 cols, CON Tipo): Concepto Projects | Código | Cuenta Contable | Tipo | Descripción
    """
    libro = Workbook()
    ingresos = libro.active
    ingresos.title = 'INGRESOS'
    if con_tipo_ingresos:
        ingresos.append(['Concepto Projects', 'Código', 'Cuenta Contable', 'Tipo', 'Descripción'])
        ingresos.append(['Venta de energía', '5510', '5510', 'Fijo', 'Ingresos operacionales'])
    else:
        ingresos.append(['Concepto Projects', 'Código', 'Cuenta Contable', 'Descripción'])
        ingresos.append(['Venta de energía', '5510', '5510', 'Ingresos operacionales'])
    ingresos.append(['Otros ingresos', '6100', '6100', 'Ingresos varios'] if not con_tipo_ingresos
                     else ['Otros ingresos', '6100', '6100', 'Variable', 'Ingresos varios'])
    gastos = libro.create_sheet('GASTOS')
    gastos.append(['Concepto Projects', 'Código', 'Cuenta Contable', 'Tipo', 'Descripción'])
    gastos.append(['Mano de obra', '5110', '5110', 'Fijo', 'Nómina cuadrillas'])
    gastos.append(['Materiales', '5111', '5111', 'Variable', 'Insumos'])
    salida = io.BytesIO()
    libro.save(salida)
    salida.seek(0)
    salida.name = 'TABLA_MAESTRA_HOMOLOGACION.xlsx'
    return salida


@pytest.mark.django_db
def test_247_r2_gap2_tabla_maestra_acepta_formato_documentado_al_cliente_sin_tipo_en_ingresos():
    """Antes: 100% de las filas de INGRESOS fallaban con 'faltan codigo
    contable, concepto, grupo, tipo' porque 'Grupo' no existe y 'Tipo' no
    existe en INGRESOS."""
    preview = previsualizar_tabla_maestra(_tabla_maestra_formato_cliente(con_tipo_ingresos=False))
    assert preview['errores'] == [], preview['errores']
    assert len(preview['filas']) == 4
    ingresos = [f for f in preview['filas'] if f['hoja'] == 'INGRESOS']
    gastos = [f for f in preview['filas'] if f['hoja'] == 'GASTOS']
    assert len(ingresos) == 2 and len(gastos) == 2
    # 'Concepto Projects' -> concepto ; 'Cuenta Contable'/'Código' -> codigo_contable
    assert {f['concepto'] for f in ingresos} == {'Venta de energía', 'Otros ingresos'}
    assert {f['codigo_contable'] for f in ingresos} == {'5510', '6100'}
    # Tipo es opcional en INGRESOS: no se exige y no se inventa un default.
    assert all(f['tipo'] == '' for f in ingresos)
    # 'Grupo' no viene en el Excel real -> se deriva del nombre de la hoja.
    assert all(f['grupo'] == 'INGRESOS' for f in ingresos)
    assert all(f['grupo'] == 'GASTOS' for f in gastos)
    assert {f['tipo'] for f in gastos} == {'Fijo', 'Variable'}


@pytest.mark.django_db
def test_247_r2_gap2_tabla_maestra_acepta_formato_documentado_con_tipo_opcional_en_ingresos():
    preview = previsualizar_tabla_maestra(_tabla_maestra_formato_cliente(con_tipo_ingresos=True))
    assert preview['errores'] == [], preview['errores']
    assert len(preview['filas']) == 4


@pytest.mark.django_db
def test_247_r2_gap2_tabla_maestra_exige_tipo_en_gastos():
    """'Tipo' sigue siendo OBLIGATORIO en GASTOS."""
    libro = Workbook()
    ingresos = libro.active
    ingresos.title = 'INGRESOS'
    ingresos.append(['Concepto Projects', 'Código', 'Cuenta Contable', 'Descripción'])
    ingresos.append(['Venta de energía', '5510', '5510', 'Ingresos'])
    gastos = libro.create_sheet('GASTOS')
    gastos.append(['Concepto Projects', 'Código', 'Cuenta Contable', 'Descripción'])
    gastos.append(['Mano de obra', '5110', '5110', 'Nómina'])
    salida = io.BytesIO()
    libro.save(salida)
    salida.seek(0)
    salida.name = 'sin_tipo_gastos.xlsx'
    preview = previsualizar_tabla_maestra(salida)
    assert any('GASTOS' in e and 'Tipo' in e for e in preview['errores'])
    assert len(preview['filas']) == 1  # sólo INGRESOS, válido


@pytest.mark.django_db
def test_247_r2_gap2_tabla_maestra_rango_codigo_5000_6999_sigue_vigente():
    """El check de rango 5XXX-6XXX YA era correcto -no se modifica-."""
    libro = Workbook()
    ingresos = libro.active
    ingresos.title = 'INGRESOS'
    ingresos.append(['Concepto Projects', 'Código', 'Cuenta Contable', 'Descripción'])
    ingresos.append(['Fuera de rango', '7000', '7000', 'Inválido'])
    gastos = libro.create_sheet('GASTOS')
    gastos.append(['Concepto Projects', 'Código', 'Cuenta Contable', 'Tipo', 'Descripción'])
    gastos.append(['Mano de obra', '5110', '5110', 'Fijo', 'Nómina'])
    salida = io.BytesIO()
    libro.save(salida)
    salida.seek(0)
    salida.name = 'fuera_de_rango.xlsx'
    preview = previsualizar_tabla_maestra(salida)
    assert any('5XXX y 6XXX' in e for e in preview['errores'])
    assert len(preview['filas']) == 1


@pytest.mark.django_db
def test_247_r2_gap2_codigo_y_cuenta_contable_son_columnas_distintas_no_sinonimos():
    """Reproduce el hallazgo del validador-cierre round-2: 'Código' (numérico)
    y 'Cuenta Contable' (texto descriptivo) son DOS columnas reales distintas
    del formato documentado al cliente. Con valores DIFERENTES entre sí (a
    diferencia de los tests anteriores, que por accidente repetían el mismo
    valor en ambas columnas y no habrían atrapado el bug), 'codigo_contable'
    debe resolver siempre desde 'Código' -nunca desde 'Cuenta Contable'-."""
    libro = Workbook()
    ingresos = libro.active
    ingresos.title = 'INGRESOS'
    ingresos.append(['Concepto Projects', 'Código', 'Cuenta Contable', 'Descripción'])
    ingresos.append(['Venta de energía', '5510', 'Ingresos Servicios Preliminares', 'Servicios previos a obra'])
    gastos = libro.create_sheet('GASTOS')
    gastos.append(['Concepto Projects', 'Código', 'Cuenta Contable', 'Tipo', 'Descripción'])
    gastos.append(['Nómina', '5110', 'Gastos de Personal', 'Fijo', 'Salarios operarios'])
    salida = io.BytesIO()
    libro.save(salida)
    salida.seek(0)
    salida.name = 'codigo_vs_cuenta_contable.xlsx'
    preview = previsualizar_tabla_maestra(salida)
    assert preview['errores'] == [], preview['errores']
    assert len(preview['filas']) == 2
    ingreso = next(f for f in preview['filas'] if f['hoja'] == 'INGRESOS')
    gasto = next(f for f in preview['filas'] if f['hoja'] == 'GASTOS')
    assert ingreso['codigo_contable'] == '5510'
    assert ingreso['rubro'] == 'Ingresos Servicios Preliminares'
    assert gasto['codigo_contable'] == '5110'
    assert gasto['rubro'] == 'Gastos de Personal'


# ---------------------------------------------------------------------------
# Gap 3 -- navegabilidad: el módulo debe ser alcanzable desde el sidebar.
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_247_r2_gap3_link_carga_financiera_visible_en_sidebar_para_usuario_con_acceso(client, admin_user):
    client.force_login(admin_user)
    respuesta = client.get('/financiero/')
    html = respuesta.content.decode()
    assert '/financiero/carga-financiera/' in html
    assert 'Homologación Projects' in html


@pytest.mark.django_db
def test_247_r2_gap3_link_carga_financiera_ausente_sin_acceso_al_submodulo(client, django_user_model):
    role = Role.objects.create(codigo='qa_sin_homolog_247', nombre='QA sin homologación', nivel='operario')
    RoleModuloPermiso.objects.create(role=role, modulo='MANTENIMIENTO', submodulo='FIN_DASHBOARD', nivel_acceso='ver')
    user = django_user_model.objects.create_user(email='sin-homolog-247@example.test', password='x', rol=role.codigo)
    cache.clear()
    client.force_login(user)
    respuesta = client.get('/financiero/')
    assert '/financiero/carga-financiera/' not in respuesta.content.decode()


# ---------------------------------------------------------------------------
# Gap 4 -- RBAC UI: controles de escritura ocultos para roles ver-only.
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_247_r2_gap4_rbac_ui_oculta_controles_de_escritura_para_ver_only(client, django_user_model):
    role = Role.objects.create(codigo='qa_ver_only_247', nombre='QA ver-only', nivel='operario')
    RoleModuloPermiso.objects.create(role=role, modulo='MANTENIMIENTO', submodulo='FIN_HOMOLOGACION', nivel_acceso='ver')
    user = django_user_model.objects.create_user(email='ver-only-247@example.test', password='x', rol=role.codigo)
    cache.clear()
    client.force_login(user)
    respuesta = client.get('/financiero/carga-financiera/')
    assert respuesta.status_code == 200
    html = respuesta.content.decode()
    assert 'id="importar-tabla-maestra-form"' not in html
    assert '>Restaurar<' not in html
    # Los controles que YA estaban correctamente gateados siguen ocultos.
    assert 'name="accion" value="homologar"' not in html
    assert '>Archivar<' not in html


@pytest.mark.django_db
def test_247_r2_gap4_rbac_ui_muestra_controles_de_escritura_para_ver_editar(client, admin_user):
    client.force_login(admin_user)
    respuesta = client.get('/financiero/carga-financiera/')
    html = respuesta.content.decode()
    assert 'id="importar-tabla-maestra-form"' in html
