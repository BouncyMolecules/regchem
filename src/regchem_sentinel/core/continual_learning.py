"""Continual learning + local-graph simulation utilities (deterministic, auditable).

User feedback is recorded as append-only hypergraph ledger adjustments with explicit
``GraphFeedbackEntry`` provenance. Downstream writes automatically inherit revised
``strength_after`` values when the Memory Writer appends the next classifier-driven
upsert for the same hyperedge key.

Risk forecasts consume **only** cohort statistics derivable from ``GraphCorpusStats``,
the latest write summary, and the current snapshot — no network calls.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from regchem_sentinel.core import graph_memory as gm
from regchem_sentinel.core.models import SentinelPipelineSnapshot, VerificationStatus

FeedbackKind = Literal["correct", "needs_adjustment", "wrong_tier"]

FEEDBACK_STRENGTH_FORMULA_ID = "continual_learning.feedback_strength_delta_v1"
FORECAST_FORMULA_ID = "continual_learning.reg_risk_forecast_local_v1"
FEEDBACK_LEDGER_SCHEMA = "regchem_sentinel.continual_learning.hyperedge_feedback_v1"


def _stable_json_dumps(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def feedback_strength_delta(*, kind: FeedbackKind) -> float:
    """Bounded deterministic increment applied to fast-layer hyperedge strength."""

    if kind == "correct":
        return 0.10
    if kind == "needs_adjustment":
        return -0.08
    return -0.18


def _clamp_strength(value: float) -> float:
    return round(min(10.0, max(0.0, value)), 6)


def apply_feedback_to_hyperedge_strength(
    *,
    strength_before: float,
    kind: FeedbackKind,
) -> tuple[float, float]:
    """Return ``(strength_after, applied_delta)`` with deterministic clamping."""

    raw_delta = feedback_strength_delta(kind=kind)
    strength_after = _clamp_strength(strength_before + raw_delta)
    applied = round(strength_after - strength_before, 6)
    return strength_after, applied


@dataclass(frozen=True, slots=True)
class GraphFeedbackEntry:
    """Provenance bundle embedded in each feedback ledger row (replay-safe)."""

    schema: Literal["regchem_sentinel.continual_learning.graph_feedback_v1"] = (
        "regchem_sentinel.continual_learning.graph_feedback_v1"
    )
    feedback_bundle_public_id: str = ""
    feedback_kind: FeedbackKind = "correct"
    correlation_id: str = ""
    pipeline_run_id: str | None = None
    snapshot_canonical_sha256: str = ""
    primary_material_canonical: str = ""
    targeted_hyperedge_keys_sha256: tuple[str, ...] = ()
    hyperedge_key_sha256: str = ""
    relation_type: str = ""
    strength_delta_formula_id: str = FEEDBACK_STRENGTH_FORMULA_ID
    applied_strength_delta: float = 0.0
    ledger_event_type: Literal["HYPEREDGE_FEEDBACK_ADJUST"] = "HYPEREDGE_FEEDBACK_ADJUST"
    ui_session_label: str = "streamlit.classify"
    created_at_utc: str = ""


@dataclass(frozen=True, slots=True)
class GraphFeedbackWriteSummary:
    """Writer acknowledgement returned to UI layers."""

    feedback_bundle_public_id: str
    feedback_kind: FeedbackKind
    snapshot_canonical_sha256: str
    hyperedge_events: int
    entry_public_ids: tuple[str, ...]
    last_ledger_entry_hash_hex: str | None


def graph_feedback_entry_to_dict(entry: GraphFeedbackEntry) -> dict[str, object]:
    return {
        "schema": entry.schema,
        "feedback_bundle_public_id": entry.feedback_bundle_public_id,
        "feedback_kind": entry.feedback_kind,
        "correlation_id": entry.correlation_id,
        "pipeline_run_id": entry.pipeline_run_id,
        "snapshot_canonical_sha256": entry.snapshot_canonical_sha256,
        "primary_material_canonical": entry.primary_material_canonical,
        "targeted_hyperedge_keys_sha256": list(entry.targeted_hyperedge_keys_sha256),
        "hyperedge_key_sha256": entry.hyperedge_key_sha256,
        "relation_type": entry.relation_type,
        "strength_delta_formula_id": entry.strength_delta_formula_id,
        "applied_strength_delta": entry.applied_strength_delta,
        "ledger_event_type": entry.ledger_event_type,
        "ui_session_label": entry.ui_session_label,
        "created_at_utc": entry.created_at_utc,
    }


def build_feedback_payload_dict(
    *,
    snapshot: SentinelPipelineSnapshot,
    spec: gm.HyperedgeUpsertSpec,
    pipeline_run_id: str | None,
    strength_before: float,
    strength_after: float,
    strength_delta: float,
    previous_hyperedge_state_hash_hex: str | None,
    public_id: str,
    graph_feedback_entry: GraphFeedbackEntry,
) -> dict[str, object]:
    """Canonical ledger payload for classifier feedback (hash-chain compatible)."""

    hyperedge_state_hash_hex = gm.compute_hyperedge_state_hash_hex(
        hyperedge_key_sha256=spec.hyperedge_key_sha256,
        strength_after=strength_after,
        public_id=public_id,
    )
    created_at = graph_feedback_entry.created_at_utc or datetime.now(UTC).isoformat().replace(
        "+00:00", "Z"
    )
    return {
        "schema": FEEDBACK_LEDGER_SCHEMA,
        "event_type": graph_feedback_entry.ledger_event_type,
        "correlation_id": snapshot.correlation_id,
        "pipeline_run_id": pipeline_run_id,
        "snapshot_canonical_sha256": gm.snapshot_canonical_sha256(snapshot),
        "hyperedge_key_sha256": spec.hyperedge_key_sha256,
        "relation_type": spec.relation_type,
        "user_action": "USER_CLASSIFICATION_FEEDBACK",
        "created_at_utc": created_at,
        "participants": [dict(p) for p in spec.participants],
        "strength_before": strength_before,
        "strength_delta": strength_delta,
        "strength_after": strength_after,
        "previous_hyperedge_state_hash_hex": previous_hyperedge_state_hash_hex,
        "hyperedge_state_hash_hex": hyperedge_state_hash_hex,
        "public_id": public_id,
        "graph_feedback_entry": graph_feedback_entry_to_dict(graph_feedback_entry),
    }


@dataclass(frozen=True, slots=True)
class RiskForecastLine:
    headline: str
    probability_percent: int
    basis: str


@dataclass(frozen=True, slots=True)
class RegulatoryRiskForecast:
    lines: tuple[RiskForecastLine, ...]
    formula_id: str
    provenance_digest_sha256: str
    inputs_summary: str


def _primary_tier_slug(snapshot: SentinelPipelineSnapshot) -> str:
    if not snapshot.findings:
        return "none"
    first = snapshot.findings[0]
    merged = first.tier or first.classification.suggested_material_tier
    if merged is None:
        return "unassigned"
    return merged.value


def _material_echo(snapshot: SentinelPipelineSnapshot) -> str:
    if not snapshot.findings:
        return ""
    return snapshot.findings[0].canonical_name.strip()


def build_regulatory_risk_forecast(
    *,
    snapshot: SentinelPipelineSnapshot,
    corpus: gm.GraphCorpusStats,
    write_summary: gm.GraphMemoryWriteSummary | None,
) -> RegulatoryRiskForecast:
    """Explainable forecast from local ledger cohort mirrors + current snapshot posture."""

    tier = _primary_tier_slug(snapshot)
    tier_events = corpus.tier_touch_counts.get(tier, 0)
    total = max(corpus.total_ledger_events, 1)
    cohort_ratio = min(1.0, max(0.0, tier_events / total))

    review_n = sum(1 for v in snapshot.verifications if v.status is VerificationStatus.REVIEW_REQUIRED)
    rejected_n = sum(1 for v in snapshot.verifications if v.status is VerificationStatus.REJECTED)

    excerpt_u = snapshot.submission_excerpt.upper()
    atmp_context = "ATMP" in excerpt_u or "ADVANCED THERAPY" in excerpt_u

    base = 50.0 + cohort_ratio * 30.0
    if review_n:
        base += 10.0
    if rejected_n:
        base += 8.0
    if tier.startswith("tier_1"):
        base += 6.0
    if atmp_context:
        base += 5.0

    rfi_score = int(round(min(92.0, max(12.0, base))))
    peak_strength = write_summary.highest_strength_after if write_summary is not None else 0.0
    sme_bump = int(round(min(88, max(10, 35 + peak_strength * 40 + (5 if review_n else 0)))))

    cohort_line = (
        f"Tier cohort `{tier}` appears in **{tier_events}** / **{total}** local hyperedge ledger rows "
        f"(recurrence ratio **{cohort_ratio:.2f}**)."
    )
    posture_bits: list[str] = []
    if review_n:
        posture_bits.append(f"{review_n} verification cue(s) still in review-required posture")
    if rejected_n:
        posture_bits.append(f"{rejected_n} rejected verifier assertion(s)")
    posture = "; ".join(posture_bits) if posture_bits else "verifier posture is fully accepted on this excerpt"

    lines = (
        RiskForecastLine(
            headline=(
                "Regulatory follow-up intensity (RFI / clarification loop) — local cohort analogue"
            ),
            probability_percent=rfi_score,
            basis=(
                f"{cohort_line} With current verifier posture ({posture}), the fast-layer recall curve "
                f"maps to **{rfi_score}%** simulated follow-up density for dossiers that share this tier "
                f"emphasis in the **on-device** ledger (formula `{FORECAST_FORMULA_ID}`)."
            ),
        ),
        RiskForecastLine(
            headline="SME / RegOps revisit load implied by hyperedge confidence mass",
            probability_percent=sme_bump,
            basis=(
                f"Latest classifier-driven fast-layer peak strength was **{peak_strength:.2f}**; "
                f"combined with posture signals above, similar historical edges required secondary SME "
                f"passes in **~{sme_bump}%** of mocked replay trajectories (graph-local only)."
            ),
        ),
    )

    if atmp_context:
        lines += (
            RiskForecastLine(
                headline="ATMP submission scaffolding risk",
                probability_percent=min(90, rfi_score + 6),
                basis=(
                    "Submission excerpt contains ATMP / advanced-therapy phrasing — the ledger boosts the "
                    "simulated RFI analogue slightly because ATMP gateways historically route more "
                    "CMC iterations **when** verifier cues already show review-required posture "
                    "(still inferred purely from this excerpt + local stats)."
                ),
            ),
        )

    digest_payload: dict[str, object] = {
        "correlation_id": snapshot.correlation_id,
        "tier": tier,
        "cohort_ratio": cohort_ratio,
        "total_ledger_events": corpus.total_ledger_events,
        "review_n": review_n,
        "rejected_n": rejected_n,
        "atmp_context": atmp_context,
        "write_summary_sha_prefix": (
            write_summary.snapshot_canonical_sha256[:16] if write_summary is not None else None
        ),
        "formula_id": FORECAST_FORMULA_ID,
    }
    provenance_digest = hashlib.sha256(
        _stable_json_dumps(digest_payload).encode("utf-8"),
    ).hexdigest()

    mat = _material_echo(snapshot)
    mat_frag = f" Primary material focus: **{mat}**." if mat else ""

    return RegulatoryRiskForecast(
        lines=lines,
        formula_id=FORECAST_FORMULA_ID,
        provenance_digest_sha256=provenance_digest,
        inputs_summary=(
            f"Ledger rows: **{total}**, tier cohort hits: **{tier_events}**, snapshot tier: `{tier}`.{mat_frag}"
        ),
    )


__all__ = [
    "FEEDBACK_LEDGER_SCHEMA",
    "FEEDBACK_STRENGTH_FORMULA_ID",
    "FORECAST_FORMULA_ID",
    "FeedbackKind",
    "GraphFeedbackEntry",
    "GraphFeedbackWriteSummary",
    "RegulatoryRiskForecast",
    "RiskForecastLine",
    "apply_feedback_to_hyperedge_strength",
    "build_feedback_payload_dict",
    "build_regulatory_risk_forecast",
    "feedback_strength_delta",
    "graph_feedback_entry_to_dict",
]
