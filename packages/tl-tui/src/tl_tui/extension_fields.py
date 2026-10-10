"""Form fields of an extension type, and where their values go (P0-I8, brief 31.1).

`type_form` (tl-core) describes the whole form of a type. The TUI's field editor edits a
`FieldMeta`, so each `TypeFormField` becomes one, and the values the user typed go back to the
place the type keeps them: the pset of a managed type, the body of an object-backed one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast, get_args

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
    kind: FieldKind
    if slot.multivalued:
        kind = LIST_KIND
    elif slot.kind in KINDS:
        kind = cast(FieldKind, slot.kind)
    else:
        kind = "string"
    return FieldMeta(
        path=slot.path,
        label=slot.label,
        description=slot.help or slot.description,
        kind=kind,
        unit=slot.unit,
        enum_values=slot.enum_values,
        enforcement="required" if slot.required else None,
        layer="standard",
        group=group,
        order=slot.order,
    )


@dataclass(frozen=True)
class FormSection:
    """One group of the form: its label and the editors' descriptions, in order."""

    name: str
    label: str
    fields: list[FieldMeta]


def sections(form: TypeForm) -> list[FormSection]:
    """The groups of ``form`` as editor descriptions, skipping a group without fields."""
    return [
        FormSection(
            group.name,
            group.label,
            [field_meta(slot, group.name) for slot in group.fields],
        )
        for group in form.groups
        if group.fields
    ]


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
    known = {slot.name for slot in form.fields()}
    chosen = {name: value for name, value in values.items() if name in known and value is not None}
    if form.storage_mode == "object-backed":
        return SplitValues(body=chosen)
    if not chosen:
        return SplitValues()
    return SplitValues(psets={form.pset: chosen})
