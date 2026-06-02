"""
Tests #100 — Renombre/normalización de torres a T-{n} + orden numérico.

Cubre:
- Torre.normalizar_numero / numero_display (torres → T-{n}, postes → P-{n},
  formatos no estándar preservados).
- Orden numérico ascendente (E-1, E-2, ..., E-10) vía ordenar_torres_num.
- Dato legacy preservado.
- TorreConstruccion.numero_display reusa la misma lógica.

Ejecutar:  pytest apps/lineas/tests/test_100_numero.py -v
"""
import pytest

from apps.lineas.models import Linea, Torre
from apps.lineas.views import ordenar_torres_num


CASOS_NORM = [
    ('E-1', 'T-1'),
    ('E-10', 'T-10'),
    ('1', 'T-1'),
    ('T15', 'T-15'),
    ('T-1', 'T-1'),
    ('P001', 'P-1'),
    ('P-3', 'P-3'),
    ('Pórtico Santamarta', 'Pórtico Santamarta'),
    ('T-AUTO', 'T-AUTO'),
    ('F3', 'F-3'),
    ('', ''),
]


@pytest.mark.parametrize('crudo,esperado', CASOS_NORM)
def test_normalizar_numero(crudo, esperado):
    assert Torre.normalizar_numero(crudo) == esperado


def _linea():
    return Linea.objects.create(codigo='LN-T100', nombre='LN T100', cliente='TRANSELCA')


def _torre(linea, numero):
    return Torre.objects.create(linea=linea, numero=numero, latitud=10, longitud=-74)


@pytest.mark.django_db
def test_numero_display_property():
    linea = _linea()
    assert _torre(linea, 'E-1').numero_display == 'T-1'
    assert _torre(linea, 'P010').numero_display == 'P-10'
    assert str(_torre(linea, '5')) == 'T-5'


@pytest.mark.django_db
def test_orden_numerico_ascendente():
    linea = _linea()
    for n in ['E-1', 'E-10', 'E-2', 'E-21', 'E-3']:
        _torre(linea, n)
    ordenadas = list(ordenar_torres_num(Torre.objects.filter(linea=linea)))
    nums = [t.numero for t in ordenadas]
    # Debe quedar 1, 2, 3, 10, 21 (numérico), NO 1, 10, 2, 21, 3 (alfabético).
    assert nums == ['E-1', 'E-2', 'E-3', 'E-10', 'E-21']
    # Y se muestran como T-1..T-21.
    assert [t.numero_display for t in ordenadas] == ['T-1', 'T-2', 'T-3', 'T-10', 'T-21']


@pytest.mark.django_db
def test_orden_no_estandar_al_final():
    linea = _linea()
    _torre(linea, 'Pórtico Santamarta')  # sin número → al final
    _torre(linea, '7')
    _torre(linea, '3')
    nums = [t.numero for t in ordenar_torres_num(Torre.objects.filter(linea=linea))]
    assert nums == ['3', '7', 'Pórtico Santamarta']


@pytest.mark.django_db
def test_dato_legacy_preservado():
    """Un poste legacy 'P001' sigue siendo poste (P-1), no se convierte en torre."""
    linea = _linea()
    poste = _torre(linea, 'P001')
    poste.refresh_from_db()
    assert poste.numero == 'P001'           # dato crudo intacto
    assert poste.numero_display == 'P-1'     # display de poste, NO 'T-1'


@pytest.mark.django_db
def test_torre_construccion_numero_display():
    from apps.contratos.models import Contrato
    from apps.construccion.models import ProyectoConstruccion, TorreConstruccion
    contrato = Contrato.objects.create(codigo='C-T100', nombre='C T100', unidad_negocio='CONSTRUCCION')
    proyecto = ProyectoConstruccion.objects.create(contrato=contrato, nombre='Proy T100')
    t = TorreConstruccion.objects.create(proyecto=proyecto, numero='E-7')
    assert t.numero_display == 'T-7'
    assert str(t) == 'T-7'
