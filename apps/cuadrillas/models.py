"""
Cuadrillas models — partitioned aggregator.

Pre-block layout: every model was defined in this file directly.
After block `portafolio_sofi_may2026` (F2 scaffolding S1) the legacy models live
in `models_base.py`. New sub-features add their own `models_<sub_id>.py` and the
aggregator re-exports them here so that `from apps.cuadrillas.models import Foo`
keeps working everywhere (admin, views, importers, third-party apps).

NEW MODELS GO IN A NEW FILE — do not append to this aggregator.
"""
from .models_base import *  # noqa: F401, F403

# B3 — Cuadrilla auditoria desactivacion (Sofi, mayo 2026). Optional import so
# the repo stays importable in `modulo/portafolio_sofi_may2026/base` before F3
# writes models_b3.
try:
    from .models_b3 import *  # noqa: F401, F403
except ImportError:
    pass

# programacion_cuadrillas (S1, #155) — Programación/Ejecución semanal por
# cuadrilla. Import protegido para que el repo siga importable aunque el módulo
# aún no exista en una rama dada.
try:
    from .models_pc import *  # noqa: F401, F403
except Exception:
    pass
