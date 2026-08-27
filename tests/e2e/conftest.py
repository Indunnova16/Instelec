"""Marca automaticamente como `e2e` todo test bajo tests/e2e/.

Motivo (2026-08-27, id:instelec-e2e-sin-marker-corren-en-selfverify): estos tests
levantan navegador/servidor vivo (Playwright, LiveServer) y NO pueden pasar en el
gate F3 self-verify, que corre offline. El gate ya los excluye con `-m "not e2e"`,
pero ese filtro solo mira MARKERS — estar en tests/e2e/ no basta. Sin marker se
colaban 41 tests de navegador en cada corrida del gate, garantizando rojo aunque
el fix bajo prueba estuviera perfecto.

Se aplica por conftest de directorio (no `pytestmark` por archivo) para que un
test e2e nuevo quede cubierto sin que nadie tenga que acordarse del marker.
"""
from pathlib import Path

import pytest

_E2E_DIR = Path(__file__).resolve().parent


def pytest_collection_modifyitems(config, items):
    for item in items:
        try:
            item_path = Path(str(item.fspath)).resolve()
        except (AttributeError, OSError):
            continue
        if _E2E_DIR == item_path.parent or _E2E_DIR in item_path.parents:
            item.add_marker(pytest.mark.e2e)
