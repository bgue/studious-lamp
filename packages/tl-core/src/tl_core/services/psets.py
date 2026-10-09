"""Pset write, form-metadata and conformance services (P0-I2 contract; brief 6.3, 27.3).

Signatures are the contract between the schema and TUI workstreams. The schema workstream replaces
the NotImplementedError bodies; changing a signature needs an orchestrator decision.
"""

from __future__ import annotations

from typing import Any, Literal

from tl_schema.forms import ConformanceReport, FormMetadata

from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork


class SetPsetValues(Command):
    stream_id: str
    expected_version: int
    pset: str  # "valve_data" | "prj.shutdown_tie_in"
    layer: Literal["standard", "custom", "project"]  # enrichment and source are not user-writable
    values: dict[str, Any]  # keys relative to the pset; custom-section keys are prefixed "x."


def handle_set_pset_values(uow: UnitOfWork, cmd: SetPsetValues) -> CommandResult:
    """Validate against the scope's effective schema and emit ``Pset.ValuesSet``."""
    raise NotImplementedError


def form_metadata(uow: UnitOfWork, scope: str, record_type: str) -> FormMetadata:
    """Form and grid metadata for a record type under the scope's effective schema."""
    raise NotImplementedError


def conformance(uow: UnitOfWork, record_id: str) -> ConformanceReport:
    """Conformance of a record's current values against its scope's current effective schema."""
    raise NotImplementedError
