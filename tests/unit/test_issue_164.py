"""Regresión Instelec#164 — comentarios Django `{# ... #}` multilínea fugaban texto.

Django Template Language solo trata `{# ... #}` como comentario cuando se queda
en UNA línea. Un `{#` al final de una línea sin su `#}` en la misma línea NO se
reconoce como comentario: el lexer emite TODO el bloque (texto + `#}` de cierre)
como texto literal visible en el HTML rendered. Ana Sofía lo reportó como
"aparecen estos textos como de codigo".

Tres templates de construcción tenían esa fuga (confirmado en prod por F2):
  - templates/construccion/spt_pintura_torre.html (#153, L165-167)
  - templates/construccion/trinchos_cunetas_lista.html (#149, L125-126)
  - templates/construccion/programacion_cuadrilla_detalle.html (#155, L132-135)

El fix reemplaza cada `{# ... #}` multilínea por `{% comment %} ... {% endcomment %}`
(que sí soporta multilínea). Este test renderiza con el motor real de Django el
fragmento de cada template que contenía el comentario y verifica que NINGÚN texto
del comentario sale al HTML.
"""

import os

from django.conf import settings
from django.template import Context, Template
from django.test import SimpleTestCase

_TEMPLATES_DIR = os.path.join(settings.BASE_DIR, "templates", "construccion")

# (archivo, texto del comentario que NO debe aparecer en el render)
_CASES = [
    (
        "spt_pintura_torre.html",
        [
            "SPT y Pintura de Patas son obligatorios",
            "marcado desde Obra Civil",
            "Si no aplica, se informa y no se renderiza.",
        ],
    ),
    (
        "trinchos_cunetas_lista.html",
        [
            "una fila por torre que aplica",
            "botón Capturar (torre preseleccionada).",
        ],
    ),
    (
        "programacion_cuadrilla_detalle.html",
        [
            "Reemplaza el placeholder: la vista pasa los datos",
            "El partial existe en el repo.",
        ],
    ),
]


def _read(template_name):
    with open(os.path.join(_TEMPLATES_DIR, template_name), encoding="utf-8") as fh:
        return fh.read()


class MultilineDjangoCommentDoesNotLeakTest(SimpleTestCase):
    """Renderiza con el motor de Django el comentario corregido de cada template.

    Para aislar el comentario sin arrastrar `{% extends %}`/`{% include %}` ni
    fixtures de BD, extraemos el bloque `{% comment %} ... {% endcomment %}` del
    source y lo renderizamos solo. Con el bug (`{# ... #}`) ese mismo bloque
    fugaría su texto; con el fix el render queda vacío de texto-comentario.
    """

    def _extract_comment_block(self, source, fragment):
        # Localiza el {% comment %} ... {% endcomment %} que contiene `fragment`.
        idx = source.find(fragment)
        self.assertNotEqual(
            idx, -1, f"No se encontró el texto del comentario {fragment!r} en el template"
        )
        start = source.rfind("{% comment %}", 0, idx)
        end = source.find("{% endcomment %}", idx)
        self.assertNotEqual(
            start, -1, f"El texto {fragment!r} ya no está dentro de un {{% comment %}}"
        )
        self.assertNotEqual(end, -1, "No se halló {% endcomment %} de cierre")
        return source[start : end + len("{% endcomment %}")]

    def test_los_tres_templates_no_filtran_texto_de_comentario(self):
        for template_name, leaked_texts in _CASES:
            source = _read(template_name)
            with self.subTest(template=template_name):
                block = self._extract_comment_block(source, leaked_texts[0])
                rendered = Template(block).render(Context({}))
                for leaked in leaked_texts:
                    self.assertNotIn(
                        leaked,
                        rendered,
                        f"{template_name}: el texto del comentario {leaked!r} fuga "
                        f"al HTML rendered (¿quedó como {{# ... #}} multilínea?)",
                    )
                # El bloque {% comment %} no debe renderizar NADA visible.
                self.assertEqual(
                    rendered.strip(),
                    "",
                    f"{template_name}: el {{% comment %}} debería renderizar vacío, "
                    f"obtuvo: {rendered.strip()[:80]!r}",
                )

    def test_no_quedan_comentarios_jinja_multilinea_en_los_tres_templates(self):
        # Defensa adicional: el patrón {# que abre y cierra en líneas distintas
        # no debe existir en ninguno de los tres templates corregidos.
        import re

        ml = re.compile(r"\{#.*?#\}", re.DOTALL)
        for template_name, _ in _CASES:
            source = _read(template_name)
            with self.subTest(template=template_name):
                offenders = [m.group(0) for m in ml.finditer(source) if "\n" in m.group(0)]
                self.assertEqual(
                    offenders,
                    [],
                    f"{template_name}: aún tiene comentarios {{# ... #}} multilínea: {offenders}",
                )
