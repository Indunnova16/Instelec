"""Regresión #111 — Django `{# ... #}` comments must be single-line.

Django Template Language only parses `{# ... #}` as a comment when it stays
on one line. Multi-line variants leak into the rendered HTML as plain text,
which Ana Sofía reported as "aparecen estos textos como de codigo".
For multi-line documentation use `{% comment %} ... {% endcomment %}`.
"""

import os
import re

from django.conf import settings

_TEMPLATES_DIR = os.path.join(settings.BASE_DIR, "templates")
_MULTILINE = re.compile(r"\{#.*?#\}", re.DOTALL)


def _walk_templates():
    for root, _, files in os.walk(_TEMPLATES_DIR):
        for f in files:
            if f.endswith(".html"):
                yield os.path.join(root, f)


def test_no_multiline_django_comments_in_templates():
    offenders = []
    for path in _walk_templates():
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        for m in _MULTILINE.finditer(content):
            if "\n" in m.group(0):
                offenders.append(f"{os.path.relpath(path, settings.BASE_DIR)}: {m.group(0)[:80]!r}")
    assert not offenders, (
        "Multi-line `{# ... #}` Django comments leak as visible text. "
        "Use `{% comment %} ... {% endcomment %}` instead.\n  - " + "\n  - ".join(offenders)
    )
