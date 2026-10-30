"""Adding a property to a record: what can be added and the command that adds it (P1-UX3 r3, r4).

Pure functions over ``AddableProperties`` (``ClientInterface.addable_properties``, the read the API
and the MCP tool offer too): no widget, no client. The properties a record can still be given are
of three kinds.

* From the standard: a property of a set the project shows that the record has no value for.
* From a set the project has not adopted: an optional set of the company standard. A superuser
  adopts it for the project (``AdoptSchemaPackage``, the schema registry's command) and then enters
  the value; anybody else sees the line greyed with the words the read gives.
* A custom field: a name and a value in the custom section of a set that allows one, up to the
  set's limit. The name rule is ``tl_core.services.psets.custom_name_problem``.

The service decides every outcome: ``set_values_command`` only builds ``SetPsetValues``; a refusal
is shown as it is.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from tl_core.addable import AddableProperties, AddableProperty, AdoptableSet
from tl_core.services.psets import SetPsetValues, custom_name_problem
from tl_mod_schemareg.handlers.adoption import AdoptSchemaPackage
from tl_schema.forms import FieldMeta

from tl_tui.paths import pset_value
from tl_tui.text import unit_label

NO_CUSTOM_SECTION = (
    "No property set of this record takes custom fields. A superuser can allow them in the "
    "standard, or add the property to the standard itself."
)
CUSTOM_HELP = (
    "A custom field is kept in the set's custom section, as text or a number. A name is "
    "lower case letters, digits and _, 1 to 40 characters, starting with a letter."
)
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def field_meta(prop: AddableProperty) -> FieldMeta:
    """The form field the typed editor edits, from what the read says about the property."""
    return FieldMeta(
        path=prop.path,
        label=prop.label,
        description=prop.description,
        kind=prop.type,
        unit=prop.unit,
        enum_values=prop.values,
        required_in_states=prop.required_in_states,
        enforcement=prop.enforcement,
        layer=prop.layer,
        readonly=False,
        group=prop.pset,
        order=prop.order,
    )


def _unit(prop: AddableProperty, record: dict[str, Any]) -> str:
    """The unit as a screen shows it: a UCUM code as its label, a ``{currency}`` placeholder as the
    value the record's set (``currency`` or ``<x>_currency``) or the record itself holds; nothing
    when it has none. A raw ``{...}`` never shows."""
    unit = prop.unit or ""
    match = _PLACEHOLDER.fullmatch(unit)
    if match is None:
        return unit_label(unit)
    name = match.group(1)
    psets: dict[str, Any] = record.get("psets") or {}
    held = pset_value(psets, f"psets.{prop.pset}")
    if isinstance(held, dict):
        for key, value in held.items():  # pyright: ignore[reportUnknownVariableType]
            text = str(key)  # pyright: ignore[reportUnknownArgumentType]
            if (text == name or text.endswith("_" + name)) and value not in (None, ""):
                return str(value)  # pyright: ignore[reportUnknownArgumentType]
    value = record.get(name)
    return "" if value in (None, "") or isinstance(value, (dict, list)) else str(value)


@dataclass(frozen=True)
class Offer:
    """One property the record could be given from the standard.

    ``adopt`` is the set to adopt first when the project does not have it yet (else ``None``).
    """

    prop: AddableProperty
    unit: str  # "" when the property has none
    adopt: AdoptableSet | None = None

    @property
    def pset(self) -> str:
        return self.prop.pset

    @property
    def set_label(self) -> str:
        return self.prop.set_label

    @property
    def label(self) -> str:
        return self.prop.label

    @property
    def field(self) -> FieldMeta:
        return field_meta(self.prop)

    @property
    def adopted(self) -> bool:
        return self.adopt is None

    @property
    def blocked(self) -> str | None:
        """Why the person cannot use this offer now (the set needs adopting by someone else)."""
        if self.adopt is not None and not self.adopt.can_adopt:
            return self.adopt.needs
        return None

    @property
    def line(self) -> str:
        """``Size  ·  Valve data  ·  in``; a set to adopt adds what to do about it."""
        parts = [self.prop.label, self.prop.set_label]
        if self.unit:
            parts.append(self.unit)
        text = "  ·  ".join(parts)
        if self.adopt is None:
            return text
        return f"{text}  ({self.blocked or 'set not adopted by this project yet'})"


@dataclass(frozen=True)
class CustomTarget:
    """A set whose custom section takes more properties."""

    pset: str
    set_label: str
    used: int
    limit: int | None  # None: no limit stated
    package: str
    layer: str  # the layer to write the custom values with

    @property
    def full(self) -> bool:
        return self.limit is not None and self.used >= self.limit

    @property
    def line(self) -> str:
        room = (
            f"{self.used} of {self.limit} used" if self.limit is not None else f"{self.used} used"
        )
        return f"{self.set_label}  ·  {room}"


def standard_offers(addable: AddableProperties, record: dict[str, Any]) -> list[Offer]:
    """The properties the record's type allows and the record has no value for.

    First those of the sets the project shows, then those of the optional sets it has not adopted
    (each carrying the set to adopt), in the order the read gives them.
    """
    offers = [Offer(p, _unit(p, record)) for p in addable.standard]
    for sheet in addable.adoptable:
        offers.extend(Offer(p, _unit(p, record), sheet) for p in sheet.properties)
    return offers


def custom_targets(addable: AddableProperties) -> list[CustomTarget]:
    """The sets of the record whose custom section is open, with how many fields it holds."""
    return [
        CustomTarget(
            pset=rule.pset,
            set_label=rule.set_label,
            used=rule.used,
            limit=rule.max_properties,
            package=rule.package,
            layer="custom",
        )
        for rule in addable.custom
        if rule.allowed
    ]


def owners(addable: AddableProperties) -> list[tuple[str, str]]:
    """``(package, set label)`` of every set the record could be given a property from, once per
    package: where a change to the standard would be proposed."""
    found: dict[str, str] = {}
    for prop in addable.standard:
        found.setdefault(prop.package, prop.set_label)
    for sheet in addable.adoptable:
        found.setdefault(sheet.package, sheet.set_label)
    for rule in addable.custom:
        found.setdefault(rule.package, rule.set_label)
    return sorted(found.items())


def adopt_label(sheet: AdoptableSet) -> str:
    """``Adopt Inspection data for P123``."""
    return f"Adopt {sheet.set_label} for {sheet.project}"


def adopt_command(sheet: AdoptableSet, *, actor: str) -> AdoptSchemaPackage:
    """The schema registry's command that pins the package of ``sheet`` for its project."""
    return AdoptSchemaPackage(
        actor=actor,
        source="tui",
        scope="company",
        project=sheet.project,
        package=sheet.package,
        version=sheet.version,
    )


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
    return set_values_command(
        record,
        pset=offer.pset,
        layer=offer.prop.layer,
        key=offer.prop.property,
        value=value,
        actor=actor,
        scope=scope,
    )


def custom_problem(name: str, chosen: CustomTarget) -> str | None:
    """Why the typed name cannot be used in ``chosen`` (``None`` when it can): the service's rule,
    said before the command goes, and a full section."""
    key = custom_key(name)
    if not key:
        return "Enter a name."
    problem = custom_name_problem(key)
    if problem is not None:
        return problem[0].upper() + problem[1:] + "."
    if chosen.full:
        return f"{chosen.set_label} takes at most {chosen.limit} custom fields on a record."
    return None
