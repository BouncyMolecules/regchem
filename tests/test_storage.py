from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from regchem_sentinel.config import Settings
from regchem_sentinel.core.storage import StorageService, create_sqlite_engine
from regchem_sentinel.main import default_dependencies, run_pipeline


def test_storage_round_trip(tmp_path: Path) -> None:
    database = tmp_path / "sentinel.db"
    engine = create_sqlite_engine(database)
    try:
        service = StorageService(engine)

        settings = Settings(app_env="development", build_id="pytest", storage_backend="memory")
        deps = default_dependencies(settings)
        snapshot = run_pipeline(
            "The starting material is supplied by Manufacturer: Acme API Co.",
            correlation_id="storage-test-1",
            deps=deps,
            persist=False,
        )
        run_id = service.save_pipeline_snapshot(snapshot)
        assert run_id

        loaded = service.get_latest_for_correlation_id("storage-test-1")
        assert loaded is not None
        assert loaded.correlation_id == snapshot.correlation_id
        assert loaded.parsed_submission.content_sha256 == snapshot.parsed_submission.content_sha256
        assert loaded.findings == snapshot.findings

        history = service.get_classification_history(correlation_id="storage-test-1", limit=10)
        assert history
        assert history[0].aggregate_confidence is not None

        trail = service.get_audit_trail(correlation_id="storage-test-1", limit=50)
        assert len(trail) == 1
        assert trail[0].event_type == "PIPELINE_SNAPSHOT_PERSISTED"
    finally:
        engine.dispose()


def test_storage_requires_non_empty_correlation_filters() -> None:
    engine = create_sqlite_engine(":memory:")
    try:
        service = StorageService(engine)
        with pytest.raises(ValueError):
            service.get_classification_history(correlation_id="", limit=10)
        with pytest.raises(ValueError):
            service.get_audit_trail(correlation_id="", limit=10)
        with pytest.raises(ValueError):
            service.get_latest_for_correlation_id("   ")
    finally:
        engine.dispose()


def test_sqlite_regulatory_storage_protocol(tmp_path: Path) -> None:
    from regchem_sentinel.core.storage import create_sqlite_regulatory_storage

    db_path = tmp_path / "audit.db"
    backend = create_sqlite_regulatory_storage(db_path)
    try:
        settings = Settings(app_env="development", build_id="pytest", storage_backend="memory")
        deps = replace(default_dependencies(settings), storage=backend)
        snapshot = run_pipeline(
            "Drug substance starting material Manufacture: TestCo LLC.",
            correlation_id="proto-ci",
            deps=deps,
            persist=True,
        )
        assert snapshot.findings
        recent = backend.recent_runs(limit=5)
        assert recent and recent[0]["correlation_id"] == "proto-ci"
        assert recent[0].get("parsed_submission") is not None
    finally:
        backend.service.engine.dispose()
