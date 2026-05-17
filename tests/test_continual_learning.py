from __future__ import annotations

from regchem_sentinel.config import Settings
from regchem_sentinel.core import graph_memory as gm
from regchem_sentinel.core.continual_learning import (
    build_regulatory_risk_forecast,
    feedback_strength_delta,
)
from regchem_sentinel.core.storage import InMemoryAuditStorage
from regchem_sentinel.main import default_dependencies, run_pipeline


def test_feedback_adjustment_is_deterministic_per_kind() -> None:
    assert feedback_strength_delta(kind="correct") == 0.10
    assert feedback_strength_delta(kind="needs_adjustment") == -0.08
    assert feedback_strength_delta(kind="wrong_tier") == -0.18


def test_user_feedback_updates_hyperedge_strength_in_memory() -> None:
    settings = Settings(app_env="development", build_id="pytest", storage_backend="memory")
    deps = default_dependencies(settings)
    snapshot = run_pipeline(
        "The starting material is supplied by Manufacturer: Acme API Co.",
        correlation_id="feedback-ledger-1",
        deps=deps,
        persist=False,
    )
    key = gm.derive_hyperedge_upserts(snapshot)[0].hyperedge_key_sha256
    assert isinstance(deps.storage, InMemoryAuditStorage)
    before = deps.storage._memory_latest_hyperedge(key)
    assert before is not None
    strength_0 = before[0]

    summary = deps.storage.append_classification_feedback(snapshot, "wrong_tier")
    assert summary.hyperedge_events >= 1

    after = deps.storage._memory_latest_hyperedge(key)
    assert after is not None
    assert after[0] < strength_0


def test_regulatory_forecast_provenance_is_stable_for_fixed_inputs() -> None:
    settings = Settings(app_env="development", build_id="pytest", storage_backend="memory")
    deps = default_dependencies(settings)
    snapshot = run_pipeline(
        "ATMP cell substrate starting material narrative for illustration.",
        correlation_id="forecast-1",
        deps=deps,
        persist=False,
    )
    corpus = deps.storage.graph_memory_corpus_stats()
    write = deps.storage.last_graph_memory_write()
    f1 = build_regulatory_risk_forecast(snapshot=snapshot, corpus=corpus, write_summary=write)
    f2 = build_regulatory_risk_forecast(snapshot=snapshot, corpus=corpus, write_summary=write)
    assert f1.provenance_digest_sha256 == f2.provenance_digest_sha256
    assert f1.lines
