# ruff: noqa: F401  (STUB P0-I8-T27: delete this line when the unused imports are gone)
"""Editing the stored body of an object-backed record (P0-I8, brief 31.2).

A body is replaced as a whole: a save stores a new document version. The edit form shows the
slots the type's form names; this module keeps the rest of the body (anything the form does not
show) and applies only what the user changed.
"""

from __future__ import annotations

from typing import Any

from tl_core.extypes.forms import TypeForm


def body_values(form: TypeForm, body: dict[str, Any]) -> dict[str, Any]:
    """The initial value of each slot of ``form`` (slot name to the body's value, else ``None``)."""
    # One entry per slot of form.fields(): the slot name and body.get(name) (None when the
    # body has no value).
    raise NotImplementedError("STUB (P0-I8-T27)")


def merged_body(form: TypeForm, body: dict[str, Any], edits: dict[str, Any]) -> dict[str, Any]:
    """``body`` with the user's ``edits`` applied (a new dict; ``body`` is not changed).

    ``edits`` maps a slot name to its new value; ``None`` clears the slot (it is removed from the
    body). Names that are not slots of ``form`` are ignored. Keys of ``body`` that are not
    slots of ``form`` are kept as they are.
    """
    # Copy body (dict(body)). For each edit whose name is a slot of the form: None removes
    # the key (pop with a default), anything else sets it. Names that are not slots are
    # ignored; body keys that are not slots stay.
    raise NotImplementedError("STUB (P0-I8-T27)")
