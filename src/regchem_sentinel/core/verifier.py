"""Multi-cue verification with explicit chain provenance — no single cue is authoritative."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal, Protocol

from regchem_sentinel.config import Settings
from regchem_sentinel.core.models import (
    AgentAttribution,
    DatabaseLookupRecord,
    DecisionProvenance,
    ParsedSubmission,
    ProvenanceSpan,
    StartingMaterial,
    Supplier,
    VerificationAssertion,
    VerificationCueResult,
    VerificationStatus,
)

SubstringPolicy = Literal["verbatim", "normalized_ws"]


class ExternalDatabaseLookup(Protocol):
    """Future hook — pharmacopeia/CDE registries. Stubs MUST label ``stub_not_configured``."""

    def lookup_by_substance_display_name(
        self,
        name: str,
        *,
        correlation_id: str,
    ) -> DatabaseLookupRecord: ...


class _StubSubstanceRegistrar(ExternalDatabaseLookup):
    """Placeholder until governed database credentials land in vault."""

    def lookup_by_substance_display_name(
        self,
        name: str,
        *,
        correlation_id: str,
    ) -> DatabaseLookupRecord:
        _ = correlation_id
        attribution = AgentAttribution(
            actor_name="regulated_substance_index_stub",
            actor_version="0.1.0",
            modality="deterministic_rules",
            rule_identifier="extdb.stub.policy",
        )
        return DatabaseLookupRecord(
            query_key=name.casefold(),
            outcome="stub_not_configured",
            detail="Registrar integration disabled — verifier records intent only.",
            attribution=attribution,
        )


@dataclass(frozen=True, slots=True)
class _NormalizationPolicy:
    """Dual-view reproducibility artifact for whitespace / unicode edge cases."""

    label: SubstringPolicy

    def view(self, text: str) -> str:
        if self.label == "verbatim":
            return text
        collapsed = " ".join(text.split())
        return collapsed.casefold()


def _norm_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _chain_provenance(
    *, correlation_id: str, claim: str, steps: tuple[str, ...]
) -> DecisionProvenance:
    return DecisionProvenance(
        correlation_id=correlation_id,
        decision_id=_norm_hash(correlation_id + claim),
        evidence=(),
        rationales=steps,
        attributions=(
            AgentAttribution(
                actor_name="chain_of_verification",
                actor_version="1.0.0",
                modality="deterministic_rules",
                rule_identifier="verify.chain.serialization",
            ),
        ),
        predecessor_refs=tuple(dict.fromkeys(steps)),
    )


class SubmissionVerifier(Protocol):
    def verify(
        self,
        *,
        submission_text: str,
        parsed_submission: ParsedSubmission,
        findings: Sequence[StartingMaterial],
        suppliers: Sequence[Supplier],
        correlation_id: str,
    ) -> tuple[VerificationAssertion, ...]:
        """Produce verification artifacts without mutating upstream objects."""


def _normalized_contains(haystack: str, needle: str) -> bool:
    stacked = _NormalizationPolicy("normalized_ws").view(haystack)
    need = _NormalizationPolicy("normalized_ws").view(needle)
    return need in stacked


class MultiCueVerifier:
    """Deterministic ensemble that must converge toward ACCEPTED."""

    ATT_SUBSTRING_VERBATIM_VERSION = "1.1.0"
    ATT_FUZZY_VERSION = "1.0.0"
    ATT_SELF_CONSISTENCY_VERSION = "1.0.0"
    ATT_SUPPLIER_WINDOW_VERSION = "1.0.0"

    def __init__(
        self, settings: Settings, *, database: ExternalDatabaseLookup | None = None
    ) -> None:
        self._settings = settings
        self._database = database or _StubSubstanceRegistrar()

    def verify(
        self,
        *,
        submission_text: str,
        parsed_submission: ParsedSubmission,
        findings: Sequence[StartingMaterial],
        suppliers: Sequence[Supplier],
        correlation_id: str,
    ) -> tuple[VerificationAssertion, ...]:
        _ = self._settings
        assertions: list[VerificationAssertion] = []

        ingest_ok = (
            submission_text.replace("\u00a0", " ").strip()
            == parsed_submission.full_text.replace("\u00a0", " ").strip()
        )
        ingest_sha_ok = (
            parsed_submission.content_sha256
            == hashlib.sha256(parsed_submission.full_text.encode("utf-8")).hexdigest()
        )
        assertions.append(
            VerificationAssertion(
                claim_summary="Parse buffer ↔ verifier buffer integrity",
                status=VerificationStatus.ACCEPTED
                if ingest_ok and ingest_sha_ok
                else VerificationStatus.REJECTED,
                reviewer_notes=(
                    "Submission text aligns with ParsedSubmission fingerprints."
                    if ingest_ok and ingest_sha_ok
                    else (
                        "Upstream parse/hash mismatch — reject automation "
                        "until pipeline integrity restored."
                    )
                ),
                cue_results=(
                    VerificationCueResult(
                        cue_id="parse_transport_integrity_sha256",
                        passed=bool(ingest_ok and ingest_sha_ok),
                        score=None,
                        detail=f"parsed_sha256={parsed_submission.content_sha256}|expected_match={ingest_sha_ok}|"
                        f"bytes_equal={ingest_ok}",
                        evidence=(
                            ProvenanceSpan(
                                excerpt=parsed_submission.full_text[:200]
                                + ("…" if len(parsed_submission.full_text) > 200 else ""),
                                locator="parse:root",
                                char_offset_start=0,
                                char_offset_end=min(200, len(parsed_submission.full_text)),
                            ),
                        ),
                        attribution=AgentAttribution(
                            actor_name="parse_transport_guard",
                            actor_version="1.0.0",
                            modality="deterministic_rules",
                            rule_identifier="verify.transport.parse_equals_text",
                        ),
                    ),
                ),
                verification_chain=_chain_provenance(
                    correlation_id=correlation_id,
                    claim="INGEST_TRANSPORT",
                    steps=(
                        "parse_buffer_byte_compare",
                        f"parsed_content_sha256_recompute:{ingest_sha_ok}",
                    ),
                ),
            ),
        )

        for finding in findings:
            assertions.append(self._verify_finding(submission_text, finding, correlation_id))

        for supplier in suppliers:
            assertions.append(self._verify_supplier(submission_text, supplier, correlation_id))

            window_assertion = self._supplier_sm_window_check(
                submission_text,
                supplier,
                findings,
                correlation_id,
            )
            if window_assertion is not None:
                assertions.append(window_assertion)

        return tuple(assertions)

    def _verify_finding(
        self, submission: str, finding: StartingMaterial, correlation_id: str
    ) -> VerificationAssertion:
        cues: list[VerificationCueResult] = []
        spans = tuple(span.excerpt for span in finding.justification.evidence)

        verbatim_ok = False
        for span in spans:
            if span and span in submission:
                verbatim_ok = True
                cues.append(
                    VerificationCueResult(
                        cue_id="verbatim_substring_anchor",
                        passed=True,
                        score=1.0,
                        detail="Evidence span reproduced exactly in submission buffer.",
                        evidence=(ProvenanceSpan(excerpt=span[:500], locator="needle:verbatim"),),
                        attribution=AgentAttribution(
                            actor_name="substring_anchor_verbatim",
                            actor_version=self.ATT_SUBSTRING_VERBATIM_VERSION,
                            modality="deterministic_rules",
                            rule_identifier="verify.substr.verbatim_in_fulltext",
                        ),
                    )
                )
                break

        if not verbatim_ok and spans:
            span0 = spans[0]
            cues.append(
                VerificationCueResult(
                    cue_id="verbatim_substring_anchor",
                    passed=False,
                    detail=(
                        "Evidence excerpt not found verbatim — "
                        "possible truncation or hallucination."
                    ),
                    evidence=(ProvenanceSpan(excerpt=span0[:400]),),
                    attribution=AgentAttribution(
                        actor_name="substring_anchor_verbatim",
                        actor_version=self.ATT_SUBSTRING_VERBATIM_VERSION,
                        modality="deterministic_rules",
                        rule_identifier="verify.substr.verbatim_in_fulltext",
                    ),
                )
            )

        normalized_match = False
        for span in spans:
            if not span:
                continue
            nws = _normalized_contains(submission, span)
            normalized_match |= nws
        cues.append(
            VerificationCueResult(
                cue_id="normalized_ws_self_consistency",
                passed=normalized_match if spans else False,
                score=None,
                detail=(
                    "Dual-view check: lowercase + collapsed whitespace containment."
                    if normalized_match
                    else "Normalized view still fails containment — escalate."
                ),
                evidence=(),
                attribution=AgentAttribution(
                    actor_name="dual_view_normalized_ws",
                    actor_version=self.ATT_SELF_CONSISTENCY_VERSION,
                    modality="deterministic_rules",
                    rule_identifier="verify.self_consistency.normalized_ws",
                ),
            )
        )

        fuzzy_scores: list[float] = []
        for span in spans:
            if not span:
                continue
            score = SequenceMatcher(None, span.lower(), submission.lower()).quick_ratio()
            fuzzy_scores.append(score)
        best_fuzzy = max(fuzzy_scores) if fuzzy_scores else 0.0
        fuzzy_gate = best_fuzzy > 0.28
        cues.append(
            VerificationCueResult(
                cue_id="fuzzy_quick_ratio_broadcast",
                passed=fuzzy_gate,
                score=round(best_fuzzy, 4),
                detail="Cheap fuzzy gate — high recall guard for OCR drift.",
                evidence=(),
                attribution=AgentAttribution(
                    actor_name="normalized_fuzzy_quick_ratio",
                    actor_version=self.ATT_FUZZY_VERSION,
                    modality="deterministic_rules",
                    rule_identifier="verify.fuzzy.quick_ratio",
                ),
            )
        )

        lookup = self._database.lookup_by_substance_display_name(
            finding.canonical_name,
            correlation_id=correlation_id,
        )
        db_pass = lookup.outcome in {"hit"}
        cues.append(
            VerificationCueResult(
                cue_id="external_registrar_stub_resolution",
                passed=db_pass,
                score=None
                if lookup.outcome == "stub_not_configured"
                else (1.0 if db_pass else 0.0),
                detail=(
                    "External registrar stub — never treated as affirmative coverage."
                    if lookup.outcome == "stub_not_configured"
                    else lookup.detail
                ),
                evidence=(
                    ProvenanceSpan(
                        excerpt=f"query={lookup.query_key}|outcome={lookup.outcome}",
                        locator="extdb:latest",
                    ),
                ),
                attribution=lookup.attribution,
                lookups=(lookup,),
            )
        )

        passed_flags = tuple(c.passed for c in cues[:3])
        strict_core = verbatim_ok or (normalized_match and fuzzy_gate)

        if strict_core:
            outcome = VerificationStatus.ACCEPTED
            notes = "Core narrative cues converge (verbatim or normalized+fuzzy)."
        elif passed_flags.count(True) >= 2:
            outcome = VerificationStatus.REVIEW_REQUIRED
            notes = (
                "Partial convergence — deterministic gates disagree; "
                "SMEs must adjudicate drift vs error."
            )
        else:
            outcome = VerificationStatus.REJECTED
            notes = (
                "High-risk divergence — treat classifier output as untrusted "
                "pending manual reconciliation."
            )

        corroborations = tuple(c.attribution for c in cues if c.passed)
        trace = _chain_provenance(
            correlation_id=correlation_id,
            claim=f"SM::{finding.justification.decision_id or finding.canonical_name}",
            steps=(
                "step1_needle_match",
                "step2_dual_whitespace_consistency_check",
                "step3_fuzzy_guard",
                f"step4_external_lookup_policy:{lookup.outcome}",
            ),
        )

        return VerificationAssertion(
            claim_summary=f"SM candidate '{finding.canonical_name}' multi-cue substantiation",
            status=outcome,
            reviewer_notes=notes,
            corroboration_passes=corroborations,
            cue_results=tuple(cues),
            verification_chain=trace,
        )

    def _verify_supplier(
        self, submission: str, supplier: Supplier, correlation_id: str
    ) -> VerificationAssertion:
        span = supplier.citation.evidence[0].excerpt if supplier.citation.evidence else ""
        verbatim = span.lower() in submission.lower() if span else False
        cues = [
            VerificationCueResult(
                cue_id="supplier_verbatim_needle",
                passed=verbatim,
                detail=(
                    "Supplier narrative span reproduces verbatim."
                    if verbatim
                    else "Supplier linkage span lost — review regex coverage / OCR artefacts."
                ),
                evidence=(ProvenanceSpan(excerpt=span[:500]),) if span else (),
                attribution=AgentAttribution(
                    actor_name="supplier_substring_anchor",
                    actor_version="1.0.0",
                    modality="deterministic_rules",
                    rule_identifier="verify.supplier.verbatim",
                ),
            )
        ]

        fuzzy = (
            SequenceMatcher(None, span.lower(), submission.lower()).quick_ratio() if span else 0.0
        )
        cues.append(
            VerificationCueResult(
                cue_id="supplier_fuzzy_quick_ratio",
                passed=fuzzy > 0.25,
                score=round(fuzzy, 4),
                detail="Fuzzy guardrail for abbreviated supplier citations.",
                evidence=(),
                attribution=AgentAttribution(
                    actor_name="supplier_quick_ratio_gate",
                    actor_version="1.0.0",
                    modality="deterministic_rules",
                    rule_identifier="verify.supplier.quick_ratio",
                ),
            ),
        )

        if verbatim:
            outcome = VerificationStatus.ACCEPTED
            notes = "Supplier span anchored verbatim with auxiliary fuzzy corroboration available."
        elif fuzzy > 0.35:
            outcome = VerificationStatus.REVIEW_REQUIRED
            notes = "Partial overlap — OCR or formatting variance likely."
        else:
            outcome = VerificationStatus.REVIEW_REQUIRED
            notes = "Linkage weak — deterministic regex may have hallucinated boundaries."

        return VerificationAssertion(
            claim_summary=f"Supplier linkage '{supplier.supplier_display_name}'",
            status=outcome,
            reviewer_notes=notes,
            corroboration_passes=tuple(c.attribution for c in cues if c.passed),
            cue_results=tuple(cues),
            verification_chain=_chain_provenance(
                correlation_id=correlation_id,
                claim=f"SUP::{supplier.supplier_display_name}",
                steps=(
                    "supplier_step1_verbatim_needle",
                    "supplier_step2_quick_ratio_fallback",
                ),
            ),
        )

    def _supplier_sm_window_check(
        self,
        submission: str,
        supplier: Supplier,
        findings: Sequence[StartingMaterial],
        correlation_id: str,
    ) -> VerificationAssertion | None:
        """Co-mentions within a sliding window reduce false-positive supplier-material edges."""

        if not supplier.citation.evidence:
            return None
        submission_low = submission.casefold()
        needle = supplier.supplier_display_name.casefold().strip()
        pivot = submission_low.find(needle)
        if pivot == -1 and supplier.citation.evidence:
            ref = supplier.citation.evidence[0].excerpt
            sniff = ref[: min(48, len(ref))].strip()
            if sniff:
                pivot = submission_low.find(sniff.casefold())
        if pivot == -1 or not findings:
            return None

        window_radius = 220
        left = max(0, pivot - window_radius)
        right = min(len(submission), pivot + window_radius)
        excerpt = submission[left:right]

        cues: list[VerificationCueResult] = []

        mentions_material = False
        ex_lower = excerpt.lower()
        for finding in findings:
            if not finding.justification.evidence:
                continue
            span = finding.justification.evidence[0].excerpt
            if not span.strip():
                continue
            snippet = span[:80].lower()
            mentions_material |= snippet in ex_lower

        cues.append(
            VerificationCueResult(
                cue_id="supplier_material_cooccurrence_window",
                passed=mentions_material,
                score=None,
                detail=(
                    "Supplier and at least one SM excerpt co-occur locally."
                    if mentions_material
                    else (
                        "Supplier not collocated with SM evidence excerpt — "
                        "linkage may be spurious."
                    )
                ),
                evidence=(ProvenanceSpan(excerpt=excerpt[:440], locator=f"window:{left}-{right}"),),
                attribution=AgentAttribution(
                    actor_name="supplier_material_window",
                    actor_version=self.ATT_SUPPLIER_WINDOW_VERSION,
                    modality="deterministic_rules",
                    rule_identifier="verify.supplier.local_comention",
                ),
            )
        )

        status = (
            VerificationStatus.ACCEPTED if mentions_material else VerificationStatus.REVIEW_REQUIRED
        )
        return VerificationAssertion(
            claim_summary=(
                f"Supplier '{supplier.supplier_display_name}' local co-mention with surfaced SMs"
            ),
            status=status,
            reviewer_notes="Structural narrative proximity check — not causality.",
            corroboration_passes=tuple(c.attribution for c in cues if c.passed),
            cue_results=tuple(cues),
            verification_chain=_chain_provenance(
                correlation_id=correlation_id,
                claim=f"WIN::{supplier.supplier_display_name}",
                steps=("spatial_window_neighbor_check",),
            ),
        )


class LLMVerifier:
    """Stub second-opinion verifier — emits explicit modality for dual-control roadmap."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def verify(
        self,
        *,
        submission_text: str,
        parsed_submission: ParsedSubmission,
        findings: Sequence[StartingMaterial],
        suppliers: Sequence[Supplier],
        correlation_id: str,
    ) -> tuple[VerificationAssertion, ...]:
        _ = submission_text
        _ = findings
        _ = suppliers
        _ = parsed_submission
        _ = self._settings
        has_key = bool(self._settings.openai_api_key)
        modality = AgentAttribution(
            actor_name="llm_verifier_stub",
            actor_version="0.4.0",
            modality="llm_verifier",
            rule_identifier="verify.llm.reserved_execution_path",
        )
        cues = (
            VerificationCueResult(
                cue_id="llm_stub_policy_gate",
                passed=False,
                detail=(
                    "LLM verifier staged but disabled — keyed execution not enabled in deployment."
                    if not has_key
                    else (
                        "LLM verifier flagged for QA harness only — deterministic core stays "
                        "authoritative until SMEs bless prompts."
                    )
                ),
                evidence=(),
                attribution=modality,
            ),
        )
        return (
            VerificationAssertion(
                claim_summary="LLM secondary verifier (non-authoritative)",
                status=VerificationStatus.REVIEW_REQUIRED,
                reviewer_notes=(
                    "Reserved for dual-control attestations alongside deterministic cues."
                ),
                corroboration_passes=(),
                cue_results=cues,
                verification_chain=_chain_provenance(
                    correlation_id=correlation_id,
                    claim="LLM_DUAL_CONTROL",
                    steps=("dual_control_placeholder",),
                ),
            ),
        )


class CompositeSubmissionVerifier:
    """Runs deterministic + optional stochastic verifiers sequentially for audit granularity."""

    def __init__(self, *layers: SubmissionVerifier) -> None:
        self._layers = layers

    def verify(
        self,
        *,
        submission_text: str,
        parsed_submission: ParsedSubmission,
        findings: Sequence[StartingMaterial],
        suppliers: Sequence[Supplier],
        correlation_id: str,
    ) -> tuple[VerificationAssertion, ...]:
        merged: list[VerificationAssertion] = []
        for layer in self._layers:
            merged.extend(
                layer.verify(
                    submission_text=submission_text,
                    parsed_submission=parsed_submission,
                    findings=findings,
                    suppliers=suppliers,
                    correlation_id=correlation_id,
                )
            )
        return tuple(merged)


__all__ = [
    "CompositeSubmissionVerifier",
    "ExternalDatabaseLookup",
    "LLMVerifier",
    "MultiCueVerifier",
    "SubmissionVerifier",
]


def default_verifier(settings: Settings) -> SubmissionVerifier:
    return CompositeSubmissionVerifier(
        MultiCueVerifier(settings),
        LLMVerifier(settings),
    )
