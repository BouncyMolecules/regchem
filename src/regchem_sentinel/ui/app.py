"""Thin Streamlit composition root — keep orchestration and side effects here."""

from __future__ import annotations

from collections.abc import Callable

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


def run_app() -> None:
    st.set_page_config(
        page_title="RegChem Sentinel",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    theme.apply_global_style()
    settings = Settings()

    onboarding.render_onboarding_carousel(st)
    onboarding.render_gxp_banner(st)

    deps = build_dependencies(settings)

    st.sidebar.markdown("### RegChem Sentinel")
    st.sidebar.caption("Starting material posture · auditable scaffold")
    st.sidebar.divider()

    persist_blurb = (
        f"SQLite `{settings.sqlite_database_path}`"
        if settings.storage_backend == "sqlite"
        else "in-memory session ledger"
    )
    st.sidebar.caption(f"Environment · `{settings.app_env}`")
    st.sidebar.caption(f"Persistence · {persist_blurb}")
    st.sidebar.caption(f"Release tag · `{settings.build_id}`")

    route = st.sidebar.radio(
        "Workspace",
        ("Dashboard", "Classify", "History"),
        key="regchem_nav_route",
    )

    if route == "Dashboard":
        dashboard.render(st, deps=deps, settings=settings)
    elif route == "Classify":
        classify.render(st, deps=deps, settings=settings)
    else:
        history.render(st, deps=deps, settings=settings)
