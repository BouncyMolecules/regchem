"""Interactive classify workspace — parse through persist with explicit DI."""

from __future__ import annotations

import io
import json
import uuid
from typing import Any

import pandas as pd

from regchem_sentinel.config import Settings
from regchem_sentinel.core.models import (
    DetectorTier,
    SentinelPipelineSnapshot,
    StartingMaterial,
    VerificationStatus,
)
from regchem_sentinel.core.storage import StorageWriteError
from regchem_sentinel.main import SentinelDependencies, run_pipeline
from regchem_sentinel.ui.utils import theme

_BULK_HINT = (
    "**CSV:** header row optional; required columns **`correlation_id`** and **`text`** (UTF-8). "
    "**Paste box:** paste the same column layout row-by-row, or concatenate with an uploaded file."
)


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
        text_val = row.get("text")
        cid = "" if cid_val is None or (isinstance(cid_val, float) and pd.isna(cid_val)) else str(cid_val).strip()
        text_raw = row.get("text")
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


def _render_interpretation_expander(st: Any, snapshot: SentinelPipelineSnapshot) -> None:
    """Plain-language implication summary — explanatory only."""

    tiers = tuple(f.tier or f.classification.suggested_material_tier for f in snapshot.findings)
    tier_names = [t.value.replace("_", " ") for t in tiers if t]
    uniq_tiers = sorted(set(tier_names))
    aggregates = tuple(f.classification.tiered_confidence.aggregate for f in snapshot.findings)
    max_t1_direct = False
    for f in snapshot.findings:
        for contrib in f.classification.rule_contributions:
            if contrib.matched and contrib.detector_tier is DetectorTier.TIER_1_DIRECT_REGISTRATION_LANGUAGE:
                max_t1_direct = True

    weak_context = any(a < 0.72 for a in aggregates) if aggregates else False
    mid_signal = aggregates and sum(aggregates) / len(aggregates) >= 0.82

    acc = sum(1 for v in snapshot.verifications if v.status is VerificationStatus.ACCEPTED)
    rev = sum(1 for v in snapshot.verifications if v.status is VerificationStatus.REVIEW_REQUIRED)
    rej = sum(1 for v in snapshot.verifications if v.status is VerificationStatus.REJECTED)

    with st.expander("What this result means", expanded=False):
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
                    "**Context-weighted contributions** dominate for some hypotheses; treat tiering "
                    "as exploratory until supporting tables or registrations are curated."
                )
            if uniq_tiers:
                st.caption(f"Suggested regulatory emphasis tiers present: `{', '.join(uniq_tiers)}`. "
                           "Tier labels are heuristic — align with regional guidance and QA classification.")
            else:
                st.caption("Material tier suggestions were ambiguous for some rows — escalate for taxonomy alignment.")
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

    with st.expander("Serialized pipeline snapshot (JSON)", expanded=False):
        st.download_button(
            label="Download snapshot JSON",
            data=snapshot.model_dump_json(indent=2),
            file_name=f"regchem_snapshot_{cid}.json",
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


def render(st: Any, *, deps: SentinelDependencies, settings: Settings) -> None:
    st.title("Classify submission narrative")
    intro_l, intro_r = st.columns([0.72, 0.28])
    with intro_l:
        st.write(
            "Paste representative **CMC** unstructured text. The pipeline executes **parse → classify → "
            "supplier linkage → verifier → persisted snapshot** against the injected storage port.",
        )
    with intro_r:
        with st.expander("Pipeline glossary", expanded=False):
            st.caption(
                "**Parse** fingerprints and segments excerpts. "
                "**Classify** tiers starting-material hypotheses. "
                "**Supplier linkage** maps named parties. "
                "**Verifier** flags claims for human adjudication.",
            )

    # --- Bulk classify (primary throughput path) ---
    st.markdown("---")
    st.markdown("### Bulk classify")
    st.caption(_BULK_HINT)
    upl_col, paste_col = st.columns([0.42, 0.58])
    with upl_col:
        bulk_upload = st.file_uploader(
            "CSV upload",
            type=["csv"],
            accept_multiple_files=False,
            key="bulk_classify_upload",
            help="Columns **correlation_id** and **text** (comma-delimited UTF-8).",
        )
    uploaded_df: pd.DataFrame | None = None
    if bulk_upload is not None:
        uploaded_df = pd.read_csv(io.BytesIO(bulk_upload.getvalue()))

    with paste_col:
        bulk_paste_area = st.text_area(
            "Paste CSV rows (optional)",
            height=260,
            placeholder=(
                'correlation_id,text\n'
                '"CHG-1024","Starting material RM-42 is synthesized by …"'
            ),
            help="Quoted fields support commas inside **text**. Empty correlation cells receive UUIDs.",
            key="bulk_classify_paste",
        )

    bulk_opts = st.columns([0.62, 0.38])
    with bulk_opts[0]:
        bulk_persist = st.toggle(
            "Persist each bulk snapshot (+ ledger)",
            value=True,
            help="Unchecked still runs verifier logic but skips persistence for that row.",
            key="bulk_classify_persist_toggle",
        )
    with bulk_opts[1]:
        st.caption("Tip · keep batches ≤50 correlations per click for workstation responsiveness.")

    bulk_clicked = st.button(
        "Run bulk classification",
        type="secondary",
        help="Sequential Sentinel runs — same classifier and verifier as single-entry.",
        key="regchem_bulk_run",
    )

    bulk_row_cap = 50
    if bulk_clicked:
        rows = _gather_bulk_rows(uploaded_df, bulk_paste_area)
        if not rows:
            st.warning(
                "No ingestible bulk rows detected — populate the CSV columns **correlation_id** and "
                "**text**, or paste equivalent rows.",
            )
        else:
            truncated = rows
            if len(rows) > bulk_row_cap:
                truncated = rows[:bulk_row_cap]

            prog = st.progress(0)
            summaries: list[dict[str, object]] = []
            errors_rows: list[dict[str, str]] = []

            total = len(truncated)
            for seq, (cid_eff, excerpt) in enumerate(truncated, start=1):
                prog.progress(int(seq / max(total, 1) * 100))
                excerpt_stripped = excerpt.strip()
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
                    errors_rows.append({"correlation_id": cid_use, "reason": f"Unhandled fault — {exc!s}"})
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

    st.markdown("---")
    st.markdown("### Single submission")
    st.caption("Use for focussed QA on one deviation or dossier excerpt — advanced controls stay tucked away.")

    default_corr = uuid.uuid4().hex
    col_primary, col_narrative = st.columns([0.38, 0.62])

    with col_primary:
        correlation_id = st.text_input(
            "Correlation / audit identifier",
            value=default_corr,
            help=(
                "Map to ECM / QMS artefacts (deviation IDs, dossier gateways). "
                "UUID auto-filled if you omit manual assignment."
            ),
        )
        with st.expander("Advanced pipeline options", expanded=False):
            persist_choice = st.toggle(
                "Persist snapshot + ledger row",
                value=True,
                help="Ephemeral probes keep verifier fidelity but omit persistence — useful during workshops.",
                key="single_persist_toggle",
            )

        st.caption("Smart default · persistence **on** aligns with audit-ready traces.")

    with col_narrative:
        submission = st.text_area(
            "Submission excerpt",
            height=360,
            placeholder=(
                "Example: Registered starting material XYZ-API (SM‑01) is manufactured at Site A pursuant to …"
            ),
            help="Prefer verbatim narrative identical to dossier excerpts you will cite in assessments.",
            key="single_submission_area",
        )

    run_clicked = st.button(
        "Run classification",
        type="primary",
        help="Equivalent pipeline fidelity to bulk — recommended after narrative finalisation.",
        key="regchem_single_run",
    )

    snapshot: SentinelPipelineSnapshot | None = None
    cid = correlation_id.strip() or default_corr

    if run_clicked:
        excerpt = submission.strip()
        if not excerpt:
            st.warning("Submission text is empty — populate the narrative pane before executing.")
        else:
            cid = correlation_id.strip() or default_corr
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
                st.success(
                    "Classification finished — adjudicate verifier outputs against controlled source statements.",
                )

                st.markdown(
                    f"**Content SHA-256:** `{snapshot.parsed_submission.content_sha256}` · "
                    f"**Pages detected:** `{len(snapshot.parsed_submission.segments)}`",
                )

                _render_interpretation_expander(st, snapshot)

                _snapshot_detail_tables(st, snapshot, cid)

    if not run_clicked and not bulk_clicked:
        st.info(
            "Use **Bulk classify** for submission fragments under time pressure; use **Single submission** "
            "when corralling verifier discussion around one artefact.",
        )

    st.caption(
        f"Build identifier: `{settings.build_id}` — override with REGCHEM_SENTINEL_BUILD_ID.",
    )
