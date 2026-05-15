"""GxP-aligned durable storage built on SQLite + SQLModel.

The public surface emphasises explicit dependency injection via ``Engine`` /
``StorageService`` construction rather than singleton registries.

Design notes:

* **Immutable pipeline facts** — persisted runs are INSERT-only via application APIs.
  Hashed canonical JSON payloads provide deterministic replay independently of denormalised
  child rows used for OLTP-style lookups.
* **Append-only ledger** — ``AuditTrailEntry`` rows carry hash-chained metadata for
  reviewer-facing integrity narratives; physical tamper-evidence still relies on
  filesystem/WORM backups as expected in Part 11-style deployments.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, TypedDict, cast, runtime_checkable

from pydantic import BaseModel
from sqlalchemy import desc, event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, SQLModel, create_engine, select

from regchem_sentinel.core.models import (
    AuditTrailEntry,
    ClassificationResultRecord,
    ParsedSubmission,
    ParsedSubmissionRecord,
    PipelineRunRecord,
    RuleContribution,
    SentinelPipelineSnapshot,
    StartingMaterialRecord,
    SupplierRecord,
    VerificationAssertionRecord,
    VerificationCueResultRecord,
)


def _sql_col(model: type[SQLModel], field_name: str) -> ColumnElement[Any]:
    """Return the SQLAlchemy column element for strict mypy-checked query construction."""

    return cast(ColumnElement[Any], getattr(model, field_name))


_GENESIS_HASH = "0" * 64


def _stable_json_dumps(payload: dict[str, object]) -> str:
    """Serialise *payload* with sorted keys for reproducible hashing."""

    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _canonical_snapshot_payload(snapshot: SentinelPipelineSnapshot) -> dict[str, object]:
    """Return the JSON-mode dict used for canonical persistence + checksums."""

    dumped = snapshot.model_dump(mode="json")
    return cast(dict[str, object], dumped)


def _snapshot_sha256(snapshot: SentinelPipelineSnapshot) -> tuple[str, str]:
    """Return ``(hex_digest, canonical_json)`` for *snapshot*."""

    payload = _canonical_snapshot_payload(snapshot)
    canonical = _stable_json_dumps(payload)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest, canonical


def _json_from_model(model: BaseModel) -> str:
    return _stable_json_dumps(cast(dict[str, object], model.model_dump(mode="json")))


def _new_id() -> str:
    return str(uuid.uuid4())


class StorageError(Exception):
    """Base class for storage-layer failures surfaced to orchestration collaborators."""


class StorageWriteError(StorageError):
    """Raised when a persistence transaction fails."""


def create_sqlite_engine(database_path: str | Path, *, echo: bool = False) -> Engine:
    """Create a SQLite ``Engine`` with WAL journaling and foreign-key enforcement."""

    raw = str(database_path)
    if raw == ":memory:":
        sqlite_url = "sqlite:///:memory:"
    else:
        resolved = Path(database_path).expanduser().resolve()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        sqlite_url = f"sqlite:///{resolved.as_posix()}"

    engine = create_engine(sqlite_url, echo=echo, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _apply_sqlite_pragmas(
        dbapi_connection: sqlite3.Connection,
        _connection_record: object,
    ) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=FULL")  # favour durability over raw speed
        cursor.close()

    return engine


@dataclass(frozen=True, slots=True)
class ClassificationHistoryRow:
    """Projection for indexed classification provenance lookups."""

    pipeline_run_id: str
    correlation_id: str
    created_at_utc: datetime
    starting_material_id: str | None
    canonical_name: str | None
    material_tier: str | None
    aggregate_confidence: float | None
    detector_summary: str | None


@dataclass(frozen=True, slots=True)
class AuditTrailView:
    """Read-only audit ledger projection (ORM-decoupled)."""

    entry_id: int
    public_id: str
    created_at_utc: datetime
    event_type: str
    correlation_id: str
    pipeline_run_id: str | None
    snapshot_canonical_sha256: str | None
    payload_json: str
    previous_entry_hash_hex: str | None
    entry_hash_hex: str


class _RecentRunPayload(TypedDict):
    correlation_id: str
    submission_excerpt: str
    findings: tuple[object, ...]
    suppliers: tuple[object, ...]
    verifications: tuple[object, ...]
    pipeline_run_id: str
    created_at_utc: datetime
    content_sha256: str
    snapshot_canonical_sha256: str
    parsed_submission: ParsedSubmission


@runtime_checkable
class RegulatoryAuditStorage(Protocol):
    """Minimal persistence port consumed by orchestration."""

    def append_snapshot(self, snapshot: SentinelPipelineSnapshot) -> None:
        """Persist a completed end-to-end pipeline bundle."""

    def recent_runs(self, *, limit: int = 20) -> list[dict[str, object]]:
        """Return newest-first lightweight dict rows suitable for dashboards."""

    def get_audit_trail(
        self,
        *,
        correlation_id: str | None = None,
        limit: int = 500,
    ) -> list[AuditTrailView]:
        """Return hash-chained (or logically equivalent in-memory) audit ledger rows."""

        ...


class InMemoryAuditStorage:
    """Process-local transactional memory — deterministic swap test double."""

    def __init__(self) -> None:
        self._runs: list[_RecentRunPayload] = []
        self._ledger: list[AuditTrailView] = []
        self._next_entry_id = 1
        self._prior_ledger_hash: str | None = None

    def append_snapshot(self, snapshot: SentinelPipelineSnapshot) -> None:
        """Store the authoritative tuple-friendly projection used by history pages."""

        digest, _ = _snapshot_sha256(snapshot)
        now = datetime.now(UTC)
        run_id = _new_id()
        self._runs.append(
            {
                "correlation_id": snapshot.correlation_id,
                "submission_excerpt": snapshot.submission_excerpt,
                "findings": snapshot.findings,
                "suppliers": snapshot.suppliers,
                "verifications": snapshot.verifications,
                "pipeline_run_id": run_id,
                "created_at_utc": now,
                "content_sha256": snapshot.parsed_submission.content_sha256,
                "snapshot_canonical_sha256": digest,
                "parsed_submission": snapshot.parsed_submission,
            },
        )
        ledger_payload: dict[str, object] = {
            "schema": "regchem_sentinel.storage.audit_v1_memory",
            "event": "PIPELINE_SNAPSHOT_PERSISTED",
            "pipeline_run_id": run_id,
            "correlation_id": snapshot.correlation_id,
            "snapshot_canonical_sha256": digest,
        }
        payload_json = _stable_json_dumps(ledger_payload)
        chaining_material = _stable_json_dumps(
            {
                "previous": self._prior_ledger_hash or _GENESIS_HASH,
                "payload": json.loads(payload_json),
            },
        )
        entry_hash = hashlib.sha256(chaining_material.encode("utf-8")).hexdigest()
        public_id = _new_id()
        ledger_view = AuditTrailView(
            entry_id=self._next_entry_id,
            public_id=public_id,
            created_at_utc=now,
            event_type="PIPELINE_SNAPSHOT_PERSISTED",
            correlation_id=snapshot.correlation_id,
            pipeline_run_id=run_id,
            snapshot_canonical_sha256=digest,
            payload_json=payload_json,
            previous_entry_hash_hex=self._prior_ledger_hash,
            entry_hash_hex=entry_hash,
        )
        self._ledger.append(ledger_view)
        self._prior_ledger_hash = entry_hash
        self._next_entry_id += 1

    def recent_runs(self, *, limit: int = 20) -> list[dict[str, object]]:
        if limit < 1:
            msg = "limit must be >= 1 when listing recent audit rows."
            raise ValueError(msg)
        window = self._runs[-limit:]
        return cast(list[dict[str, object]], list(reversed(window)))

    def get_audit_trail(
        self,
        *,
        correlation_id: str | None = None,
        limit: int = 500,
    ) -> list[AuditTrailView]:
        if limit < 1:
            msg = "limit must be >= 1 when requesting audit trail rows."
            raise ValueError(msg)

        rows = self._ledger
        if correlation_id is not None:
            if not correlation_id.strip():
                msg = "When provided, correlation_id must be non-empty."
                raise ValueError(msg)
            rows = [row for row in rows if row.correlation_id == correlation_id]
        slice_rows = rows[-limit:]
        return list(slice_rows)


class StorageService:
    """Typed façade over SQLite persistence with regulatory-oriented invariants."""

    def __init__(self, engine: Engine) -> None:
        """Initialise bound to *engine* and materialise schemas if missing."""

        self._engine = engine
        self.ensure_schema()

    @property
    def engine(self) -> Engine:
        """SQLAlchemy engine backing this service."""

        return self._engine

    def ensure_schema(self) -> None:
        """Create missing tables/indexes."""

        SQLModel.metadata.create_all(self._engine)

    @staticmethod
    def _contributions_stable_json(rule_contribs: Iterable[RuleContribution]) -> str:
        serialisable = sorted(
            (contrib.model_dump(mode="json") for contrib in rule_contribs),
            key=lambda row: cast(str, row["rule_id"]),
        )
        return json.dumps(serialisable, ensure_ascii=False, separators=(",", ":"))

    def _latest_audit_hash(self, session: Session) -> str | None:
        stmt = (
            select(AuditTrailEntry).order_by(desc(_sql_col(AuditTrailEntry, "entry_id"))).limit(1)
        )
        row = session.exec(stmt).first()
        if row is None:
            return None
        return row.entry_hash_hex

    def save_pipeline_snapshot(self, snapshot: SentinelPipelineSnapshot) -> str:
        """Atomically persist *snapshot*, returning ``pipeline_run.id``.

        Writes:

        * A hash-anchored ``PipelineRunRecord`` capturing canonical JSON replay material.
        * Normalised relational rows for submissions, classifications, supplier linkages,
          verifier assertions/cues, and cryptographic audit-chain metadata.

        Raises:
            StorageWriteError: When the database rejects the transaction.

        """

        digest, canonical_json = _snapshot_sha256(snapshot)
        run_id = _new_id()
        created_at = datetime.now(UTC)
        ledger_public_id = _new_id()

        try:
            with Session(self._engine) as session:
                previous_hash = self._latest_audit_hash(session)

                session.add(
                    PipelineRunRecord(
                        id=run_id,
                        correlation_id=snapshot.correlation_id,
                        created_at_utc=created_at,
                        submission_excerpt=snapshot.submission_excerpt,
                        snapshot_canonical_sha256=digest,
                        snapshot_json_canonical=canonical_json,
                    ),
                )
                session.flush()

                parsed = snapshot.parsed_submission
                session.add(
                    ParsedSubmissionRecord(
                        id=_new_id(),
                        pipeline_run_id=run_id,
                        content_sha256_hex=parsed.content_sha256,
                        parser_name=parsed.audit.parser_name,
                        parser_version=parsed.audit.parser_version,
                        parse_audit_json=_json_from_model(parsed.audit),
                        record_json=_json_from_model(parsed),
                    ),
                )

                for sm_index, sm in enumerate(snapshot.findings):
                    sm_row_id = _new_id()
                    session.add(
                        StartingMaterialRecord(
                            id=sm_row_id,
                            pipeline_run_id=run_id,
                            sequence_index=sm_index,
                            canonical_name=sm.canonical_name,
                            material_tier=sm.tier.value if sm.tier else None,
                            synonyms_json=json.dumps(sm.synonyms, ensure_ascii=False),
                            justification_json=_json_from_model(sm.justification),
                            record_json=_json_from_model(sm),
                        ),
                    )
                    session.flush()
                    clsf = sm.classification
                    scores = clsf.tiered_confidence
                    session.add(
                        ClassificationResultRecord(
                            id=_new_id(),
                            pipeline_run_id=run_id,
                            starting_material_id=sm_row_id,
                            detector_summary=clsf.detector_summary,
                            tiered_json=_json_from_model(scores),
                            contributions_json=self._contributions_stable_json(
                                clsf.rule_contributions
                            ),
                            suggested_material_tier=clsf.suggested_material_tier.value
                            if clsf.suggested_material_tier
                            else None,
                            tier_1_score=scores.tier_1_score,
                            tier_2_score=scores.tier_2_score,
                            tier_3_score=scores.tier_3_score,
                            aggregate_score=scores.aggregate,
                            record_json=_json_from_model(clsf),
                        ),
                    )

                for sup_index, sup in enumerate(snapshot.suppliers):
                    session.add(
                        SupplierRecord(
                            id=_new_id(),
                            pipeline_run_id=run_id,
                            sequence_index=sup_index,
                            supplier_display_name=sup.supplier_display_name,
                            role=sup.role.value,
                            linked_material_names_json=json.dumps(
                                sup.linked_material_names, ensure_ascii=False
                            ),
                            citation_json=_json_from_model(sup.citation),
                            record_json=_json_from_model(sup),
                        ),
                    )

                for va_index, assertion in enumerate(snapshot.verifications):
                    va_row_id = _new_id()
                    chain_json = (
                        _json_from_model(assertion.verification_chain)
                        if assertion.verification_chain is not None
                        else None
                    )
                    session.add(
                        VerificationAssertionRecord(
                            id=va_row_id,
                            pipeline_run_id=run_id,
                            sequence_index=va_index,
                            claim_summary=assertion.claim_summary,
                            verification_status=assertion.status.value,
                            reviewer_notes=assertion.reviewer_notes,
                            verification_chain_json=chain_json,
                            record_json=_json_from_model(assertion),
                        ),
                    )
                    session.flush()
                    for cue_index, cue in enumerate(assertion.cue_results):
                        session.add(
                            VerificationCueResultRecord(
                                id=_new_id(),
                                pipeline_run_id=run_id,
                                verification_assertion_id=va_row_id,
                                sequence_index=cue_index,
                                cue_stable_id=cue.cue_id,
                                passed=cue.passed,
                                attribution_json=_json_from_model(cue.attribution),
                                record_json=_json_from_model(cue),
                            ),
                        )

                # Ensure parent ``pipeline_run`` rows materialise before attaching the FK-backed
                # ledger entry (SQLite enforces ordering deterministically via explicit flush).
                session.flush()

                ledger_payload: dict[str, object] = {
                    "schema": "regchem_sentinel.storage.audit_v1",
                    "event": "PIPELINE_SNAPSHOT_PERSISTED",
                    "pipeline_run_id": run_id,
                    "correlation_id": snapshot.correlation_id,
                    "snapshot_canonical_sha256": digest,
                }
                payload_json = _stable_json_dumps(ledger_payload)
                chaining_material = _stable_json_dumps(
                    {
                        "previous": previous_hash or _GENESIS_HASH,
                        "payload": json.loads(payload_json),
                    },
                )
                entry_hash = hashlib.sha256(chaining_material.encode("utf-8")).hexdigest()

                session.add(
                    AuditTrailEntry(
                        public_id=ledger_public_id,
                        created_at_utc=created_at,
                        event_type="PIPELINE_SNAPSHOT_PERSISTED",
                        correlation_id=snapshot.correlation_id,
                        pipeline_run_id=run_id,
                        payload_json=payload_json,
                        previous_entry_hash_hex=previous_hash,
                        entry_hash_hex=entry_hash,
                    ),
                )

                session.commit()
        except IntegrityError as exc:  # pragma: no cover - defensive
            msg = "Database rejected the pipeline snapshot due to a constraint violation."
            raise StorageWriteError(msg) from exc
        except SQLAlchemyError as exc:
            msg = "Unexpected relational engine failure while persisting Sentinel snapshot."
            raise StorageWriteError(msg) from exc

        return run_id

    def get_latest_for_correlation_id(self, correlation_id: str) -> SentinelPipelineSnapshot | None:
        """Return newest persisted snapshot matching *correlation_id*, if any."""

        if not correlation_id.strip():
            msg = "correlation_id must be a non-empty string."
            raise ValueError(msg)

        stmt = (
            select(PipelineRunRecord)
            .where(PipelineRunRecord.correlation_id == correlation_id)
            .order_by(desc(_sql_col(PipelineRunRecord, "created_at_utc")))
            .limit(1)
        )

        try:
            with Session(self._engine) as session:
                run = session.exec(stmt).first()
        except SQLAlchemyError as exc:  # pragma: no cover
            msg = "Failed querying latest pipeline snapshot."
            raise StorageError(msg) from exc

        if run is None:
            return None
        return SentinelPipelineSnapshot.model_validate_json(run.snapshot_json_canonical)

    def get_classification_history(
        self,
        *,
        correlation_id: str | None,
        limit: int = 100,
    ) -> list[ClassificationHistoryRow]:
        """Return ordered classification lineage rows optionally scoped to one correlation."""

        if limit < 1:
            msg = "limit must be >= 1 when requesting classification history."
            raise ValueError(msg)

        stmt = (
            select(PipelineRunRecord, StartingMaterialRecord, ClassificationResultRecord)
            .join(
                StartingMaterialRecord,
                _sql_col(StartingMaterialRecord, "pipeline_run_id")
                == _sql_col(PipelineRunRecord, "id"),
            )
            .join(
                ClassificationResultRecord,
                _sql_col(ClassificationResultRecord, "starting_material_id")
                == _sql_col(StartingMaterialRecord, "id"),
            )
            .order_by(desc(_sql_col(PipelineRunRecord, "created_at_utc")))
            .limit(limit)
        )
        if correlation_id is not None:
            if not correlation_id.strip():
                msg = "When provided, correlation_id must be non-empty."
                raise ValueError(msg)
            stmt = stmt.where(PipelineRunRecord.correlation_id == correlation_id)

        try:
            with Session(self._engine) as session:
                rows = session.exec(stmt).all()
        except SQLAlchemyError as exc:  # pragma: no cover
            msg = "Failed querying classification history."
            raise StorageError(msg) from exc

        return [
            ClassificationHistoryRow(
                pipeline_run_id=pr.id,
                correlation_id=pr.correlation_id,
                created_at_utc=pr.created_at_utc,
                starting_material_id=sm.id,
                canonical_name=sm.canonical_name,
                material_tier=sm.material_tier,
                aggregate_confidence=cr.aggregate_score,
                detector_summary=cr.detector_summary,
            )
            for pr, sm, cr in rows
        ]

    def get_audit_trail(
        self,
        *,
        correlation_id: str | None = None,
        limit: int = 500,
    ) -> list[AuditTrailView]:
        """Return hash-chained audit ledger rows optionally filtered by correlation id."""

        if limit < 1:
            msg = "limit must be >= 1 when requesting audit trail rows."
            raise ValueError(msg)

        stmt = select(AuditTrailEntry).order_by(_sql_col(AuditTrailEntry, "entry_id"))
        if correlation_id is not None:
            if not correlation_id.strip():
                msg = "When provided, correlation_id must be non-empty."
                raise ValueError(msg)
            stmt = stmt.where(AuditTrailEntry.correlation_id == correlation_id)
        stmt = stmt.limit(limit)

        try:
            with Session(self._engine) as session:
                rows = list(session.exec(stmt).all())
        except SQLAlchemyError as exc:  # pragma: no cover
            msg = "Failed querying immutable audit ledger."
            raise StorageError(msg) from exc

        views: list[AuditTrailView] = []
        for entry in rows:
            payload_digest: str | None = None
            try:
                payload_obj = cast(dict[str, object], json.loads(entry.payload_json))
                digest_value = payload_obj.get("snapshot_canonical_sha256")
                if isinstance(digest_value, str):
                    payload_digest = digest_value
            except json.JSONDecodeError:
                payload_digest = None

            entry_id_val = entry.entry_id
            if entry_id_val is None:  # pragma: no cover - autoincrement should always populate
                continue
            views.append(
                AuditTrailView(
                    entry_id=entry_id_val,
                    public_id=entry.public_id,
                    created_at_utc=entry.created_at_utc,
                    event_type=entry.event_type,
                    correlation_id=entry.correlation_id,
                    pipeline_run_id=entry.pipeline_run_id,
                    snapshot_canonical_sha256=payload_digest,
                    payload_json=entry.payload_json,
                    previous_entry_hash_hex=entry.previous_entry_hash_hex,
                    entry_hash_hex=entry.entry_hash_hex,
                ),
            )
        return views

    def recent_runs_dict(self, *, limit: int = 20) -> list[dict[str, object]]:
        """Hydrate immutable snapshots for dashboards (newest first)."""

        if limit < 1:
            msg = "limit must be >= 1 when listing persisted runs."
            raise ValueError(msg)

        stmt = (
            select(PipelineRunRecord)
            .order_by(desc(_sql_col(PipelineRunRecord, "created_at_utc")))
            .limit(limit)
        )

        try:
            with Session(self._engine) as session:
                runs = session.exec(stmt).all()
        except SQLAlchemyError as exc:  # pragma: no cover
            msg = "Failed listing recent Sentinel pipeline snapshots."
            raise StorageError(msg) from exc

        payload: list[dict[str, object]] = []
        for run in runs:
            snap = SentinelPipelineSnapshot.model_validate_json(run.snapshot_json_canonical)
            payload.append(
                {
                    "correlation_id": snap.correlation_id,
                    "submission_excerpt": snap.submission_excerpt,
                    "findings": snap.findings,
                    "suppliers": snap.suppliers,
                    "verifications": snap.verifications,
                    "pipeline_run_id": run.id,
                    "created_at_utc": run.created_at_utc,
                    "content_sha256": snap.parsed_submission.content_sha256,
                    "snapshot_canonical_sha256": run.snapshot_canonical_sha256,
                    "parsed_submission": snap.parsed_submission,
                },
            )
        return payload


class SqliteRegulatoryAuditStorage:
    """SQLite-backed adapter implementing ``RegulatoryAuditStorage`` via ``StorageService``."""

    def __init__(self, *, service: StorageService) -> None:
        """Bind to an already-constructed ``StorageService``."""

        self._svc = service

    @property
    def service(self) -> StorageService:
        """Underlying service (for teardown / advanced introspection only)."""

        return self._svc

    def append_snapshot(self, snapshot: SentinelPipelineSnapshot) -> None:
        self._svc.save_pipeline_snapshot(snapshot)

    def recent_runs(self, *, limit: int = 20) -> list[dict[str, object]]:
        return self._svc.recent_runs_dict(limit=limit)

    def get_audit_trail(
        self,
        *,
        correlation_id: str | None = None,
        limit: int = 500,
    ) -> list[AuditTrailView]:
        return self._svc.get_audit_trail(correlation_id=correlation_id, limit=limit)


def create_memory_storage() -> RegulatoryAuditStorage:
    """Baseline in-memory store for development / unit tests."""

    return InMemoryAuditStorage()


def create_sqlite_regulatory_storage(database_path: str | Path) -> SqliteRegulatoryAuditStorage:
    """Factory wiring SQLite + WAL with the regulatory audit adapter."""

    engine = create_sqlite_engine(database_path)
    service = StorageService(engine)
    return SqliteRegulatoryAuditStorage(service=service)
