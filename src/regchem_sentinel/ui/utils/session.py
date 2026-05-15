"""Session-scoped dependency injection and Streamlit session contracts."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from regchem_sentinel.config import Settings
from regchem_sentinel.main import SentinelDependencies

_DEPS_SESSION_KEY = "regchem_sentinel.sentinel_dependencies"
_DEPS_SETTINGS_FINGERPRINT_KEY = "regchem_sentinel.deps_settings_fingerprint"
_ONBOARDING_DISMISSED_KEY = "regchem_sentinel.onboarding_dismissed"
_ONBOARDING_SLIDE_INDEX_KEY = "regchem_sentinel.onboarding_slide_index"


def onboarding_dismissed_key() -> str:
    """Expose key for onboarding visibility controls (presentation tests may patch)."""

    return _ONBOARDING_DISMISSED_KEY


def onboarding_slide_index_key() -> str:
    """Expose carousel progression key."""

    return _ONBOARDING_SLIDE_INDEX_KEY


def _deps_fingerprint(settings: Settings) -> tuple[object, ...]:
    fingerprint: tuple[object, ...] = (
        settings.app_env,
        settings.build_id,
        settings.storage_backend,
        str(settings.sqlite_database_path) if settings.storage_backend == "sqlite" else "",
    )
    return fingerprint


def ensure_dependencies(
    st_module: Any,
    *,
    settings: Settings,
    factory: Callable[[Settings], SentinelDependencies],
) -> SentinelDependencies:
    """Bind ``SentinelDependencies`` once per browser session."""

    state = st_module.session_state
    fingerprint = _deps_fingerprint(settings)
    if _DEPS_SESSION_KEY not in state or state.get(_DEPS_SETTINGS_FINGERPRINT_KEY) != fingerprint:
        state[_DEPS_SESSION_KEY] = factory(settings)
        state[_DEPS_SETTINGS_FINGERPRINT_KEY] = fingerprint

    return cast(SentinelDependencies, state[_DEPS_SESSION_KEY])
