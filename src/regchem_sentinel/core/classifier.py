"""Tiered deterministic starting-material identification with explicit rule provenance."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from typing import Literal, Protocol

from regchem_sentinel.config import Settings
from regchem_sentinel.core.models import (
    AgentAttribution,
    ClassificationResult,
    DecisionProvenance,
    DetectorTier,
    MaterialTier,
    ParsedSubmission,
    ProvenanceSpan,
    RuleContribution,
    StartingMaterial,
    TieredConfidence,
)

RuleMethod = Literal["context", "table", "sentence_structure", "follow_on_word", "regex"]

_CLASSIFIER_ATTR = AgentAttribution(
    actor_name="tiered_sm_classifier",
    actor_version="2.0.0",
    modality="deterministic_rules",
    rule_identifier="sm.ensemble.tiered_v2",
)

_TABLE_LINE = re.compile(r"^\s*\|.+$", re.MULTILINE)
_CELL_SPLIT = re.compile(r"\|")


def _split_table_rows(text: str) -> tuple[str, ...]:
    return tuple(row for row in _TABLE_LINE.findall(text) if row.strip())


def _looks_like_table_sm_row(row: str) -> bool:
    if "|" not in row:
        return False
    tokens = [t.strip().lower() for t in _CELL_SPLIT.split(row) if t.strip()]
    if not tokens:
        return False
    return any("starting material" in t for t in tokens) or any(
        re.match(r"^sm[-\s]?\d", t) is not None for t in tokens
    )


@dataclass
class _CuePattern:
    rule_id: str
    pattern: re.Pattern[str]
    detector_tier: DetectorTier
    method: RuleMethod
    base_weight: float
    material_hint: MaterialTier | None


@dataclass
class _HitCluster:
    start: int
    end: int
    page: int | None
    name_hint: str
    rules: list[RuleContribution] = field(default_factory=list)


def _regex_cue_catalog() -> tuple[_CuePattern, ...]:
    return (
        _CuePattern(
            rule_id="tier1.phrase.starting_material",
            pattern=re.compile(r"\bstarting materials?\b", re.IGNORECASE),
            detector_tier=DetectorTier.TIER_1_DIRECT_REGISTRATION_LANGUAGE,
            method="context",
            base_weight=0.62,
            material_hint=MaterialTier.TIER_1_REGISTERED,
        ),
        _CuePattern(
            rule_id="tier1.phrase.designated_sm",
            pattern=re.compile(
                r"\bdesignated\s+(?:the\s+)?starting materials?\b",
                re.IGNORECASE,
            ),
            detector_tier=DetectorTier.TIER_1_DIRECT_REGISTRATION_LANGUAGE,
            method="context",
            base_weight=0.7,
            material_hint=MaterialTier.TIER_1_REGISTERED,
        ),
        _CuePattern(
            rule_id="tier1.phrase.sm_colon",
            pattern=re.compile(r"\bSM\s*:\s*([^\n|,]{2,80})", re.IGNORECASE),
            detector_tier=DetectorTier.TIER_1_DIRECT_REGISTRATION_LANGUAGE,
            method="context",
            base_weight=0.66,
            material_hint=MaterialTier.TIER_1_REGISTERED,
        ),
        _CuePattern(
            rule_id="tier2.sentence.is_starting_material",
            pattern=re.compile(
                r"\b([A-Za-z0-9][A-Za-z0-9\s\-]{2,60}?)\s+is\s+"
                r"(?:the\s+)?designated\s+starting material\b",
                re.IGNORECASE,
            ),
            detector_tier=DetectorTier.TIER_2_STRUCTURE_TABLE_SENTENCE,
            method="sentence_structure",
            base_weight=0.55,
            material_hint=MaterialTier.TIER_2_CRITICAL,
        ),
        _CuePattern(
            rule_id="tier2.token.sm_code",
            pattern=re.compile(r"\b(SM[-\s]?[0-9]{1,4}[A-Za-z]?)\b", re.IGNORECASE),
            detector_tier=DetectorTier.TIER_2_STRUCTURE_TABLE_SENTENCE,
            method="sentence_structure",
            base_weight=0.5,
            material_hint=MaterialTier.TIER_2_CRITICAL,
        ),
        _CuePattern(
            rule_id="tier2.phrase.supplied_as_sm",
            pattern=re.compile(
                r"\bsupplied\s+as\s+(?:the\s+)?starting materials?\b",
                re.IGNORECASE,
            ),
            detector_tier=DetectorTier.TIER_2_STRUCTURE_TABLE_SENTENCE,
            method="sentence_structure",
            base_weight=0.48,
            material_hint=MaterialTier.TIER_2_CRITICAL,
        ),
        _CuePattern(
            rule_id="tier3.followon.commercial_source",
            pattern=re.compile(
                r"\b(?:obtained|sourced)\s+from\s+(?:a\s+)?commercial\s+(?:supplier|source)\b",
                re.IGNORECASE,
            ),
            detector_tier=DetectorTier.TIER_3_CONTEXTUAL_WEAK,
            method="follow_on_word",
            base_weight=0.22,
            material_hint=MaterialTier.TIER_3_SUPPORTING,
        ),
        _CuePattern(
            rule_id="tier3.context.synthetic_precursor",
            pattern=re.compile(r"\bprecursors?\b|\bintermediates?\b", re.IGNORECASE),
            detector_tier=DetectorTier.TIER_3_CONTEXTUAL_WEAK,
            method="context",
            base_weight=0.18,
            material_hint=MaterialTier.TIER_3_SUPPORTING,
        ),
    )


def _guess_name_from_match(match: re.Match[str], cue: _CuePattern, window: str) -> str:
    groups = match.groups()
    if groups and groups[0]:
        return groups[0].strip()[:120]

    if cue.rule_id == "tier2.token.sm_code":
        return match.group(1).strip().upper()

    sm_tail = re.search(
        r"(?:starting materials?|SM)\s*[:\-]?\s*(.{3,80}?)(?:\n|\.|;|,|\s{2,}|$)",
        window,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if sm_tail:
        return sm_tail.group(1).strip()

    digest = hashlib.sha1(match.group(0).encode()).hexdigest()[:8]
    return f"Unresolved-SM-{digest}"


def _window(full: str, center_start: int, center_end: int, radius: int = 160) -> str:
    left = max(0, center_start - radius)
    right = min(len(full), center_end + radius)
    return full[left:right]


def _compute_tier_scores(rules: tuple[RuleContribution, ...]) -> TieredConfidence:
    t1 = 0.0
    t2 = 0.0
    t3 = 0.0
    for r in rules:
        if not r.matched:
            continue
        if r.detector_tier is DetectorTier.TIER_1_DIRECT_REGISTRATION_LANGUAGE:
            t1 += r.contribution
        elif r.detector_tier is DetectorTier.TIER_2_STRUCTURE_TABLE_SENTENCE:
            t2 += r.contribution
        elif r.detector_tier is DetectorTier.TIER_3_CONTEXTUAL_WEAK:
            t3 += r.contribution

    t1 = min(1.0, t1)
    t2 = min(1.0, t2)
    t3 = min(1.0, t3)
    aggregate = min(1.0, 0.52 * t1 + 0.33 * t2 + 0.18 * t3)
    return TieredConfidence(
        tier_1_score=t1,
        tier_2_score=t2,
        tier_3_score=t3,
        aggregate=aggregate,
        formula_id="tier_weighted_sum_cap_0.52_0.33_0.18_v1",
    )


def _suggest_material_tier(rules: tuple[RuleContribution, ...]) -> MaterialTier | None:
    tier1 = [
        r
        for r in rules
        if r.matched and r.detector_tier is DetectorTier.TIER_1_DIRECT_REGISTRATION_LANGUAGE
    ]
    tier2 = [
        r
        for r in rules
        if r.matched and r.detector_tier is DetectorTier.TIER_2_STRUCTURE_TABLE_SENTENCE
    ]
    tier3 = [
        r for r in rules if r.matched and r.detector_tier is DetectorTier.TIER_3_CONTEXTUAL_WEAK
    ]

    if tier1:
        best = max(tier1, key=lambda r: r.contribution)
        return best.material_hint or MaterialTier.TIER_1_REGISTERED
    if tier2:
        best = max(tier2, key=lambda r: r.contribution)
        return best.material_hint or MaterialTier.TIER_2_CRITICAL
    if tier3:
        return MaterialTier.TIER_3_SUPPORTING
    return None


def _guess_name_from_table_row(row: str) -> str:
    code_match = re.search(r"\b(SM[-\s]?\w+)\b", row, re.IGNORECASE)
    if code_match:
        return code_match.group(1).strip().upper()
    return f"TABLE-SM-{hashlib.sha1(row.encode()).hexdigest()[:6]}"


def _canonical_from_cluster(full_text: str, start: int, end: int, name_hint: str) -> str:
    window = full_text[max(0, start - 40) : min(len(full_text), end + 80)]
    sm_code = re.search(r"\b(SM[-\s]?\d{1,4}[A-Za-z]?)\b", window, re.IGNORECASE)
    if sm_code:
        return sm_code.group(1).strip().upper()
    verbal = re.search(
        r"starting materials?\s*[:\-]\s*(.{3,80}?)(?:\n|\.|;|,|$)",
        window,
        re.IGNORECASE,
    )
    if verbal:
        return verbal.group(1).strip()[:120]
    cleaned = name_hint.strip()
    if cleaned and not cleaned.startswith("Unresolved"):
        return cleaned[:120]
    return f"CLUSTER-{hashlib.sha1(window.encode()).hexdigest()[:10]}"


def _synonyms_from_cluster(full: str, start: int, end: int, radius: int = 100) -> tuple[str, ...]:
    snippet = full[max(0, start - radius) : min(len(full), end + radius)]
    return tuple(
        sorted(
            {
                m.group(1).upper()
                for m in re.finditer(r"\b(SM[-\s]?\d{1,4}[A-Za-z]?)\b", snippet, re.IGNORECASE)
            }
        ),
    )[:5]


def _merge_clusters(raw: list[_HitCluster], gap: int = 96) -> list[_HitCluster]:
    raw.sort(key=lambda h: (h.page or 0, h.start))
    merged: list[_HitCluster] = []
    for hit in raw:
        if (
            merged
            and (hit.page or -1) == (merged[-1].page or -2)
            and hit.start - merged[-1].end <= gap
        ):
            prev = merged[-1]
            prev.end = max(prev.end, hit.end)
            prev.rules.extend(hit.rules)
            if len(hit.name_hint) > len(prev.name_hint):
                prev.name_hint = hit.name_hint
        else:
            merged.append(
                _HitCluster(
                    start=hit.start,
                    end=hit.end,
                    page=hit.page,
                    name_hint=hit.name_hint,
                    rules=list(hit.rules),
                )
            )
    return merged


def _dedupe_rules(rules: list[RuleContribution]) -> tuple[RuleContribution, ...]:
    seen: set[str] = set()
    out: list[RuleContribution] = []
    for r in rules:
        key = f"{r.rule_id}|{r.locator}"
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return tuple(out)


class StartingMaterialClassifier(Protocol):
    def classify(
        self,
        submission: ParsedSubmission,
        *,
        correlation_id: str,
    ) -> tuple[StartingMaterial, ...]:
        """Produce SM hypotheses with verbatim evidence spans and rule contributions."""


class TieredStartingMaterialClassifier:
    """Deterministic FDA-style ensemble across context, table geometry, and weak cues."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def classify(
        self,
        submission: ParsedSubmission,
        *,
        correlation_id: str,
    ) -> tuple[StartingMaterial, ...]:
        _ = self._settings
        full = submission.full_text
        raw_hits: list[_HitCluster] = []

        for segment in submission.segments:
            for row in _split_table_rows(segment.text):
                if not _looks_like_table_sm_row(row):
                    continue
                rel = segment.text.find(row)
                if rel == -1:
                    continue
                start = segment.char_offset_start + rel
                end = start + len(row)
                rc = RuleContribution(
                    rule_id="tier2.table.row_sm_marker",
                    detector_tier=DetectorTier.TIER_2_STRUCTURE_TABLE_SENTENCE,
                    contribution=0.44,
                    matched=True,
                    detail="Row contains starting-material table marker or SM code token.",
                    method="table",
                    page_number=segment.page_number,
                    locator=f"char:{start}-{end}",
                    material_hint=MaterialTier.TIER_2_CRITICAL,
                )
                raw_hits.append(
                    _HitCluster(
                        start=start,
                        end=end,
                        page=segment.page_number,
                        name_hint=_guess_name_from_table_row(row),
                        rules=[rc],
                    )
                )

            cues = _regex_cue_catalog()
            for cue in cues:
                for m in cue.pattern.finditer(segment.text):
                    abs_start = segment.char_offset_start + m.start()
                    abs_end = segment.char_offset_start + m.end()
                    w = _window(full, abs_start, abs_end)
                    local_slice = full[abs_start:abs_end]
                    local_match = cue.pattern.search(local_slice) or m
                    name = _guess_name_from_match(local_match, cue, w)
                    rc = RuleContribution(
                        rule_id=cue.rule_id,
                        detector_tier=cue.detector_tier,
                        contribution=cue.base_weight,
                        matched=True,
                        detail=f"Matched pattern for {cue.rule_id}.",
                        method=cue.method,
                        page_number=segment.page_number,
                        locator=f"char:{abs_start}-{abs_end}",
                        material_hint=cue.material_hint,
                    )
                    raw_hits.append(
                        _HitCluster(
                            start=abs_start,
                            end=abs_end,
                            page=segment.page_number,
                            name_hint=name,
                            rules=[rc],
                        )
                    )

        clusters = _merge_clusters(raw_hits)

        if not clusters:
            return self._no_signal_case(full, submission, correlation_id)

        materials: list[StartingMaterial] = []
        for cluster in clusters:
            rule_tuple = _dedupe_rules(cluster.rules)
            tiered = _compute_tier_scores(rule_tuple)
            suggested = _suggest_material_tier(rule_tuple)
            start, end = cluster.start, cluster.end
            excerpt = full[start : min(end, len(full))]
            if not excerpt.strip():
                excerpt = full[start : min(len(full), start + 120)]

            classification = ClassificationResult(
                detector_summary=(
                    f"Merged ensemble with {len(rule_tuple)} rule contributions "
                    f"(page={cluster.page})."
                ),
                tiered_confidence=tiered,
                rule_contributions=rule_tuple,
                suggested_material_tier=suggested,
            )
            decision_id = uuid.uuid4().hex
            justification = DecisionProvenance(
                correlation_id=correlation_id,
                decision_id=decision_id,
                evidence=(
                    ProvenanceSpan(
                        excerpt=excerpt or full[start : start + 1],
                        locator=f"char:{start}-{end}",
                        page_number=cluster.page,
                        section_label=next(
                            (r.rule_id for r in rule_tuple if r.method == "table"),
                            None,
                        ),
                        char_offset_start=start,
                        char_offset_end=min(end, len(full)),
                    ),
                ),
                rationales=(
                    f"aggregate={tiered.aggregate:.3f}; formula={tiered.formula_id}; "
                    f"T1={tiered.tier_1_score:.2f} T2={tiered.tier_2_score:.2f} "
                    f"T3={tiered.tier_3_score:.2f}.",
                ),
                attributions=(_CLASSIFIER_ATTR,),
                predecessor_refs=(f"content_sha256:{submission.content_sha256}",),
            )
            materials.append(
                StartingMaterial(
                    canonical_name=_canonical_from_cluster(full, start, end, cluster.name_hint),
                    synonyms=_synonyms_from_cluster(full, start, end),
                    tier=suggested,
                    classification=classification,
                    justification=justification,
                )
            )

        return tuple(
            sorted(materials, key=lambda x: x.justification.evidence[0].char_offset_start or 0)
        )

    def _no_signal_case(
        self,
        full: str,
        submission: ParsedSubmission,
        correlation_id: str,
    ) -> tuple[StartingMaterial, ...]:
        fallback_rules = (
            RuleContribution(
                rule_id="ensemble.no_positive_cue",
                detector_tier=DetectorTier.TIER_3_CONTEXTUAL_WEAK,
                contribution=0.0,
                matched=False,
                detail="No detector tier produced a positive cue on this submission.",
                method="context",
                page_number=1,
            ),
        )
        tiered = _compute_tier_scores(fallback_rules)
        classification = ClassificationResult(
            detector_summary="Classifier found no starting-material ensemble agreement.",
            tiered_confidence=tiered,
            rule_contributions=fallback_rules,
            suggested_material_tier=None,
        )
        excerpt = full[:200] + ("…" if len(full) > 200 else "")
        decision_id = uuid.uuid4().hex
        prov = DecisionProvenance(
            correlation_id=correlation_id,
            decision_id=decision_id,
            evidence=(
                ProvenanceSpan(
                    excerpt=excerpt,
                    page_number=1,
                    section_label="whole_submission_excerpt",
                    char_offset_start=0,
                    char_offset_end=min(len(full), 200),
                ),
            ),
            rationales=(
                "No registrant-explicit starting material language detected — treat as unresolved "
                "until SME confirms or ingestion adds structured tables.",
            ),
            attributions=(_CLASSIFIER_ATTR,),
            predecessor_refs=(f"content_sha256:{submission.content_sha256}",),
        )
        return (
            StartingMaterial(
                canonical_name=f"UNRESOLVED-{uuid.uuid4().hex[:8]}",
                synonyms=(),
                tier=None,
                classification=classification,
                justification=prov,
            ),
        )


def default_classifier(settings: Settings) -> StartingMaterialClassifier:
    """Factory hook for regulated deployments that swap ensembles without touching callers."""

    return TieredStartingMaterialClassifier(settings)
