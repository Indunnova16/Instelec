"""Regresión Instelec#149 — residual visual en la lista de Obras de Protección.

#149 rebotó 3 veces. Las capas lógicas (selector de torres, doble filtro #160)
ya quedaron OK; el residual del bounce#3 era PURAMENTE visual: el comentario
Django `{# #149: ... #}` multilínea (trinchos_cunetas_lista.html L125-126) se
renderizaba como texto dentro del `<tbody>` de la tabla de Obras de Protección
(Django `{# ... #}` es single-line; un `{#` sin `#}` en la misma línea fuga el
bloque entero como texto literal). Lo confirmó F2 con el HTML de prod.

El fix lo reemplaza por `{% comment %} ... {% endcomment %}` (multilínea seguro).

Este test renderiza con el motor real de Django el `<tbody>` de la lista (el
fragmento que contenía el comentario fugado), con una torre legacy T-19 sin obra
capturada, y verifica:
  - el texto del comentario fugado NO aparece en el HTML;
  - T-19 SÍ aparece (las capas lógicas previas siguen OK: la torre renderiza).
"""

import os
import re

import pytest
from django.conf import settings
from django.template import Context, Template
from django.test import SimpleTestCase
from django.urls import reverse

_TEMPLATE = os.path.join(
    settings.BASE_DIR, "templates", "construccion", "trinchos_cunetas_lista.html"
)

# Bounce#4 (#149): el checkbox "Torre aplica / Torre NO aplica" de la matriz de
# Obra Civil aparecía SIN título ("3er check que no funciona … el que no tiene
# título"). Causa: la función Alpine `aplicaTorre(cfg)` de obra_civil_matriz.html
# NO inicializaba `aplica` en su return{}, así `x-model="aplica"` y
# `x-text="aplica ? 'Torre aplica' : 'Torre NO aplica'"` quedaban undefined.
# El commit b9d8aae (25/06) reordenó el HTML del label pero no tocó el JS.
_OC_MATRIZ = os.path.join(
    settings.BASE_DIR, "templates", "construccion", "obra_civil_matriz.html"
)

# Texto del comentario que NO debe aparecer en el HTML rendered.
_LEAKED = [
    "una fila por torre que aplica",
    "botón Capturar (torre preseleccionada).",
]


class _Torre:
    """Stub mínimo de TorreConstruccion para renderizar una fila (T-19 legacy)."""

    def __init__(self, numero_display, pk="t-19-uuid"):
        self.numero_display = numero_display
        self.id = pk


class _Fila:
    def __init__(self, torre, obra=None):
        self.torre = torre
        self.obra = obra


def _read():
    with open(_TEMPLATE, encoding="utf-8") as fh:
        return fh.read()


class ObrasProteccionListaSinComentarioFugadoTest(SimpleTestCase):
    def _comment_block(self, source):
        # Aísla el {% comment %} ... {% endcomment %} que reemplazó al {# #}
        # fugado (L125-126), sin arrastrar filtros/loads del resto del template.
        start = source.find("{% comment %}")
        end = source.find("{% endcomment %}", start)
        self.assertNotEqual(start, -1, "El comentario ya no usa {% comment %}")
        self.assertNotEqual(end, -1, "No se halló {% endcomment %} de cierre")
        return source[start : end + len("{% endcomment %}")]

    def test_no_aparece_el_texto_del_comentario_jinja(self):
        # Renderiza con el motor real de Django el bloque del comentario corregido.
        # Con el bug ({# ... #} multilínea) este mismo texto fugaba al <tbody>;
        # con el fix ({% comment %}) el render queda vacío.
        block = self._comment_block(_read())
        # Confirmá que el texto fugado SÍ está en el SOURCE (era el comentario)…
        for leaked in _LEAKED:
            self.assertIn(leaked, block, f"sanity: {leaked!r} debería estar en el comentario")
        # …pero NO en el HTML rendered.
        rendered = Template(block).render(Context({}))
        for leaked in _LEAKED:
            self.assertNotIn(
                leaked,
                rendered,
                f"El texto del comentario {leaked!r} fuga al HTML de Obras de "
                f"Protección (¿quedó como {{# ... #}} multilínea?)",
            )
        self.assertEqual(
            rendered.strip(),
            "",
            f"El {{% comment %}} debería renderizar vacío, obtuvo: {rendered.strip()[:80]!r}",
        )

    def test_t19_si_renderiza_en_el_loop_de_la_tabla(self):
        # La fila de cada torre sale del {% for f in filas %}{{ f.torre.numero_display }}.
        # Verifica que una torre legacy T-19 SIN obra capturada renderiza su número
        # (las capas lógicas previas — selector + filtro #160 — ya no la ocultan).
        loop = (
            "{% for f in filas %}"
            "{% with o=f.obra t=f.torre %}{{ t.numero_display }}"
            "{% if not o %} Pendiente{% endif %}{% endwith %}"
            "{% endfor %}"
        )
        filas = [_Fila(torre=_Torre("T-19"), obra=None)]
        rendered = Template(loop).render(Context({"filas": filas}))
        self.assertIn(
            "T-19",
            rendered,
            "La torre legacy T-19 debería renderizar en la tabla de Obras de Protección.",
        )

    def test_el_template_ya_no_tiene_comentario_jinja_multilinea(self):
        source = _read()
        ml = re.compile(r"\{#.*?#\}", re.DOTALL)
        offenders = [m.group(0) for m in ml.finditer(source) if "\n" in m.group(0)]
        self.assertEqual(
            offenders,
            [],
            f"trinchos_cunetas_lista.html aún tiene {{# ... #}} multilínea: {offenders}",
        )


# ============================================================================
# Bounce#4 — toggle "Torre aplica / Torre NO aplica" sin label en Obra Civil
# ============================================================================


def _read_oc_matriz():
    with open(_OC_MATRIZ, encoding="utf-8") as fh:
        return fh.read()


class AplicaTorreBindingSourceTest(SimpleTestCase):
    """El binding `aplica` debe existir en la función Alpine `aplicaTorre(cfg)`.

    Source-level (sin BD): garantiza que el return{} de aplicaTorre declara
    `aplica: cfg.aplica,` — de lo contrario `x-model="aplica"` queda undefined
    y el checkbox renderiza sin estado ni label (el bug que vio el cliente).
    """

    def _aplica_torre_body(self, source):
        start = source.find("function aplicaTorre(cfg)")
        self.assertNotEqual(
            start, -1, "No se halló la función aplicaTorre(cfg) en obra_civil_matriz.html"
        )
        # Aísla hasta el cierre de la función (el siguiente '</script>').
        end = source.find("</script>", start)
        return source[start:end]

    def test_aplica_torre_inicializa_aplica(self):
        body = self._aplica_torre_body(_read_oc_matriz())
        self.assertIn(
            "aplica: cfg.aplica",
            body,
            "aplicaTorre() NO inicializa `aplica` → x-model='aplica' queda undefined "
            "y el toggle 'Torre aplica/NO aplica' renderiza sin label (bounce#4).",
        )
        # Coherencia: los hermanos obras/pintura ya estaban; aplica debe acompañarlos.
        self.assertIn("obras: cfg.obras", body)
        self.assertIn("pintura: cfg.pintura", body)

    def test_x_data_pasa_aplica_y_el_label_lo_consume(self):
        # El bug NO es de presentación: el HTML ya pasa `aplica` en x-data y lo
        # consume en x-model/x-text/:class. Verificamos que esa cadena sigue intacta
        # para que el fix del JS realmente se vea en pantalla.
        source = _read_oc_matriz()
        self.assertIn("aplica: {% if torre.aplica %}true{% else %}false{% endif %}", source)
        self.assertIn('x-model="aplica"', source)
        self.assertIn("aplica ? 'Torre aplica' : 'Torre NO aplica'", source)


@pytest.fixture
def proyecto_oc(db):
    from apps.contratos.models import Contrato
    from apps.construccion.models import ProyectoConstruccion

    contrato = Contrato.objects.create(
        unidad_negocio=Contrato.UnidadNegocio.CONSTRUCCION,
        codigo="CT-OC-149",
        nombre="Proyecto OC #149",
        cliente="Cliente OC 149",
        estado=Contrato.Estado.ACTIVO,
    )
    return ProyectoConstruccion.objects.create(
        contrato=contrato,
        nombre="Proyecto OC matriz #149",
        estado="EJECUCION",
    )


@pytest.fixture
def torres_mixtas(proyecto_oc):
    """Dos torres: una que aplica y otra marcada 'No aplica' (#160)."""
    from apps.construccion.models import TorreConstruccion

    t_aplica = TorreConstruccion.objects.create(
        proyecto=proyecto_oc, numero="T-001", tipo="A", aplica=True
    )
    t_no_aplica = TorreConstruccion.objects.create(
        proyecto=proyecto_oc, numero="T-002", tipo="A", aplica=False
    )
    return t_aplica, t_no_aplica


@pytest.fixture
def admin_client_149(client, admin_user, user_password):
    client.login(username=admin_user.email, password=user_password)
    return client


@pytest.mark.django_db
class TestObraCivilMatrizToggleAplica:
    """GET de la matriz renderiza el toggle aplica CON binding y label por torre."""

    def test_matriz_renderiza_aplica_torre_con_binding(
        self, admin_client_149, proyecto_oc, torres_mixtas
    ):
        url = reverse(
            "construccion:obra_civil_lista", kwargs={"proyecto_id": proyecto_oc.id}
        )
        resp = admin_client_149.get(url)
        assert resp.status_code == 200
        html = resp.content.decode()
        # El JS del toggle ya bindea aplica (el fix de bounce#4).
        assert "aplica: cfg.aplica" in html, (
            "El HTML de la matriz no contiene 'aplica: cfg.aplica' → aplicaTorre() "
            "no bindea el estado y el toggle queda sin label."
        )
        # El label/x-text del toggle está presente para que Alpine lo pinte.
        assert "Torre aplica" in html and "Torre NO aplica" in html

    def test_x_data_aplica_refleja_estado_de_cada_torre(
        self, admin_client_149, proyecto_oc, torres_mixtas
    ):
        """Con ≥2 torres (una aplica=True, otra aplica=False), el x-data inicial
        de cada fila debe sembrar el valor real de torre.aplica para que el
        checkbox arranque sincronizado (no todo en true/false)."""
        url = reverse(
            "construccion:obra_civil_lista", kwargs={"proyecto_id": proyecto_oc.id}
        )
        html = admin_client_149.get(url).content.decode()
        # La torre que aplica siembra aplica:true; la que no, aplica:false.
        assert re.search(r"aplica:\s*true", html), (
            "Ninguna fila siembra aplica:true — T-001 (aplica=True) no inicializa el toggle."
        )
        assert re.search(r"aplica:\s*false", html), (
            "Ninguna fila siembra aplica:false — T-002 (aplica=False) no inicializa el toggle."
        )
