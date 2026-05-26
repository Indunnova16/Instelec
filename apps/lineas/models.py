"""
Lineas models — partitioned aggregator.

Pre-block layout: every model was defined in this file directly.
After block `portafolio_sofi_may2026` (F2 scaffolding S1) the legacy models live
in `models_base.py`. New sub-features add their own `models_<sub_id>.py` and the
aggregator re-exports them here so that `from apps.lineas.models import Foo`
keeps working everywhere (admin, views, importers, third-party apps).

NEW MODELS GO IN A NEW FILE — do not append to this aggregator.
"""
from .models_base import *  # noqa: F401, F403

# B2.1 — Vano semestre (Sofi, mayo 2026). Optional import so the repo stays
# importable in `modulo/portafolio_sofi_may2026/base` before F3 writes models_b21.
try:
    from .models_b21 import *  # noqa: F401, F403
except ImportError:
    pass
