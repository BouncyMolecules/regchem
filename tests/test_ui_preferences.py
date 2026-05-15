"""UX preference persistence — mirrors onboarding carousel state to disk."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from regchem_sentinel.ui.utils import onboarding
from regchem_sentinel.ui.utils import session as session_utils


def test_preferences_merge_preserves_unknown_keys(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "preferences.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"legacy_install_marker": True}), encoding="utf-8")
    monkeypatch.setattr(onboarding, "preferences_path", lambda: target)

    fake_st = MagicMock()
    fake_st.session_state = {
        session_utils.onboarding_dismissed_key(): True,
        session_utils.onboarding_slide_index_key(): 2,
    }

    onboarding._persist_onboarding_preferences(fake_st)

    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["legacy_install_marker"] is True
    assert data["onboarding_dismissed"] is True
    assert data["onboarding_slide_index"] == 2


def test_hydrate_restores_onboarding_keys(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "preferences.json"
    payload = {"onboarding_dismissed": False, "onboarding_slide_index": 3}
    target.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(onboarding, "preferences_path", lambda: target)

    fake_st = MagicMock()
    fake_st.session_state = {}

    onboarding._hydrate_onboarding_from_disk(fake_st)

    assert fake_st.session_state[session_utils.onboarding_slide_index_key()] == 3
    assert onboarding._DISK_PREFS_HYDRATED_KEY in fake_st.session_state


def test_hydrate_skips_when_already_hydrated(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "preferences.json"
    target.write_text(json.dumps({"onboarding_slide_index": 9}), encoding="utf-8")
    monkeypatch.setattr(onboarding, "preferences_path", lambda: target)

    fake_st = MagicMock()
    slide_key = session_utils.onboarding_slide_index_key()
    fake_st.session_state = {onboarding._DISK_PREFS_HYDRATED_KEY: True, slide_key: 1}

    onboarding._hydrate_onboarding_from_disk(fake_st)

    assert fake_st.session_state[slide_key] == 1
