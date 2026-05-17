from __future__ import annotations

from regchem_sentinel.config import Settings
from regchem_sentinel.core.graph_memory import (
    GraphCorpusStats,
    build_graph_insights,
    derive_hyperedge_upserts,
    hyperedge_key_sha256,
    snapshot_canonical_sha256,
)
from regchem_sentinel.main import default_dependencies, run_pipeline


def test_hyperedge_key_is_deterministic_for_identical_payload() -> None:
    rows = (
        {
            "role": "MATERIAL",
            "ref_key": "a",
            "label": "M",
        },
        {
            "role": "SUPPLIER",
            "ref_key": "b",
            "label": "S",
        },
    )
    rel = "material_supplier_process_regulatory_hyperedge"
    assert hyperedge_key_sha256(rows, rel) == hyperedge_key_sha256(rows, rel)


def test_run_pipeline_appends_graph_memory() -> None:
    settings = Settings(app_env="development", build_id="pytest", storage_backend="memory")
    deps = default_dependencies(settings)
    snapshot = run_pipeline(
        "The starting material is supplied by Manufacturer: Acme API Co.",
        correlation_id="graph-mem-1",
        deps=deps,
        persist=True,
    )
    assert snapshot.findings
    write = deps.storage.last_graph_memory_write()
    assert write is not None
    assert write.hyperedge_events >= 1
    corpus = deps.storage.graph_memory_corpus_stats()
    assert corpus.total_ledger_events >= 1
    insights = build_graph_insights(snapshot=snapshot, write_summary=write, corpus=corpus)
    assert insights.continual_learning_signal
    assert insights.benchmark_lines


def test_graph_memory_workshop_mode_still_records_edges() -> None:
    settings = Settings(app_env="development", build_id="pytest", storage_backend="memory")
    deps = default_dependencies(settings)
    snapshot = run_pipeline(
        "Drug substance starting material Manufacture: Example Pharma GmbH.",
        correlation_id="graph-mem-2",
        deps=deps,
        persist=False,
    )
    assert deps.storage.last_graph_memory_write() is not None
    assert snapshot_canonical_sha256(snapshot)


def test_corpus_stats_projection() -> None:
    stats = GraphCorpusStats(
        total_ledger_events=10,
        distinct_hyperedge_keys=4,
        tier_touch_counts={"tier_2_critical": 3},
    )
    assert stats.total_ledger_events == 10
    assert stats.tier_touch_counts["tier_2_critical"] == 3


def test_derive_hyperedge_includes_process_and_regulatory_roles() -> None:
    settings = Settings(app_env="development", build_id="pytest", storage_backend="memory")
    deps = default_dependencies(settings)
    snapshot = run_pipeline(
        "The starting material is supplied by Manufacturer: Acme API Co.",
        correlation_id="graph-derive",
        deps=deps,
        persist=False,
    )
    specs = derive_hyperedge_upserts(snapshot)
    assert specs
    roles = {p["role"] for p in specs[0].participants}
    assert "PROCESS_BUNDLE" in roles
    assert "REGULATORY_CONTEXT" in roles
