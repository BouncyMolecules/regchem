"""Application orchestration — pure sequencing with injectable collaborators."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from regchem_sentinel.config import Settings
from regchem_sentinel.core.classifier import StartingMaterialClassifier, default_classifier
# Importing payloads from ``core.models`` loads every SQLModel table (graph ledger, audit trails, pipeline rows)
# onto ``SQLModel.metadata`` — keep ORM centralized; graph-memory / continual-learning code uses snapshot types only.
from regchem_sentinel.core.models import ParsedSubmission, SentinelPipelineSnapshot
from regchem_sentinel.core.storage import (
    RegulatoryAuditStorage,
    create_memory_storage,
    create_sqlite_regulatory_storage,
)
from regchem_sentinel.core.supplier_linker import SupplierLinker, default_supplier_linker
from regchem_sentinel.core.verifier import SubmissionVerifier, default_verifier


@dataclass(frozen=True, slots=True)
class SentinelDependencies:
    """Explicit composition container — avoids module-level service registries."""

    settings: Settings
    classifier: StartingMaterialClassifier
    supplier_linker: SupplierLinker
    verifier: SubmissionVerifier
    storage: RegulatoryAuditStorage


def resolve_storage(settings: Settings) -> RegulatoryAuditStorage:
    """Select the audit port from settings (SQLite WAL or in-process memory)."""

    if settings.storage_backend == "sqlite":
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        return create_sqlite_regulatory_storage(settings.sqlite_database_path)
    return create_memory_storage()


def default_dependencies(settings: Settings) -> SentinelDependencies:
    """Baseline wiring for demos; replace factories in regulated deployments."""

    return SentinelDependencies(
        settings=settings,
        classifier=default_classifier(settings),
        supplier_linker=default_supplier_linker(settings),
        verifier=default_verifier(settings),
        storage=resolve_storage(settings),
    )


def parse_submission(submission_text: str) -> ParsedSubmission:
    """Deterministic preprocessing — page segmentation + cryptographic fingerprint."""

    return ParsedSubmission.from_full_text(submission_text.strip())


def run_pipeline(
    submission_text: str,
    *,
    correlation_id: str,
    deps: SentinelDependencies,
    persist: bool = True,
    storage_writer: Callable[[RegulatoryAuditStorage, SentinelPipelineSnapshot], None]
    | None = None,
) -> SentinelPipelineSnapshot:
    """Parse → classify → supplier linkage → verify → optional persist."""

    excerpt = submission_text.strip()
    if not excerpt:
        raise ValueError("Submission text cannot be empty.")

    parsed = parse_submission(submission_text)

    findings = deps.classifier.classify(parsed, correlation_id=correlation_id)
    suppliers = deps.supplier_linker.link(
        parsed.full_text,
        materials=findings,
        correlation_id=correlation_id,
    )
    verifications = deps.verifier.verify(
        submission_text=parsed.full_text,
        parsed_submission=parsed,
        findings=findings,
        suppliers=suppliers,
        correlation_id=correlation_id,
    )

    snapshot = SentinelPipelineSnapshot(
        correlation_id=correlation_id,
        submission_excerpt=excerpt[:2000],
        parsed_submission=parsed,
        findings=findings,
        suppliers=suppliers,
        verifications=verifications,
    )

    run_id: str | None = None
    if persist:
        if storage_writer:
            storage_writer(deps.storage, snapshot)
        else:
            run_id = deps.storage.append_snapshot(snapshot)
    deps.storage.append_graph_memory(snapshot, pipeline_run_id=run_id)

    return snapshot
