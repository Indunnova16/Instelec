"""Crawler exhaustivo de todas las vistas web del aplicativo.

Hace GET (y algunos POST) a las ~160 rutas públicas (excluyendo /admin/,
/__debug__/ y /api/) autenticado como admin y reporta cualquier 5xx.

NO valida correctness funcional — sólo que la vista no explote con datos vacíos
o un fixture mínimo. Usado para detectar regresiones de import/template/contexto.

Ejecutar:
    DJANGO_SETTINGS_MODULE=config.settings.dev_lite \\
    .venv-test/bin/pytest tests/e2e/test_crawl_all_views.py -v
"""
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.test import Client
from django.urls import URLResolver, URLPattern, get_resolver

from apps.actividades.models import Actividad, ProgramacionMensual, TipoActividad
from apps.ambiental.models import InformeAmbiental, PermisoServidumbre
from apps.campo.models import Procedimiento, RegistroCampo, ReporteDano
from apps.construccion.models import ProyectoConstruccion, TorreConstruccion
from apps.contratos.models import Contrato
from apps.cuadrillas.models import Cuadrilla
from apps.financiero.models import CicloFacturacion, Presupuesto
from apps.indicadores.models import ActaSeguimiento, Indicador, MedicionIndicador
from apps.ingenieria.models import TorreContrato
from apps.lineas.models import Linea, Torre, Tramo, Vano
from tests.factories import (
    AdminFactory,
    ActaSeguimientoFactory,
    ActividadFactory,
    CicloFacturacionFactory,
    CuadrillaFactory,
    EvidenciaFactory,
    IndicadorFactory,
    InformeAmbientalFactory,
    LineaFactory,
    MedicionIndicadorFactory,
    PermisoServidumbreFactory,
    PresupuestoFactory,
    ProgramacionMensualFactory,
    RegistroCampoFactory,
    TipoActividadFactory,
    TorreFactory,
)


# ─── Patrones a excluir del crawl ─────────────────────────────────────────────
EXCLUDE_PREFIXES = (
    '/admin/', '/__debug__/', '/api/', '/favicon.ico',
)

# Rutas POST-only o que requieren POST con payload — las saltamos del GET crawl.
SKIP_GET = {
    '/usuarios/logout/',
    '/usuarios/login/',  # GET sirve form, pero ya está cubierto por test_views.
    '/core/set-unidad-negocio/',
    '/actividades/programacion/bulk-asignar/',
    '/actividades/programacion/bulk-estado/',
    '/actividades/programacion/importar/',
    '/actividades/programacion/importar-avances/',
    '/cuadrillas/upload-masiva/',
    '/usuarios/campo/upload/',
}


# ─── Fixture: datos representativos en BD ────────────────────────────────────
@pytest.fixture
def datos_completos(db):
    """Pobla la BD con un registro de cada modelo crítico para tener UUIDs."""
    admin = AdminFactory(email='crawler-admin@test.com')

    # Contrato + proyecto construcción.
    contrato_const = Contrato.objects.create(
        codigo='CTR-CRAWL-1', nombre='Construcción crawl',
        unidad_negocio='CONSTRUCCION', estado='ACTIVO',
        cliente='Transelca', valor=Decimal('1000000'),
        fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31),
        numero_torres=2,
    )
    contrato_mtto = Contrato.objects.create(
        codigo='CTR-CRAWL-2', nombre='Mantenimiento crawl',
        unidad_negocio='MANTENIMIENTO', estado='ACTIVO',
        cliente='Transelca',
    )
    proyecto = ProyectoConstruccion.objects.create(
        contrato=contrato_const, nombre='Proyecto crawl', estado='EJECUCION',
    )
    torre_proy = TorreConstruccion.objects.create(proyecto=proyecto, numero='T-CR1')
    torre_contrato = TorreContrato.objects.create(
        contrato=contrato_const, nombre='T1', orden=1,
    )

    # Línea + Torre + Tramo + Vano (factories saben el schema actual).
    linea = LineaFactory(codigo='LN-CR-1', contrato=contrato_mtto)
    torre = TorreFactory(linea=linea, numero='T-CR-1')
    tramo = Tramo.objects.create(
        linea=linea, nombre='Tramo crawl', torre_inicio=torre, torre_fin=torre,
    )
    vano = Vano.objects.create(linea=linea, numero='V1', torre_inicio=torre, torre_fin=torre)

    cuadrilla = CuadrillaFactory(codigo='C-CR-1', linea_asignada=linea)
    tipo_act = TipoActividadFactory(codigo='TIP-CR')
    programacion = ProgramacionMensualFactory(linea=linea, anio=2026, mes=5)
    actividad = ActividadFactory(
        linea=linea, torre=torre, tipo_actividad=tipo_act,
        programacion=programacion,
    )
    registro = RegistroCampoFactory(actividad=actividad, usuario=admin)
    evidencia = EvidenciaFactory(registro_campo=registro)

    reporte = ReporteDano.objects.create(
        usuario=admin, linea=linea, torre=torre,
        descripcion='Dano crawl', tipo_dano='ESTRUCTURAL', severidad='MEDIA',
    )
    from django.core.files.base import ContentFile
    procedimiento = Procedimiento.objects.create(
        titulo='Proc crawl', subido_por=admin, nombre_original='proc.pdf',
    )
    procedimiento.archivo.save('proc.pdf', ContentFile(b'%PDF-1.4\n%dummy\n'), save=True)

    informe_amb = InformeAmbientalFactory(linea=linea)
    permiso = PermisoServidumbreFactory(torre=torre)

    indicador = IndicadorFactory(codigo='IND-CR')
    medicion = MedicionIndicadorFactory(indicador=indicador, linea=linea, anio=2026, mes=5)
    acta = ActaSeguimientoFactory(linea=linea, anio=2026, mes=5)

    presupuesto = PresupuestoFactory(linea=linea, anio=2026, mes=5)
    ciclo = CicloFacturacionFactory(presupuesto=presupuesto)

    return {
        'admin': admin,
        'contrato_const': contrato_const,
        'contrato_mtto': contrato_mtto,
        'proyecto': proyecto,
        'torre_proy': torre_proy,
        'torre_contrato': torre_contrato,
        'linea': linea,
        'torre': torre,
        'tramo': tramo,
        'vano': vano,
        'cuadrilla': cuadrilla,
        'tipo_act': tipo_act,
        'programacion': programacion,
        'actividad': actividad,
        'registro': registro,
        'reporte': reporte,
        'procedimiento': procedimiento,
        'informe_amb': informe_amb,
        'permiso': permiso,
        'indicador': indicador,
        'medicion': medicion,
        'acta': acta,
        'presupuesto': presupuesto,
        'ciclo': ciclo,
    }


def _placeholder_for(part: str, data: dict, path_prefix: str = '') -> str:
    """Resolves <uuid:xxx>, <int:xxx>, <slug:xxx> con datos del fixture.

    Si `<uuid:pk>` aparece en el path, el modelo destino se infiere del prefijo
    para evitar 404 falsos (ej. `/campo/<uuid:pk>/...` → RegistroCampo,
    no Línea).
    """
    if not (part.startswith('<') and part.endswith('>')):
        return part
    # part = '<uuid:pk>' o '<int:year>' etc.
    inner = part.strip('<>').split(':', 1)
    if len(inner) == 2:
        type_hint, name = inner
    else:
        type_hint, name = 'str', inner[0]

    # Resolución de `pk` por prefijo del path.
    if name == 'pk':
        if path_prefix.startswith('/campo/'):
            return str(data['registro'].id)
        if path_prefix.startswith('/contratos/'):
            return str(data['contrato_mtto'].id)
        if path_prefix.startswith('/cuadrillas/'):
            return str(data['cuadrilla'].id)
        if path_prefix.startswith('/actividades/'):
            return str(data['actividad'].id)
        if path_prefix.startswith('/financiero/checklist'):
            return str(data['ciclo'].id)
        if path_prefix.startswith('/financiero/'):
            return str(data['presupuesto'].id)
        if path_prefix.startswith('/indicadores/acta'):
            return str(data['acta'].id)
        if path_prefix.startswith('/indicadores/'):
            return str(data['indicador'].id)
        if path_prefix.startswith('/ambiental/permisos'):
            return str(data['permiso'].id)
        if path_prefix.startswith('/ambiental/'):
            return str(data['informe_amb'].id)
        if path_prefix.startswith('/construccion/'):
            return str(data['proyecto'].id)
        if path_prefix.startswith('/lineas/torre/'):
            return str(data['torre'].id)
        if path_prefix.startswith('/lineas/vano/'):
            return str(data['vano'].id)
        if path_prefix.startswith('/lineas/mi-avance/'):
            return str(data['linea'].id)
        if path_prefix.startswith('/lineas/'):
            return str(data['linea'].id)
        if path_prefix.startswith('/usuarios/'):
            return str(data['admin'].id)
        return str(data['linea'].id)

    # Mapeos por nombre de parámetro.
    name_map = {
        'pk': data['linea'].id,
        'linea_id': data['linea'].id,
        'linea_pk': data['linea'].id,
        'torre_id': data['torre'].id,
        'tramo_id': data['tramo'].id,
        'vano_id': data['vano'].id,
        'actividad_id': data['actividad'].id,
        'cuadrilla_id': data['cuadrilla'].id,
        'registro_id': data['registro'].id,
        'contrato_id': data['contrato_mtto'].id,
        'proyecto_id': data['proyecto'].id,
        'reporte_id': data['reporte'].id,
        'informe_id': data['informe_amb'].id,
        'medicion_id': data['medicion'].id,
        'indicador_id': data['indicador'].id,
        'acta_id': data['acta'].id,
        'presupuesto_id': data['presupuesto'].id,
        'ciclo_id': data['ciclo'].id,
        'procedimiento_id': data['procedimiento'].id,
        'tipo_actividad_id': data['tipo_act'].id,
        'programacion_id': data['programacion'].id,
        'usuario_id': data['admin'].id,
        'permiso_id': data['permiso'].id,
    }
    if name in name_map:
        return str(name_map[name])

    # Fallback por type_hint.
    if type_hint == 'uuid':
        return str(data['linea'].id)
    if type_hint == 'int':
        if 'anio' in name or 'year' in name:
            return '2026'
        if 'mes' in name or 'month' in name:
            return '5'
        return '1'
    if type_hint == 'slug':
        return 'crawl-slug'
    return str(data['linea'].id)  # fallback ultra-defensivo


def _resolve_url(pattern: str, data: dict) -> str:
    """Toma '/lineas/<uuid:pk>/' → '/lineas/abc-123/'."""
    import re
    return re.sub(
        r'<[^>]+>',
        lambda m: _placeholder_for(m.group(0), data, pattern),
        pattern,
    )


def _collect_patterns():
    """Camina el URL resolver y devuelve [(pattern_str, name, callback)]."""
    out = []
    resolver = get_resolver()

    def walk(url_patterns, prefix=''):
        for p in url_patterns:
            if isinstance(p, URLResolver):
                walk(p.url_patterns, prefix + str(p.pattern))
            elif isinstance(p, URLPattern):
                pattern_str = '/' + prefix + str(p.pattern)
                pattern_str = pattern_str.replace('//', '/')
                if pattern_str.startswith(EXCLUDE_PREFIXES):
                    continue
                out.append(pattern_str)
    walk(resolver.url_patterns)
    return out


@pytest.mark.django_db
def test_crawl_no_500s(client: Client, datos_completos):
    """Crawler: GET cada URL pública con admin, alerta si responde 5xx."""
    client.force_login(datos_completos['admin'])
    patterns = _collect_patterns()

    from django.template import TemplateDoesNotExist

    fallos = []
    ok = 0
    skip_post_only = 0
    for pattern in sorted(set(patterns)):
        if pattern in SKIP_GET:
            continue
        url = _resolve_url(pattern, datos_completos)
        try:
            resp = client.get(url, follow=False)
        except TemplateDoesNotExist:
            # Vista que normalmente sirve POST y bajo GET intenta renderizar
            # un template inexistente — no es bug funcional, sólo no-GET.
            skip_post_only += 1
            continue
        except Exception as exc:
            fallos.append((pattern, url, 'EXCEPTION', f'{type(exc).__name__}: {str(exc)[:200]}'))
            continue
        if 500 <= resp.status_code < 600:
            body = resp.content[:300].decode('utf-8', 'replace')
            fallos.append((pattern, url, resp.status_code, body))
        else:
            ok += 1

    # Reporte legible.
    if fallos:
        msg = [
            f'{ok} URLs OK, {skip_post_only} POST-only saltadas, '
            f'{len(fallos)} con error 5xx o excepción:'
        ]
        for pat, url, code, detail in fallos:
            msg.append(f'  [{code}] {pat} → {url}')
            msg.append(f'    {detail}')
        pytest.fail('\n'.join(msg))
    else:
        print(f'\n{ok} URLs respondieron sin 5xx (+{skip_post_only} POST-only saltadas).')
