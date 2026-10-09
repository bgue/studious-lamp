"""Form and conformance metadata contracts (P0-I2 fanout, brief 6.3 and 10.2).

Shared contract between the schema workstream (which produces these from the effective schema)
and the TUI workstream (which renders them). Changing a field here is a contract change: it needs
an orchestrator decision.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Layer = Literal["core", "standard", "custom", "project", "enrichment", "source"]
Enforcement = Literal["advisory", "required", "locked"]
FieldKind = Literal[
    "string",
    "text",
    "int",
    "decimal",
    "bool",
    "date",
    "datetime",
    "enum",
    "quantity",
    "ref",
    "json",
]
ConformanceLevel = Literal["ok", "warning", "nonconformant", "waived"]


class EnumValue(BaseModel):
    code: str
    label: str
    crosswalk: str | None = None  # company code that a project-added value maps to


class FieldMeta(BaseModel):
    path: str  # "title" | "psets.valve_data.size_in" | "psets.valve_data.x.fat_witness_by"
    label: str
    description: str
    kind: FieldKind
    unit: str | None = None  # UCUM code
    enum_values: list[EnumValue] | None = None
    required_in_states: list[str] = []
    enforcement: Enforcement | None = None
    layer: Layer
    readonly: bool = False  # enrichment and source layers are never user-writable
    group: str  # pset name, or "details" for core fields
    order: int


class PsetGroupMeta(BaseModel):
    name: str  # "valve_data" | "prj.shutdown_tie_in"
    label: str
    package: str  # "co.acme.engineering"
    version: str  # "3.2.0"
    enforcement: Enforcement | None
    layer: Layer
    fields: list[FieldMeta]


class FormMetadata(BaseModel):
    record_type: str
    effective_schema_hash: str
    core_fields: list[FieldMeta]
    psets: list[PsetGroupMeta]


class ConformanceIssue(BaseModel):
    path: str
    level: Literal["warning", "nonconformant"]
    rule: str  # "required_in_state" | "value_list" | "range" | "pattern" | "locked" | "type"
    message: str


class ConformanceReport(BaseModel):
    status: ConformanceLevel
    issues: list[ConformanceIssue]
    effective_schema_hash: str
