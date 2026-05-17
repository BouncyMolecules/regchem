"""Pharma-aligned Streamlit visuals — disciplined navy/teal sentinel palette."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from regchem_sentinel.config import Settings
from regchem_sentinel.core.models import SentinelPipelineSnapshot

# Refined RegOps chrome — calm navy shelf, restrained teal accents (Vault-adjacent clarity).
NAVY_DEEP = "#0B1220"
NAVY_MID = "#111E33"
NAVY_SIDEBAR = "#0F1B30"
TEAL_PRIMARY = "#14B8A9"
TEAL_GLOW = "#2DD4BF"
TEAL_SOFT = "#0F766E"
SURFACE = "#F4F6FA"
SURFACE_CARD = "#FFFFFF"
CARD_BORDER = "rgba(15, 118, 110, 0.12)"
TEXT_MUTED = "#64748b"
TEXT_INK = "#0F172A"

KpiBand = Literal["neutral", "low", "watch", "elevated"]


def apply_global_style() -> None:
    """Inject CSS once per script run — Streamlit re-executes safely."""

    import streamlit as st

    st.markdown(
        f"""
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&display=swap" rel="stylesheet">
        <style>
            :root {{
                --regchem-navy-deep: {NAVY_DEEP};
                --regchem-navy-mid: {NAVY_MID};
                --regchem-navy-sidebar: {NAVY_SIDEBAR};
                --regchem-teal-primary: {TEAL_PRIMARY};
                --regchem-teal-glow: {TEAL_GLOW};
                --regchem-teal-soft: {TEAL_SOFT};
                --regchem-surface: {SURFACE};
                --regchem-surface-card: {SURFACE_CARD};
                --regchem-ink: {TEXT_INK};
                --regchem-muted: {TEXT_MUTED};
                --regchem-risk-low: #0d9488;
                --regchem-risk-watch: #d97706;
                --regchem-risk-elevated: #e11d48;
            }}

            html, body, [class*="css"] {{
                font-family: "DM Sans", "Segoe UI", system-ui, sans-serif;
                color-scheme: light;
            }}

            .stApp {{
                background: radial-gradient(
                    1200px 600px at 12% -10%,
                    rgba(20, 184, 169, 0.07),
                    transparent 55%
                  ),
                  linear-gradient(180deg, {SURFACE} 0%, #eef2f7 100%);
            }}

            .main .block-container {{
                padding-top: 1.5rem;
                padding-bottom: 4rem;
                max-width: 1280px;
            }}

            [data-testid="stSidebar"] {{
                background: linear-gradient(
                    175deg,
                    var(--regchem-navy-sidebar) 0%,
                    var(--regchem-navy-deep) 55%,
                    #070c14 100%
                );
                border-right: 1px solid rgba(45, 212, 191, 0.12);
                box-shadow: 8px 0 32px rgba(7, 12, 20, 0.35);
            }}

            [data-testid="stSidebar"] *,
            [data-testid="stSidebar"] span,
            [data-testid="stSidebar"] label {{
                color: #e2e8f0 !important;
            }}

            [data-testid="stSidebar"] .stMarkdown strong,
            [data-testid="stSidebar"] p {{
                color: #f1f5f9 !important;
            }}

            [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{
                opacity: 0.88;
            }}

            section[data-testid="stSidebar"] button[kind="primary"] {{
                background: linear-gradient(135deg, {TEAL_PRIMARY} 0%, {TEAL_SOFT} 100%) !important;
                border: none !important;
                font-weight: 600 !important;
                letter-spacing: 0.02em;
                box-shadow: 0 8px 22px rgba(20, 184, 169, 0.35) !important;
            }}

            section[data-testid="stSidebar"] button[kind="secondary"],
            section[data-testid="stSidebar"] .stButton > button[kind="secondary"] {{
                background: rgba(248, 250, 252, 0.12) !important;
                border: 1px solid rgba(226, 232, 240, 0.6) !important;
                color: #f8fafc !important;
                font-weight: 600 !important;
                box-shadow: none !important;
            }}

            section[data-testid="stSidebar"] button[kind="secondary"]:hover {{
                background: rgba(248, 250, 252, 0.2) !important;
                border-color: rgba(45, 212, 191, 0.75) !important;
                color: #ffffff !important;
            }}

            section[data-testid="stSidebar"] button[kind="secondary"]:focus-visible {{
                outline: 2px solid #2dd4bf !important;
                outline-offset: 2px !important;
            }}

            section[data-testid="stSidebar"] button[kind="primary"]:focus-visible {{
                outline: 2px solid #ccfbf1 !important;
                outline-offset: 2px !important;
            }}

            h1 {{
                letter-spacing: -0.035em;
                font-weight: 700 !important;
                color: var(--regchem-navy-deep) !important;
                border-bottom: none !important;
                padding-bottom: 0;
                margin-bottom: 0.25rem;
            }}

            h2, h3 {{
                color: var(--regchem-navy-mid) !important;
                letter-spacing: -0.02em;
            }}

            div[data-testid="stVerticalBlockBorderWrapper"] {{
                border-color: rgba(15, 118, 110, 0.1) !important;
                border-radius: 14px !important;
                background: var(--regchem-surface-card) !important;
                box-shadow: 0 10px 30px rgba(11, 18, 32, 0.06) !important;
            }}

            .stAlert {{
                border-radius: 12px !important;
                border: 1px solid rgba(15, 118, 110, 0.1) !important;
            }}

            .stMetric label {{
                color: var(--regchem-muted) !important;
            }}

            div[data-testid="stDecoration"] {{
                background-image: linear-gradient(
                    90deg,
                    var(--regchem-teal-primary),
                    var(--regchem-teal-glow)
                );
            }}

            .regchem-kpi {{
                border-radius: 14px;
                padding: 1.15rem 1.25rem;
                background: var(--regchem-surface-card);
                border: 1px solid rgba(11, 18, 32, 0.06);
                border-left-width: 4px;
                box-shadow: 0 14px 36px rgba(11, 18, 32, 0.07);
                min-height: 92px;
            }}

            .regchem-kpi-label {{
                font-size: 0.72rem;
                font-weight: 600;
                letter-spacing: 0.06em;
                text-transform: uppercase;
                color: var(--regchem-muted);
                margin-bottom: 0.4rem;
            }}

            .regchem-kpi-value {{
                font-size: 1.6rem;
                font-weight: 700;
                color: var(--regchem-ink);
                letter-spacing: -0.025em;
                line-height: 1.12;
            }}

            .regchem-kpi-foot {{
                margin-top: 0.4rem;
                font-size: 0.8rem;
                color: var(--regchem-muted);
                line-height: 1.4;
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
                padding: 0.38rem 0.72rem;
                border-radius: 999px;
                font-size: 0.8rem;
                font-weight: 600;
                border: 1px solid rgba(11, 18, 32, 0.06);
                background: var(--regchem-surface-card);
                box-shadow: 0 2px 8px rgba(11, 18, 32, 0.04);
            }}

            .regchem-chip--low {{
                border-color: rgba(20, 184, 169, 0.35);
                color: #0f766e;
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
                padding: 0.75rem 1rem;
                background: linear-gradient(
                    92deg,
                    rgba(20, 184, 169, 0.08) 0%,
                    var(--regchem-surface-card) 88%
                );
                border-radius: 10px;
                box-shadow: 0 8px 24px rgba(11, 18, 32, 0.06);
                color: var(--regchem-ink);
                font-size: 0.92rem;
                line-height: 1.55;
            }}

            .regchem-shell-header {{
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                justify-content: space-between;
                gap: 0.75rem 1.25rem;
                padding: 1rem 1.15rem 1.05rem;
                margin-bottom: 1.35rem;
                border-radius: 16px;
                background: var(--regchem-surface-card);
                border: 1px solid rgba(11, 18, 32, 0.06);
                box-shadow: 0 12px 40px rgba(11, 18, 32, 0.06);
            }}

            .regchem-shell-header h1 {{
                margin: 0 !important;
                font-size: 1.35rem !important;
                font-weight: 700 !important;
                letter-spacing: -0.03em !important;
                color: var(--regchem-navy-deep) !important;
            }}

            .regchem-shell-header .regchem-product-tag {{
                font-size: 0.68rem;
                font-weight: 700;
                letter-spacing: 0.12em;
                text-transform: uppercase;
                color: var(--regchem-teal-soft);
                opacity: 0.95;
            }}

            .regchem-shell-header .regchem-footnote {{
                color: #475569 !important;
            }}

            .regchem-status-row {{
                display: flex;
                flex-wrap: wrap;
                gap: 0.45rem;
                align-items: center;
                justify-content: flex-end;
            }}

            .regchem-pill {{
                display: inline-flex;
                align-items: center;
                gap: 0.35rem;
                padding: 0.28rem 0.65rem;
                border-radius: 999px;
                font-size: 0.75rem;
                font-weight: 600;
                letter-spacing: 0.02em;
                background: rgba(11, 18, 32, 0.04);
                border: 1px solid rgba(11, 18, 32, 0.07);
                color: #334155;
            }}

            .regchem-pill-dot {{
                width: 7px;
                height: 7px;
                border-radius: 50%;
                background: var(--regchem-teal-primary);
                box-shadow: 0 0 0 3px rgba(20, 184, 169, 0.22);
            }}

            .regchem-pill--prod .regchem-pill-dot {{
                background: var(--regchem-teal-soft);
                box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.2);
            }}

            .regchem-pill--alt .regchem-pill-dot {{
                background: #64748b;
                box-shadow: none;
            }}

            .regchem-sidebar-brand {{
                padding: 0.15rem 0 0.35rem;
            }}

            .regchem-sidebar-brand-line {{
                font-size: 1.15rem;
                font-weight: 700;
                letter-spacing: -0.02em;
                color: #f8fafc !important;
                margin: 0;
            }}

            .regchem-sidebar-brand-sub {{
                margin: 0.35rem 0 0;
                font-size: 0.82rem;
                line-height: 1.45;
                color: #94a3b8 !important;
            }}

            .regchem-sidebar-section {{
                font-size: 0.68rem;
                font-weight: 700;
                letter-spacing: 0.14em;
                text-transform: uppercase;
                color: #64748b !important;
                margin: 1rem 0 0.45rem;
            }}

            .regchem-card-surface {{
                border-radius: 16px;
                padding: 1.35rem 1.45rem;
                background: var(--regchem-surface-card);
                border: 1px solid rgba(11, 18, 32, 0.06);
                box-shadow: 0 14px 40px rgba(11, 18, 32, 0.06);
                margin-bottom: 1.25rem;
            }}

            .regchem-provenance-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 0.75rem 1.25rem;
                margin-top: 0.5rem;
            }}

            .regchem-prov-item dt {{
                font-size: 0.68rem;
                font-weight: 700;
                letter-spacing: 0.08em;
                text-transform: uppercase;
                color: var(--regchem-muted);
                margin: 0 0 0.2rem;
            }}

            .regchem-prov-item dd {{
                margin: 0;
                font-size: 0.88rem;
                font-weight: 500;
                color: var(--regchem-ink);
                font-variant-numeric: tabular-nums;
                word-break: break-all;
            }}

            .regchem-page-eyebrow {{
                font-size: 0.72rem;
                font-weight: 700;
                letter-spacing: 0.12em;
                text-transform: uppercase;
                color: var(--regchem-teal-soft);
                margin-bottom: 0.35rem;
            }}

            .regchem-page-lede {{
                font-size: 1.02rem;
                line-height: 1.65;
                color: #475569;
                max-width: 52rem;
                margin: 0 0 1.25rem;
            }}

            .regchem-step-track {{
                display: flex;
                flex-wrap: wrap;
                gap: 0.5rem;
                margin: 0.75rem 0 1rem;
            }}

            .regchem-step-dot {{
                display: inline-flex;
                align-items: center;
                gap: 0.45rem;
                padding: 0.35rem 0.75rem;
                border-radius: 999px;
                font-size: 0.78rem;
                font-weight: 600;
                color: #475569;
                background: rgba(11, 18, 32, 0.04);
                border: 1px solid rgba(11, 18, 32, 0.06);
            }}

            .regchem-step-dot strong {{
                color: var(--regchem-navy-deep);
                font-weight: 700;
            }}

            .regchem-results-panel {{
                border-radius: 16px;
                padding: 1.35rem 1.45rem 1.15rem;
                margin: 1rem 0;
                background: linear-gradient(
                    145deg,
                    rgba(20, 184, 169, 0.06) 0%,
                    var(--regchem-surface-card) 38%
                );
                border: 1px solid rgba(20, 184, 169, 0.14);
                box-shadow: 0 16px 42px rgba(11, 18, 32, 0.07);
            }}

            .regchem-results-panel h3 {{
                margin-top: 0 !important;
            }}

            .regchem-onboarding-card {{
                background: var(--regchem-surface-card);
                border: 1px solid {CARD_BORDER};
                border-radius: 14px;
                padding: 1.25rem 1.35rem;
                margin-bottom: 1rem;
                box-shadow: 0 14px 36px rgba(11, 18, 32, 0.06);
            }}

            .regchem-onboarding-card h4 {{
                color: var(--regchem-teal-soft) !important;
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

            /* Bordered workspace cards: keep native controls readable on light surfaces. */
            .main div[data-testid="stVerticalBlockBorderWrapper"] .stRadio label,
            .main div[data-testid="stVerticalBlockBorderWrapper"] .stRadio > div > label {{
                color: var(--regchem-ink) !important;
            }}
            .main div[data-testid="stVerticalBlockBorderWrapper"] .stMarkdown {{
                color: var(--regchem-ink);
            }}

            /*
             * Main workspace — WCAG AA-friendly controls (Classify + other pages).
             * Force light-well inputs and high-contrast buttons on the central column only.
             */
            section[data-testid="stMain"] .stMarkdown p,
            section[data-testid="stMain"] .stMarkdown li,
            section[data-testid="stMain"] .stMarkdown span[data-testid="stMarkdownSpan"] {{
                color: var(--regchem-ink);
            }}

            section[data-testid="stMain"] [data-testid="stCaptionContainer"] {{
                color: #475569 !important;
            }}

            section[data-testid="stMain"] label,
            section[data-testid="stMain"] [data-testid="stWidgetLabel"] p {{
                color: #0f172a !important;
            }}

            section[data-testid="stMain"] [data-baseweb="textarea"] textarea,
            section[data-testid="stMain"] [data-testid="stTextArea"] textarea {{
                background-color: #ffffff !important;
                background: #ffffff !important;
                color: #0f172a !important;
                border: 2px solid #94a3b8 !important;
                border-radius: 12px !important;
                caret-color: #0f172a !important;
            }}

            section[data-testid="stMain"] [data-testid="stTextArea"] textarea:focus {{
                border-color: {TEAL_SOFT} !important;
                box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.22) !important;
                outline: none !important;
            }}

            section[data-testid="stMain"] [data-testid="stTextArea"] textarea::placeholder {{
                color: #64748b !important;
                opacity: 1 !important;
            }}

            section[data-testid="stMain"] [data-testid="stTextInput"] input {{
                background-color: #ffffff !important;
                color: #0f172a !important;
                border: 2px solid #94a3b8 !important;
                border-radius: 10px !important;
            }}

            section[data-testid="stMain"] [data-testid="stTextInput"] input:focus {{
                border-color: {TEAL_SOFT} !important;
                box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.2) !important;
                outline: none !important;
            }}

            section[data-testid="stMain"] pre,
            section[data-testid="stMain"] div[data-testid="stCode"] code {{
                background-color: #f1f5f9 !important;
                color: #0f172a !important;
                border: 1px solid #cbd5e1 !important;
                border-radius: 8px !important;
            }}

            /* Expanders — keep header text dark on light surfaces */
            section[data-testid="stMain"] [data-testid="stExpander"] summary,
            section[data-testid="stMain"] details summary {{
                color: #0b1220 !important;
                font-weight: 600 !important;
            }}

            section[data-testid="stMain"] [data-testid="stExpander"] svg {{
                fill: #0f172a !important;
            }}

            /* Primary CTAs — teal fill, white label (AAA on fill) */
            section[data-testid="stMain"] button[kind="primary"],
            section[data-testid="stMain"] .stButton > button[kind="primary"] {{
                background-color: {TEAL_SOFT} !important;
                background-image: none !important;
                border: 2px solid #0f766e !important;
                color: #ffffff !important;
                font-weight: 600 !important;
                box-shadow: 0 2px 10px rgba(15, 118, 110, 0.25) !important;
            }}

            section[data-testid="stMain"] button[kind="primary"]:hover {{
                background-color: #115e56 !important;
                border-color: #134e47 !important;
                color: #ffffff !important;
            }}

            /* Secondary — light fill, decisive border & ink text (fixes low-contrast preview button) */
            section[data-testid="stMain"] button[kind="secondary"],
            section[data-testid="stMain"] .stButton > button[kind="secondary"],
            section[data-testid="stMain"] div[data-testid="column"] button[kind="secondary"] {{
                background-color: #ffffff !important;
                border: 2px solid #334155 !important;
                color: #0f172a !important;
                font-weight: 600 !important;
            }}

            section[data-testid="stMain"] button[kind="secondary"]:hover {{
                background-color: #f0fdfa !important;
                border-color: {TEAL_SOFT} !important;
                color: #0b352f !important;
            }}

            section[data-testid="stMain"] .stDownloadButton button {{
                background-color: #ffffff !important;
                border: 2px solid #334155 !important;
                color: #0f172a !important;
                font-weight: 600 !important;
            }}

            section[data-testid="stMain"] .stDownloadButton button:hover {{
                background-color: #f0fdfa !important;
                border-color: {TEAL_SOFT} !important;
            }}

            section[data-testid="stMain"] .stButton > button[disabled],
            section[data-testid="stMain"] button[disabled] {{
                opacity: 0.52 !important;
                border-style: dashed !important;
            }}

            section[data-testid="stMain"] button[kind="primary"]:focus-visible,
            section[data-testid="stMain"] button[kind="secondary"]:focus-visible,
            section[data-testid="stMain"] .stDownloadButton button:focus-visible {{
                outline: 3px solid #0f766e !important;
                outline-offset: 2px !important;
            }}

            /* Radio pills on light cards */
            section[data-testid="stMain"] [data-baseweb="radio"] label,
            section[data-testid="stMain"] div[data-testid="stMarkdownContainer"] ul li {{
                color: #1e293b;
            }}

            /* Toggle + file uploader copy */
            section[data-testid="stMain"] [data-testid="stFileUploader"] section,
            section[data-testid="stMain"] [data-testid="stFileUploader"] small {{
                color: #334155 !important;
            }}

            [data-testid="stMarkdownContainer"] a {{
                color: var(--regchem-teal-soft) !important;
            }}

            hr {{
                margin: 1.6rem 0;
                border: none;
                border-top: 1px solid rgba(15, 118, 110, 0.14);
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def canonical_snapshot_sha256(snapshot: SentinelPipelineSnapshot) -> str:
    """SHA-256 of canonical JSON — matches storage hashing for provenance labels (UI-only)."""

    payload = snapshot.model_dump(mode="json")
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def render_app_shell_header(
    container: Any,
    *,
    settings: Settings,
    page_title: str,
    page_subtitle: str,
) -> None:
    """Branded main-area header with calm status cues (no raw connection strings)."""

    env_norm = (settings.app_env or "").strip().lower()
    is_prod = env_norm == "production"
    env_label = settings.app_env or "unknown"
    persist_label = (
        "Durable ledger" if settings.storage_backend == "sqlite" else "In-memory session"
    )
    pill_env_class = "regchem-pill regchem-pill--prod" if is_prod else "regchem-pill regchem-pill--alt"

    container.markdown(
        f"""
        <div class="regchem-shell-header">
            <div>
                <div class="regchem-product-tag">Quanta</div>
                <h1>{page_title}</h1>
                <p class="regchem-footnote" style="margin:0.35rem 0 0; max-width:40rem;">{page_subtitle}</p>
            </div>
            <div class="regchem-status-row">
                <span class="{pill_env_class}"><span class="regchem-pill-dot"></span> {env_label}</span>
                <span class="regchem-pill"><span class="regchem-pill-dot"></span> {persist_label}</span>
                <span class="regchem-pill regchem-pill--alt"><span class="regchem-pill-dot"></span> {settings.build_id}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_validation_footer(container: Any) -> None:
    """Compact decision-support disclaimer for page bottoms."""

    container.markdown(
        """
        <div class="regchem-banner" style="margin-top:1.75rem;">
            <strong>For decision-support only.</strong> Outputs are not a validated system of record, are not
            substitutes for qualified human review, and must be mapped to controlled sources under your quality system
            before reliance in GxP or regulatory submissions.
        </div>
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
