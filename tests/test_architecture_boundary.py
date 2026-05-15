"""Guarantee presentation dependencies never leak into ``core/``."""

from __future__ import annotations

import re
from pathlib import Path

import regchem_sentinel.core as core_pkg

_IMPORT_STREAMLIT = re.compile(r"^\s*import\s+streamlit\b", re.MULTILINE)
_FROM_STREAMLIT = re.compile(r"^\s*from\s+streamlit\b", re.MULTILINE)


def test_core_python_sources_do_not_import_streamlit() -> None:
    root = Path(core_pkg.__file__).resolve().parent
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if _IMPORT_STREAMLIT.search(text) or _FROM_STREAMLIT.search(text):
            offenders.append(str(path))
    assert not offenders, f"streamlit leakage in core/: {offenders}"
