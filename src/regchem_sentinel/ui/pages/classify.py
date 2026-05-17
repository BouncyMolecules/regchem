"""Interactive classify workspace — parse through persist with explicit DI."""

from __future__ import annotations

import hashlib
import html
import io
import json
import uuid
from typing import Any

import pandas as pd

from regchem_sentinel.config import Settings
from regchem_sentinel.core.models import (
    DetectorTier,
    ParsedSubmission,
    SentinelPipelineSnapshot,
    StartingMaterial,
    VerificationStatus,
)
# Graph-memory / continual-learning modules import payloads from ``models`` only; persisted ORM tables are
# centralized in that module alongside ``extend_existing`` metadata guards.
from regchem_sentinel.core.graph_memory import GraphCorpusStats, GraphMemoryWriteSummary
from regchem_sentinel.core.continual_learning import (
    FeedbackKind,
    GraphFeedbackWriteSummary,
    RiskForecastLine,
    build_regulatory_risk_forecast,
)
from regchem_sentinel.core.storage import StorageWriteError
from regchem_sentinel.main import SentinelDependencies, parse_submission, run_pipeline
from regchem_sentinel.ui.utils import theme

_BULK_HINT = (
    "**CSV:** UTF-8; columns **`correlation_id`** and **`text`** (header row optional). "
    "**Paste:** same columns row-by-row, or merge with an uploaded file."
)

_PLACEHOLDER_PRIMARY = """Paste verbatim CMC narrative from your submission package (3.2.S.2.x, smChange, or supplier response). Example:

Starting material SM-04 (CAS 123-45-6) is the registered intermediate manufactured at Oceanic API Partners Ltd. (Site O-112) under DMF 12,345. The final API is synthesized at our Rockford finishing site from SM-04 via the hydrogenolysis step described in S.2.2/S.2.3…

Tip: insert a form-feed character between pages if you want paging preserved in the parse preview.
"""


def _ui_gen_key(st: Any) -> int:
    if "classify_ui_nonce" not in st.session_state:
        st.session_state["classify_ui_nonce"] = 0
    return int(st.session_state["classify_ui_nonce"])


def _ui_escape(text: object) -> str:
    """Escape strings embedded in ``unsafe_allow_html`` markdown; flatten stray tuples defensively."""

    if isinstance(text, tuple):
        flat = " ".join(str(part).strip() for part in text if str(part).strip())
        return html.escape(flat)
    return html.escape(str(text))


def _classify_page_css(st: Any) -> None:
    st.markdown(
        """
        <style>
            .regchem-classify-textarea-hint {
                font-size: 0.88rem;
                color: #334155;
                margin: -0.25rem 0 0.75rem;
                line-height: 1.45;
            }
            /*
             * Post-classification result: explicit “paper” surfaces — ink-forward body copy (AA+ on white).
             */
            .regchem-soft-card {
                color: #0f172a !important;
                background: #ffffff !important;
                border: 1px solid rgba(15, 23, 42, 0.12) !important;
                box-shadow: 0 10px 28px rgba(11, 18, 32, 0.06) !important;
            }
            .regchem-soft-card h4 {
                color: #0b1220 !important;
            }
            .regchem-soft-muted {
                color: #334155 !important;
            }
            .regchem-soft-card .regchem-soft-muted {
                color: #334155 !important;
            }
            p.regchem-forecast-echo {
                margin: 0;
                font-size: 0.82rem;
                font-weight: 650;
                color: #1e293b !important;
            }
            .regchem-story-card-lite {
                color: #0f172a !important;
                background: #ffffff !important;
            }
            .regchem-story-heading {
                color: #0b1220 !important;
            }
            .regchem-story-lede {
                color: #1e293b !important;
            }
            ul.regchem-calm-list,
            ul.regchem-calm-steps {
                color: #1e293b !important;
            }
            p.regchem-prose-relaxed {
                color: #1e293b !important;
            }
            html[data-theme="dark"] .regchem-soft-card,
            section[data-testid="stAppViewContainer"][data-theme="dark"] .regchem-soft-card,
            [data-baseweb-theme="dark"] .regchem-soft-card {
                background: #f8fafc !important;
                border-color: rgba(148, 163, 184, 0.45) !important;
                color: #0f172a !important;
            }
            html[data-theme="dark"] .regchem-story-card-lite,
            section[data-testid="stAppViewContainer"][data-theme="dark"] .regchem-story-card-lite {
                background: #f8fafc !important;
                border-color: rgba(148, 163, 184, 0.4) !important;
                color: #0f172a !important;
            }
            /* Readable text inside bordered Streamlit containers (avoids washed / mismatched inheritance). */
            .main div[data-testid="stVerticalBlockBorderWrapper"]
                div[data-testid="stMarkdownContainer"] :not(pre):not(code) {
                color: #0f172a;
            }
            .main div[data-testid="stVerticalBlockBorderWrapper"]
                div[data-testid="stMarkdownContainer"] strong {
                color: #0b1220;
            }
            /* Alert boxes — ensure body copy stays dark on tinted surfaces. */
            .main div[data-testid="stAlert"] div[data-testid="stMarkdownContainer"],
            .main div[data-testid="stAlert"] div[data-testid="stMarkdownContainer"] p,
            .main div[data-testid="stAlert"] div[data-testid="stMarkdownContainer"] li,
            .main div[data-testid="stAlert"] div[data-testid="stMarkdownContainer"] span {
                color: #0f172a !important;
            }
            /* Classify page: captions stay readable (not washed gray) */
            .main div[data-testid="stCaptionContainer"] {
                color: #334155 !important;
            }
            .regchem-plain-callout {
                border-radius: 14px;
                padding: 1.15rem 1.35rem;
                margin: 0 0 1.25rem;
                background: linear-gradient(120deg, rgba(20, 184, 169, 0.09) 0%, #ffffff 55%);
                border: 1px solid rgba(20, 184, 169, 0.22);
                box-shadow: 0 12px 32px rgba(11, 18, 32, 0.06);
                color: #0f172a;
                font-size: 1.02rem;
                line-height: 1.62;
            }
            .regchem-plain-eyebrow {
                font-size: 0.7rem;
                font-weight: 700;
                letter-spacing: 0.14em;
                text-transform: uppercase;
                color: #0f766e;
                margin-bottom: 0.45rem;
            }
            .regchem-plain-callout .regchem-plain-eyebrow {
                margin-bottom: 0.45rem;
            }
            .regchem-story-shell {
                border-radius: 16px;
                padding: 0.25rem 0 1.35rem;
                margin: 0 0 1.5rem;
            }
            .regchem-soft-card {
                border-radius: 14px;
                padding: 1.05rem 1.2rem 1rem;
                margin: 0.65rem 0 0;
                /* layout-only; contrast tokens live in earlier .regchem-soft-card block */
            }
            .regchem-soft-card h4 {
                margin: 0 0 0.45rem !important;
                font-size: 0.94rem !important;
                font-weight: 650 !important;
                letter-spacing: -0.02em !important;
            }
            .regchem-soft-muted {
                font-size: 0.86rem;
                line-height: 1.55;
                margin: 0;
            }
            .regchem-provenance-compact dt {
                font-size: 0.65rem;
                font-weight: 700;
                letter-spacing: 0.07em;
                text-transform: uppercase;
                color: #475569;
                margin: 0 0 0.15rem;
            }
            .regchem-provenance-compact dd {
                margin: 0 0 0.85rem;
                font-size: 0.82rem;
                color: #1e293b;
                word-break: break-all;
            }
            .regchem-result-break {
                height: 1.25rem;
            }
            .regchem-soft-sep {
                border: none;
                border-top: 1px solid rgba(15, 118, 110, 0.12);
                margin: 1.65rem 0;
            }
            .regchem-story-card-lite {
                border-radius: 16px;
                padding: 1.25rem 1.35rem 1.05rem;
                margin: 0 0 1.1rem;
                border: 1px solid rgba(11, 18, 32, 0.07);
                box-shadow: 0 8px 26px rgba(11, 18, 32, 0.04);
            }
            .regchem-story-heading {
                margin: 0 0 0.55rem;
                font-size: 1.05rem;
                font-weight: 650;
                letter-spacing: -0.02em;
                line-height: 1.3;
            }
            .regchem-story-lede {
                font-size: 0.95rem;
                line-height: 1.55;
                margin: 0 0 0.65rem;
            }
            ul.regchem-calm-list {
                margin: 0.35rem 0 0;
                padding-left: 1.15rem;
                font-size: 0.92rem;
                line-height: 1.55;
            }
            ul.regchem-calm-list li {
                margin-bottom: 0.45rem;
            }
            /* Post-classification: calm rhythm + glanceable anchors */
            .regchem-result-rail {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: 0.5rem;
                margin: 0 0 0.35rem;
            }
            .regchem-result-chip {
                display: inline-flex;
                align-items: baseline;
                gap: 0.35rem;
                padding: 0.34rem 0.78rem;
                border-radius: 999px;
                font-size: 0.78rem;
                font-weight: 650;
                letter-spacing: 0.02em;
                color: #0b1220;
                background: rgba(20, 184, 169, 0.12);
                border: 1px solid rgba(15, 118, 110, 0.28);
            }
            .regchem-result-chip-num {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 1.15rem;
                height: 1.15rem;
                border-radius: 50%;
                font-size: 0.68rem;
                font-weight: 700;
                color: #ffffff;
                background: #0f766e;
                flex-shrink: 0;
            }
            .regchem-result-gap {
                height: 2.35rem;
            }
            .regchem-result-gap-sm {
                height: 1.35rem;
            }
            p.regchem-prose-relaxed {
                margin: 0 0 1rem;
                font-size: 0.96rem;
                line-height: 1.62;
            }
            p.regchem-prose-relaxed:last-child {
                margin-bottom: 0;
            }
            ul.regchem-calm-steps {
                margin: 0.15rem 0 0;
                padding-left: 1.2rem;
                font-size: 0.94rem;
                line-height: 1.6;
                list-style-position: outside;
            }
            ul.regchem-calm-steps li {
                margin: 0.55rem 0;
                padding-left: 0.2rem;
            }
            /* —— Classification result: narrative rhythm + teaching-the-desk prominence —— */
            .regchem-result-hero {
                border-radius: 18px;
                padding: 1.35rem 1.5rem 1.2rem;
                margin: 0 0 1.75rem;
                background: linear-gradient(
                    125deg,
                    rgba(20, 184, 169, 0.11) 0%,
                    #ffffff 48%,
                    #f8fafc 100%
                );
                border: 1px solid rgba(15, 118, 110, 0.2);
                box-shadow: 0 14px 40px rgba(11, 18, 32, 0.07);
            }
            .regchem-result-hero h2.regchem-result-title {
                margin: 0 0 0.35rem !important;
                font-size: 1.35rem !important;
                font-weight: 700 !important;
                letter-spacing: -0.03em !important;
                color: #0b1220 !important;
            }
            .regchem-result-hero p.regchem-result-sub {
                margin: 0 !important;
                font-size: 0.98rem;
                line-height: 1.55;
                color: #1e293b !important;
                max-width: 46rem;
            }
            .regchem-section-eyebrow {
                font-size: 0.7rem;
                font-weight: 700;
                letter-spacing: 0.14em;
                text-transform: uppercase;
                color: #0f766e;
                margin: 0 0 0.4rem;
            }
            .regchem-section-title {
                margin: 0 0 0.65rem !important;
                font-size: 1.08rem !important;
                font-weight: 650 !important;
                letter-spacing: -0.02em !important;
                line-height: 1.28 !important;
                color: #0b1220 !important;
            }
            .regchem-section-hint {
                margin: -0.35rem 0 1rem !important;
                font-size: 0.92rem;
                line-height: 1.55;
                color: #334155 !important;
            }
            div[data-testid="stVerticalBlockBorderWrapper"].regchem-story-section-wrap {
                margin-bottom: 1.25rem !important;
            }
            /* Classify page KPIs — elevate label + footnote contrast (page-local stylesheet only). */
            .main .regchem-kpi-label,
            .main .regchem-kpi-foot {
                color: #334155 !important;
            }
            .main .regchem-kpi-value {
                color: #0b1220 !important;
            }
            /* Teaching the Desk — inviting, high-contrast focal card */
            .regchem-teach-desk-shell {
                border-radius: 18px;
                padding: 0.2rem;
                margin: 0 0 1.65rem;
                background: linear-gradient(
                    135deg,
                    rgba(20, 184, 169, 0.45) 0%,
                    rgba(15, 118, 110, 0.12) 42%,
                    rgba(11, 18, 32, 0.04) 100%
                );
                box-shadow: 0 18px 48px rgba(11, 18, 32, 0.08);
            }
            .regchem-teach-desk-inner {
                border-radius: 16px;
                padding: 1.45rem 1.5rem 1.35rem;
                background: #ffffff;
                border: 1px solid rgba(15, 118, 110, 0.18);
            }
            .regchem-teach-desk-inner .regchem-teach-kicker {
                font-size: 0.72rem;
                font-weight: 700;
                letter-spacing: 0.12em;
                text-transform: uppercase;
                color: #0f766e;
                margin: 0 0 0.5rem;
            }
            .regchem-teach-desk-inner h3.regchem-teach-title {
                margin: 0 0 0.5rem !important;
                font-size: 1.2rem !important;
                font-weight: 700 !important;
                color: #0b1220 !important;
                letter-spacing: -0.025em !important;
            }
            .regchem-teach-desk-inner p.regchem-teach-lede {
                margin: 0 !important;
                font-size: 0.98rem;
                line-height: 1.6;
                color: #1e293b !important;
            }
            .regchem-teach-desk-shell {
                margin-bottom: 0.75rem !important;
            }
            /* Result actions — secondary CTAs read as tappable */
            .regchem-result-actions-panel {
                border-radius: 16px;
                padding: 1.15rem 1.15rem 1.05rem;
                margin: 0.5rem 0 1rem;
                background: #f1f5f9;
                border: 1px solid rgba(11, 18, 32, 0.08);
            }
            .regchem-result-actions-panel .regchem-section-eyebrow {
                margin-bottom: 0.75rem;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _excerpt_fingerprint(excerpt: str) -> str:
    return hashlib.sha256(excerpt.strip().encode("utf-8")).hexdigest()


def _normalize_bulk_columns(raw: pd.DataFrame) -> pd.DataFrame | None:
    """Return a dataframe with correlation_id / text columns, or None if unusable."""

    if raw.empty or len(raw.columns) < 2:
        return None
    trimmed = raw.copy()
    trim_cols: list[str] = []
    for col in trimmed.columns:
        base = str(col).strip().lower().replace(" ", "_")
        synonyms = {
            "correlation_id": "correlation_id",
            "correlation": "correlation_id",
            "corr_id": "correlation_id",
            "audit_id": "correlation_id",
            "id": "correlation_id",
            "submission": "text",
            "submission_excerpt": "text",
            "excerpt": "text",
            "narrative": "text",
            "body": "text",
        }
        mapped = synonyms.get(base, base)
        trim_cols.append(mapped if mapped in frozenset({"correlation_id", "text"}) else base)
    trimmed.columns = trim_cols
    if "correlation_id" not in trimmed.columns or "text" not in trimmed.columns:
        if len(trimmed.columns) >= 2:
            trimmed = trimmed.iloc[:, :2].copy()
            trimmed.columns = ["correlation_id", "text"]
        else:
            return None
    return trimmed[["correlation_id", "text"]]


def _rows_from_optional_csv_string(payload: str) -> list[tuple[str, str]]:
    """Parse pasted CSV-ish text."""

    stripe = payload.strip()
    if not stripe:
        return []
    try:
        frame = pd.read_csv(io.StringIO(stripe))
    except Exception:
        return []
    norm = _normalize_bulk_columns(frame)
    if norm is None:
        return []
    rows: list[tuple[str, str]] = []
    for _, row in norm.iterrows():
        cid_val = row.get("correlation_id")
        text_raw = row.get("text")
        cid = "" if cid_val is None or (isinstance(cid_val, float) and pd.isna(cid_val)) else str(cid_val).strip()
        text_str = ""
        if text_raw is not None and not (isinstance(text_raw, float) and pd.isna(text_raw)):
            text_str = str(text_raw).strip()
        if cid or text_str:
            rows.append((cid, text_str))
    return rows


def _gather_bulk_rows(uploaded_df: pd.DataFrame | None, pasted: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if uploaded_df is not None and not uploaded_df.empty:
        norm_up = _normalize_bulk_columns(uploaded_df)
        if norm_up is not None:
            for _, row in norm_up.iterrows():
                cid_raw, text_raw = row["correlation_id"], row["text"]
                cid = str(cid_raw).strip() if pd.notna(cid_raw) else ""
                ts = str(text_raw).strip() if pd.notna(text_raw) else ""
                rows.append((cid, ts))
    rows.extend(_rows_from_optional_csv_string(pasted))

    consolidated: dict[str, str] = {}
    order_keys: list[str] = []
    for cid_in, excerpt in rows:
        cid_eff = cid_in.strip() or uuid.uuid4().hex
        if cid_eff not in consolidated:
            order_keys.append(cid_eff)
        consolidated[cid_eff] = excerpt
    return [(k, consolidated[k]) for k in order_keys]


def _primary_tier_label(snapshot: SentinelPipelineSnapshot) -> tuple[str, str]:
    """Return (display tier name, slug) for headline KPI."""

    if not snapshot.findings:
        return ("No SM hypothesis surfaced", "none")
    finding = snapshot.findings[0]
    merged = finding.tier or finding.classification.suggested_material_tier
    if merged is None:
        return ("Unassigned tier", "unassigned")
    friendly = merged.value.replace("_", " ").title()
    return (friendly, merged.value)


def _confidence_span(snapshot: SentinelPipelineSnapshot) -> tuple[str, str]:
    aggregates = tuple(f.classification.tiered_confidence.aggregate for f in snapshot.findings)
    if not aggregates:
        return ("—", "—")
    lo = min(aggregates)
    hi = max(aggregates)
    if abs(hi - lo) < 0.02:
        return (f"{hi:.0%}", f"{hi:.2f}")
    return (f"{lo:.0%} – {hi:.0%}", f"min {lo:.2f} / max {hi:.2f}")


def _practice_reminder_paragraph(_snapshot: SentinelPipelineSnapshot) -> str:
    """Anchor the read in procedures — keeps Section 2 actionable without duplicating model outputs."""

    return (
        "**Your controls still decide:** map every surfaced name, site code, and filing statement to the registrations, "
        "DMFs/CEPs, and quality agreements your quality system already treats as authoritative."
    )


def _primary_tier_slug(snapshot: SentinelPipelineSnapshot) -> str:
    """Slug used for workstation memory tallies."""

    if not snapshot.findings:
        return "none"
    merged = snapshot.findings[0].tier or snapshot.findings[0].classification.suggested_material_tier
    return merged.value if merged is not None else "unassigned"


def _opening_meaning_paragraph(snapshot: SentinelPipelineSnapshot) -> str:
    """Plain-language bridge from model outputs to what a regulatory owner should actually do."""

    tier_disp, tier_slug = _primary_tier_label(snapshot)
    conf_disp, _ = _confidence_span(snapshot)
    aggregates = tuple(f.classification.tiered_confidence.aggregate for f in snapshot.findings)

    acc = sum(1 for v in snapshot.verifications if v.status is VerificationStatus.ACCEPTED)
    rev = sum(1 for v in snapshot.verifications if v.status is VerificationStatus.REVIEW_REQUIRED)
    rej = sum(1 for v in snapshot.verifications if v.status is VerificationStatus.REJECTED)

    blocks: list[str] = []

    if not snapshot.findings:
        blocks.append(
            "**Emphasis tag:** Quanta did **not** surface a starting-material storyline in this excerpt. "
            "That usually means the clip is tight or the wording lacks the cues we listen for — "
            "not that your dossier lacks starting materials elsewhere."
        )
    elif "tier_1" in tier_slug:
        blocks.append(
            f"**What “{tier_disp}” means:** the language **resembles how registered-route starting materials are "
            f"often narrated** in CMC sections. It is **pattern recognition on text**, not a determination from any "
            f"health authority, and **not** a replacement for your controlled register."
        )
    elif "tier_2" in tier_slug:
        blocks.append(
            f"**What “{tier_disp}” means:** the excerpt **mixes filing-style facts with supporting story**. "
            "Use the tag to **route the paragraph to an SME**, then confirm names, sites, and attachments against "
            "approved sources."
        )
    elif "tier_3" in tier_slug:
        blocks.append(
            f"**What “{tier_disp}” means:** cues lean on **background wording** more than crisp registry statements. "
            "Expect to **pair this narrative with tables or registrations** before treating the tag as settled."
        )
    else:
        blocks.append(
            f"**What “{tier_disp}” means:** treat it as a **draft routing hint** from wording alone until your "
            "internal taxonomy / QA classification agrees."
        )

    if aggregates:
        lo = min(aggregates)
        if lo < 0.55:
            strength = "That lands in a **tentative** band — widen the excerpt or pull primary sources before you rely on it."
        elif lo < 0.80:
            strength = (
                "That sits in a **moderately supportive** band — helpful directionally, but still deserves the usual "
                "document cross-check."
            )
        else:
            strength = (
                "That sits in a **stronger-agreement** band for this paste, yet **does not replace** structured evidence."
            )
        blocks.append(
            f"**What the confidence score ({conf_disp}) means:** it measures **how strongly wording cues lined up** "
            "inside this excerpt — similar to an internal agreement meter. "
            f"{strength} "
            "It is **not** an approval probability and **not** an Agency communication risk score."
        )
    else:
        blocks.append("**Confidence:** not reported because no storyline rows were produced for this excerpt.")

    if rej:
        blocks.append(
            f"**Verifier flags — blocked ({rej}):** automated checks saw **hard mismatches** between inferred claims "
            "and this excerpt. **Pause outbound reuse** until QA reconciles the wording with controlled records."
        )
    elif rev:
        blocks.append(
            f"**Verifier flags — review ({rev}):** something needs **human confirmation** (sites, MF/DMF scope, "
            "roles, or wording alignment). Log the follow-up in your quality tools before calling the paragraph clean."
        )
    else:
        blocks.append(
            f"**Verifier flags — accepted ({acc}):** no automated stop signals on this clip. "
            "**Accepted only means “nothing algorithmic contradicted the excerpt here.”** "
            "Perform your normal attestations against ECM-linked sources regardless."
        )

    return "\n\n".join(blocks)


def _plain_language_regulatory(snapshot: SentinelPipelineSnapshot) -> str:
    """Compat alias — same wording as the guided story opener."""

    return _opening_meaning_paragraph(snapshot)


def _what_we_found_sentence(snapshot: SentinelPipelineSnapshot) -> str:
    """Step 1 snapshot — facts first, minimal jargon."""

    tier_disp, _slug = _primary_tier_label(snapshot)
    conf_disp, _ = _confidence_span(snapshot)
    review_n = sum(1 for v in snapshot.verifications if v.status is VerificationStatus.REVIEW_REQUIRED)
    rejected_n = sum(1 for v in snapshot.verifications if v.status is VerificationStatus.REJECTED)

    if not snapshot.findings:
        lead = (
            f"We **did not** detect a starting-material storyline in this excerpt. "
            f"The residual label reads **{tier_disp}** with blended confidence **{conf_disp}**."
        )
    else:
        lead = (
            f"We surfaced **{len(snapshot.findings)}** storyline row(s) labeled **{tier_disp}** "
            f"with blended confidence **{conf_disp}**."
        )

    if rejected_n:
        tail = (
            f"The verifier **blocked {rejected_n}** automated check(s) — **stop and reconcile** with controlled wording "
            "before reuse."
        )
    elif review_n:
        tail = (
            f"The verifier marked **{review_n}** check(s) for **explicit human review** before circulation."
        )
    else:
        tail = (
            "The verifier raised **no automated blocks** on this excerpt — still complete your usual documentary "
            "spot-checks."
        )

    return f"{lead}\n\n{tail}"


def _guided_next_steps_body(snapshot: SentinelPipelineSnapshot) -> str:
    """Step 3 — concrete moves an RA/CMC lead can hand to QA."""

    review_n = sum(1 for v in snapshot.verifications if v.status is VerificationStatus.REVIEW_REQUIRED)
    rejected_n = sum(1 for v in snapshot.verifications if v.status is VerificationStatus.REJECTED)

    if not snapshot.findings:
        return (
            '<ul class="regchem-calm-steps">'
            "<li>Expand the excerpt until registered names, sites, and route language are plainly visible.</li>"
            "<li>Save this correlation ID beside the ECM snippet reviewers will cite.</li>"
            "</ul>"
        )
    lines_open = (
        '<ul class="regchem-calm-steps">'
        "<li>Compare each surfaced substance and manufacturing site to your approved register and quality agreements.</li>"
        "<li>Attach the verbatim excerpt plus this correlation ID (and hashes from History) to your change record.</li>"
    )
    if rejected_n:
        lines_close = (
            "<li>Do **not** reuse disputed wording externally until QA closes each blocked verifier row.</li>"
        )
    elif review_n:
        lines_close = (
            "<li>Assign owners for every review-required verifier row and capture dispositions in your tracking tool.</li>"
        )
    else:
        lines_close = (
            "<li>Pick two high-impact claims (typically supplier scope or registered route language) and confirm them "
            "against ECM before broader circulation.</li>"
        )
    return lines_open + lines_close + "</ul>"


def _pattern_memory_friend_paragraphs(
    snapshot: SentinelPipelineSnapshot,
    *,
    write_summary: GraphMemoryWriteSummary,
    corpus: GraphCorpusStats,
) -> tuple[str, ...]:
    """Two or three calm sentences — no graph jargon."""

    snaps = write_summary.hyperedge_events
    paragraphs: list[str] = [
        (
            f"Quanta tucked away **{snaps}** tiny 'who showed up alongside whom' summaries for this passage on "
            "**this workstation only**. They only polish tomorrow's skim; they never rewrite the read you see above."
        ),
    ]

    new_n = write_summary.new_hyperedges
    strong_n = write_summary.strengthened_hyperedges
    if new_n and strong_n:
        paragraphs.append(
            f"**{new_n}** pairing(s) looked new here today, while **{strong_n}** pairing(s) echoed earlier saves "
            "and grew a notch more familiar."
        )
    elif new_n:
        paragraphs.append(f"**{new_n}** pairing(s) had not appeared in your local history until this paste.")
    elif strong_n:
        paragraphs.append(
            f"**{strong_n}** pairing(s) matched past saves closely — helpful when today mirrors earlier filings."
        )
    else:
        paragraphs.append(
            "Your local familiarity barely budged — think of this as a quiet rerun of wording you already trust."
        )

    tier_slug = _primary_tier_slug(snapshot)
    seen = corpus.tier_touch_counts.get(tier_slug, 0)
    total = corpus.total_ledger_events
    if total > 0:
        share = min(100, max(0, int(round(100 * seen / max(total, 1)))))
        paragraphs.append(
            f"**Local comparison only:** about **{share}%** of similarly tagged saves on this workstation looked like "
            "today's read — a coarse echo, **not** a KPI or forecast."
        )

    return tuple(paragraphs[:3])


def _render_result_story_rail(st: Any) -> None:
    st.markdown(
        """
        <div class="regchem-result-rail" aria-hidden="true">
          <span class="regchem-result-chip"><span class="regchem-result-chip-num">1</span> What we found</span>
          <span class="regchem-result-chip"><span class="regchem-result-chip-num">2</span> What it means</span>
          <span class="regchem-result-chip"><span class="regchem-result-chip-num">3</span> What to do next</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_interpretation_expander(st: Any, snapshot: SentinelPipelineSnapshot) -> None:
    """Plain-language implication summary — explanatory only."""

    tiers = tuple(f.tier or f.classification.suggested_material_tier for f in snapshot.findings)
    tier_names = [t.value.replace("_", " ") for t in tiers if t]
    uniq_tiers = sorted(set(tier_names))
    max_t1_direct = False
    for f in snapshot.findings:
        for contrib in f.classification.rule_contributions:
            if contrib.matched and contrib.detector_tier is DetectorTier.TIER_1_DIRECT_REGISTRATION_LANGUAGE:
                max_t1_direct = True

    aggregates = tuple(f.classification.tiered_confidence.aggregate for f in snapshot.findings)
    weak_context = any(a < 0.72 for a in aggregates) if aggregates else False
    mid_signal = aggregates and sum(aggregates) / len(aggregates) >= 0.82

    acc = sum(1 for v in snapshot.verifications if v.status is VerificationStatus.ACCEPTED)
    rev = sum(1 for v in snapshot.verifications if v.status is VerificationStatus.REVIEW_REQUIRED)
    rej = sum(1 for v in snapshot.verifications if v.status is VerificationStatus.REJECTED)

    with st.expander("Still curious — optional SME notes", expanded=False):
        st.markdown(
            "Interpretation reflects **automated scaffolding** mapped to dossier excerpts. "
            "It does not replace SME review against approved registrations and quality agreements."
        )
        st.markdown("###### Verifier posture (this correlation)")
        if rej:
            st.warning(
                f"One or more verifier assertions are **rejected** ({rej} row(s)). "
                "Treat as a hard stop until claims are reconciled with controlled dossier wording."
            )
        elif rev:
            st.info(
                f"**Human adjudication cues** ({rev}) — cross-check surfaced claims vs. registrations, "
                "DMFs, CEPS, sites, and test lab scope before filing or closure."
            )
        else:
            st.success(
                f"Recorded **accepted** verifier posture on {acc} assertion(s); "
                "still confirm lineage to source documents per internal procedure."
            )
        st.markdown("###### Classification signal strength")
        if not snapshot.findings:
            st.caption(
                "No starting-material hypotheses surfaced — wording may omit typical registry cues "
                "(or excerpts are truncated relative to dossier)."
            )
        else:
            if max_t1_direct:
                st.caption(
                    "Direct registration-style language cues were triggered for at least one entity. "
                    "Expect stronger linkage to dossier-listed starting materials pending SME mapping."
                )
            elif mid_signal:
                st.caption(
                    "Confidence aggregates sit in an intermediate band — plausible SM associations exist, "
                    "but corroborating structural or tabular excerpts should be gathered before decisions."
                )
            if weak_context:
                st.caption(
                    "**Background wording** carried more weight than registry phrases for some rows — tier tags stay "
                    "draft until registrations or tables back them."
                )
            if uniq_tiers:
                st.caption(
                    f"Suggested regulatory emphasis tiers present: `{', '.join(uniq_tiers)}`. "
                    "Tier labels are heuristic — align with regional guidance and QA classification."
                )
            else:
                st.caption(
                    "Material tier suggestions were ambiguous for some rows — escalate for taxonomy alignment."
                )
        st.markdown("###### Practical next steps (RegOps)")
        st.markdown(
            "- Preserve this correlation identifier in your change/deviation artefact bundle.\n"
            "- Paste or attach the verbatim submission span used here into your ECM trail.\n"
            "- Queue supplier statements and CoA scope where verifier cues mention external parties.\n"
            "- If verifier status is review-required, annotate the disposition in your QA tracking tool."
        )


def _dataframe_from_snapshot(cid: str, snapshot: SentinelPipelineSnapshot) -> dict[str, object]:
    accepted_n = sum(1 for v in snapshot.verifications if v.status is VerificationStatus.ACCEPTED)
    review_n = sum(
        1 for v in snapshot.verifications if v.status is VerificationStatus.REVIEW_REQUIRED
    )
    rejected_n = sum(1 for v in snapshot.verifications if v.status is VerificationStatus.REJECTED)

    aggregates = tuple(f.classification.tiered_confidence.aggregate for f in snapshot.findings)
    agg_min = min(aggregates) if aggregates else None
    agg_max = max(aggregates) if aggregates else None

    def _tier_slug(finding: StartingMaterial) -> str:
        merged = finding.tier or finding.classification.suggested_material_tier
        return merged.value if merged is not None else "unassigned"

    tiers = tuple(_tier_slug(f) for f in snapshot.findings)
    return {
        "correlation_id": cid,
        "findings_count": len(snapshot.findings),
        "tier_hints": "; ".join(dict.fromkeys(tiers)),
        "confidence_min": f"{agg_min:.2f}" if agg_min is not None else "—",
        "confidence_max": f"{agg_max:.2f}" if agg_max is not None else "—",
        "verifier_accepted": accepted_n,
        "verifier_review": review_n,
        "verifier_rejected": rejected_n,
        "sha256_short": snapshot.parsed_submission.content_sha256[:12],
    }


def _snapshot_detail_tables(st: Any, snapshot: SentinelPipelineSnapshot, cid: str) -> None:
    findings_rows: list[dict[str, object]] = []
    for finding in snapshot.findings:
        findings_rows.append(
            {
                "canonical_name": finding.canonical_name,
                "tier": finding.tier.value if finding.tier else "unassigned",
                "evidence": "; ".join(span.excerpt for span in finding.justification.evidence),
                "correlation_id": finding.justification.correlation_id,
            },
        )

    supplier_rows: list[dict[str, object]] = []
    for supplier in snapshot.suppliers:
        supplier_rows.append(
            {
                "supplier": supplier.supplier_display_name,
                "role": supplier.role.value,
                "linked_materials": ", ".join(supplier.linked_material_names),
            },
        )

    verification_rows: list[dict[str, object]] = []
    for assertion in snapshot.verifications:
        verification_rows.append(
            {
                "claim": assertion.claim_summary,
                "status": assertion.status.value,
                "notes": assertion.reviewer_notes or "",
            },
        )

    accepted_n = sum(1 for v in snapshot.verifications if v.status is VerificationStatus.ACCEPTED)
    review_n = sum(
        1 for v in snapshot.verifications if v.status is VerificationStatus.REVIEW_REQUIRED
    )
    rejected_n = sum(1 for v in snapshot.verifications if v.status is VerificationStatus.REJECTED)

    with st.expander("Technical artefacts & row-level tables", expanded=False):
        with st.expander("Serialized pipeline snapshot (JSON)", expanded=False):
            st.download_button(
                label="Download snapshot JSON",
                data=snapshot.model_dump_json(indent=2),
                file_name=f"quanta_snapshot_{cid}.json",
                mime="application/json",
                key=f"download_snapshot_json_{cid}",
            )
            st.json(json.loads(snapshot.model_dump_json()))

        st.subheader("Findings")
        st.dataframe(pd.DataFrame(findings_rows), use_container_width=True, hide_index=True)

        st.subheader("Supplier linkages")
        st.dataframe(pd.DataFrame(supplier_rows), use_container_width=True, hide_index=True)

        st.subheader("Verification")
        st.markdown("##### Verifier posture (this run)")
        theme.render_verifier_chips(st, accepted=accepted_n, review_required=review_n, rejected=rejected_n)
        st.dataframe(pd.DataFrame(verification_rows), use_container_width=True, hide_index=True)

        st.markdown(
            f"**Content SHA-256:** `{snapshot.parsed_submission.content_sha256}` · "
            f"**Pages detected:** `{len(snapshot.parsed_submission.segments)}`",
        )


def _render_parse_preview(st: Any, parsed: ParsedSubmission) -> None:
    st.markdown("##### What we understood (parse-only)")
    c1, c2 = st.columns(2)
    with c1:
        st.metric("Fingerprinted segments", len(parsed.segments))
    with c2:
        st.metric("Characters ingested", f"{len(parsed.full_text):,}")

    head = parsed.segments[0].text.strip().replace("\n", " ")
    if len(head) > 320:
        head = head[:320] + "…"
    st.caption("Opening segment preview (verbatim)")
    st.code(head or "—", language=None)

    st.caption(
        f"SHA-256: `{parsed.content_sha256[:20]}…` · Parser: `{parsed.audit.parser_name}` v`{parsed.audit.parser_version}`"
    )


def _render_run_provenance(
    st: Any,
    *,
    cid: str,
    snapshot: SentinelPipelineSnapshot,
    settings: Settings,
    persisted: bool | None,
) -> None:
    digest = theme.canonical_snapshot_sha256(snapshot)
    audit = snapshot.parsed_submission.audit
    parser_line = html.escape(audit.parser_name or "—")
    parser_ver = html.escape(audit.parser_version or "—")
    corr = html.escape(cid)
    content_sha = html.escape(snapshot.parsed_submission.content_sha256)
    digest_esc = html.escape(digest)
    build_esc = html.escape(settings.build_id)
    if persisted is True:
        persist_dd = "Written to durable ledger (same digest as storage canonical JSON)"
    elif persisted is False:
        persist_dd = "Workshop mode — pipeline executed, persistence toggled off for this run"
    else:
        persist_dd = "—"

    st.markdown(
        f"""
        <div class="regchem-card-surface">
            <div class="regchem-page-eyebrow">Run provenance · immutable references</div>
            <p class="regchem-footnote" style="margin-top:0;">
                Identifiers below tether this screen to hashes and parser versions. The <strong>canonical snapshot digest</strong>
                mirrors the sorted JSON checksum used when snapshots are persisted (recomputed here for labeling only).
            </p>
            <dl class="regchem-provenance-grid">
                <div class="regchem-prov-item">
                    <dt>Correlation ID</dt><dd>{corr}</dd>
                </div>
                <div class="regchem-prov-item">
                    <dt>Submission content (SHA-256)</dt><dd>{content_sha}</dd>
                </div>
                <div class="regchem-prov-item">
                    <dt>Canonical snapshot digest (SHA-256)</dt><dd>{digest_esc}</dd>
                </div>
                <div class="regchem-prov-item">
                    <dt>Deterministic parser</dt><dd>{parser_line} · v{parser_ver}</dd>
                </div>
                <div class="regchem-prov-item">
                    <dt>Release tag</dt><dd>{build_esc}</dd>
                </div>
                <div class="regchem-prov-item">
                    <dt>Persistence posture</dt><dd>{html.escape(persist_dd)}</dd>
                </div>
            </dl>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_graph_insights_panel(
    st: Any,
    *,
    snapshot: SentinelPipelineSnapshot,
    deps: SentinelDependencies,
) -> None:
    """Workstation familiarity — wording only."""

    write_summary = deps.storage.last_graph_memory_write()
    if write_summary is None:
        return
    corpus = deps.storage.graph_memory_corpus_stats()

    digest = html.escape(write_summary.snapshot_canonical_sha256[:18])
    chain = write_summary.last_entry_hash_hex
    chain_note = (
        f"Latest save links to `{html.escape(chain[:18])}…` in your local sequence."
        if chain
        else "Sequence chain not yet present for this workstation state."
    )

    with st.container(border=True):
        st.markdown(
            '<p class="regchem-page-eyebrow">Pattern memory · local context</p>',
            unsafe_allow_html=True,
        )
        st.markdown("##### How today lines up with past saves on this workstation")
        st.markdown(
            '<p class="regchem-story-lede" style="margin:0 0 1rem;">Quiet background from earlier reads you stored '
            "here — same facts as always, folded into teammate language.</p>",
            unsafe_allow_html=True,
        )
        paras = _pattern_memory_friend_paragraphs(snapshot, write_summary=write_summary, corpus=corpus)
        for ix, paragraph in enumerate(paras):
            st.markdown(paragraph)
            if ix < len(paras) - 1:
                st.markdown('<div class="regchem-result-gap-sm"></div>', unsafe_allow_html=True)
        st.markdown('<div class="regchem-result-gap-sm"></div>', unsafe_allow_html=True)
        st.caption(
            "**Privacy:** nothing in this panel leaves your device. History exports keep hashes if auditors need a trail."
        )
        st.caption(f"Snapshot fingerprint `{digest}…` · {chain_note}")


def _forecast_story_title_and_blurb(index: int, line: RiskForecastLine) -> tuple[str, str]:
    """UI-only friendly labels for deterministic forecast lines."""

    pct = line.probability_percent
    if index == 0:
        return (
            "Room for post-submission questions",
            (
                f"About {pct}% of comparable passages on this machine historically needed another clarifying pass — "
                "think resourcing, not predictions about agencies."
            ),
        )
    if index == 1:
        return (
            "Budget one more expert pass",
            (
                f"Roughly {pct}% of similar reads here attracted a second regulatory eye before language froze — "
                "helpful for staffing stories, not headcount math."
            ),
        )
    return (
        "Advanced-therapy stories often invite another CMC polish",
        "Because the excerpt hints at ATMP-style work, we nudge the planning cue slightly — still derived "
        f"only from your text and what is saved locally (about {pct}% in this framing).",
    )


def _render_regulatory_risk_forecast(st: Any, *, snapshot: SentinelPipelineSnapshot, deps: SentinelDependencies) -> None:
    """Local-graph regulatory simulation — no external inference."""

    write_summary = deps.storage.last_graph_memory_write()
    corpus = deps.storage.graph_memory_corpus_stats()
    forecast = build_regulatory_risk_forecast(
        snapshot=snapshot,
        corpus=corpus,
        write_summary=write_summary,
    )

    with st.container(border=True):
        st.markdown(
            '<p class="regchem-page-eyebrow">Planning cue · local history only</p>',
            unsafe_allow_html=True,
        )
        st.markdown("##### Gentle workload hints from past saves on this machine")
        st.markdown(
            '<p class="regchem-story-lede" style="margin:0 0 1rem;">Percentages are **planning shorthand** '
            "mirroring similar excerpts already stored here. They are **not** Agency probabilities, deficiency "
            "signals, or staffing promises.</p>",
            unsafe_allow_html=True,
        )
        if not forecast.lines:
            st.markdown(
                "**No scenarios yet.** Once enough comparable passages exist in your local history, soft workload hints "
                "will appear in this panel."
            )
        else:
            for idx, line in enumerate(forecast.lines):
                if idx:
                    st.markdown('<div class="regchem-result-gap-sm"></div>', unsafe_allow_html=True)
                title, blurb = _forecast_story_title_and_blurb(idx, line)
                title_safe = _ui_escape(title)
                blurb_safe = _ui_escape(blurb)
                st.markdown(
                    f"""
                    <div class="regchem-soft-card">
                        <h4>{title_safe}</h4>
                        <p class="regchem-soft-muted" style="margin:0 0 0.35rem;">{blurb_safe}</p>
                        <p class="regchem-forecast-echo">Echo from similar past excerpts · ~{line.probability_percent}%</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                with st.expander("Supporting detail (technical readout)", expanded=False):
                    st.markdown(line.basis)

        st.caption(
            f"Replay fingerprint `{forecast.provenance_digest_sha256[:16]}…` · Inputs: {forecast.inputs_summary}. "
            "Derived locally only."
        )
        with st.expander("Blend label for audits", expanded=False):
            st.code(forecast.formula_id, language=None)


def _render_classification_feedback(
    st: Any,
    *,
    snapshot: SentinelPipelineSnapshot,
    deps: SentinelDependencies,
    cid_show: str,
    pipeline_run_id: str | None,
) -> None:
    """User-in-the-loop continual learning controls."""

    digest_short = theme.canonical_snapshot_sha256(snapshot)[:16]
    ack_key = f"classify_feedback_ack_{cid_show}_{digest_short}"

    st.markdown(
        """
        <div class="regchem-teach-desk-shell">
            <div class="regchem-teach-desk-inner">
                <p class="regchem-teach-kicker">Optional · sharpens tomorrow&rsquo;s skim on this machine</p>
                <h3 class="regchem-teach-title">Teaching the Desk</h3>
                <p class="regchem-teach-lede">
                    One honest tap tells us whether this read matches how your team routes the dossier.
                    Your note stays on <strong>this workstation only</strong> and never rewrites the result above.
                </p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        fb_labels: dict[str, FeedbackKind] = {
            "Yes — matches how we read the dossier": "correct",
            "Mostly — tweak emphasis or wording": "needs_adjustment",
            "No — emphasis tag feels wrong here": "wrong_tier",
        }
        choice = st.radio(
            "Where did Quanta land versus your reviewer instinct?",
            tuple(fb_labels.keys()),
            horizontal=True,
            key=f"classify_feedback_choice_{cid_show}_{digest_short}",
            help="Optional. Saved with the same audit trail as classification runs.",
            label_visibility="visible",
        )
        submitted = st.button(
            "Save my perspective locally",
            key=f"classify_feedback_submit_{cid_show}_{digest_short}",
            type="primary",
            use_container_width=True,
        )

        if submitted:
            kind: FeedbackKind = fb_labels[choice]
            try:
                summary: GraphFeedbackWriteSummary = deps.storage.append_classification_feedback(
                    snapshot,
                    kind,
                    pipeline_run_id=pipeline_run_id,
                )
            except StorageWriteError as exc:
                st.error("We couldn't store that preference — disk space or database permissions blocked the write.")
                with st.expander("Technical detail"):
                    st.exception(exc)
            else:
                st.session_state[ack_key] = {
                    "bundle_id": summary.feedback_bundle_public_id,
                    "events": summary.hyperedge_events,
                    "chain": summary.last_ledger_entry_hash_hex,
                }
                st.success("Noted — thank you. The storyline above stays exactly as generated.")
                st.caption(
                    f"Reference `{summary.feedback_bundle_public_id}` · "
                    f"{summary.hyperedge_events} local relationship reminder(s) refreshed · "
                    f"audit tail `{summary.last_ledger_entry_hash_hex}`"
                )

        ack = st.session_state.get(ack_key)
        if isinstance(ack, dict) and ack.get("bundle_id") and not submitted:
            st.info(
                f"You already weighed in for this fingerprint — reference `{ack['bundle_id']}` "
                f"({ack.get('events', 0)} reminder(s) stored)."
            )


def render(st: Any, *, deps: SentinelDependencies, settings: Settings) -> None:
    _classify_page_css(st)

    nonce = _ui_gen_key(st)
    primary_key = f"classify_primary_text_{nonce}"
    last_hash_key = "classify_last_preview_hash"
    parsed_cache_key = "classify_cached_parsed"

    if "classify_last_result" not in st.session_state:
        st.session_state["classify_last_result"] = None

    st.markdown('<div class="regchem-page-eyebrow">Intake rhythm</div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="regchem-step-track">
            <span class="regchem-step-dot"><strong>1</strong> Paste verbatim excerpt</span>
            <span class="regchem-step-dot"><strong>2</strong> Preview parsing</span>
            <span class="regchem-step-dot"><strong>3</strong> Classify & capture provenance</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="regchem-page-lede" style="margin-bottom:1rem;">Lead with the narrative you intend to cite. '
        "Optional batch tools stay tucked away so single-change reviews stay quiet and fast.</p>",
        unsafe_allow_html=True,
    )

    default_corr = uuid.uuid4().hex
    with st.container(border=True):
        st.markdown("##### Primary paste · verbatim CMC narrative")
        submission_raw = st.text_area(
            "Narrative body",
            height=320,
            placeholder=_PLACEHOLDER_PRIMARY,
            help=(
                "Match ECM excerpts you will cite; form-feed page breaks are honored by the deterministic segmenter."
            ),
            key=primary_key,
            label_visibility="collapsed",
        )
        st.markdown(
            '<p class="regchem-classify-textarea-hint">Fast path for smChange snippets, gateway responses, and SME '
            "spot-checks — keep language identical to the controlled package you will reference.</p>",
            unsafe_allow_html=True,
        )
    submission = submission_raw if isinstance(submission_raw, str) else ""

    with st.expander("Batch CSV, reference files, and throughput tools", expanded=False):
        st.caption(_BULK_HINT)
        sec_left, sec_right = st.columns(2)
        with sec_left:
            st.markdown("**CSV batch (bulk classify)**")
            bulk_upload = st.file_uploader(
                "Upload UTF-8 CSV",
                type=["csv"],
                accept_multiple_files=False,
                key="bulk_classify_upload",
                help="Columns **correlation_id** + **text**.",
                label_visibility="collapsed",
            )
            uploaded_df: pd.DataFrame | None = None
            if bulk_upload is not None:
                uploaded_df = pd.read_csv(io.BytesIO(bulk_upload.getvalue()))
            bulk_paste_area = st.text_area(
                "Or paste CSV rows",
                height=140,
                placeholder='correlation_id,text\n"CHG-1024","Starting material RM-42 is …"',
                help="Quoted fields keep commas inside **text**.",
                key="bulk_classify_paste",
                label_visibility="visible",
            )
        with sec_right:
            st.markdown("**PDF or Word (reference)**")
            st.caption(
                "Upload **`.pdf`** or **`.docx`** for your local trace. The classifier consumes the **paste area "
                "above** — extract the passage in Acrobat/Word, then paste verbatim. "
                "(Native text extraction is not enabled in this Quanta build.)"
            )
            ref_docs = st.file_uploader(
                "Attach PDF / Word",
                type=["pdf", "docx"],
                accept_multiple_files=True,
                key="classify_ref_docs_upload",
                label_visibility="collapsed",
            )
            if ref_docs:
                names = ", ".join(getattr(f, "name", "document") for f in ref_docs)
                st.success(f"**Reference on file (UI trace):** {names}")

    st.markdown("---")

    with st.expander("Advanced options (correlation ID, persistence, glossary)", expanded=False):
        col_a, col_b = st.columns(2)
        with col_a:
            correlation_id = st.text_input(
                "Correlation / audit identifier",
                value=default_corr,
                help="Maps to ECM / QMS artefacts (deviation IDs, gateways).",
                key="classify_correlation_input",
            )
        with col_b:
            persist_choice = st.toggle(
                "Persist snapshot + ledger row",
                value=True,
                help="Off = workshop mode; verifier still runs.",
                key="single_persist_toggle",
            )
        st.caption("Persistence defaults **on** for audit-ready traces.")
        st.markdown(
            "**Pipeline glossary** — **Parse** fingerprints text; **Classify** tiers SM hypotheses; "
            "**Supplier linkage** maps parties; **Verifier** surfaces adjudication cues."
        )

    cid_raw = st.session_state.get("classify_correlation_input", default_corr)
    if not isinstance(cid_raw, str):
        cid_raw = default_corr
    cid = (cid_raw or "").strip() or default_corr

    preview_clicked = st.button(
        "Preview & parse",
        type="secondary",
        help="Deterministic segmentation only — no classifier yet.",
        key="classify_preview_parse",
        use_container_width=True,
    )

    excerpt = submission.strip()
    raw_cached = st.session_state.get(parsed_cache_key)
    parsed_preview: ParsedSubmission | None = (
        raw_cached if isinstance(raw_cached, ParsedSubmission) else None
    )

    if preview_clicked:
        if not excerpt:
            st.warning("Add narrative text before running preview.")
            st.session_state[last_hash_key] = None
            st.session_state[parsed_cache_key] = None
        else:
            try:
                parsed_preview = parse_submission(excerpt)
            except Exception as exc:  # pragma: no cover - defensive UI
                st.error("Parse could not complete for this excerpt.")
                st.exception(exc)
                parsed_preview = None
                st.session_state[last_hash_key] = None
                st.session_state[parsed_cache_key] = None
            else:
                st.session_state[last_hash_key] = _excerpt_fingerprint(excerpt)
                st.session_state[parsed_cache_key] = parsed_preview
                st.success("Parse preview ready — review what Quanta understood, then classify.")

    fp_now = _excerpt_fingerprint(excerpt) if excerpt else None
    last_prev = st.session_state.get(last_hash_key)
    preview_ok = (
        bool(excerpt)
        and fp_now is not None
        and isinstance(last_prev, str)
        and last_prev == fp_now
    )
    if (
        excerpt
        and isinstance(last_prev, str)
        and last_prev
        and fp_now is not None
        and last_prev != fp_now
    ):
        st.info("Text changed since the last preview — run **Preview & parse** again before classifying.")

    if parsed_preview is not None and preview_ok:
        with st.container(border=True):
            st.markdown("### Parse preview")
            st.caption("Confirm what Quanta understood before invoking classification.")
            _render_parse_preview(st, parsed_preview)
        st.markdown("---")

    classify_clicked = st.button(
        "Classify now",
        type="primary",
        disabled=not preview_ok,
        help="Runs the full Quanta pipeline (same fidelity as bulk).",
        key="regchem_single_run",
        use_container_width=True,
    )

    snapshot: SentinelPipelineSnapshot | None = None

    if classify_clicked:
        if not preview_ok:
            st.warning("Run **Preview & parse** on the current text first.")
        else:
            cid_in = st.session_state.get("classify_correlation_input", default_corr)
            if not isinstance(cid_in, str):
                cid_in = default_corr
            cid = (cid_in or "").strip() or default_corr
            with st.spinner("Executing parse → classify → supplier link → verify → persist …"):
                try:
                    snapshot = run_pipeline(
                        excerpt,
                        correlation_id=cid,
                        deps=deps,
                        persist=persist_choice,
                    )
                except ValueError as exc:
                    st.error(f"Validation blocked the run — {exc}")
                    snapshot = None
                except StorageWriteError as exc:
                    st.error(
                        "Persistence refused the snapshot. Verify disk space, SQLite permissions, and "
                        "that the correlation identifier meets storage invariants.",
                    )
                    with st.expander("Technical detail"):
                        st.exception(exc)
                    snapshot = None
                except Exception as exc:
                    st.error(
                        "Unexpected orchestration fault — preserve console logs and escalate per your "
                        "deviation playbook.",
                    )
                    st.exception(exc)
                    snapshot = None

            if snapshot is not None:
                st.session_state["classify_last_result"] = {
                    "cid": cid,
                    "snapshot": snapshot,
                    "persist": persist_choice,
                    "excerpt_fp": fp_now,
                    "pipeline_run_id": deps.storage.last_persisted_pipeline_run_id()
                    if persist_choice
                    else None,
                }
                st.success("Run captured — walk through your read below when you have a calm minute.")

    result = st.session_state.get("classify_last_result")
    if isinstance(result, dict) and result.get("snapshot") is not None:
        snap_show: SentinelPipelineSnapshot = result["snapshot"]
        cid_show = str(result.get("cid") or cid)

        st.markdown("---")
        cid_esc = html.escape(cid_show)
        st.markdown(
            f"""
            <div class="regchem-result-hero">
                <p class="regchem-section-eyebrow" style="margin-bottom:0.35rem;">Classification result</p>
                <h2 class="regchem-result-title">Your read — composed in three beats</h2>
                <p class="regchem-result-sub">
                    <strong>Finding</strong>, then <strong>meaning in practice</strong> (tier, confidence, verifier),
                    then <strong>sensible next steps</strong> — before optional context panels and exports below.
                </p>
                <p class="regchem-result-sub" style="margin-top:0.85rem;font-size:0.93rem;color:#334155;">
                    <strong>Correlation</strong> · <span style="font-variant-numeric:tabular-nums;">{cid_esc}</span>
                    &mdash; keep this screen beside the pasted excerpt.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if result.get("excerpt_fp") != fp_now:
            st.warning(
                "Primary narrative changed since this run — numbers below reflect the earlier excerpt until you "
                "classify again."
            )

        _render_result_story_rail(st)
        st.markdown('<div class="regchem-result-gap-sm"></div>', unsafe_allow_html=True)

        with st.container(border=True):
            st.markdown(
                '<p class="regchem-section-title">Here&#8217;s what we found</p>',
                unsafe_allow_html=True,
            )
            st.markdown(
                '<p class="regchem-section-hint" style="margin-top:-0.25rem;">Facts from this excerpt only.</p>',
                unsafe_allow_html=True,
            )
            st.markdown(_what_we_found_sentence(snap_show))

            tier_disp, _tier_slug = _primary_tier_label(snap_show)
            conf_disp, _ = _confidence_span(snap_show)
            review_n = sum(1 for v in snap_show.verifications if v.status is VerificationStatus.REVIEW_REQUIRED)
            rejected_n = sum(1 for v in snap_show.verifications if v.status is VerificationStatus.REJECTED)
            band = theme.kpi_band_for_verifier_counts(review=review_n, rejected=rejected_n)

            st.markdown('<div class="regchem-result-gap-sm"></div>', unsafe_allow_html=True)
            k1, k2, k3 = st.columns(3)
            theme.render_kpi_card(
                k1,
                title="Emphasis tag",
                value=tier_disp,
                band="neutral",
                footnote="From wording patterns — not an Agency determination",
            )
            theme.render_kpi_card(
                k2,
                title="Model confidence",
                value=conf_disp,
                band=band,
                footnote="Agreement meter on this excerpt — not approval odds",
            )
            theme.render_kpi_card(
                k3,
                title="Verifier strip",
                value="Quiet" if rejected_n == 0 and review_n == 0 else "Needs routing",
                band=band,
                footnote=f"{review_n} review · {rejected_n} blocked — automated claim checks only",
            )

        st.markdown('<div class="regchem-result-gap"></div>', unsafe_allow_html=True)

        with st.container(border=True):
            st.markdown(
                '<p class="regchem-section-title">Here&#8217;s what it means in practice</p>',
                unsafe_allow_html=True,
            )
            st.markdown(
                '<p class="regchem-section-hint" style="margin-top:-0.25rem;">Plain-language read on tier tag, '
                "confidence band, and verifier posture &mdash; still not a substitute for your controlled register.</p>",
                unsafe_allow_html=True,
            )
            st.markdown(_opening_meaning_paragraph(snap_show))
            st.markdown('<div class="regchem-result-gap-sm"></div>', unsafe_allow_html=True)
            st.markdown(_practice_reminder_paragraph(snap_show))
            st.caption(
                "Quanta is decision-support software — your controlled registrations, agreements, and ECM excerpts "
                "remain the evidence package."
            )

        st.markdown('<div class="regchem-result-gap"></div>', unsafe_allow_html=True)

        with st.container(border=True):
            st.markdown(
                '<p class="regchem-section-title">Here&#8217;s what you should consider next</p>',
                unsafe_allow_html=True,
            )
            st.markdown(
                '<p class="regchem-section-hint" style="margin-top:-0.25rem;">Practical moves your RA / CMC leads '
                "can track &mdash; governed by your internal SOPs.</p>",
                unsafe_allow_html=True,
            )
            st.markdown(_guided_next_steps_body(snap_show), unsafe_allow_html=True)

        st.markdown('<div class="regchem-result-gap"></div>', unsafe_allow_html=True)

        pl_run = result.get("pipeline_run_id")
        pl_run_typed: str | None = pl_run if (pl_run is None or isinstance(pl_run, str)) else None
        _render_classification_feedback(
            st,
            snapshot=snap_show,
            deps=deps,
            cid_show=cid_show,
            pipeline_run_id=pl_run_typed,
        )

        st.markdown('<div class="regchem-result-gap-sm"></div>', unsafe_allow_html=True)

        _render_regulatory_risk_forecast(st, snapshot=snap_show, deps=deps)

        st.markdown('<div class="regchem-result-gap-sm"></div>', unsafe_allow_html=True)

        _render_graph_insights_panel(st, snapshot=snap_show, deps=deps)

        st.markdown('<div class="regchem-result-gap-sm"></div>', unsafe_allow_html=True)

        with st.expander("Integrity trail — correlation, hashes & parser (open anytime)", expanded=False):
            _render_run_provenance(
                st,
                cid=cid_show,
                snapshot=snap_show,
                settings=settings,
                persisted=result.get("persist") if isinstance(result.get("persist"), bool) else None,
            )

        st.markdown(
            """
            <div class="regchem-result-actions-panel">
                <p class="regchem-section-eyebrow">When you&#8217;re ready</p>
                <p class="regchem-section-title" style="margin-bottom:0.35rem;">Move this run forward</p>
                <p style="margin:0;font-size:0.92rem;line-height:1.55;color:#334155;">
                    Save, route, or export &mdash; the technical row tables stay below if you need depth.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        b1, b2 = st.columns(2)
        b3, b4 = st.columns(2)
        with b1:
            if st.button("Save & classify another", key="classify_action_reset", use_container_width=True):
                st.session_state["classify_last_result"] = None
                st.session_state[last_hash_key] = None
                st.session_state[parsed_cache_key] = None
                st.session_state["classify_ui_nonce"] = nonce + 1
                st.rerun()
        with b2:
            if st.button("Save as draft (session)", key="classify_action_draft", use_container_width=True):
                drafts = st.session_state.setdefault("classify_session_drafts", [])
                drafts.append(
                    {
                        "correlation_id": cid_show,
                        "excerpt_fp": result.get("excerpt_fp"),
                        "saved_at_hint": "browser session only",
                    }
                )
                st.toast("Draft pointer saved for this browser session — sync to your ECM separately.", icon="📝")
        with b3:
            if st.button("Route for review", key="classify_action_route", use_container_width=True):
                st.info(
                    f"**Route package** · correlation `{cid_show}` — attach verifier table + SHA-256 from History, "
                    "and link this Quanta run ID in your QA tool / gated workflow."
                )
        with b4:
            st.download_button(
                label="Export audit bundle (JSON)",
                data=snap_show.model_dump_json(indent=2),
                file_name=f"quanta_audit_bundle_{cid_show}.json",
                mime="application/json",
                key=f"classify_export_bundle_{cid_show}",
                use_container_width=True,
            )

        _render_interpretation_expander(st, snap_show)

        st.caption(
            f"Segmentation footprint: **{len(snap_show.parsed_submission.segments)}** logical page(s) · "
            f"verbatim character span hashed above."
        )

        _snapshot_detail_tables(st, snap_show, cid_show)

    # --- Bulk classify (unchanged orchestration, progressive placement) ---
    with st.expander("Batch throughput · CSV bulk classify (same engine)", expanded=False):
        st.markdown(_BULK_HINT)
        bulk_opts = st.columns(2)
        with bulk_opts[0]:
            bulk_persist = st.toggle(
                "Persist each bulk snapshot (+ ledger)",
                value=True,
                help="Unchecked still runs verifier logic but skips persistence for that row.",
                key="bulk_classify_persist_toggle",
            )
        with bulk_opts[1]:
            st.caption("Keep batches ≤50 correlations per run for workstation responsiveness.")

        bulk_clicked = st.button(
            "Run bulk classification",
            type="secondary",
            key="regchem_bulk_run",
            use_container_width=True,
        )

        bulk_row_cap = 50
        if bulk_clicked:
            rows = _gather_bulk_rows(uploaded_df, bulk_paste_area)
            if not rows:
                st.warning(
                    "No ingestible bulk rows — populate **correlation_id** + **text**, or paste equivalent rows "
                    "in the batch panel.",
                )
            else:
                truncated = rows
                if len(rows) > bulk_row_cap:
                    truncated = rows[:bulk_row_cap]

                prog = st.progress(0)
                summaries: list[dict[str, object]] = []
                errors_rows: list[dict[str, str]] = []

                total = len(truncated)
                for seq, (cid_eff, row_excerpt) in enumerate(truncated, start=1):
                    prog.progress(int(seq / max(total, 1) * 100))
                    excerpt_stripped = row_excerpt.strip()
                    if not excerpt_stripped:
                        errors_rows.append(
                            {"correlation_id": cid_eff, "reason": "Empty submission excerpt."},
                        )
                        continue

                    cid_use = cid_eff.strip() or uuid.uuid4().hex
                    try:
                        snap_bulk = run_pipeline(
                            excerpt_stripped,
                            correlation_id=cid_use,
                            deps=deps,
                            persist=bulk_persist,
                        )
                    except ValueError as exc:
                        errors_rows.append({"correlation_id": cid_use, "reason": str(exc)})
                        continue
                    except StorageWriteError:
                        errors_rows.append(
                            {
                                "correlation_id": cid_use,
                                "reason": "Persistence refused snapshot — inspect disk/sqlite permits.",
                            },
                        )
                        continue
                    except Exception as exc:
                        errors_rows.append(
                            {"correlation_id": cid_use, "reason": f"Unhandled fault — {exc!s}"},
                        )
                        continue

                    summaries.append(_dataframe_from_snapshot(cid_use, snap_bulk))

                prog.progress(100)

                notice_frag = ""
                if len(rows) > bulk_row_cap:
                    notice_frag = f" Showing first **{bulk_row_cap}** of {len(rows)} correlations."

                st.success(
                    "Bulk classification sweep finished — triage outliers, then adjudicate verifier cues per SOP."
                    + notice_frag
                    + " Use **History** for full JSON replay.",
                )

                if summaries:
                    st.subheader("Bulk summary")
                    frame_sum = pd.DataFrame(summaries)
                    st.dataframe(frame_sum, use_container_width=True, hide_index=True)

                with st.expander("Reading the bulk summary (RegOps)", expanded=False):
                    st.markdown(
                        "- **Confidence min/max:** classifier aggregate heuristic per correlation — benchmarks for "
                        "mature portfolios often concentrate Tier-1-heavy rows near the **high 0.8s**, whereas "
                        "context-only cues can sit lower without automatically implying regulatory non-compliance.\n"
                        "- **Verifier review / rejected:** escalation signals — filings should not rely solely on "
                        "automation until SME disposition lives in QA records.\n"
                        "- Export detailed artefacts from **History** when attaching to deviations or inspections."
                    )

                if errors_rows:
                    with st.expander("Bulk diagnostics (rows skipped)", expanded=False):
                        st.dataframe(pd.DataFrame(errors_rows), use_container_width=True, hide_index=True)

    idle_bulk = not bulk_clicked
    idle_single = not classify_clicked and not preview_clicked
    if idle_bulk and idle_single and result is None:
        st.info(
            "**Workflow tip:** Paste narrative → **Preview & parse** → **Classify now**. "
            "CSV batches stay in the expandable throughput panel when you need scale."
        )

    theme.render_validation_footer(st)
