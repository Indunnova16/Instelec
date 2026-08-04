"""Regresión issue #206 — logo SVG gigante cuando el CDN de Tailwind no carga.

Root cause: el proyecto carga Tailwind vía `<script src="https://cdn.tailwindcss.com">`
en runtime (no hay build compilado). El logo (icono "rayo") dependía SOLO de las
clases Tailwind `w-N h-N` para su tamaño -- si el script del CDN no llega a
cargar, ninguna clase se aplica y el `<svg>` sin dimensiones propias renderiza a
su tamaño intrínseco del navegador, ocupando gran parte de la pantalla (reportado
por un usuario real, ver issue #206).

Reproducido de forma independiente con Playwright (fuera de esta suite, ver
SPRINTS/PLAN_2026-08-03_issue206.md): sin Tailwind cargado, el SVG del logo sin
`width`/`height` mide ~1260x1260px en un viewport de 1280px; con `width="32"
height="32"` mide exactamente 32x32px.

Este test NO puede reproducir el fallo del CDN (no hay navegador en la suite
pytest), pero SÍ puede garantizar la precondición necesaria para que el fallback
funcione: que el HTML servido tenga `width`/`height` HTML explícitos en el
`<svg>` del logo, en cada plantilla donde aparece.

NOTA (hallazgo F2): el path `M13 10V3L4 14h7v7l9-11h-7z` (icono "rayo") se
reutiliza en el repo para OTROS íconos de UI que no son el logo -- ej. un ítem
de navegación con `class="w-5 h-5 mr-3"` en el propio `sidebar.html`, que
sigue sin `width`/`height` porque el fix de #206 solo tocó los usos como
*logo*. Por eso este test acota la búsqueda al bloque específico del logo
(el `<a aria-label="...Ir al inicio">` en sidebar, el div del logo en login)
en vez de buscar por path -- así no da falsos positivos con otros íconos que
comparten la misma forma pero no son el logo.
"""

import re

import pytest


LOGO_ANCHOR_RE = re.compile(
    r'<a href="[^"]*"\s+class="flex items-center space-x-2"\s+aria-label="TransMaint - Ir al inicio">.*?</a>',
    re.DOTALL,
)
LOGIN_LOGO_BLOCK_RE = re.compile(
    r'<div class="inline-flex items-center justify-center w-16 h-16 bg-blue-100 rounded-full mb-4"[^>]*>.*?</div>',
    re.DOTALL,
)


def _svg_tags(html_fragment: str) -> list[str]:
    return re.findall(r"<svg\b[^>]*>.*?</svg>", html_fragment, re.DOTALL)


def _tiene_width_height_explicitos(svg_tag: str) -> bool:
    open_tag = svg_tag.split(">", 1)[0]
    return bool(re.search(r'\bwidth="\d+"', open_tag)) and bool(
        re.search(r'\bheight="\d+"', open_tag)
    )


@pytest.mark.django_db
class TestLogoSvgDimensionesIntrinsecas:
    """El logo (icono rayo, en el header de login y en el sidebar) debe tener
    width/height HTML explícitos, no solo clases Tailwind -- así degrada con
    gracia si cdn.tailwindcss.com no carga."""

    def test_login_logo_tiene_dimensiones_explicitas(self, client):
        response = client.get("/usuarios/login/")
        assert response.status_code == 200
        html = response.content.decode()

        bloque = LOGIN_LOGO_BLOCK_RE.search(html)
        assert bloque, "No se encontró el bloque del logo en la página de login"

        svgs = _svg_tags(bloque.group(0))
        assert svgs, "No se encontró el <svg> del logo dentro del bloque de login"

        for svg in svgs:
            assert _tiene_width_height_explicitos(svg), (
                "El <svg> del logo en login.html no tiene width/height HTML "
                f"explícitos (regresión #206): {svg}"
            )

    def test_sidebar_logo_tiene_dimensiones_explicitas(self, client, admin_user, user_password):
        client.login(username=admin_user.email, password=user_password)
        response = client.get("/")
        assert response.status_code == 200
        html = response.content.decode()

        ancla = LOGO_ANCHOR_RE.search(html)
        assert ancla, "No se encontró el <a aria-label='...Ir al inicio'> del logo en el sidebar"

        svgs = _svg_tags(ancla.group(0))
        assert svgs, "No se encontró el <svg> del logo dentro del ancla del sidebar"

        for svg in svgs:
            assert _tiene_width_height_explicitos(svg), (
                "El <svg> del logo en sidebar.html no tiene width/height HTML "
                f"explícitos (regresión #206): {svg}"
            )
