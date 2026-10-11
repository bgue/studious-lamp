"""What a type package compiles to (brief 31.1, 27.3), and the hint files it may carry.

``CompiledType`` is the in-memory form of ``type.yaml``: the slots of the class, which of them are
index fields, where the body lives, and the form hints of ``form.yaml``. It is a pure function of
the package files, so the same files give the same ``schema_hash``. The registry, the effective
schema (as a ``PackageDoc`` with one pset) and the body validator all read it.
"""

from __future__ import annotations

import hashlib
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from tl_schema.effective import canonical_dump
from tl_schema.forms import EnumValue

from tl_core.extypes.names import pset_name

SlotKind = Literal[
    "string", "text", "int", "decimal", "bool", "date", "datetime", "enum", "ref", "json"
]
Widget = Literal["input", "textarea", "select", "checkbox", "date"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CompiledSlot(BaseModel):
    """One slot of the class. A multivalued slot has the kind of one item and ``multivalued``."""

    name: str
    label: str
    description: str
    kind: SlotKind
    required: bool = False
    multivalued: bool = False
    indexed: bool = False
    unit: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    pattern: str | None = None
    enum_name: str | None = None
    enum_values: list[EnumValue] | None = None

    @property
    def pset_kind(self) -> str:
        """The pset property kind: a multivalued slot is a JSON list."""
        return "json" if self.multivalued else self.kind


class FormFieldHint(_Strict):
    label: str | None = None
    help: str | None = None
    widget: Widget | None = None


class FormGroupHint(_Strict):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str | None = None
    fields: list[str] = Field(min_length=1)


class GridHint(_Strict):
    columns: list[str] = []


class FormHints(_Strict):
    """``form.yaml``: layout hints for generated forms and grids. Every name is a slot."""

    groups: list[FormGroupHint] = []
    fields: dict[str, FormFieldHint] = {}
    grid: GridHint = GridHint()

    def names(self) -> list[str]:
        named = [name for group in self.groups for name in group.fields]
        return [*named, *self.fields, *self.grid.columns]


class CompiledType(BaseModel):
    namespace: str
    name: str
    version: str
    description: str
    storage_mode: Literal["managed", "object-backed"]
    slots: list[CompiledSlot]
    form: FormHints = FormHints()

    @property
    def type_name(self) -> str:
        return f"{self.namespace}.{self.name}"

    @property
    def type_ref(self) -> str:
        return f"{self.type_name}@{self.version}"

    @property
    def pset(self) -> str:
        return pset_name(self.namespace, self.name)

    @property
    def index_fields(self) -> list[str]:
        return [slot.name for slot in self.slots if slot.indexed]

    def slot(self, name: str) -> CompiledSlot | None:
        for slot in self.slots:
            if slot.name == name:
                return slot
        return None

    def pset_slots(self) -> list[CompiledSlot]:
        """The slots stored as pset values: every slot when managed, the index fields otherwise."""
        if self.storage_mode == "managed":
            return list(self.slots)
        return [slot for slot in self.slots if slot.indexed]

    def schema_hash(self) -> str:
        """sha256 of the compiled class: type name, pset, storage mode and slots.

        The version, description and form hints are left out, so a release that changes none of the
        slots keeps the hash and the bodies stored under the older release stay valid.
        """
        body: dict[str, Any] = {
            "type_name": self.type_name,
            "pset": self.pset,
            "storage_mode": self.storage_mode,
            "slots": [slot.model_dump(mode="json") for slot in self.slots],
        }
        return hashlib.sha256(canonical_dump(body).encode("utf-8")).hexdigest()
