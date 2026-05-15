from __future__ import annotations

import pytest

from regchem_sentinel.config import Settings
from regchem_sentinel.main import default_dependencies, run_pipeline


def test_pipeline_persists_runs() -> None:
    settings = Settings(app_env="development", build_id="pytest", storage_backend="memory")
    deps = default_dependencies(settings)
    snapshot = run_pipeline(
        "The starting material is supplied by Manufacturer: Acme API Co.",
        correlation_id="trace-1",
        deps=deps,
        persist=True,
    )
    assert snapshot.findings
    assert deps.storage.recent_runs(limit=1)


def test_pipeline_rejects_empty_text() -> None:
    settings = Settings(app_env="development", build_id="pytest", storage_backend="memory")
    deps = default_dependencies(settings)
    with pytest.raises(ValueError):
        run_pipeline("   ", correlation_id="trace-empty", deps=deps, persist=False)
