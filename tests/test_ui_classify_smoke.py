"""UI smoke tests using Streamlit doubles (no running server)."""

from __future__ import annotations

from unittest.mock import MagicMock

from regchem_sentinel.config import Settings
from regchem_sentinel.core.continual_learning import RiskForecastLine
from regchem_sentinel.main import default_dependencies
from regchem_sentinel.ui.pages import classify


def test_forecast_story_cards_escape_plain_strings() -> None:
    """Regression: third scenario must not return a 1-tuple blurb (breaks ``html.escape``)."""

    line = RiskForecastLine(headline="h", probability_percent=44, basis="technical basis text")
    for idx in range(3):
        title, blurb = classify._forecast_story_title_and_blurb(idx, line)
        assert isinstance(title, str)
        assert isinstance(blurb, str)


def test_classify_page_exits_early_before_run() -> None:
    fake_st = MagicMock()
    fake_st.session_state = {}

    def columns_side_effect(*args, **_kwargs):
        n = 2
        if args and isinstance(args[0], int):
            n = args[0]
        elif args and isinstance(args[0], (list, tuple)):
            n = len(args[0])
        return tuple(MagicMock() for _ in range(n))

    fake_st.columns.side_effect = columns_side_effect
    fake_st.button.return_value = False
    fake_st.file_uploader.return_value = None
    fake_st.text_area.return_value = ""
    fake_st.text_input.return_value = ""
    fake_st.toggle.return_value = True
    settings = Settings(app_env="development", build_id="pytest", storage_backend="memory")
    deps = default_dependencies(settings)

    classify.render(fake_st, deps=deps, settings=settings)

    fake_st.info.assert_called()
    fake_st.dataframe.assert_not_called()
