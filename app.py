"""Quanta - Streamlit Cloud entrypoint (2026 best practice)."""
from __future__ import annotations
import sys
from pathlib import Path

# === CRITICAL: Ensure src/ is on PYTHONPATH for Streamlit Cloud ===
_ROOT = Path(__file__).resolve().parent
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

try:
    from regchem_sentinel.ui.app import run_app  # noqa: E402
except ImportError as exc:
    import streamlit as st  # noqa: E402
    st.error(
        "❌ Failed to import Quanta application modules.\n\n"
        "This usually means dependencies were not installed.\n"
        "Please ensure the app is using the root requirements.txt and click 'Rebuild app'."
    )
    st.stop()

if __name__ == "__main__":
    run_app()
