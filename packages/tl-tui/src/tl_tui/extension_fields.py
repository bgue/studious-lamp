# ruff: noqa: F401  (STUB P0-I8-T25: delete this line when the unused imports are gone)
"""Form fields of an extension type, and where their values go (P0-I8, brief 31.1).

`type_form` (tl-core) describes the whole form of a type. The TUI's field editor edits a
`FieldMeta`, so each `TypeFormField` becomes one, and the values the user typed go back to the
place the type keeps them: the pset of a managed type, the body of an object-backed one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, get_args

from tl_core.extypes.forms import TypeForm, TypeFormField
from tl_schema.forms import FieldKind, FieldMeta

KINDS: tuple[str, ...] = get_args(FieldKind)
LIST_KIND: FieldKind = "json"  # a multivalued slot is typed as a JSON array


def field_meta(slot: TypeFormField, group: str) -> FieldMeta:
    """The editor description of ``slot``, in the form group ``group``.

    A multivalued slot is edited as JSON (``["a", "b"]``). A kind the editor does not know is
    edited as text. A required slot is marked required; the unit, enum values and the help text
    of ``form.yaml`` (else the slot's description) come along.
    """
    # Build FieldMeta(path=slot.path, label=slot.label, description=slot.help or
    # slot.description, kind, unit=slot.unit, enum_values=slot.enum_values,
    # enforcement="required" or None, layer="standard", group=group, order=slot.order).
    # kind: LIST_KIND when slot.multivalued, else slot.kind when it is in KINDS, else
    # "string".
    raise NotImplementedError("STUB (P0-I8-T25)")


@dataclass(frozen=True)
class FormSection:
    """One group of the form: its label and the editors' descriptions, in order."""

    name: str
    label: str
    fields: list[FieldMeta]


def sections(form: TypeForm) -> list[FormSection]:
    """The groups of ``form`` as editor descriptions, skipping a group without fields."""
    # One FormSection(group.name, group.label, [field_meta(f, group.name) ...]) per group
    # that has fields.
    raise NotImplementedError("STUB (P0-I8-T25)")


@dataclass
class SplitValues:
    """Typed values sorted to where the type keeps them (``create_instance`` arguments)."""

    psets: dict[str, dict[str, Any]] = field(default_factory=lambda: {})
    body: dict[str, Any] | None = None


def split_values(form: TypeForm, values: dict[str, Any]) -> SplitValues:
    """Sort ``values`` (slot name to value; ``None`` is unset and left out) for ``form``'s type.

    A managed type keeps every value in its pset: ``psets = {pset: {name: value}}``, ``body``
    ``None``. An object-backed type keeps all of them in the body (its index fields are copied to
    the pset from there): ``body = {name: value}``, no psets. Names that are not fields of the form
    are ignored.
    """
    # Keep only names that are fields of the form (form.fields()) with a value that is not
    # None. form.storage_mode == "object-backed": SplitValues(body=chosen). Otherwise
    # SplitValues(psets={form.pset: chosen}) or empty psets when nothing is chosen (body
    # stays None).
    raise NotImplementedError("STUB (P0-I8-T25)")
