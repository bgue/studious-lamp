"""Classify the change between two versions of a package (brief 27.5; P1-I8-T02).

``classify_packages(old, new)`` compares two ``PackageDoc`` versions of one package and returns a
``ClassificationReport``: every change with its class, the worst class, and what that class means
for handling. The classes are the ones of the brief's table:

=============  ==============================================================================
class          what is in it
=============  ==============================================================================
additive       a new optional property, pset, code or code list; a relaxed rule; a clarified text
constraining   a new required property, a tighter range, pattern, enforcement or value list
renaming       a property that went away and came back under another name (same range, unit and
               description): the change needs an alias
promotion      reserved for the move of a project property into a company package (it needs two
               packages, so ``classify_packages`` never produces it)
breaking       a changed type, a changed unit, a changed package kind
deprecation    something removed (a property, a pset, a code, a code list)
forbidden      a change of meaning: an existing external mapping removed or replaced, a changed
               value meaning
=============  ==============================================================================

Rules of thumb the code applies, so a reviewer can predict a result:

* A rule that becomes *stricter* is ``constraining``; one that becomes *looser* is ``additive`` with
  ``relaxing`` set. Existing records are never rewritten, so a looser rule cannot make one
  non-conformant.
* A text whose words changed (description) is ``additive`` with ``review`` set: the meaning must
  not change and only a person can tell.
* The report is deterministic: changes are sorted by path and code, and ``digest`` is the SHA-256
  of the canonical JSON of the base, the target and the changes. A review that approved a digest
  has approved exactly those changes.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict

from tl_schema.packages import (
    CodeList,
    CodeValue,
    ConformanceDef,
    ExtendsDef,
    PackageDoc,
    PropertyDef,
    PsetDef,
    TightenDef,
    version_tuple,
)

ChangeClass = Literal[
    "additive",
    "deprecation",
    "renaming",
    "promotion",
    "constraining",
    "breaking",
    "forbidden",
]

#: From mildest to worst; ``worst`` of a report is the last of these that occurs.
CLASS_ORDER: tuple[ChangeClass, ...] = (
    "additive",
    "deprecation",
    "renaming",
    "promotion",
    "constraining",
    "breaking",
    "forbidden",
)

#: What each class means for handling (brief 27.5).
HANDLING: dict[ChangeClass, str] = {
    "additive": "Auto-adoptable; forms and columns appear.",
    "deprecation": "Hidden from forms; values stay queryable in history and the lake; "
    "retired after the notice period.",
    "renaming": "Declare an alias; the old path is accepted with a deprecation warning until "
    "retirement.",
    "promotion": "Alias from the project property to the standard path; values are carried by "
    "mapping, no event is rewritten.",
    "constraining": "Grace period; existing records are flagged non-conformant, not rewritten; "
    "waivers are possible; a project adopts it after reading its impact report.",
    "breaking": "Not allowed in place: add a new property, optionally convert with a correlated "
    "job, and deprecate the old one.",
    "forbidden": "A different meaning is a new property with a new IRI.",
}

BLOCKING: frozenset[ChangeClass] = frozenset({"breaking", "forbidden"})

_ENFORCEMENT_RANK = {"advisory": 0, "required": 1, "locked": 2}
_ADOPTION_RANK = {"optional": 0, "default": 1, "mandatory": 2}
_POLICY_RANK = {"project_defined": 0, "extensible": 1, "closed": 2}
_MODE_RANK = {"lenient": 0, "strict_with_waivers": 1, "strict": 2}
_ALWAYS = "*"


class Change(BaseModel):
    """One difference between two versions."""

    model_config = ConfigDict(frozen=True)

    cls: ChangeClass
    code: str  # a short machine word: ``property_added``, ``minimum_raised``
    path: str  # ``psets.valve_data.size_in``, ``code_lists.MaterialCode.values.CS``
    detail: str  # one sentence a person reads
    relaxing: bool = False  # a rule got looser
    review: bool = False  # a person must confirm (a text changed)


class ClassificationReport(BaseModel):
    """What changed between ``base`` and ``target`` and what the change means."""

    model_config = ConfigDict(frozen=True)

    base: str | None  # ``name@version`` of the older version; None for a new package
    target: str
    changes: tuple[Change, ...]
    counts: dict[str, int]
    worst: ChangeClass
    auto_adoptable: bool  # every change is additive
    blocks_submit: bool  # a breaking or forbidden change is in it
    handling: dict[str, str]  # the text for each class that occurs
    digest: str  # SHA-256 over the base, the target and the changes


def build_report(base: str | None, target: str, changes: Sequence[Change]) -> ClassificationReport:
    """Assemble a report from a list of changes (sorted here, so callers need not)."""
    ordered = tuple(sorted(changes, key=lambda c: (c.path, c.code, c.cls, c.detail)))
    counts: dict[ChangeClass, int] = {name: 0 for name in CLASS_ORDER}
    for change in ordered:
        counts[change.cls] += 1
    present: list[ChangeClass] = [name for name in CLASS_ORDER if counts[name]]
    worst: ChangeClass = present[-1] if present else "additive"
    body = json.dumps(
        {"base": base, "target": target, "changes": [c.model_dump() for c in ordered]},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return ClassificationReport(
        base=base,
        target=target,
        changes=ordered,
        counts={name: n for name, n in counts.items() if n},
        worst=worst,
        auto_adoptable=worst == "additive",
        blocks_submit=any(c.cls in BLOCKING for c in ordered),
        handling={name: HANDLING[name] for name in present},
        digest=hashlib.sha256(body.encode("utf-8")).hexdigest(),
    )


class _Sink:
    """Collects changes; the helpers below write through it so paths stay short."""

    def __init__(self) -> None:
        self.items: list[Change] = []

    def add(
        self,
        cls: ChangeClass,
        code: str,
        path: str,
        detail: str,
        *,
        relaxing: bool = False,
        review: bool = False,
    ) -> None:
        self.items.append(
            Change(cls=cls, code=code, path=path, detail=detail, relaxing=relaxing, review=review)
        )


def classify_packages(old: PackageDoc | None, new: PackageDoc) -> ClassificationReport:
    """Classify ``new`` against ``old`` (the version it follows), or as a first version.

    Raises ``ValueError`` when the packages differ in name or ``new`` is not a higher version.
    """
    sink = _Sink()
    if old is None:
        sink.add("additive", "package_added", "(package)", f"new package {new.key()}")
        return build_report(None, new.key(), sink.items)
    if old.package != new.package:
        raise ValueError(f"cannot compare {old.key()} with {new.key()}: different packages")
    if version_tuple(new.version) <= version_tuple(old.version):
        raise ValueError(f"{new.key()} must be a higher version than {old.key()}")
    _package_level(old, new, sink)
    _code_lists(old.code_lists, new.code_lists, sink)
    _psets(old, new, sink)
    _extends(old.extends, new.extends, sink)
    _conformance(old.conformance, new.conformance, sink)
    return build_report(old.key(), new.key(), sink.items)


# --- package ---------------------------------------------------------------------------------


def _package_level(old: PackageDoc, new: PackageDoc, sink: _Sink) -> None:
    if old.kind != new.kind:
        sink.add("breaking", "kind_changed", "(package)", f"kind {old.kind} became {new.kind}")
    if old.project != new.project:
        sink.add(
            "breaking",
            "project_changed",
            "(package)",
            f"project {old.project} became {new.project}",
        )
    for name in sorted(set(old.depends) | set(new.depends)):
        before, after = old.depends.get(name), new.depends.get(name)
        if before == after:
            continue
        if before is None:
            sink.add(
                "additive", "depends_added", f"depends.{name}", f"now depends on {name}@{after}"
            )
        elif after is None:
            sink.add(
                "additive",
                "depends_removed",
                f"depends.{name}",
                f"no longer pins {name}@{before}",
                relaxing=True,
            )
        else:
            sink.add(
                "additive",
                "depends_changed",
                f"depends.{name}",
                f"{name} pin {before} became {after}",
            )
    if old.description != new.description:
        sink.add(
            "additive",
            "description_changed",
            "(package)",
            "the package description changed",
            review=True,
        )
    if old.title != new.title:
        sink.add("additive", "title_changed", "(package)", "the package title changed")


# --- code lists ------------------------------------------------------------------------------


def _code_lists(old: Mapping[str, CodeList], new: Mapping[str, CodeList], sink: _Sink) -> None:
    for name in sorted(set(old) | set(new)):
        path = f"code_lists.{name}"
        before, after = old.get(name), new.get(name)
        if before is None:
            sink.add("additive", "code_list_added", path, f"code list {name} added")
            continue
        if after is None:
            sink.add(
                "deprecation",
                "code_list_removed",
                path,
                f"code list {name} removed",
            )
            continue
        _rank_change(
            _POLICY_RANK,
            before.value_list_policy,
            after.value_list_policy,
            sink,
            path + ".value_list_policy",
            "value_list_policy",
        )
        old_values = {v.code: v for v in before.values}
        new_values = {v.code: v for v in after.values}
        for code in sorted(set(old_values) | set(new_values)):
            value_path = f"{path}.values.{code}"
            was, now = old_values.get(code), new_values.get(code)
            if was is None:
                sink.add("additive", "value_added", value_path, f"value {code} added to {name}")
            elif now is None:
                sink.add(
                    "deprecation",
                    "value_removed",
                    value_path,
                    f"value {code} removed from {name}; records keep it",
                )
            else:
                if was.meaning != now.meaning:
                    if was.meaning is None:
                        sink.add(
                            "additive",
                            "meaning_added",
                            value_path,
                            f"value {code} gained a meaning",
                        )
                    else:
                        sink.add(
                            "forbidden",
                            "meaning_changed",
                            value_path,
                            f"the meaning of {code} changed; a different meaning is a new value",
                        )
                if was.label != now.label:
                    sink.add("additive", "label_changed", value_path, f"label of {code} changed")
                if was.crosswalk != now.crosswalk:
                    sink.add(
                        "additive", "crosswalk_changed", value_path, f"crosswalk of {code} changed"
                    )


def _rank_change(
    ranks: Mapping[str, int], before: str, after: str, sink: _Sink, path: str, code: str
) -> None:
    """A rule with an order (enforcement, adoption, list policy): higher is stricter."""
    if before == after:
        return
    if ranks[after] > ranks[before]:
        sink.add("constraining", f"{code}_tightened", path, f"{code} {before} became {after}")
    else:
        sink.add(
            "additive", f"{code}_relaxed", path, f"{code} {before} became {after}", relaxing=True
        )


# --- psets and properties --------------------------------------------------------------------


def _psets(old: PackageDoc, new: PackageDoc, sink: _Sink) -> None:
    for name in sorted(set(old.psets) | set(new.psets)):
        path = f"psets.{name}"
        before, after = old.psets.get(name), new.psets.get(name)
        if before is None and after is not None:
            _pset_added(name, after, sink)
        elif after is None:
            sink.add("deprecation", "pset_removed", path, f"pset {name} removed")
        elif before is not None:
            _pset_changed(name, before, after, sink)


def _pset_added(name: str, pset: PsetDef, sink: _Sink) -> None:
    required = sorted(p for p, d in pset.properties.items() if _states(d))
    if pset.adoption == "mandatory" and required:
        sink.add(
            "constraining",
            "pset_added_required",
            f"psets.{name}",
            f"mandatory pset {name} added with required properties: {', '.join(required)}",
        )
    else:
        sink.add("additive", "pset_added", f"psets.{name}", f"pset {name} added")


def _pset_changed(name: str, before: PsetDef, after: PsetDef, sink: _Sink) -> None:
    path = f"psets.{name}"
    for record_type in sorted(set(before.applies_to) - set(after.applies_to)):
        sink.add(
            "deprecation",
            "applies_to_removed",
            path + ".applies_to",
            f"pset {name} no longer applies to {record_type}",
        )
    for record_type in sorted(set(after.applies_to) - set(before.applies_to)):
        sink.add(
            "additive",
            "applies_to_added",
            path + ".applies_to",
            f"pset {name} now applies to {record_type}",
        )
    if before.class_filter != after.class_filter:
        sink.add(
            "constraining",
            "class_filter_changed",
            path + ".class_filter",
            "the class filter changed; records of other classes may be affected",
        )
    _rank_change(
        _ENFORCEMENT_RANK,
        before.enforcement,
        after.enforcement,
        sink,
        path + ".enforcement",
        "enforcement",
    )
    _rank_change(
        _ADOPTION_RANK, before.adoption, after.adoption, sink, path + ".adoption", "adoption"
    )
    if before.description != after.description:
        sink.add(
            "additive", "description_changed", path, f"description of {name} changed", review=True
        )
    if before.label != after.label:
        sink.add("additive", "label_changed", path, f"label of {name} changed")
    _custom_section(path, before, after, sink)
    removed = {p: d for p, d in before.properties.items() if p not in after.properties}
    added = {p: d for p, d in after.properties.items() if p not in before.properties}
    renamed = _renames(removed, added)
    for old_name, new_name in sorted(renamed.items()):
        sink.add(
            "renaming",
            "property_renamed",
            f"{path}.{old_name}",
            f"{old_name} may have become {new_name} (same range, unit and description); "
            "declare an alias",
        )
    for prop in sorted(removed):
        if prop not in renamed:
            sink.add(
                "deprecation", "property_removed", f"{path}.{prop}", f"property {prop} removed"
            )
    for prop in sorted(added):
        if prop in renamed.values():
            continue
        if _states(added[prop]):
            sink.add(
                "constraining",
                "property_added_required",
                f"{path}.{prop}",
                f"required property {prop} added",
            )
        else:
            sink.add("additive", "property_added", f"{path}.{prop}", f"property {prop} added")
    for prop in sorted(set(before.properties) & set(after.properties)):
        _property(
            f"{path}.{prop}",
            before.properties[prop],
            after.properties[prop],
            before.enforcement,
            after.enforcement,
            sink,
        )


def _custom_section(path: str, before: PsetDef, after: PsetDef, sink: _Sink) -> None:
    was, now = before.custom_section, after.custom_section
    if was.allowed and not now.allowed:
        sink.add(
            "constraining",
            "custom_section_closed",
            path + ".custom_section",
            "project custom properties are no longer allowed",
        )
    elif not was.allowed and now.allowed:
        sink.add(
            "additive",
            "custom_section_opened",
            path + ".custom_section",
            "project custom properties are allowed",
            relaxing=True,
        )
    if was.max_properties != now.max_properties:
        lowered = now.max_properties is not None and (
            was.max_properties is None or now.max_properties < was.max_properties
        )
        if lowered:
            sink.add(
                "constraining",
                "custom_limit_lowered",
                path + ".custom_section",
                "fewer custom properties are allowed",
            )
        else:
            sink.add(
                "additive",
                "custom_limit_raised",
                path + ".custom_section",
                "more custom properties are allowed",
                relaxing=True,
            )


def _renames(
    removed: Mapping[str, PropertyDef], added: Mapping[str, PropertyDef]
) -> dict[str, str]:
    """Removed properties that came back under a new name: same range, unit and description."""
    pairs: dict[str, str] = {}
    taken: set[str] = set()
    for old_name in sorted(removed):
        gone = removed[old_name]
        for new_name in sorted(added):
            if new_name in taken:
                continue
            came = added[new_name]
            if (
                gone.range == came.range
                and _unit(gone) == _unit(came)
                and gone.description.strip() == came.description.strip()
            ):
                pairs[old_name] = new_name
                taken.add(new_name)
                break
    return pairs


def _unit(prop: PropertyDef) -> str | None:
    return prop.unit.ucum if prop.unit is not None else None


def _states(prop: PropertyDef | TightenDef) -> list[str]:
    """The states a property needs a value in; ``["*"]`` is every state."""
    if isinstance(prop, PropertyDef):
        return [_ALWAYS] if prop.required else list(prop.required_in_states)
    return list(prop.required_in_states or [])


def _property(
    path: str,
    before: PropertyDef,
    after: PropertyDef,
    pset_before: str,
    pset_after: str,
    sink: _Sink,
) -> None:
    if before.range != after.range:
        sink.add("breaking", "type_changed", path, f"range {before.range} became {after.range}")
    if _unit(before) != _unit(after):
        sink.add("breaking", "unit_changed", path, f"unit {_unit(before)} became {_unit(after)}")
    _states_change(_states(before), _states(after), sink, path)
    was = before.enforcement or pset_before
    now = after.enforcement or pset_after
    _rank_change(_ENFORCEMENT_RANK, was, now, sink, path + ".enforcement", "enforcement")
    if before.value_list_policy != after.value_list_policy:
        _rank_change(
            _POLICY_RANK,
            before.value_list_policy or "extensible",
            after.value_list_policy or "extensible",
            sink,
            path + ".value_list_policy",
            "value_list_policy",
        )
    _bound("minimum", before.minimum, after.minimum, sink, path)
    _bound("maximum", before.maximum, after.maximum, sink, path)
    _pattern(before.pattern, after.pattern, sink, path)
    if before.default != after.default:
        sink.add("additive", "default_changed", path, "the default changed")
    if before.materialize and not after.materialize:
        sink.add("deprecation", "materialize_removed", path, "the promoted column goes away")
    elif after.materialize and not before.materialize:
        sink.add("additive", "materialize_added", path, "a promoted column appears")
    _mappings(before.exact_mappings, after.exact_mappings, sink, path)
    if before.description != after.description:
        sink.add("additive", "description_changed", path, "the description changed", review=True)
    if before.label != after.label:
        sink.add("additive", "label_changed", path, "the label changed")


def _states_change(before: Sequence[str], after: Sequence[str], sink: _Sink, path: str) -> None:
    old_all, new_all = _ALWAYS in before, _ALWAYS in after
    grown = (new_all and not old_all) or (not new_all and not old_all and set(after) - set(before))
    shrunk = (old_all and not new_all) or (not new_all and not old_all and set(before) - set(after))
    if grown:
        sink.add(
            "constraining",
            "required_added",
            path + ".required_in_states",
            "a value is required in more states",
        )
    if shrunk:
        sink.add(
            "additive",
            "required_dropped",
            path + ".required_in_states",
            "a value is required in fewer states",
            relaxing=True,
        )


def _bound(kind: str, before: float | None, after: float | None, sink: _Sink, path: str) -> None:
    if before == after:
        return
    tighter: bool
    if before is None:
        tighter = True
    elif after is None:
        tighter = False
    elif kind == "minimum":
        tighter = after > before
    else:
        tighter = after < before
    where = f"{path}.{kind}"
    if tighter:
        sink.add("constraining", f"{kind}_tightened", where, f"{kind} {before} became {after}")
    else:
        sink.add(
            "additive", f"{kind}_relaxed", where, f"{kind} {before} became {after}", relaxing=True
        )


def _pattern(before: str | None, after: str | None, sink: _Sink, path: str) -> None:
    if before == after:
        return
    if after is None:
        sink.add(
            "additive",
            "pattern_dropped",
            path + ".pattern",
            "the pattern was dropped",
            relaxing=True,
        )
    else:
        sink.add(
            "constraining",
            "pattern_changed",
            path + ".pattern",
            "a pattern was added or changed; whether it is stricter cannot be told",
        )


def _mappings(before: Sequence[str], after: Sequence[str], sink: _Sink, path: str) -> None:
    lost = sorted(set(before) - set(after))
    if lost:
        sink.add(
            "forbidden",
            "mapping_removed",
            path + ".exact_mappings",
            f"an existing external mapping was removed or replaced ({', '.join(lost)}); "
            "a different meaning is a new property",
        )
    gained = sorted(set(after) - set(before))
    if gained and not lost:
        sink.add(
            "additive",
            "mapping_added",
            path + ".exact_mappings",
            f"external mapping added ({', '.join(gained)})",
        )


# --- extensions ------------------------------------------------------------------------------


def _extends(old: Sequence[ExtendsDef], new: Sequence[ExtendsDef], sink: _Sink) -> None:
    before = {e.ref: e for e in old}
    after = {e.ref: e for e in new}
    for ref in sorted(set(before) | set(after)):
        path = f"extends.{ref}"
        was, now = before.get(ref), after.get(ref)
        if was is None and now is not None:
            was = ExtendsDef(ref=ref)
            sink.add("additive", "extension_added", path, f"extension of {ref} added")
        elif now is None:
            sink.add("deprecation", "extension_removed", path, f"extension of {ref} removed")
            continue
        assert was is not None and now is not None
        _tighten(path, was.tighten, now.tighten, sink)
        _add_values(path, was.add_values, now.add_values, sink)
        _custom(path, was.custom, now.custom, sink)
        if was.defaults != now.defaults:
            sink.add("additive", "defaults_changed", path + ".defaults", "defaults changed")
        if was.labels != now.labels:
            sink.add("additive", "labels_changed", path + ".labels", "labels changed")


def _tighten(
    path: str, before: Mapping[str, TightenDef], after: Mapping[str, TightenDef], sink: _Sink
) -> None:
    for prop in sorted(set(before) | set(after)):
        where = f"{path}.tighten.{prop}"
        was, now = before.get(prop), after.get(prop)
        if was is None and now is not None:
            sink.add("constraining", "tighten_added", where, f"{prop} is made stricter")
        elif now is None:
            sink.add(
                "additive",
                "tighten_removed",
                where,
                f"{prop} is no longer made stricter",
                relaxing=True,
            )
        else:
            assert was is not None
            _states_change(_states(was), _states(now), sink, where)
            if was.enforcement != now.enforcement:
                lo = _ENFORCEMENT_RANK.get(was.enforcement or "advisory", 0)
                hi = _ENFORCEMENT_RANK.get(now.enforcement or "advisory", 0)
                if hi > lo:
                    sink.add(
                        "constraining",
                        "enforcement_tightened",
                        where + ".enforcement",
                        f"enforcement {was.enforcement} became {now.enforcement}",
                    )
                else:
                    sink.add(
                        "additive",
                        "enforcement_relaxed",
                        where + ".enforcement",
                        f"enforcement {was.enforcement} became {now.enforcement}",
                        relaxing=True,
                    )
            _bound("minimum", was.minimum, now.minimum, sink, where)
            _bound("maximum", was.maximum, now.maximum, sink, where)
            _pattern(was.pattern, now.pattern, sink, where)


def _add_values(
    path: str,
    before: Mapping[str, list[CodeValue]],
    after: Mapping[str, list[CodeValue]],
    sink: _Sink,
) -> None:
    for name in sorted(set(before) | set(after)):
        was = {v.code for v in before.get(name, [])}
        now = {v.code for v in after.get(name, [])}
        where = f"{path}.add_values.{name}"
        for code in sorted(now - was):
            sink.add("additive", "value_added", where, f"value {code} added to {name}")
        for code in sorted(was - now):
            sink.add(
                "deprecation", "value_removed", where, f"value {code} no longer added to {name}"
            )


def _custom(
    path: str, before: Mapping[str, PropertyDef], after: Mapping[str, PropertyDef], sink: _Sink
) -> None:
    for prop in sorted(set(before) | set(after)):
        where = f"{path}.custom.{prop}"
        was, now = before.get(prop), after.get(prop)
        if was is None and now is not None:
            code: ChangeClass = "constraining" if _states(now) else "additive"
            sink.add(code, "custom_added", where, f"custom property {prop} added")
        elif now is None:
            sink.add("deprecation", "custom_removed", where, f"custom property {prop} removed")
        elif was is not None:
            _property(where, was, now, "advisory", "advisory", sink)


# --- conformance -----------------------------------------------------------------------------


def _conformance(before: ConformanceDef | None, after: ConformanceDef | None, sink: _Sink) -> None:
    if before is None and after is None:
        return
    was = before or ConformanceDef()
    now = after or ConformanceDef()
    _rank_change(_MODE_RANK, was.mode, now.mode, sink, "conformance.mode", "mode")
    if was.lenient_until != now.lenient_until:
        ends_sooner = now.lenient_until is not None and (
            was.lenient_until is None or now.lenient_until < was.lenient_until
        )
        sink.add(
            "constraining" if ends_sooner else "additive",
            "lenient_until_changed",
            "conformance.lenient_until",
            f"the lenient period ends {now.lenient_until} (was {was.lenient_until})",
            relaxing=not ends_sooner,
        )
    old_paths = {w.path: w for w in was.waivers}
    new_paths = {w.path: w for w in now.waivers}
    for path in sorted(set(new_paths) - set(old_paths)):
        sink.add(
            "additive",
            "waiver_added",
            f"conformance.waivers.{path}",
            f"waiver for {path} added",
            relaxing=True,
        )
    for path in sorted(set(old_paths) - set(new_paths)):
        sink.add(
            "constraining",
            "waiver_removed",
            f"conformance.waivers.{path}",
            f"waiver for {path} removed; records it covered are checked again",
        )
