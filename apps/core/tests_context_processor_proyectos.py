"""Regression tests (#144) — el selector "Ir a proyecto…" debe incluir
proyectos FINALIZADO.

Bug: ``apps.core.context_processors.modulo_context`` filtraba
``ProyectoConstruccion`` por ``estado__in=['PLANIFICACION','EJECUCION','CIERRE']``,
omitiendo ``'FINALIZADO'``. Un proyecto finalizado nunca aparecía en el
selector del sidebar y su dashboard quedaba inalcanzable por esa vía.

Fix: agregar ``'FINALIZADO'`` al whitelist. Estos tests reproducen el bug
(un proyecto FINALIZADO debe estar en ``proyectos_construccion``) y verifican
que los demás estados siguen incluidos.

Nombre de archivo ``tests_*`` por paridad con los demás tests del repo; se
ejecuta pasando la ruta a pytest.
"""
import pytest
from django.test import RequestFactory

from apps.core.context_processors import modulo_context


def _make_proyecto(estado, codigo):
    """Crea un Contrato CONSTRUCCION + su ProyectoConstruccion en el estado dado."""
    from apps.construccion.models import ProyectoConstruccion
    from apps.contratos.models import Contrato

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo=codigo,
        nombre=f'Contrato {codigo}',
        cliente='Cliente test #144',
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre=f'Proyecto {estado}',
        estado=estado,
    )


@pytest.fixture
def request_obj():
    """Request con sesión vacía (modulo_context -> get_unidad_negocio la lee)."""
    from importlib import import_module
    from django.conf import settings

    request = RequestFactory().get('/construccion/')
    engine = import_module(settings.SESSION_ENGINE)
    request.session = engine.SessionStore()
    return request


@pytest.mark.django_db
def test_proyecto_finalizado_aparece_en_selector(request_obj):
    """REGRESIÓN #144: un proyecto FINALIZADO debe estar en proyectos_construccion."""
    proyecto = _make_proyecto('FINALIZADO', 'C144-FIN-001')

    ctx = modulo_context(request_obj)
    ids = list(ctx['proyectos_construccion'].values_list('id', flat=True))

    assert proyecto.id in ids, (
        'Un proyecto en estado FINALIZADO debe aparecer en el selector '
        '"Ir a proyecto…" (regresión del filtro estado__in que lo omitía)'
    )


@pytest.mark.django_db
def test_todos_los_estados_incluidos(request_obj):
    """Los 4 estados del modelo (incluido FINALIZADO) deben aparecer."""
    proyectos = {
        estado: _make_proyecto(estado, f'C144-{estado[:3]}')
        for estado in ('PLANIFICACION', 'EJECUCION', 'CIERRE', 'FINALIZADO')
    }

    ctx = modulo_context(request_obj)
    ids = set(ctx['proyectos_construccion'].values_list('id', flat=True))

    for estado, proyecto in proyectos.items():
        assert proyecto.id in ids, f'Proyecto {estado} ausente del selector'


@pytest.mark.django_db
def test_whitelist_cubre_choices_del_modelo(request_obj):
    """El queryset debe cubrir todos los choices de estado declarados en el modelo.

    Guarda contra una futura regresión donde se agregue un nuevo estado al
    modelo y se olvide actualizar el whitelist del context processor.
    """
    from apps.construccion.models import ProyectoConstruccion

    estados_modelo = [c[0] for c in ProyectoConstruccion._meta.get_field('estado').choices]
    proyectos_por_estado = {
        estado: _make_proyecto(estado, f'C144-CHK-{i}')
        for i, estado in enumerate(estados_modelo)
    }

    ctx = modulo_context(request_obj)
    ids = set(ctx['proyectos_construccion'].values_list('id', flat=True))

    faltantes = [
        estado for estado, p in proyectos_por_estado.items() if p.id not in ids
    ]
    assert not faltantes, (
        f'El selector omite proyectos en estado(s) {faltantes}; el whitelist '
        'estado__in del context processor debe cubrir todos los choices del modelo'
    )
