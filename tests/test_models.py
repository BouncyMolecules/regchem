from __future__ import annotations

from regchem_sentinel.core.models import (
    AgentAttribution,
    ClassificationResult,
    DecisionProvenance,
    MaterialTier,
    ProvenanceSpan,
    StartingMaterialFinding,
    TieredConfidence,
)


def test_starting_material_synonyms_deduplicate() -> None:
    tiered = TieredConfidence(
        tier_1_score=0.8,
        tier_2_score=0.4,
        tier_3_score=0.2,
        aggregate=0.66,
        formula_id="test",
    )
    classification = ClassificationResult(
        detector_summary="fixture",
        tiered_confidence=tiered,
        rule_contributions=(),
        suggested_material_tier=MaterialTier.TIER_1_REGISTERED,
    )

    provenance = DecisionProvenance(
        correlation_id="corr",
        evidence=(ProvenanceSpan(excerpt="alpha"),),
        attributions=(AgentAttribution(actor_name="test"),),
    )
    finding = StartingMaterialFinding(
        canonical_name="SM-1",
        synonyms=(" a ", "a", "b"),
        tier=MaterialTier.TIER_1_REGISTERED,
        classification=classification,
        justification=provenance,
    )
    assert finding.synonyms == ("a", "b")
