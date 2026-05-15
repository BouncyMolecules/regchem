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
    st.title("History & audit")
    st.write(
        "Filter stored pipeline snapshots within this browser session. Expand any row for the "
        "full trace bundle — findings, supplier graph, verifier assertions, and ledger payloads."
    )

    try:
        rows_src = deps.storage.recent_runs(limit=250)
        trail = deps.storage.get_audit_trail(limit=500)
    except Exception as exc:
        st.error("Unable to read audit history.")
        st.exception(exc)
        return

    filter_text = st.text_input(
        "Correlation filter (substring)",
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
            "No executions match your filter yet. Submit a classify run — persistence defaults "
            "to SQLite under your configured ``data_dir`` unless you deliberately select memory "
            "backend."
        )
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
                "content_sha256": row.get("content_sha256"),
                "snapshot_digest": row.get("snapshot_canonical_sha256"),
            }
        )

    st.subheader("Snapshot index")
    st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

    st.subheader("Full trace")
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
        f"**Pipeline run ID:** `{selected_row.get('pipeline_run_id', '—')}`  \n"
        f"**Opened (UTC):** `{selected_row.get('created_at_utc', '—')}`  \n"
        f"**Content SHA-256:** `{selected_row.get('content_sha256', '—')}`  \n"
        f"**Snapshot digest:** `{selected_row.get('snapshot_canonical_sha256', '—')}`"
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
        file_name=f"regchem_history_{bundle.correlation_id}.json",
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

    st.subheader("Immutable audit ledger (subset)")
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
        "Production deployments should mirror this ledger to WORM media and tie hash chains to "
        "your Part 11 / Annex 11 evidence packages."
    )
