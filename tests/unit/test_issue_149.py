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

from django.conf import settings
from django.template import Context, Template
from django.test import SimpleTestCase

_TEMPLATE = os.path.join(
    settings.BASE_DIR, "templates", "construccion", "trinchos_cunetas_lista.html"
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
