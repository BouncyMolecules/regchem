"""Application configuration — loaded once per composition root and injected downward."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly typed settings constructed at the composition root and injected downstream."""

    model_config = SettingsConfigDict(
        env_prefix="REGCHEM_SENTINEL_",
        env_file=(".env",),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Deployment environment tag used in provenance bundles.",
    )
    build_id: str = Field(
        default="local",
        description="Build / release identifier surfaced in audit exports.",
    )
    data_dir: Path = Field(
        default=Path("data"),
        description="Directory for persisted exports and cache (created on demand).",
    )
    storage_backend: Literal["memory", "sqlite"] = Field(
        default="sqlite",
        description="Persistence port for audit trails — SQLite WAL for durability; "
        "memory for isolated tests sandboxes.",
    )
    sqlite_database_filename: str = Field(
        default="sentinel.db",
        description="SQLite file resolved under ``data_dir`` when using the sqlite backend.",
    )
    openai_api_key: str | None = Field(
        default=None,
        description="Optional API key for future LLM-backed extractors (never logged).",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sqlite_database_path(self) -> Path:
        """Absolute location of the sentinel SQLite datastore."""

        return self.data_dir.expanduser().resolve() / self.sqlite_database_filename
