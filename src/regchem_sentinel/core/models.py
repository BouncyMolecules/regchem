"""Pure domain models for traceable SM / supplier decision support."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from enum import Enum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import Column, Index, Text
from sqlmodel import Field as SQLField
from sqlmodel import SQLModel


class MaterialTier(Enum):
    """Heuristic regulatory emphasis — not a validated GMP classification."""

    TIER_1_REGISTERED = "tier_1_registered"
    TIER_2_CRITICAL = "tier_2_critical"
    TIER_3_SUPPORTING = "tier_3_supporting"


class SupplierRole(Enum):
    MANUFACTURER = "manufacturer"
    TESTING = "testing_laboratory"
    DISTRIBUTOR = "distributor"
    UNKNOWN = "unknown"


class VerificationStatus(Enum):
    ACCEPTED = "accepted"
    REVIEW_REQUIRED = "review_required"
    REJECTED = "rejected"


class DetectorTier(Enum):
    """Layered cue strength for explainable ensembles (FDA-style narrative synthesis).

    orthogonal to ``MaterialTier`` (regulatory emphasis of the surfaced entity).
    """

    TIER_1_DIRECT_REGISTRATION_LANGUAGE = "tier_1_direct"
    TIER_2_STRUCTURE_TABLE_SENTENCE = "tier_2_structure"
    TIER_3_CONTEXTUAL_WEAK = "tier_3_contextual"


DatabaseLookupOutcome = Literal[
    "hit",
    "miss",
    "ambiguous",
    "stub_not_configured",
    "rate_limited",
    "error_transient",
]


class ProvenanceSpan(BaseModel):
    """Pointer to user-provided text plus optional structural locator for audit replay."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    excerpt: str = Field(
        min_length=1,
        description="Quoted or copied span from the submission text.",
    )
    locator: str | None = Field(
        default=None,
        description="Structural hint / opaque path (page, section, XPath) supplied by ingesters.",
    )
    page_number: int | None = Field(default=None, ge=1)
    section_label: str | None = Field(
        default=None,
        description="Human-readable section/table label when structurally inferred.",
    )
    char_offset_start: int | None = Field(default=None, ge=0)
    char_offset_end: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _offsets_ordered(self) -> Self:
        if (
            self.char_offset_start is not None
            and self.char_offset_end is not None
            and self.char_offset_end < self.char_offset_start
        ):
            raise ValueError("char_offset_end must be >= char_offset_start")
        return self


class AgentAttribution(BaseModel):
    """Captures which algorithm / ruleset produced a piece of evidence or a verifier cue."""

    model_config = ConfigDict(frozen=True)

    actor_name: str = Field(min_length=1)
    actor_version: str | None = None
    modality: Literal[
        "deterministic_rules",
        "ml_model",
        "llm_primary",
        "llm_verifier",
        "human_curated",
    ] = "deterministic_rules"
    rule_identifier: str | None = Field(
        default=None,
        description="Stable identifier for auditors (e.g. ``sm.tier2.sentence_skeleton``).",
    )


class DecisionProvenance(BaseModel):
    """Bundles trace for a surfaced field — machine- and reviewer-readable."""

    model_config = ConfigDict(frozen=True)

    correlation_id: str = Field(min_length=1)
    decision_id: str | None = Field(
        default=None,
        description="Optional stable id tying together classifier + verifier chain rows.",
    )
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    evidence: tuple[ProvenanceSpan, ...] = ()
    rationales: tuple[str, ...] = ()
    attributions: tuple[AgentAttribution, ...] = ()
    predecessor_refs: tuple[str, ...] = Field(
        default=(),
        description="Upstream artefact refs (prior model hashes, dossier hashes) — optional.",
    )


class SubmissionParseAudit(BaseModel):
    model_config = ConfigDict(frozen=True)

    parser_name: str = Field(default="deterministic_page_segmenter")
    parser_version: str = Field(default="1.0.0")
    attributions: tuple[AgentAttribution, ...] = ()


class TextSegment(BaseModel):
    """A contiguous fragment of submission text anchored in global character offsets."""

    model_config = ConfigDict(frozen=True)

    text: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    char_offset_start: int = Field(ge=0)
    char_offset_end: int = Field(ge=0)

    @model_validator(mode="after")
    def _span_consistent(self) -> Self:
        if self.char_offset_end < self.char_offset_start:
            raise ValueError("char_offset_end must be >= char_offset_start")
        return self


class ParsedSubmission(BaseModel):
    """Structured view of unstructured narrative — first hop in the audited pipeline."""

    model_config = ConfigDict(frozen=True)

    full_text: str = Field(min_length=1)
    segments: tuple[TextSegment, ...] = Field(min_length=1)
    content_sha256: str = Field(min_length=32, max_length=64)
    audit: SubmissionParseAudit = Field(default_factory=SubmissionParseAudit)

    @classmethod
    def from_full_text(
        cls, raw: str, *, audit: SubmissionParseAudit | None = None
    ) -> ParsedSubmission:
        """Deterministic splitter on form-feed page breaks — common in PDF ingest."""

        stripped = raw
        digest = hashlib.sha256(stripped.encode("utf-8")).hexdigest()

        segments: list[TextSegment] = []

        def build_segment(slice_start: int, slice_end: int, *, page_no: int) -> None:
            chunk = stripped[slice_start:slice_end]
            if chunk.strip():
                segments.append(
                    TextSegment(
                        text=chunk,
                        page_number=page_no,
                        char_offset_start=slice_start,
                        char_offset_end=slice_end,
                    )
                )

        separators = tuple(m.span() for m in re.finditer(r"\f+", stripped))

        slice_start = 0
        page = 1
        for span_start, span_end in separators:
            build_segment(slice_start, span_start, page_no=page)
            slice_start = span_end
            page += 1
        build_segment(slice_start, len(stripped), page_no=page)

        if not segments:
            segments = [
                TextSegment(
                    text=stripped,
                    page_number=1,
                    char_offset_start=0,
                    char_offset_end=len(stripped),
                )
            ]

        used_audit = audit or SubmissionParseAudit(
            attributions=(
                AgentAttribution(
                    actor_name="deterministic_page_segmenter",
                    actor_version="1.0.0",
                    modality="deterministic_rules",
                    rule_identifier="parse.form_feed_pages",
                ),
            )
        )
        return cls(
            full_text=stripped, segments=tuple(segments), content_sha256=digest, audit=used_audit
        )


class TieredConfidence(BaseModel):
    """Explicit per-layer scores used in audit responses to model-drift questions."""

    model_config = ConfigDict(frozen=True)

    tier_1_score: float = Field(ge=0.0, le=1.0)
    tier_2_score: float = Field(ge=0.0, le=1.0)
    tier_3_score: float = Field(ge=0.0, le=1.0)
    aggregate: float = Field(ge=0.0, le=1.0)
    formula_id: str = Field(
        default="weighted_sum_cap_1.0_v1",
        description="Versioned aggregate recipe for downstream regression baselines.",
    )


class RuleContribution(BaseModel):
    """One explainable rule firing within the ensemble."""

    model_config = ConfigDict(frozen=True)

    rule_id: str = Field(min_length=1)
    detector_tier: DetectorTier
    contribution: float = Field(ge=0.0, le=1.0)
    matched: bool
    detail: str = Field(min_length=1)
    method: Literal["context", "table", "sentence_structure", "follow_on_word", "regex"] = "regex"
    page_number: int | None = Field(default=None, ge=1)
    locator: str | None = None
    material_hint: MaterialTier | None = Field(
        default=None,
        description="Regulatory-emphasis suggestion carried from the firing rule.",
    )


class ClassificationResult(BaseModel):
    """Structured classifier output layered on narrative evidence."""

    model_config = ConfigDict(frozen=True)

    detector_summary: str = Field(min_length=1)
    tiered_confidence: TieredConfidence
    rule_contributions: tuple[RuleContribution, ...]
    suggested_material_tier: MaterialTier | None = None


class StartingMaterial(BaseModel):
    """Hypothesis surfaced from unstructured text with explicit classification provenance."""

    model_config = ConfigDict(frozen=True)

    canonical_name: str = Field(min_length=1)
    synonyms: tuple[str, ...] = ()
    tier: MaterialTier | None = None
    classification: ClassificationResult
    justification: DecisionProvenance

    @field_validator("synonyms")
    @classmethod
    def _normalize_synonyms(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        collapsed = tuple(sorted({s.strip(): None for s in value if s.strip()}.keys()))
        return collapsed

    @model_validator(mode="after")
    def _tier_alignment(self) -> Self:
        if self.tier is None and self.classification.suggested_material_tier is not None:
            return self.model_copy(update={"tier": self.classification.suggested_material_tier})
        return self


class Supplier(BaseModel):
    """Supplier / testing org linkage grounded in narrative spans."""

    model_config = ConfigDict(frozen=True)

    supplier_display_name: str = Field(min_length=1)
    role: SupplierRole = SupplierRole.UNKNOWN
    linked_material_names: tuple[str, ...] = ()
    citation: DecisionProvenance


class DatabaseLookupRecord(BaseModel):
    """Stub-friendly external reference — never implies vendor validation without SME sign-off."""

    model_config = ConfigDict(frozen=True)

    query_key: str = Field(min_length=1)
    outcome: DatabaseLookupOutcome
    detail: str = Field(default="")
    queried_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    attribution: AgentAttribution = Field(
        default_factory=lambda: AgentAttribution(actor_name="external_db_stub"),
    )


class VerificationCueResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    cue_id: str = Field(min_length=1)
    passed: bool
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    detail: str = Field(min_length=1)
    evidence: tuple[ProvenanceSpan, ...] = ()
    attribution: AgentAttribution
    lookups: tuple[DatabaseLookupRecord, ...] = ()


class VerificationAssertion(BaseModel):
    model_config = ConfigDict(frozen=True)

    claim_summary: str = Field(min_length=1)
    status: VerificationStatus
    reviewer_notes: str | None = None
    corroboration_passes: tuple[AgentAttribution, ...] = ()
    cue_results: tuple[VerificationCueResult, ...] = ()
    verification_chain: DecisionProvenance | None = None


StartingMaterialFinding = StartingMaterial
SupplierLinkage = Supplier


class SentinelPipelineSnapshot(BaseModel):
    """Immutable bundle returned to UI / exporters after one end-to-end pass."""

    model_config = ConfigDict(frozen=True)

    correlation_id: str = Field(min_length=1)
    submission_excerpt: str = Field(min_length=1)
    parsed_submission: ParsedSubmission
    findings: tuple[StartingMaterial, ...]
    suppliers: tuple[Supplier, ...]
    verifications: tuple[VerificationAssertion, ...]


# ---------------------------------------------------------------------------
# SQL persistence models (SQLModel + SQLite) — append-only at service boundary
# ---------------------------------------------------------------------------


class PipelineRunRecord(SQLModel, table=True):
    """Root immutable row for a single ``run_pipeline`` persistence event.

    The canonical binary-equivalent payload is ``snapshot_json_canonical`` together with
    ``snapshot_canonical_sha256``; normalized child tables exist for indexed retrieval
    and regulatory traceability without requiring JSON scanning at read time.
    """

    __tablename__ = "pipeline_run"
    __table_args__ = (
        Index("ix_pipeline_run_corr_created", "correlation_id", "created_at_utc"),
        Index("ix_pipeline_run_created", "created_at_utc"),
    )

    id: str = SQLField(primary_key=True, max_length=36)
    correlation_id: str = SQLField(nullable=False, index=True, max_length=512)
    created_at_utc: datetime = SQLField(nullable=False, index=True)
    submission_excerpt: str = SQLField(sa_column=Column(Text, nullable=False))
    snapshot_canonical_sha256: str = SQLField(nullable=False, max_length=64, index=True)
    snapshot_json_canonical: str = SQLField(sa_column=Column(Text, nullable=False))


class ParsedSubmissionRecord(SQLModel, table=True):
    """Persisted parse artefact (1:1 with a pipeline run)."""

    __tablename__ = "parsed_submission"
    __table_args__ = (Index("ix_parsed_submission_sha", "content_sha256_hex"),)

    id: str = SQLField(primary_key=True, max_length=36)
    pipeline_run_id: str = SQLField(
        foreign_key="pipeline_run.id", nullable=False, unique=True, index=True
    )
    content_sha256_hex: str = SQLField(nullable=False, max_length=64)
    parser_name: str = SQLField(nullable=False, default="", max_length=256)
    parser_version: str = SQLField(nullable=False, default="", max_length=64)
    parse_audit_json: str = SQLField(
        sa_column=Column(Text, nullable=False),
        description="Serialized ``SubmissionParseAudit`` (parser provenance).",
    )
    record_json: str = SQLField(
        sa_column=Column(Text, nullable=False),
        description="Full ``ParsedSubmission`` JSON including segments.",
    )


class StartingMaterialRecord(SQLModel, table=True):
    """Material hypothesis row with embedded justification / provenance JSON."""

    __tablename__ = "starting_material"
    __table_args__ = (
        Index("ix_starting_material_run_seq", "pipeline_run_id", "sequence_index"),
        Index("ix_starting_material_name", "canonical_name"),
    )

    id: str = SQLField(primary_key=True, max_length=36)
    pipeline_run_id: str = SQLField(foreign_key="pipeline_run.id", nullable=False, index=True)
    sequence_index: int = SQLField(nullable=False, ge=0)
    canonical_name: str = SQLField(nullable=False, index=True, max_length=1024)
    material_tier: str | None = SQLField(default=None, max_length=64, index=True)
    synonyms_json: str = SQLField(sa_column=Column(Text, nullable=False))
    justification_json: str = SQLField(
        sa_column=Column(Text, nullable=False),
        description="Serialized ``DecisionProvenance`` for the material hypothesis.",
    )
    record_json: str = SQLField(
        sa_column=Column(Text, nullable=False),
        description="Full ``StartingMaterial`` JSON for round-trip fidelity checks.",
    )


class ClassificationResultRecord(SQLModel, table=True):
    """Structured classifier emission tied 1:1 to a persisted starting-material row."""

    __tablename__ = "classification_result"
    __table_args__ = (Index("ix_classification_run", "pipeline_run_id"),)

    id: str = SQLField(primary_key=True, max_length=36)
    pipeline_run_id: str = SQLField(foreign_key="pipeline_run.id", nullable=False, index=True)
    starting_material_id: str = SQLField(
        foreign_key="starting_material.id", nullable=False, unique=True, index=True
    )
    detector_summary: str = SQLField(sa_column=Column(Text, nullable=False))
    tiered_json: str = SQLField(sa_column=Column(Text, nullable=False))
    contributions_json: str = SQLField(
        sa_column=Column(Text, nullable=False),
        description="Serialized ``tuple[RuleContribution, ...]`` as JSON array.",
    )
    suggested_material_tier: str | None = SQLField(default=None, max_length=64)
    tier_1_score: float | None = SQLField(default=None, nullable=True)
    tier_2_score: float | None = SQLField(default=None, nullable=True)
    tier_3_score: float | None = SQLField(default=None, nullable=True)
    aggregate_score: float | None = SQLField(default=None, nullable=True, index=True)
    record_json: str = SQLField(
        sa_column=Column(Text, nullable=False),
        description="Full ``ClassificationResult`` JSON.",
    )


class SupplierRecord(SQLModel, table=True):
    """Persisted supplier / testing-org linkage surfaced by the linker."""

    __tablename__ = "supplier"
    __table_args__ = (
        Index("ix_supplier_run_seq", "pipeline_run_id", "sequence_index"),
        Index("ix_supplier_display", "supplier_display_name"),
    )

    id: str = SQLField(primary_key=True, max_length=36)
    pipeline_run_id: str = SQLField(foreign_key="pipeline_run.id", nullable=False, index=True)
    sequence_index: int = SQLField(nullable=False, ge=0)
    supplier_display_name: str = SQLField(nullable=False, index=True, max_length=1024)
    role: str = SQLField(nullable=False, max_length=64)
    linked_material_names_json: str = SQLField(sa_column=Column(Text, nullable=False))
    citation_json: str = SQLField(
        sa_column=Column(Text, nullable=False),
        description="Serialized ``DecisionProvenance`` for supplier citation.",
    )
    record_json: str = SQLField(
        sa_column=Column(Text, nullable=False),
        description="Full ``Supplier`` JSON.",
    )


class VerificationAssertionRecord(SQLModel, table=True):
    """Verifier bundle for a pipeline run (assertion-level provenance)."""

    __tablename__ = "verification_assertion"
    __table_args__ = (
        Index("ix_verification_run_seq", "pipeline_run_id", "sequence_index"),
        Index("ix_verification_status", "verification_status"),
    )

    id: str = SQLField(primary_key=True, max_length=36)
    pipeline_run_id: str = SQLField(foreign_key="pipeline_run.id", nullable=False, index=True)
    sequence_index: int = SQLField(nullable=False, ge=0)
    claim_summary: str = SQLField(sa_column=Column(Text, nullable=False))
    verification_status: str = SQLField(nullable=False, max_length=64)
    reviewer_notes: str | None = SQLField(sa_column=Column(Text, nullable=True), default=None)
    verification_chain_json: str | None = SQLField(
        sa_column=Column(Text, nullable=True),
        default=None,
        description="Optional serialized ``DecisionProvenance`` for verifier chain.",
    )
    record_json: str = SQLField(
        sa_column=Column(Text, nullable=False),
        description="Full ``VerificationAssertion`` including cue tuples.",
    )


class VerificationCueResultRecord(SQLModel, table=True):
    """Exploded verifier cue rows for indexed review of cue-level outcomes."""

    __tablename__ = "verification_cue_result"
    __table_args__ = (
        Index("ix_cue_run_cue_id", "pipeline_run_id", "cue_stable_id"),
        Index("ix_cue_assertion_seq", "verification_assertion_id", "sequence_index"),
    )

    id: str = SQLField(primary_key=True, max_length=36)
    pipeline_run_id: str = SQLField(foreign_key="pipeline_run.id", nullable=False, index=True)
    verification_assertion_id: str = SQLField(
        foreign_key="verification_assertion.id", nullable=False, index=True
    )
    sequence_index: int = SQLField(nullable=False, ge=0)
    cue_stable_id: str = SQLField(nullable=False, index=True, max_length=512)
    passed: bool = SQLField(nullable=False)
    attribution_json: str = SQLField(
        sa_column=Column(Text, nullable=False),
        description="Serialized ``AgentAttribution`` for the cue.",
    )
    record_json: str = SQLField(
        sa_column=Column(Text, nullable=False),
        description="Full ``VerificationCueResult`` JSON including evidence and lookups.",
    )


class AuditTrailEntry(SQLModel, table=True):
    """Append-only integrity-oriented audit ledger row (hash-chained where supported).

    Mutating or deleting rows via application APIs is intentionally unsupported; database
    administrators must treat tamper evidence through filesystem / backup controls.
    """

    __tablename__ = "audit_trail_entry"
    __table_args__ = (
        Index("ix_audit_corr_entry", "correlation_id", "entry_id"),
        Index("ix_audit_run", "pipeline_run_id"),
    )

    entry_id: int | None = SQLField(default=None, primary_key=True)
    public_id: str = SQLField(nullable=False, unique=True, index=True, max_length=36)
    created_at_utc: datetime = SQLField(nullable=False, index=True)
    event_type: str = SQLField(nullable=False, index=True, max_length=128)
    correlation_id: str = SQLField(nullable=False, index=True, max_length=512)
    pipeline_run_id: str | None = SQLField(
        default=None, foreign_key="pipeline_run.id", nullable=True, index=True, max_length=36
    )
    payload_json: str = SQLField(sa_column=Column(Text, nullable=False))
    previous_entry_hash_hex: str | None = SQLField(default=None, max_length=64)
    entry_hash_hex: str = SQLField(nullable=False, max_length=64, index=True)


__all__ = [
    "AgentAttribution",
    "AuditTrailEntry",
    "ClassificationResult",
    "ClassificationResultRecord",
    "DatabaseLookupOutcome",
    "DatabaseLookupRecord",
    "DecisionProvenance",
    "DetectorTier",
    "MaterialTier",
    "ParsedSubmission",
    "ParsedSubmissionRecord",
    "PipelineRunRecord",
    "ProvenanceSpan",
    "RuleContribution",
    "SentinelPipelineSnapshot",
    "StartingMaterial",
    "StartingMaterialFinding",
    "StartingMaterialRecord",
    "SubmissionParseAudit",
    "Supplier",
    "SupplierLinkage",
    "SupplierRecord",
    "SupplierRole",
    "TextSegment",
    "TieredConfidence",
    "VerificationAssertion",
    "VerificationAssertionRecord",
    "VerificationCueResult",
    "VerificationCueResultRecord",
    "VerificationStatus",
]
