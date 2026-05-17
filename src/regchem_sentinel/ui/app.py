"""Thin Streamlit composition root — keep orchestration and side effects here."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st

from regchem_sentinel.config import Settings
from regchem_sentinel.main import SentinelDependencies, default_dependencies
from regchem_sentinel.ui.pages import classify, dashboard, history
from regchem_sentinel.ui.utils import onboarding, theme
from regchem_sentinel.ui.utils.session import ensure_dependencies


def build_dependencies(
    settings: Settings,
    *,
    factory: Callable[[Settings], SentinelDependencies] | None = None,
) -> SentinelDependencies:
    """Session-scoped wiring so history persists across reroutes."""

    resolved_factory = factory or default_dependencies
    return ensure_dependencies(st, settings=settings, factory=resolved_factory)


def _render_sidebar(st: Any, *, settings: Settings, route: str) -> None:
    """Focused navigation: obvious primary path to Classify, quiet workspace switches."""

    with st.sidebar:
        st.markdown(
            """
            <div class="regchem-sidebar-brand">
                <p class="regchem-sidebar-brand-line">Quanta</p>
                <p class="regchem-sidebar-brand-sub">CMC decision support · auditable trace</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button(
            "New classification",
            type="primary",
            use_container_width=True,
            key="regchem_sidebar_new_classification",
        ):
            st.session_state["regchem_nav_route"] = "Classify"
            st.rerun()

        st.markdown(
            '<p class="regchem-sidebar-section">Workspaces</p>',
            unsafe_allow_html=True,
        )

        dash_type = "primary" if route == "Dashboard" else "secondary"
        hist_type = "primary" if route == "History" else "secondary"

        if st.button(
            "Portfolio overview",
            type=dash_type,
            use_container_width=True,
            key="regchem_sidebar_nav_dashboard",
        ):
            st.session_state["regchem_nav_route"] = "Dashboard"
            st.rerun()

        if st.button(
            "History & audit",
            type=hist_type,
            use_container_width=True,
            key="regchem_sidebar_nav_history",
        ):
            st.session_state["regchem_nav_route"] = "History"
            st.rerun()

        st.divider()

        with st.expander("Deployment context", expanded=False):
            persist_blurb = (
                f"SQLite `{settings.sqlite_database_path}`"
                if settings.storage_backend == "sqlite"
                else "in-memory session ledger"
            )
            st.caption(f"Environment · `{settings.app_env}`")
            st.caption(f"Persistence · {persist_blurb}")
            st.caption(f"Release tag · `{settings.build_id}`")


def run_app() -> None:
    st.set_page_config(
        page_title="Quanta",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    theme.apply_global_style()
    settings = Settings()

    onboarding.render_onboarding_carousel(st)

    deps = build_dependencies(settings)

    route = st.session_state.setdefault("regchem_nav_route", "Classify")
    if route not in ("Dashboard", "Classify", "History"):
        route = "Classify"
        st.session_state["regchem_nav_route"] = route

    _render_sidebar(st, settings=settings, route=route)

    header_copy: dict[str, tuple[str, str]] = {
        "Dashboard": (
            "Portfolio command center",
            "At-a-glance posture for retained runs: prioritise verifier escalations, sample history, and keep "
            "cadence aligned with submission milestones.",
        ),
        "Classify": (
            "Classification workspace",
            "Paste dossier-grade narrative first, preview the parse, then run the full chain when the excerpt "
            "matches what you will cite.",
        ),
        "History": (
            "History & immutable audit",
            "Indexed snapshots with content fingerprints, canonical bundle digests, and hash-chained ledger rows "
            "for traceability narratives.",
        ),
    }
    page_title, page_subtitle = header_copy[route]
    theme.render_app_shell_header(
        st,
        settings=settings,
        page_title=page_title,
        page_subtitle=page_subtitle,
    )

    onboarding.render_gxp_banner(st)

    if route == "Dashboard":
        dashboard.render(st, deps=deps, settings=settings)
    elif route == "Classify":
        classify.render(st, deps=deps, settings=settings)
    else:
        history.render(st, deps=deps, settings=settings)
