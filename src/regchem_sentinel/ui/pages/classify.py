"""Interactive classify workspace — parse through persist with explicit DI."""

from __future__ import annotations

import json
import uuid
from typing import Any

import pandas as pd

from regchem_sentinel.config import Settings
from regchem_sentinel.core.models import VerificationStatus
from regchem_sentinel.core.storage import StorageWriteError
from regchem_sentinel.main import SentinelDependencies, run_pipeline
from regchem_sentinel.ui.utils import theme


def render(st: Any, *, deps: SentinelDependencies, settings: Settings) -> None:
    st.title("Classify submission narrative")
    st.write(
        "Paste representative CMC unstructured text. The pipeline executes **parse → classify → "
        "supplier linkage → verifier → persisted snapshot** against the injected storage port "
        "(SQLite WAL when configured)."
    )

    default_corr = uuid.uuid4().hex
    correlation_id = st.text_input(
        "Correlation / audit identifier",
        value=default_corr,
        help=(
            "Use your deviation, change, or dossier artefact identifier; "
            "UUID shown for convenience."
        ),
    )

    persist_choice = st.toggle(
        "Persist snapshot + ledger row",
        value=True,
        help="Disable only for ephemeral what-if probes (still routed through verifier).",
    )

    submission = st.text_area(
        "Submission excerpt",
        height=320,
        placeholder=(
            "Example: The starting material SM-01 is supplied by Example Labs pursuant to …"
        ),
    )

    run_clicked = st.button(
        "Run classification",
        type="primary",
        help="Executes the full Sentinel pipeline with the services bound in this session.",
    )

    if not run_clicked:
        st.info("Provide narrative text, then run classification to produce traceable hypotheses.")
        st.caption(
            f"Build identifier: `{settings.build_id}` — override with REGCHEM_SENTINEL_BUILD_ID."
        )
        return

    if not submission.strip():
        st.warning("Submission text is empty — nothing to analyze.")
        return

    cid = correlation_id.strip() or default_corr

    with st.spinner("Executing parse → classify → supplier link → verify → persist …"):
        try:
            snapshot = run_pipeline(
                submission,
                correlation_id=cid,
                deps=deps,
                persist=persist_choice,
            )
        except ValueError as exc:
            st.error(f"Validation blocked the run — {exc}")
            return
        except StorageWriteError as exc:
            st.error(
                "Persistence refused the snapshot. Verify disk space, SQLite permissions, and "
                "that the correlation identifier meets storage invariants."
            )
            with st.expander("Technical detail"):
                st.exception(exc)
            return
        except Exception as exc:
            st.error(
                "Unexpected orchestration fault — preserve console logs and escalate per your "
                "deviation playbook."
            )
            st.exception(exc)
            return

    st.success(
        "Classification finished — adjudicate verifier outputs against approved source statements."
    )

    st.markdown(
        f"**Content SHA-256:** `{snapshot.parsed_submission.content_sha256}` · "
        f"**Pages detected:** `{len(snapshot.parsed_submission.segments)}`"
    )

    findings_rows: list[dict[str, object]] = []
    for finding in snapshot.findings:
        findings_rows.append(
            {
                "canonical_name": finding.canonical_name,
                "tier": finding.tier.value if finding.tier else "unassigned",
                "evidence": "; ".join(span.excerpt for span in finding.justification.evidence),
                "correlation_id": finding.justification.correlation_id,
            }
        )

    supplier_rows: list[dict[str, object]] = []
    for supplier in snapshot.suppliers:
        supplier_rows.append(
            {
                "supplier": supplier.supplier_display_name,
                "role": supplier.role.value,
                "linked_materials": ", ".join(supplier.linked_material_names),
            }
        )

    verification_rows: list[dict[str, object]] = []
    for assertion in snapshot.verifications:
        verification_rows.append(
            {
                "claim": assertion.claim_summary,
                "status": assertion.status.value,
                "notes": assertion.reviewer_notes or "",
            }
        )

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

    accepted_n = sum(1 for v in snapshot.verifications if v.status is VerificationStatus.ACCEPTED)
    review_n = sum(
        1 for v in snapshot.verifications if v.status is VerificationStatus.REVIEW_REQUIRED
    )
    rejected_n = sum(1 for v in snapshot.verifications if v.status is VerificationStatus.REJECTED)

    st.subheader("Verification")
    st.markdown("##### Verifier posture (this run)")
    theme.render_verifier_chips(
        st,
        accepted=accepted_n,
        review_required=review_n,
        rejected=rejected_n,
    )

    st.dataframe(pd.DataFrame(verification_rows), use_container_width=True, hide_index=True)
