"""Adding a property to a record: what can be added and the command that adds it (P1-UX3 round 3).

Pure functions over the form metadata the client already reads (``form_metadata``): no widget, no
client. The properties a record can still be given are of two kinds.

* From the standard: a property of a set the record's type allows that the record has no value for.
  The set may be one the project shows already (its empty rows) or an optional set of the company
  standard that the project has not adopted (the company's form lists it, the project's does not).
* A custom field: a name and a value in the custom section of a set that has one.

The service decides every outcome: ``set_values_command`` only builds ``SetPsetValues``; a set the
project has not adopted, a name the project's schema does not define and a full custom section are
refused by the command, and the refusal is shown as it is.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from tl_core.services.psets import SetPsetValues
from tl_schema.forms import FieldMeta, FormMetadata, PsetGroupMeta

from tl_tui.display import pset_label
from tl_tui.paths import pset_value, relative_key
from tl_tui.widgets.psets_tab import unit_text

NOT_ADOPTED = "set not adopted by this project"
NO_CUSTOM_SECTION = (
    "No property set of this record takes custom fields. An admin can allow them in the "
    "standard, or add the property to the standard itself."
)
CUSTOM_HELP = (
    "A custom field is kept in the set's custom section. The project's schema must define its "
    "name; a name it does not define is refused."
)
WRITABLE_LAYERS = ("standard", "project", "custom")


@dataclass(frozen=True)
class Offer:
    """One property the record could be given from the standard."""

    pset: str
    set_label: str
    field: FieldMeta
    unit: str  # "" when the property has none
    adopted: bool  # False: an optional set the project has not adopted
    package: str

    @property
    def label(self) -> str:
        return self.field.label

    @property
    def line(self) -> str:
        """``Size  ·  Valve data  ·  in`` plus ``(set not adopted by this project)``."""
        parts = [self.field.label, self.set_label]
        if self.unit:
            parts.append(self.unit)
        text = "  ·  ".join(parts)
        return text if self.adopted else f"{text}  ({NOT_ADOPTED})"


@dataclass(frozen=True)
class CustomTarget:
    """A set whose custom section takes more properties."""

    pset: str
    set_label: str
    used: int
    limit: int | None  # None: no limit
    package: str
    layer: str  # the layer to write the custom values with

    @property
    def line(self) -> str:
        room = (
            f"{self.used} of {self.limit} used" if self.limit is not None else f"{self.used} used"
        )
        return f"{self.set_label}  ·  {room}"


def _empty(psets: dict[str, Any], path: str) -> bool:
    return pset_value(psets, path) in (None, "")


def _writable(field: FieldMeta) -> bool:
    return not field.readonly and field.layer in WRITABLE_LAYERS


def standard_offers(
    meta: FormMetadata, company: FormMetadata | None, record: dict[str, Any]
) -> list[Offer]:
    """The properties the record's type allows and the record has no value for.

    First the empty properties of the sets the project shows, then the properties of the optional
    sets only the company standard lists (``company`` is the company's form for the same type),
    each in the order of the standard.
    """
    psets: dict[str, Any] = record.get("psets") or {}
    offers: list[Offer] = []
    shown = {group.name for group in meta.psets}
    for group in meta.psets:
        for field in group.fields:
            if _writable(field) and _empty(psets, field.path):
                offers.append(_offer(group, field, psets, record, adopted=True))
    if company is not None:
        for group in company.psets:
            if group.name in shown:
                continue
            for field in group.fields:
                if _writable(field) and field.layer != "custom":
                    offers.append(_offer(group, field, psets, record, adopted=False))
    return offers


def _offer(
    group: PsetGroupMeta,
    field: FieldMeta,
    psets: dict[str, Any],
    record: dict[str, Any],
    *,
    adopted: bool,
) -> Offer:
    return Offer(
        pset=group.name,
        set_label=pset_label(group),
        field=field,
        unit=unit_text(field, psets, group.fields, record),
        adopted=adopted,
        package=group.package,
    )


def custom_targets(meta: FormMetadata, record: dict[str, Any]) -> list[CustomTarget]:
    """The sets of the record whose custom section is open, with how many fields it holds."""
    psets: dict[str, Any] = record.get("psets") or {}
    targets: list[CustomTarget] = []
    for group in meta.psets:
        if not group.custom_allowed:
            continue
        held = pset_value(psets, f"psets.{group.name}.x")
        targets.append(
            CustomTarget(
                pset=group.name,
                set_label=pset_label(group),
                used=len(held) if isinstance(held, dict) else 0,
                limit=group.custom_max,
                package=group.package,
                layer="custom",
            )
        )
    return targets


def owners(meta: FormMetadata, company: FormMetadata | None) -> list[tuple[str, str]]:
    """``(package, set label)`` of every set the record could be given a property from, once per
    package: where a change to the standard would be proposed."""
    found: dict[str, str] = {}
    for form in (meta, company):
        for group in form.psets if form is not None else ():
            if group.layer == "standard":
                found.setdefault(group.package, pset_label(group))
    return sorted(found.items())


_NAME_SPLIT = re.compile(r"[^a-z0-9]+")


def custom_key(name: str) -> str:
    """The key a typed name is kept under: lower snake case (``Fat witness by`` becomes
    ``fat_witness_by``); ``""`` when nothing usable is left."""
    return _NAME_SPLIT.sub("_", name.strip().lower()).strip("_")


def set_values_command(
    record: dict[str, Any],
    *,
    pset: str,
    layer: Literal["standard", "custom", "project"],
    key: str,
    value: Any,
    actor: str,
    scope: str,
) -> SetPsetValues:
    """``SetPsetValues`` for one value; ``key`` is relative to the set (``x.`` when custom)."""
    return SetPsetValues(
        actor=actor,
        source="tui",
        scope=scope,
        stream_id=record["id"],
        expected_version=int(record["version"]),
        pset=pset,
        layer=layer,
        values={key: value},
    )


def offer_command(
    record: dict[str, Any], offer: Offer, value: Any, *, actor: str, scope: str
) -> SetPsetValues:
    """The command that gives ``offer`` its ``value``."""
    layer: Literal["standard", "custom", "project"] = (
        "custom"
        if offer.field.layer == "custom"
        else "project"
        if offer.field.layer == "project"
        else "standard"
    )
    return set_values_command(
        record,
        pset=offer.pset,
        layer=layer,
        key=relative_key(offer.field.path, offer.pset),
        value=value,
        actor=actor,
        scope=scope,
    )
