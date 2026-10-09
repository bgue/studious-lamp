"""The effective schema: what a scope's adopted packages resolve to (brief 27.3).

``EffectiveSchema`` is the resolved, validated, hashable model every runtime consumer reads: JSON
Schema generation, form metadata, the conformance evaluator, and the pset command handler. It is
built by ``tl_schema.compose`` from package documents and never edited afterwards. Its ``hash`` is
the content hash that events record as ``effective_schema_hash``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel

from tl_schema.forms import EnumValue, FieldKind
from tl_schema.packages import Adoption, ConformanceMode, Enforcement, ValueListPolicy

PropertyLayer = Literal["standard", "custom", "project"]
PsetLayer = Literal["standard", "project"]

#: ``required_in_states`` entry meaning "required in every state, including no state".
ALWAYS = "*"

#: Rank used when comparing enforcement levels. Higher is stricter.
ENFORCEMENT_RANK: dict[str, int] = {"advisory": 0, "required": 1, "locked": 2}


def states_cover(new: Sequence[str], old: Sequence[str]) -> bool:
    """Whether ``new`` requires a value in every state ``old`` does (``ALWAYS`` covers all)."""
    if ALWAYS in new:
        return True
    return ALWAYS not in old and all(state in new for state in old)


def required_in(states: Sequence[str], state: str | None) -> bool:
    """Whether a property with these ``required_in_states`` needs a value in ``state``.

    ``ALWAYS`` means every state, including no state at all.
    """
    return ALWAYS in states or (state is not None and state in states)


class PackageRef(BaseModel):
    name: str
    version: str


class EffectiveProperty(BaseModel):
    name: str  # plain name; a custom property is addressed as "x.<name>" inside its pset
    layer: PropertyLayer
    label: str
    description: str
    kind: FieldKind
    unit: str | None = None  # UCUM code
    code_list: str | None = None  # name of the code list when kind == "enum"
    enum_values: list[EnumValue] | None = None
    enum_meanings: dict[str, str] = {}  # code -> meaning IRI; part of the hash (brief 27.1, 27.6)
    value_list_policy: ValueListPolicy | None = None
    required_in_states: list[str] = []  # ALWAYS means every state
    enforcement: Enforcement
    materialize: bool = False
    minimum: float | None = None
    maximum: float | None = None
    pattern: str | None = None
    default: Any = None
    exact_mappings: list[str] = []
    origin: str  # "name@version" of the package that defined the property
    order: int = 0  # position within the pset's form; custom properties follow standard ones

    def relative_key(self) -> str:
        """Key inside the pset's value object: ``size_in`` or ``x.fat_witness_by``."""
        return f"x.{self.name}" if self.layer == "custom" else self.name


class EffectivePset(BaseModel):
    name: str  # "valve_data" or "prj.shutdown_tie_in"
    layer: PsetLayer
    label: str
    description: str
    package: str
    version: str
    extension: str | None = None  # "x.P123@1.4.0" when a project extends this pset
    applies_to: list[str]
    class_filter: str | None = None
    enforcement: Enforcement
    adoption: Adoption
    custom_allowed: bool
    custom_max: int | None = None
    properties: dict[str, EffectiveProperty]  # in declaration order
    custom: dict[str, EffectiveProperty] = {}  # in declaration order

    def all_properties(self) -> list[EffectiveProperty]:
        """Standard (or project) properties first, then custom-section ones."""
        return [*self.properties.values(), *self.custom.values()]

    def find(self, relative_key: str) -> EffectiveProperty | None:
        """Look up ``size_in`` or ``x.fat_witness_by``."""
        if relative_key.startswith("x."):
            return self.custom.get(relative_key[2:])
        return self.properties.get(relative_key)


class EffectiveWaiver(BaseModel):
    path: str
    reason: str
    approver: str
    expires: date | None = None


class EffectiveConformance(BaseModel):
    mode: ConformanceMode = "strict"
    lenient_until: date | None = None
    waivers: list[EffectiveWaiver] = []


class EffectiveSchema(BaseModel):
    scope: str  # "company" or "project:<id>"
    packages: list[PackageRef]  # sorted by name
    core_digest: str  # digest of the core schema release the psets were composed on
    psets: dict[str, EffectivePset]  # sorted by name
    conformance: EffectiveConformance = EffectiveConformance()
    hash: str = ""

    def for_record_type(self, record_type: str) -> list[EffectivePset]:
        """Psets whose ``applies_to`` names ``record_type``, in name order."""
        return [p for p in self.psets.values() if record_type in p.applies_to]

    def find_pset(self, name: str) -> EffectivePset | None:
        return self.psets.get(name)


def canonical_dump(value: Any) -> str:
    """Canonical JSON text: sorted keys, no whitespace, UTF-8 characters kept."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_hash(schema: EffectiveSchema) -> str:
    """SHA-256 hex of the canonical JSON of every field except ``hash``."""
    body = schema.model_dump(mode="json", exclude={"hash"})
    return hashlib.sha256(canonical_dump(body).encode("utf-8")).hexdigest()


def with_hash(schema: EffectiveSchema) -> EffectiveSchema:
    """A copy of ``schema`` with ``hash`` filled in."""
    return schema.model_copy(update={"hash": compute_hash(schema)})


def resolve_path(schema: EffectiveSchema, path: str) -> tuple[EffectivePset, str] | None:
    """Split ``psets.valve_data.x.fat_witness_by`` into ``(pset, "x.fat_witness_by")``.

    Returns ``None`` when no pset of the schema owns the path or the property is unknown. The
    longest matching pset name wins, so ``prj.shutdown_tie_in`` resolves although it contains a dot.
    """
    if not path.startswith("psets."):
        return None
    rest = path[len("psets.") :]
    for name in sorted(schema.psets, key=len, reverse=True):
        if rest.startswith(name + "."):
            pset = schema.psets[name]
            key = rest[len(name) + 1 :]
            return (pset, key) if pset.find(key) is not None else None
    return None
