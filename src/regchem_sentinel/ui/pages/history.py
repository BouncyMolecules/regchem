"""Execution history and audit drill-down."""

from __future__ import annotations

import json
from typing import Any, cast

import pandas as pd

from regchem_sentinel.config import Settings
from regchem_sentinel.core.models import (
    ParsedSubmission,
    SentinelPipelineSnapshot,
    StartingMaterial,
    Supplier,
    VerificationAssertion,
    VerificationStatus,
)
from regchem_sentinel.main import SentinelDependencies
from regchem_sentinel.ui.utils import theme


def _as_tuple(value: object) -> tuple[object, ...]:
    return value if isinstance(value, tuple) else ()


def render(st: Any, *, deps: SentinelDependencies, settings: Settings) -> None:
    _ = settings
    st.markdown(
        '<p class="regchem-page-lede" style="margin-top:0.25rem;">Every row below is an <strong>immutable snapshot '
        "reference</strong> — use correlation IDs and digests when binding Quanta output to your quality records. "
        "This view is filtered to this workstation&rsquo;s ledger.</p>",
        unsafe_allow_html=True,
    )

    try:
        rows_src = deps.storage.recent_runs(limit=250)
        trail = deps.storage.get_audit_trail(limit=500)
    except Exception as exc:
        st.error("Unable to read audit history.")
        st.exception(exc)
        return

    filter_text = st.text_input(
        "Filter by correlation (partial match)",
        value="",
        help="Narrows matching correlation identifiers.",
    ).strip()

    rows = rows_src
    if filter_text:
        rows = [
            item
            for item in rows
            if filter_text.casefold() in str(item.get("correlation_id", "")).casefold()
        ]

    if not rows:
        st.info(
            "No executions match your filter yet. Run **New classification** — persistence defaults "
            "to SQLite under your configured ``data_dir`` unless you deliberately select the memory backend."
        )
        theme.render_validation_footer(st)
        return

    table_rows: list[dict[str, object]] = []
    for row in rows:
        findings = _as_tuple(row.get("findings", ()))
        ver_counts = [
            candidate
            for candidate in _as_tuple(row.get("verifications", ()))
            if isinstance(candidate, VerificationAssertion)
        ]
        table_rows.append(
            {
                "correlation_id": row.get("correlation_id"),
                "pipeline_run_id": row.get("pipeline_run_id"),
                "opened_at": row.get("created_at_utc"),
                "submission_preview": str(row.get("submission_excerpt", ""))[:160],
                "finding_count": len(findings),
                "review_open": sum(1 for v in ver_counts if v.status.value == "review_required"),
                "rejected": sum(1 for v in ver_counts if v.status.value == "rejected"),
                "submission_content_sha256": row.get("content_sha256"),
                "canonical_snapshot_sha256": row.get("snapshot_canonical_sha256"),
            }
        )

    st.markdown("##### Snapshot index")
    st.caption(
        "Sorted newest-first within the retention window — **canonical snapshot SHA-256** is the bundle digest "
        "stored with each run."
    )
    st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

    st.markdown("##### Detailed trace")
    correlation_ids = sorted(
        {str(item.get("correlation_id")) for item in rows if item.get("correlation_id")}
    )
    selected = st.selectbox("Select correlation for detailed trace", correlation_ids)

    selected_row = next(
        (item for item in rows if str(item.get("correlation_id")) == selected),
        None,
    )
    if selected_row is None:
        st.error("Could not resolve the selected correlation row.")
        return

    findings_raw = _as_tuple(selected_row.get("findings", ()))
    suppliers_raw = _as_tuple(selected_row.get("suppliers", ()))
    verifications_raw = _as_tuple(selected_row.get("verifications", ()))

    findings = cast(
        tuple[StartingMaterial, ...],
        tuple(cast(StartingMaterial, f) for f in findings_raw),
    )
    suppliers = cast(
        tuple[Supplier, ...],
        tuple(cast(Supplier, s) for s in suppliers_raw),
    )
    verifications = cast(
        tuple[VerificationAssertion, ...],
        tuple(cast(VerificationAssertion, v) for v in verifications_raw),
    )
    parsed_raw = selected_row.get("parsed_submission")
    if not isinstance(parsed_raw, ParsedSubmission):
        st.error("Stored snapshot is missing typed parse artefacts — cannot rebuild bundle.")
        return

    bundle = SentinelPipelineSnapshot(
        correlation_id=str(selected_row.get("correlation_id", "")),
        submission_excerpt=str(selected_row.get("submission_excerpt", "")),
        parsed_submission=parsed_raw,
        findings=findings,
        suppliers=suppliers,
        verifications=verifications,
    )

    st.markdown(
        """
        <div class="regchem-card-surface">
            <div class="regchem-page-eyebrow">Selected run · provenance</div>
            <p class="regchem-footnote" style="margin:0;">
                Treat these identifiers as the immutable snapshot references for QA narratives, deviations, and
                inspection talking points. Download JSON to attach to your ECM bundle.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f"**Pipeline run ID:** `{selected_row.get('pipeline_run_id', '—')}`  \n"
        f"**Opened (UTC):** `{selected_row.get('created_at_utc', '—')}`  \n"
        f"**Submission content SHA-256:** `{selected_row.get('content_sha256', '—')}`  \n"
        f"**Canonical snapshot SHA-256:** `{selected_row.get('snapshot_canonical_sha256', '—')}`"
    )

    accepted_h = sum(1 for v in verifications if v.status is VerificationStatus.ACCEPTED)
    review_h = sum(1 for v in verifications if v.status is VerificationStatus.REVIEW_REQUIRED)
    rejected_h = sum(1 for v in verifications if v.status is VerificationStatus.REJECTED)
    st.markdown("##### Verifier posture (stored snapshot)")
    theme.render_verifier_chips(
        st,
        accepted=accepted_h,
        review_required=review_h,
        rejected=rejected_h,
    )

    st.download_button(
        label="Download canonical snapshot JSON",
        data=bundle.model_dump_json(indent=2),
        file_name=f"quanta_history_{bundle.correlation_id}.json",
        mime="application/json",
        key=f"hist_dl_{bundle.correlation_id}",
    )

    with st.expander("Submission excerpt", expanded=False):
        st.text(str(selected_row.get("submission_excerpt", "")))

    with st.expander("Structured findings + suppliers + verifier matrix", expanded=True):
        st.json(
            {
                "findings": [f.model_dump(mode="json") for f in findings],
                "suppliers": [s.model_dump(mode="json") for s in suppliers],
                "verifications": [v.model_dump(mode="json") for v in verifications],
            }
        )

    st.markdown("##### Hash-chained audit ledger (replay subset)")
    filtered_trail = [entry for entry in trail if entry.correlation_id == selected]

    ledger_rows: list[dict[str, object]] = []
    for entry in filtered_trail[-100:]:
        ledger_rows.append(
            {
                "entry_id": entry.entry_id,
                "created_at_utc": entry.created_at_utc,
                "event_type": entry.event_type,
                "correlation_id": entry.correlation_id,
                "pipeline_run_id": entry.pipeline_run_id,
                "snapshot_digest": entry.snapshot_canonical_sha256,
                "prev_hash": entry.previous_entry_hash_hex,
                "entry_hash": entry.entry_hash_hex,
            }
        )

    if not ledger_rows:
        st.caption("No ledger entries matched this correlation.")
    else:
        st.dataframe(pd.DataFrame(ledger_rows), use_container_width=True, hide_index=True)

    with st.expander("Raw ledger payload (latest five)", expanded=False):
        for entry in filtered_trail[-5:]:
            st.markdown(f"**Entry {entry.entry_id}** — `{entry.event_type}`")
            try:
                st.json(json.loads(entry.payload_json))
            except json.JSONDecodeError:
                st.code(entry.payload_json)

    st.caption(
        "Ledger rows are append-only in Quanta storage — **mirror to WORM media** and tie entry hashes to your "
        "Part 11 / Annex 11 evidence packages in qualified deployments."
    )

    theme.render_validation_footer(st)
