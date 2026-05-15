"""Pharma-aligned Streamlit visuals — disciplined navy/teal sentinel palette."""

from __future__ import annotations

from typing import Any, Literal

# Software Update Guardian-aligned sentinel chrome (regulated workstation metaphor).
NAVY_DEEP = "#0A1428"
NAVY_SIDEBAR = "#0E1F3D"
TEAL_PRIMARY = "#00D4FF"
TEAL_BRIGHT = "#5CEFFF"
TEAL_SOFT = "#0891B2"
SURFACE = "#f8fafc"
CARD_BORDER = "rgba(0, 212, 255, 0.22)"
TEXT_MUTED = "#64748b"

KpiBand = Literal["neutral", "low", "watch", "elevated"]


def apply_global_style() -> None:
    """Inject CSS once per script run — Streamlit re-executes safely."""

    import streamlit as st

    st.markdown(
        f"""
        <style>
            :root {{
                --regchem-navy-deep: {NAVY_DEEP};
                --regchem-navy-sidebar: {NAVY_SIDEBAR};
                --regchem-teal-primary: {TEAL_PRIMARY};
                --regchem-teal-bright: {TEAL_BRIGHT};
                --regchem-teal-soft: {TEAL_SOFT};
                --regchem-surface: {SURFACE};
                --regchem-muted: {TEXT_MUTED};
                --regchem-risk-low: #0d9488;
                --regchem-risk-watch: #d97706;
                --regchem-risk-elevated: #e11d48;
            }}

            html, body, [class*="css"] {{
                font-family: "Segoe UI", "Helvetica Neue", system-ui, sans-serif;
                color-scheme: light;
            }}

            .main .block-container {{
                padding-top: 2rem;
                padding-bottom: 4rem;
                max-width: 1200px;
            }}

            [data-testid="stSidebar"] {{
                background: linear-gradient(
                    165deg,
                    var(--regchem-navy-sidebar) 0%,
                    var(--regchem-navy-deep) 100%
                );
                border-right: 1px solid rgba(0, 212, 255, 0.14);
            }}

            [data-testid="stSidebar"] *,
            [data-testid="stSidebar"] span,
            [data-testid="stSidebar"] label {{
                color: #e2e8f0 !important;
            }}

            [data-testid="stSidebar"] .stMarkdown strong {{
                color: var(--regchem-teal-bright) !important;
            }}

            h1 {{
                letter-spacing: -0.03em;
                color: var(--regchem-navy-deep) !important;
                border-bottom: 2px solid var(--regchem-teal-primary);
                padding-bottom: 0.35rem;
                margin-bottom: 1rem;
            }}

            h2, h3 {{
                color: #0c4a6e !important;
            }}

            div[data-testid="stVerticalBlockBorderWrapper"] {{
                border-color: rgba(0, 212, 255, 0.12) !important;
            }}

            .stAlert {{
                border-radius: 10px !important;
            }}

            .stMetric label {{
                color: var(--regchem-muted) !important;
            }}

            div[data-testid="stDecoration"] {{
                background-image: linear-gradient(
                    90deg,
                    var(--regchem-teal-primary),
                    var(--regchem-teal-bright)
                );
            }}

            .regchem-kpi {{
                border-radius: 10px;
                padding: 1rem 1.15rem;
                background: linear-gradient(165deg, #ffffff 0%, #f1f5f9 100%);
                border: 1px solid rgba(10, 20, 40, 0.08);
                border-left-width: 4px;
                box-shadow: 0 10px 28px rgba(10, 20, 40, 0.06);
                min-height: 88px;
            }}

            .regchem-kpi-label {{
                font-size: 0.78rem;
                font-weight: 600;
                letter-spacing: 0.04em;
                text-transform: uppercase;
                color: var(--regchem-muted);
                margin-bottom: 0.35rem;
            }}

            .regchem-kpi-value {{
                font-size: 1.65rem;
                font-weight: 700;
                color: var(--regchem-navy-deep);
                letter-spacing: -0.02em;
                line-height: 1.15;
            }}

            .regchem-kpi-foot {{
                margin-top: 0.35rem;
                font-size: 0.8rem;
                color: var(--regchem-muted);
            }}

            .regchem-kpi--neutral {{ border-left-color: #94a3b8; }}
            .regchem-kpi--low {{ border-left-color: var(--regchem-teal-primary); }}
            .regchem-kpi--watch {{ border-left-color: var(--regchem-risk-watch); }}
            .regchem-kpi--elevated {{ border-left-color: var(--regchem-risk-elevated); }}

            .regchem-chip-row {{
                display: flex;
                flex-wrap: wrap;
                gap: 0.5rem;
                margin: 0.35rem 0 1rem;
            }}

            .regchem-chip {{
                display: inline-flex;
                align-items: center;
                gap: 0.35rem;
                padding: 0.35rem 0.65rem;
                border-radius: 999px;
                font-size: 0.82rem;
                font-weight: 600;
                border: 1px solid rgba(10, 20, 40, 0.08);
                background: #ffffff;
            }}

            .regchem-chip--low {{
                border-color: rgba(0, 212, 255, 0.35);
                color: #0e7490;
            }}

            .regchem-chip--watch {{
                border-color: rgba(217, 119, 6, 0.35);
                color: #b45309;
            }}

            .regchem-chip--elevated {{
                border-color: rgba(225, 29, 72, 0.35);
                color: #be123c;
            }}

            .regchem-banner {{
                border-left: 4px solid var(--regchem-teal-primary);
                padding: 0.85rem 1rem;
                background: linear-gradient(
                    90deg,
                    #ecfefff2 0%,
                    var(--regchem-surface) 85%
                );
                border-radius: 8px;
                box-shadow: 0 4px 12px rgba(10, 22, 40, 0.06);
                color: #0f172a;
            }}

            .regchem-onboarding-card {{
                background: #ffffffcc;
                border: 1px solid {CARD_BORDER};
                border-radius: 12px;
                padding: 1.25rem 1.35rem;
                margin-bottom: 1rem;
                box-shadow: 0 14px 32px rgba(10, 22, 40, 0.07);
                backdrop-filter: blur(10px);
            }}

            .regchem-onboarding-card h4 {{
                color: #0369a1 !important;
                margin: 0 0 0.5rem;
            }}

            .regchem-onboarding-steps {{
                color: #475569;
                font-size: 0.93rem;
                line-height: 1.65;
                margin-top: 0.6rem;
            }}

            .regchem-footnote {{
                font-size: 0.85rem;
                color: var(--regchem-muted);
            }}

            [data-testid="stMarkdownContainer"] a {{
                color: var(--regchem-teal-soft) !important;
            }}

            hr {{
                margin: 1.5rem 0;
                border: none;
                border-top: 1px solid rgba(0, 212, 255, 0.18);
            }}

            div[data-testid="stSidebar"] .stRadio label {{
                border-radius: 8px;
                padding: 0.35rem 0.45rem;
            }}

            div[data-testid="stSidebar"] .stRadio [aria-checked="true"] {{
                outline: 1px solid rgba(0, 212, 255, 0.35);
                background: rgba(0, 212, 255, 0.06);
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def kpi_band_for_verifier_counts(*, review: int, rejected: int) -> KpiBand:
    """Map verifier pressure to a presentation band (not clinical risk)."""

    if rejected > 0:
        return "elevated"
    if review > 0:
        return "watch"
    return "low"


def render_kpi_card(
    container: Any,
    *,
    title: str,
    value: str,
    band: KpiBand,
    footnote: str | None = None,
) -> None:
    """KPI tile with risk-band accent — use inside ``st.columns`` slots."""

    foot_html = (
        f'<div class="regchem-kpi-foot">{footnote}</div>' if footnote else ""
    )
    container.markdown(
        f"""
        <div class="regchem-kpi regchem-kpi--{band}">
            <div class="regchem-kpi-label">{title}</div>
            <div class="regchem-kpi-value">{value}</div>
            {foot_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_verifier_chips(
    container: Any,
    *,
    accepted: int,
    review_required: int,
    rejected: int,
) -> None:
    """Compact status strip for verifier outcomes."""

    chips: tuple[tuple[str, int, Literal["low", "watch", "elevated"]], ...] = (
        ("Accepted", accepted, "low"),
        ("Review required", review_required, "watch" if review_required > 0 else "low"),
        ("Rejected", rejected, "elevated" if rejected > 0 else "low"),
    )
    parts = [
        f'<span class="regchem-chip regchem-chip--{band}">{label}: {count}</span>'
        for label, count, band in chips
    ]
    html = '<div class="regchem-chip-row">' + "".join(parts) + "</div>"
    container.markdown(html, unsafe_allow_html=True)


def metric_row(st: Any, columns: tuple[str, ...], values: tuple[str, ...]) -> None:
    """Render balanced metric columns for dashboard summaries."""

    cols = st.columns(len(columns))
    for col, title, value in zip(cols, columns, values, strict=True):
        col.metric(title, value)
