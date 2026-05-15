"""Streamlit Cloud / local entrypoint.

Prepends ``src`` to ``PYTHONPATH`` for Streamlit Cloud, then invokes
``regchem_sentinel.ui.app.run_app`` which binds the Streamlit workstation to the audited
pipeline (parse → classify → supplier link → verify → persist) through explicit dependency
injection.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
_src_str = str(_SRC)
if _src_str not in sys.path:
    sys.path.insert(0, _src_str)

from regchem_sentinel.ui.app import run_app  # noqa: E402

if __name__ == "__main__":
    run_app()
