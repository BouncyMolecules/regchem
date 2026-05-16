"""UI smoke tests using Streamlit doubles (no running server)."""

from __future__ import annotations

from unittest.mock import MagicMock

from regchem_sentinel.config import Settings
from regchem_sentinel.main import default_dependencies
from regchem_sentinel.ui.pages import classify


def test_classify_page_exits_early_before_run() -> None:
    fake_st = MagicMock()
    fake_st.button.return_value = False
    fake_st.columns.side_effect = lambda *_a, **_k: (MagicMock(), MagicMock())
    fake_st.file_uploader.return_value = None
    settings = Settings(app_env="development", build_id="pytest", storage_backend="memory")
    deps = default_dependencies(settings)

    classify.render(fake_st, deps=deps, settings=settings)

    fake_st.info.assert_called()
    fake_st.dataframe.assert_not_called()
