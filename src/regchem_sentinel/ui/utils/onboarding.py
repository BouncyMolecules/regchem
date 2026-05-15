"""First-run onboarding copy and interaction — decision support, not validated SoR."""

from __future__ import annotations

import json
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from regchem_sentinel.ui.utils import session as session_utils

_DISK_PREFS_HYDRATED_KEY = "regchem_sentinel.disk_prefs_hydrated"


def _coerce_int(value: object, *, default: int = 0) -> int:
    with suppress(TypeError, ValueError):
        return int(cast(Any, value))
    return default


def preferences_path() -> Path:
    """User-local Sentinel UX preferences (not regulated records)."""

    return Path.home() / ".regchem-sentinel" / "preferences.json"


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(serialized, encoding="utf-8")
    tmp.replace(path)


def _load_preferences_disk() -> dict[str, object]:
    path = preferences_path()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _persist_onboarding_preferences(st: Any) -> None:
    dismissed_key = session_utils.onboarding_dismissed_key()
    slide_key = session_utils.onboarding_slide_index_key()
    merged = _load_preferences_disk()
    merged["onboarding_dismissed"] = bool(st.session_state.get(dismissed_key, False))
    slide_raw = st.session_state.get(slide_key, 0)
    merged["onboarding_slide_index"] = _coerce_int(slide_raw)
    _atomic_write_json(preferences_path(), merged)


def _hydrate_onboarding_from_disk(st: Any) -> None:
    if st.session_state.get(_DISK_PREFS_HYDRATED_KEY):
        return

    prefs = _load_preferences_disk()
    dismissed_key = session_utils.onboarding_dismissed_key()
    slide_key = session_utils.onboarding_slide_index_key()

    if prefs.get("onboarding_dismissed") is True:
        st.session_state[dismissed_key] = True

    if "onboarding_slide_index" in prefs:
        st.session_state[slide_key] = _coerce_int(prefs["onboarding_slide_index"])

    st.session_state[_DISK_PREFS_HYDRATED_KEY] = True


@dataclass(frozen=True, slots=True)
class _OnboardingSlide:
    title: str
    subtitle: str
    body: str


_SLIDES: tuple[_OnboardingSlide, ...] = (
    _OnboardingSlide(
        title="Welcome to RegChem Sentinel",
        subtitle="Traceable CMC starting-material decision support",
        body=(
            "Sentinel ingests narrative Chemistry, Manufacturing, and Controls (CMC) text, "
            "surfaces Starting Material cues with explicit excerpt provenance, links supplier "
            "language, and checkpoints outputs through a verifier layer before persistence."
        ),
    ),
    _OnboardingSlide(
        title="Controlled pipeline",
        subtitle="Parse → classify → link → verify → persist",
        body=(
            "Every run fingerprints source text, emits structured hypotheses (not binding "
            "determinations), and commits an immutable snapshot plus hash-chained ledger facts "
            "suited to ALCOA+-style review packages when you pair it with your validated QMS."
        ),
    ),
    _OnboardingSlide(
        title="Human-in-the-loop posture",
        subtitle="Reviewers remain the decision authority",
        body=(
            "Use the Classify workspace to generate runs, then adjudicate findings in your "
            "own quality system. Export provenance from the History view: correlation IDs, "
            "content digests, verifier states, and ledger entries are surfaced for audit drills."
        ),
    ),
    _OnboardingSlide(
        title="Responsible deployment",
        subtitle="Map limitations to your CSV program",
        body=(
            "This build is not certified for Part 11 on its own. Configure environment controls, "
            "access governance, anomaly handling, backups, and record retention upstream—Sentinel "
            "is scaffolding you qualify within your computerized system validation lifecycle."
        ),
    ),
)


def render_gxp_banner(st: Any) -> None:
    """Surface honest limitations on every execution."""

    st.markdown(
        """
        <div class="regchem-banner">
            <strong>Governance reminder:</strong> RegChem Sentinel provides contextual decision
            support only. It is not intended as a validated system of record, does not replace
            qualified human review, and must not be used as the sole basis for regulatory filings
            or GxP decisions unless governed by your quality system.
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        "Map every automated output to source text, retain audit trails, and follow your "
        "SOPs for computer system validation (CSV) and data integrity (ALCOA+)."
    )


def render_onboarding_carousel(st: Any) -> None:
    """Four-step onboarding — dismissal + carousel index mirrored to disk preferences."""

    _hydrate_onboarding_from_disk(st)

    dismissed_key = session_utils.onboarding_dismissed_key()
    slide_key = session_utils.onboarding_slide_index_key()

    if st.session_state.get(dismissed_key, False):
        return

    if slide_key not in st.session_state:
        st.session_state[slide_key] = 0

    slide_ix = min(max(int(st.session_state[slide_key]), 0), len(_SLIDES) - 1)
    slide = _SLIDES[slide_ix]

    with st.container(border=True):
        st.markdown(
            f"**Getting started** · step {slide_ix + 1} of {len(_SLIDES)}",
        )
        st.caption(f"Tour progress is saved locally at `{preferences_path()}`.")

        st.markdown(f"### {slide.title}")
        st.caption(slide.subtitle)
        st.markdown(
            f'<p class="regchem-onboarding-steps">{slide.body}</p>',
            unsafe_allow_html=True,
        )

        controls = st.columns([1.1, 1.1, 1.1, 2.9])
        if controls[0].button("← Back", disabled=slide_ix <= 0, key="regchem_onboarding_back"):
            st.session_state[slide_key] = slide_ix - 1
            _persist_onboarding_preferences(st)
            st.rerun()

        next_label = "Next →" if slide_ix < len(_SLIDES) - 1 else "Finish tour"
        if controls[1].button(next_label, key="regchem_onboarding_next"):
            if slide_ix >= len(_SLIDES) - 1:
                st.session_state[dismissed_key] = True
            else:
                st.session_state[slide_key] = slide_ix + 1
            _persist_onboarding_preferences(st)
            st.rerun()

        if controls[2].button(
            "Skip onboarding",
            key="regchem_onboarding_skip",
            help="Hide the onboarding tour for future visits on this workstation.",
        ):
            st.session_state[dismissed_key] = True
            _persist_onboarding_preferences(st)
            st.rerun()
