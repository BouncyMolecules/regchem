"""Associate supplier mentions with surfaced materials."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Protocol

from regchem_sentinel.config import Settings
from regchem_sentinel.core.models import (
    AgentAttribution,
    DecisionProvenance,
    ProvenanceSpan,
    StartingMaterialFinding,
    SupplierLinkage,
    SupplierRole,
)


class SupplierLinker(Protocol):
    def link(
        self,
        text: str,
        *,
        materials: Sequence[StartingMaterialFinding],
        correlation_id: str,
    ) -> tuple[SupplierLinkage, ...]:
        """Return supplier edges grounded in textual evidence."""


_SUPPLIER_PATTERN = re.compile(
    r"(?P<label>(?:Manufacturer|Vendor|Supplier|Distributor))\s*[:\-]\s*(?P<name>[^\n\.]+)",
    re.IGNORECASE,
)


class RegexSupplierLinker:
    """Deterministic linker used while LLM-assisted resolution remains opt-in."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def link(
        self,
        text: str,
        *,
        materials: Sequence[StartingMaterialFinding],
        correlation_id: str,
    ) -> tuple[SupplierLinkage, ...]:
        _ = self._settings
        names = tuple(m.canonical_name for m in materials)
        linkages: list[SupplierLinkage] = []
        for match in _SUPPLIER_PATTERN.finditer(text):
            raw_name = match.group("name").strip()
            locator = f"regex:{match.start()}-{match.end()}"
            span = text[match.start() : match.end()]
            role = SupplierRole.UNKNOWN
            label = match.group("label").lower()
            if "manufacturer" in label:
                role = SupplierRole.MANUFACTURER
            elif "distributor" in label:
                role = SupplierRole.DISTRIBUTOR
            provenance = DecisionProvenance(
                correlation_id=correlation_id,
                evidence=(
                    ProvenanceSpan(
                        excerpt=span,
                        locator=locator,
                        char_offset_start=match.start(),
                        char_offset_end=match.end(),
                    ),
                ),
                rationales=("Linked via regex cue aligned to narrative supplier label.",),
                attributions=(
                    AgentAttribution(
                        actor_name="regex_supplier_linker",
                        actor_version="0.1.0",
                        modality="deterministic_rules",
                    ),
                ),
            )
            linkages.append(
                SupplierLinkage(
                    supplier_display_name=raw_name or "Unknown supplier",
                    role=role,
                    linked_material_names=names[:1],
                    citation=provenance,
                )
            )
        return tuple(linkages)


def default_supplier_linker(settings: Settings) -> SupplierLinker:
    return RegexSupplierLinker(settings)
