"""Operational dashboard — posture, KPIs, and lightweight risk cues."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd

from regchem_sentinel.config import Settings
from regchem_sentinel.core.models import VerificationAssertion, VerificationStatus
from regchem_sentinel.main import SentinelDependencies
from regchem_sentinel.ui.utils import theme


def _as_tuple_objects(value: object) -> tuple[object, ...]:
    return value if isinstance(value, tuple) else ()


def _format_ts(value: object) -> str:
    if isinstance(value, datetime):
        aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return aware.strftime("%Y-%m-%d %H:%M UTC")
    return "—"


def render(st: Any, *, deps: SentinelDependencies, settings: Settings) -> None:
    st.title("Monitored portfolio")
    st.caption(
        "Session-scoped metrics derived from stored pipeline snapshots. "
        "Pair with your QMS for controlled trending over longer horizons."
    )

    try:
        runs = deps.storage.recent_runs(limit=500)
    except Exception as exc:
        st.error("Unable to read recent executions from persistence.")
        st.exception(exc)
        return

    if not runs:
        st.warning(
            "No pipeline snapshots yet — run classification to populate KPIs "
            "and risk posture signals."
        )
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
    theme.render_kpi_card(cols[0], title="Tracked runs", value=f"{len(runs)}", band="neutral")
    theme.render_kpi_card(
        cols[1],
        title="Recorded findings",
        value=f"{total_findings}",
        band="neutral",
        footnote="Across retained snapshots",
    )
    theme.render_kpi_card(
        cols[2],
        title="Verifier cues (review)",
        value=f"{review_required_total}",
        band="watch" if review_required_total > 0 else "low",
        footnote="Human adjudication signals",
    )
    theme.render_kpi_card(
        cols[3],
        title="Verifier cues (rejected)",
        value=f"{rejected_total}",
        band="elevated" if rejected_total > 0 else "low",
        footnote="Blocked assertions",
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

    st.markdown("##### Latest correlation")
    st.write(
        f"**Correlation ID:** `{latest_corr}`  \n"
        f"**Last opened:** {_format_ts(latest.get('created_at_utc', ''))}  \n"
        f"**Content SHA-256:** `{latest.get('content_sha256', '—')}`  \n"
        f"**Snapshot digest:** `{latest.get('snapshot_canonical_sha256', '—')}`"
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
    else:
        st.info("Need at least two stored runs to render a trajectory chart.")

    st.markdown("##### Operating envelope")
    st.markdown(
        """
- Sentinel parses unstructured CMC text, fingerprints it, tiers Starting Material hypotheses,
  links supplier wording, verifies structured checks, then persists hashed snapshots suitable
  for inspection readiness drills.
- Results remain **deterministic scaffolding** intended for SMEs who map each row back to dossier-
  controlled sources.
"""
    )

    env_posture = (
        "Production-grade posture requested — "
        if settings.app_env == "production"
        else "Non-production telemetry — "
    )
    st.info(
        f"{env_posture}environment tag `{settings.app_env}` matched to build "
        f"`{settings.build_id}`. "
        "Retain change control evidence when promoting configuration between tiers."
    )
