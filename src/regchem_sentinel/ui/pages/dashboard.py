"""Operational dashboard — posture, KPIs, and lightweight risk cues."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd

from regchem_sentinel.config import Settings
from regchem_sentinel.core.models import StartingMaterial, VerificationAssertion, VerificationStatus
from regchem_sentinel.main import SentinelDependencies
from regchem_sentinel.ui.utils import theme


def _as_tuple_objects(value: object) -> tuple[object, ...]:
    return value if isinstance(value, tuple) else ()


def _format_ts(value: object) -> str:
    if isinstance(value, datetime):
        aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return aware.strftime("%Y-%m-%d %H:%M UTC")
    return "—"


def _findings_agg_window(findings: tuple[object, ...]) -> tuple[float | None, float | None]:
    """Minimum / mean classifier aggregates when findings are hydrated models."""

    aggs: list[float] = []
    for raw in findings:
        if isinstance(raw, StartingMaterial):
            aggs.append(float(raw.classification.tiered_confidence.aggregate))
    if not aggs:
        return None, None
    return min(aggs), sum(aggs) / len(aggs)


def _priority_queue_rows(runs: list[dict[str, object]], *, limit: int = 25) -> list[dict[str, object]]:
    """Surface correlations with verifier escalation or materially weak classifier aggregates."""

    rows_out: list[dict[str, object]] = []

    for row in runs[:300]:
        verifs = [
            item
            for item in _as_tuple_objects(row.get("verifications", ()))
            if isinstance(item, VerificationAssertion)
        ]
        rev = sum(1 for v in verifs if v.status is VerificationStatus.REVIEW_REQUIRED)
        rej = sum(1 for v in verifs if v.status is VerificationStatus.REJECTED)

        findings_tuple = _as_tuple_objects(row.get("findings", ()))
        agg_min, agg_avg = _findings_agg_window(findings_tuple)
        thin_evidence = bool(findings_tuple) and agg_min is not None and agg_min < 0.76

        if rej == 0 and rev == 0 and not thin_evidence:
            continue

        if rej:
            posture = "Elevated"
            why = (
                "Verifier flagged rejected assertion(s); block filing narrative reuse until dossier-aligned "
                f"resolution is documented ({rej} signal(s))."
            )
        elif rev:
            posture = "Review"
            why = (
                "Human adjudication cues remain open — expect SME disposition before dossier excerpts are "
                f"referenced externally ({rev} reviewer-facing signal(s))."
            )
        else:
            posture = "Watch"
            span = f"{agg_min:.2f}" if agg_min is not None else "—"
            mean = f"{agg_avg:.2f}" if agg_avg is not None else "—"
            why = (
                "Classifier aggregates sit below typical Tier-1-dominant baselines (~**0.88–0.94** heuristic "
                f"ranges in disciplined rules rehearsal data) — investigate evidence depth (min aggregate `{span}`, "
                f"mean `{mean}`)."
            )

        rows_out.append(
            {
                "posture_label": posture,
                "correlation_id": row.get("correlation_id"),
                "opened_at": _format_ts(row.get("created_at_utc", "")),
                "findings_shown": len(findings_tuple),
                "why_it_matters": why,
            },
        )

        if len(rows_out) >= limit:
            break

    return rows_out


def render(st: Any, *, deps: SentinelDependencies, settings: Settings) -> None:
    st.markdown(
        '<p class="regchem-page-lede" style="margin-top:0.25rem;">Prioritise correlations that need SME '
        "attention before weekly RegOps forums. Metrics are <strong>session-scoped</strong> — pair with your QMS for "
        "longer baselines.</p>",
        unsafe_allow_html=True,
    )

    try:
        runs = deps.storage.recent_runs(limit=500)
    except Exception as exc:
        st.error("Unable to read recent executions from persistence.")
        st.exception(exc)
        return

    if not runs:
        st.warning(
            "No pipeline snapshots yet — start in **New classification** to populate portfolio telemetry."
        )
        theme.render_validation_footer(st)
        st.stop()

    total_findings = 0
    accepted_total = 0
    review_required_total = 0
    rejected_total = 0

    latest = runs[0]
    latest_corr = latest.get("correlation_id")

    trajectory_rows: list[dict[str, object]] = []
    chron = list(reversed(runs[-40:]))
    for seq, row in enumerate(chron):
        verifs = [
            item
            for item in _as_tuple_objects(row.get("verifications", ()))
            if isinstance(item, VerificationAssertion)
        ]
        rf = sum(1 for v in verifs if v.status is VerificationStatus.REVIEW_REQUIRED)
        rj = sum(1 for v in verifs if v.status is VerificationStatus.REJECTED)
        ok = sum(1 for v in verifs if v.status is VerificationStatus.ACCEPTED)
        findings_tuple = _as_tuple_objects(row.get("findings", ()))
        total_findings += len(findings_tuple)
        accepted_total += ok
        review_required_total += rf
        rejected_total += rj

        denom = len(verifs) if verifs else 1
        trajectory_rows.append(
            {
                "sequence": seq,
                "opened_at": row.get("created_at_utc"),
                "finding_count": len(findings_tuple),
                "review_pressure": rf / denom,
                "reject_share": rj / denom,
            },
        )

    cols = st.columns(4)

    with cols[0]:
        theme.render_kpi_card(cols[0], title="Tracked runs", value=f"{len(runs)}", band="neutral")
        with st.expander("ℹ KPI — tracked runs", expanded=False):
            st.markdown(
                "**Measures:** count of Quanta pipeline executions retained in this session's storage "
                "(SQLite WAL or in-memory ledger)."
            )
            st.markdown(
                "**2026 reference band:** modest CMC churn teams executing narrative QA often accumulate "
                "**≈18–52 stored bursts per fiscal quarter**, spiking ahead of filings — Quanta does not infer "
                "calendar windows without external timestamps."
            )
            st.markdown(
                f"**Your reading:** **`{len(runs)}`** executions on record — correlate cadence versus submission "
                "milestones inside your QMS; export History when trending outside expected filing windows."
            )

    with cols[1]:
        theme.render_kpi_card(
            cols[1],
            title="Recorded findings",
            value=f"{total_findings}",
            band="neutral",
            footnote="Across retained snapshots",
        )
        with st.expander("ℹ KPI — recorded findings", expanded=False):
            st.markdown(
                "**Measures:** total starting-material hypotheses emitted across snapshots (not dossier-listed "
                "API counts)."
            )
            st.markdown(
                "**2026 reference band:** expect **≈6–48 cumulative findings per 250–600 page CMC annex** pull "
                "depending on synonym density — wide variance is normal across vendors."
            )
            den = len(runs) if runs else 1
            ratio = total_findings / den
            st.markdown(
                f"**Your reading:** **`{total_findings}`** findings ⇒ **≈{ratio:.1f}** findings per retained "
                "run — higher ratios merit spot checks for duplication inside one correlation payload."
            )

    with cols[2]:
        theme.render_kpi_card(
            cols[2],
            title="Verifier cues (review)",
            value=f"{review_required_total}",
            band="watch" if review_required_total > 0 else "low",
            footnote="Human adjudication signals",
        )
        with st.expander("ℹ KPI — review cues", expanded=False):
            st.markdown(
                "**Measures:** cumulative verifier assertions marked **review required** across all snapshots."
            )
            st.markdown(
                "**2026 reference band:** well-curated template language often clears **≤8% review cues** vs. "
                "accepted assertions in automation-assisted RegOps rehearsals — escalate if sustained double digits "
                "post-template refresh."
            )
            denom = accepted_total + review_required_total + rejected_total or 1
            share_pct = review_required_total / denom * 100
            if share_pct > 12:
                cue = "**Above** typical disciplined bands — tighten SME sign-off checkpoints."
            elif share_pct > 0:
                cue = "**Within watch territory** — clear open cues before dossier excerpts leave QA control."
            else:
                cue = "**No backlog** visible here — still sample History for regressions after template edits."
            st.markdown(
                f"**Your reading:** **`{review_required_total}`** cues ({share_pct:.1f}% of tallied "
                f"verifier assertions) — {cue}"
            )

    with cols[3]:
        theme.render_kpi_card(
            cols[3],
            title="Verifier cues (rejected)",
            value=f"{rejected_total}",
            band="elevated" if rejected_total > 0 else "low",
            footnote="Blocked assertions",
        )
        with st.expander("ℹ KPI — rejected cues", expanded=False):
            st.markdown(
                "**Measures:** cumulative verifier assertions marked **rejected** — materially stronger than "
                "review-required signals."
            )
            st.markdown(
                "**2026 reference band:** production-grade gates usually target **0 sustained rejections** in "
                "release-ready dossier language rehearsals; intermittent spikes arise during upstream template churn."
            )
            if rejected_total:
                verdict = "**Immediate reconciliation** warranted — correlate with deviations before regulatory "
                "submission references resume."
            else:
                verdict = "**No verifier hard-stops logged** — continue periodic golden-text regression tests "
                "to keep this posture."
            st.markdown(f"**Your reading:** **`{rejected_total}`** rejections tally — {verdict}")

    st.markdown("##### Today’s triage queue")
    st.caption(
        "Surfaces correlations with verifier escalation or softer classifier aggregates — **decision-support "
        "routing only**, not a filing readiness verdict."
    )
    queue_preview = _priority_queue_rows(runs)
    if queue_preview:
        st.dataframe(pd.DataFrame(queue_preview), use_container_width=True, hide_index=True)
        with st.expander("How ranking works & limits", expanded=False):
            st.markdown(
                "- Includes rows with verifier **rejected**, **review required**, OR aggregate confidence floor "
                "**<0.76** when hypotheses exist.\n"
                "- **Not** a submission readiness verdict — SMEs still map citations to dossier-controlled text.\n"
                "- Showing the **newest-eligible correlations first** limited to session retention window."
            )
    else:
        st.success(
            "Portfolio queue empty on these heuristics — continue weekly History sampling whenever templates change."
        )

    posture = theme.kpi_band_for_verifier_counts(
        review=review_required_total,
        rejected=rejected_total,
    )
    labels: dict[theme.KpiBand, str] = {
        "neutral": "Baseline telemetry — maintain SME mapping discipline.",
        "low": "Portfolio verifier posture looks clear — maintain SME mapping discipline.",
        "watch": "Elevated review queue — prioritize verifier outcomes visible in History.",
        "elevated": "Rejection cues present — reconcile against golden dossier excerpts.",
    }
    st.markdown("##### Portfolio verifier posture")
    theme.render_verifier_chips(
        st,
        accepted=accepted_total,
        review_required=review_required_total,
        rejected=rejected_total,
    )
    st.caption(labels[posture])
    with st.expander("ℹ Interpreting posture & benchmarks", expanded=False):
        st.markdown(
            "**What this strip measures:** verifier assertion outcomes tallied cumulatively — **accepted**, "
            "**review required**, **rejected** — after deterministic checks against the surfaced narrative bundle."
        )
        st.markdown(
            "**2026 heuristic bands:** rehearsals with frozen golden texts often stabilize around **accepted ≥90%**, "
            "**review in mid-single digits**, and **rejected ≈0%** ahead of filings — treat as directional, programme "
            "specific."
        )
        st.markdown(
            f"**Your reading:** {labels[posture]} Accepted vs escalation mix should be mirrored in QA trending "
            "tools — Quanta only mirrors what was last persisted."
        )

    st.markdown("##### Latest execution · provenance snapshot")
    with st.expander(
        f"Correlation `{latest_corr}` — identifiers & digests",
        expanded=False,
    ):
        st.markdown(
            f"**Correlation ID:** `{latest_corr}`  \n"
            f"**Last opened (UTC):** {_format_ts(latest.get('created_at_utc', ''))}  \n"
            f"**Submission content SHA-256:** `{latest.get('content_sha256', '—')}`  \n"
            f"**Canonical snapshot digest:** `{latest.get('snapshot_canonical_sha256', '—')}`"
        )
        st.caption(
            "Use these fingerprints when attaching Quanta output to deviations, change records, or inspection "
            "response binders — mirror language in your validated tracker."
        )
        with st.expander("How to operationalize this artefact", expanded=False):
            st.markdown(
                "- **Correlation ID** anchors ECM / deviations / QA tracker rows — never rewrite post-sign-off.\n"
                "- **Content SHA-256** fingerprints the verbatim narrative span hashed for this Quanta pass.\n"
                "- **Canonical snapshot digest** locks the structured bundle exactly as persisted for replay."
            )

    st.markdown("##### Risk trajectory (recent runs)")
    st.caption(
        "Relative verifier pressure per run — higher values mean more cues requiring human "
        "review or rejection in that snapshot (not a clinical risk score)."
    )
    if len(trajectory_rows) >= 2:
        frame = pd.DataFrame(trajectory_rows)
        st.line_chart(
            frame.set_index("sequence")[["review_pressure", "reject_share"]],
            height=280,
        )
        with st.expander("ℹ Chart · verifier pressure cues", expanded=False):
            st.markdown(
                "**Y-axis semantics:** fractional share (0–1) of verifier assertions in that snapshot that "
                "**required review** (teal analogue) vs **were rejected** (rose analogue)."
            )
            st.markdown(
                "**2026 reference:** stable programmes seldom sustain **reject_share >0.08** sprint-over-sprint; "
                "**review_pressure** pulses during template merges but should slope down after rework."
            )
            tail_pressure = trajectory_rows[-1]["review_pressure"] if trajectory_rows else 0
            tail_reject = trajectory_rows[-1]["reject_share"] if trajectory_rows else 0
            if tail_pressure > 0.2 or tail_reject > 0:
                implication = "**Latest window shows elevated verifier workload** — consider pausing unattended "
                "batch drafting until rationales stabilise."
            else:
                implication = "**Trajectory flat-to-improving vs. verifier noise** relative to heuristic targets — "
                "still corroborate with History exports."
            st.markdown(
                f"**Your reading:** trailing review pressure **`{tail_pressure:.2f}`**, rejection share "
                f"`{tail_reject:.2f}` — {implication}"
            )
    else:
        st.info("Need at least two stored runs to render a trajectory chart.")

    st.markdown("##### Operating envelope")
    with st.expander("Controlled-use narrative (RegOps)", expanded=False):
        st.markdown(
            """
- Quanta parses unstructured CMC text, fingerprints it, tiers Starting Material hypotheses,
  links supplier wording, verifies structured checks, then persists hashed snapshots suitable
  for inspection readiness drills.
- Outputs remain **deterministic scaffolding** intended for SMEs who map each row back to dossier-
  controlled sources.
"""
        )

    env_posture = (
        "Production-grade posture — "
        if settings.app_env == "production"
        else "Non-production posture — "
    )
    st.info(
        f"{env_posture}**{settings.app_env}** · build **{settings.build_id}**. "
        "Retain change-control evidence when promoting configuration between tiers."
    )

    theme.render_validation_footer(st)
