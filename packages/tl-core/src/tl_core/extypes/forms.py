"""The generated form of an extension type: every slot, grouped and labelled by ``form.yaml``.

``tl_schema.formgen.form_metadata`` describes the *psets* of a record type, which for an
object-backed type are its index fields only. A form for such a type must also show and edit the
other slots of the body. ``type_form`` is the one description of a type's whole form, for the TUI
form and grid, the API (``GET /types/{type_ref}/form``) and the MCP type tools: a pure function of
the compiled class and its hints.

A slot stored as a pset value has the path ``psets.<pset>.<name>`` (the same path
``form_metadata`` uses and the query language filters); an object-backed type's other slots have
the path ``body.<name>``.
"""

from __future__ import annotations

from pydantic import BaseModel
from tl_schema.forms import EnumValue

from tl_core.extypes.model import CompiledSlot, CompiledType

#: Used when ``form.yaml`` does not place a slot in a group.
OTHER_GROUP = "other"
DEFAULT_GRID_COLUMNS = 4


class TypeFormField(BaseModel):
    name: str
    path: str  # "psets.<pset>.<name>" or "body.<name>"
    label: str
    description: str
    kind: str  # string, text, int, decimal, bool, date, datetime, enum, ref
    multivalued: bool = False
    required: bool = False
    indexed: bool = False
    unit: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    pattern: str | None = None
    enum_values: list[EnumValue] | None = None
    widget: str  # input, textarea, select, checkbox, date
    help: str | None = None
    order: int


class TypeFormGroup(BaseModel):
    name: str
    label: str
    fields: list[TypeFormField]


class TypeForm(BaseModel):
    type_ref: str
    type_name: str
    storage_mode: str
    pset: str
    schema_hash: str
    groups: list[TypeFormGroup]
    grid_columns: list[str]  # slot names, in order

    def fields(self) -> list[TypeFormField]:
        return [field for group in self.groups for field in group.fields]

    def field(self, name: str) -> TypeFormField | None:
        for candidate in self.fields():
            if candidate.name == name:
                return candidate
        return None


def default_widget(slot: CompiledSlot) -> str:
    if slot.kind == "enum" and not slot.multivalued:
        return "select"
    if slot.kind == "text":
        return "textarea"
    if slot.kind == "bool":
        return "checkbox"
    if slot.kind == "date":
        return "date"
    return "input"


def _field(compiled: CompiledType, slot: CompiledSlot, order: int) -> TypeFormField:
    hint = compiled.form.fields.get(slot.name)
    stored_as_pset = compiled.storage_mode == "managed" or slot.indexed
    path = f"psets.{compiled.pset}.{slot.name}" if stored_as_pset else f"body.{slot.name}"
    return TypeFormField(
        name=slot.name,
        path=path,
        label=(hint.label if hint and hint.label else slot.label),
        description=slot.description,
        kind=slot.kind,
        multivalued=slot.multivalued,
        required=slot.required,
        indexed=slot.indexed,
        unit=slot.unit,
        minimum=slot.minimum,
        maximum=slot.maximum,
        pattern=slot.pattern,
        enum_values=None
        if slot.enum_values is None
        else [EnumValue(code=v.code, label=v.label) for v in slot.enum_values],
        widget=(hint.widget if hint and hint.widget else default_widget(slot)),
        help=hint.help if hint else None,
        order=order,
    )


def type_form(compiled: CompiledType) -> TypeForm:
    """The grouped form of ``compiled``.

    Groups follow ``form.yaml``; a slot it does not place goes in a final ``other`` group (or in
    one group named for the type when the file has no groups). Within a group, fields keep the
    order the file gives. ``grid_columns`` is the file's ``grid.columns``, else the index fields,
    else the first four slots.
    """
    by_name = {slot.name: slot for slot in compiled.slots}
    placed: set[str] = set()
    groups: list[TypeFormGroup] = []
    order = 0
    for hint in compiled.form.groups:
        fields: list[TypeFormField] = []
        for name in hint.fields:
            slot = by_name.get(name)
            if slot is None or name in placed:
                continue
            placed.add(name)
            fields.append(_field(compiled, slot, order))
            order += 1
        if fields:
            groups.append(
                TypeFormGroup(
                    name=hint.name, label=hint.label or hint.name.capitalize(), fields=fields
                )
            )
    rest: list[TypeFormField] = []
    for slot in compiled.slots:
        if slot.name not in placed:
            rest.append(_field(compiled, slot, order))
            order += 1
    if rest:
        if groups:
            groups.append(TypeFormGroup(name=OTHER_GROUP, label="Other", fields=rest))
        else:
            groups.append(TypeFormGroup(name="fields", label=compiled.name, fields=rest))
    columns = [name for name in compiled.form.grid.columns if name in by_name]
    if not columns:
        columns = compiled.index_fields or [s.name for s in compiled.slots[:DEFAULT_GRID_COLUMNS]]
    return TypeForm(
        type_ref=compiled.type_ref,
        type_name=compiled.type_name,
        storage_mode=compiled.storage_mode,
        pset=compiled.pset,
        schema_hash=compiled.schema_hash(),
        groups=groups,
        grid_columns=columns,
    )
