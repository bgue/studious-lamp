# pyright: basic
"""Classify the change between two trees of repository LinkML schemas (brief 27.5; P1-I8-T02).

The gate `tl schema classify --base <git ref>` (build spec 04, section 1) compares the schemas of
the working tree with the ones at a git ref. Packages of companies and projects are classified by
``tl_schema.classify``; this module does the same job for the files under ``schema/core`` and
``schema/modules``, which are real LinkML and which generate the tables, events and API of the
platform.

There is no ``linkml diff`` in the installed LinkML, so the comparison is made here, class by class
and slot by slot, on what ``SchemaView`` induces for each class defined in a file. The rules are
the ones of ``tl_schema.classify`` with two differences that follow from what a repository schema
generates:

* removing a class, a slot or an enum value is ``breaking`` (a column or an event field goes away;
  the gate asks for an upcaster, an ADR and a person), where a package only ``deprecation``s it;
* a required slot added to an *event payload* class is ``breaking``, not ``constraining``: events
  are immutable and the old ones cannot carry it.

A file that is new is ``additive``; one that is gone is ``breaking``. Files whose YAML does not load
are reported as ``breaking`` with the loader's message, so a broken schema never passes as clean.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from linkml_runtime.linkml_model.meta import ClassDefinition, EnumDefinition, SlotDefinition
from linkml_runtime.utils.schemaview import SchemaView

from tl_schema.classify import Change, ChangeClass, ClassificationReport, build_report

#: Directories (below the schema root) whose files are LinkML. ``fixtures`` holds packages and data.
LINKML_DIRS = ("core", "modules")
_EVENT_TAG = "tl:event_type"


def _annotation(definition: Any, tag: str) -> str | None:
    annotations = getattr(definition, "annotations", None) or {}
    entry = annotations.get(tag)
    if entry is None:
        return None
    return str(getattr(entry, "value", entry))


def _files(root: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for top in LINKML_DIRS:
        base = root / top
        if base.is_dir():
            for path in sorted(base.rglob("*.yaml")):
                found[path.relative_to(root).as_posix()] = path
    return found


def classify_trees(old_root: Path, new_root: Path) -> ClassificationReport:
    """Classify ``new_root`` (a ``schema`` directory) against ``old_root``.

    Both are ``schema`` directories (the one at the base ref is a checked-out copy). The report's
    paths start with the file's path below the root, then ``classes.<Name>.<slot>`` and so on.
    """
    before, after = _files(old_root), _files(new_root)
    changes: list[Change] = []
    for name in sorted(set(before) | set(after)):
        if name not in before:
            changes.append(
                Change(cls="additive", code="file_added", path=name, detail="new schema file")
            )
        elif name not in after:
            changes.append(
                Change(cls="breaking", code="file_removed", path=name, detail="schema file removed")
            )
        else:
            try:
                changes.extend(_compare_files(name, before[name], after[name]))
            except Exception as exc:  # noqa: BLE001 - a file that does not load must not pass
                changes.append(
                    Change(
                        cls="breaking",
                        code="schema_unreadable",
                        path=name,
                        detail=f"cannot be loaded: {type(exc).__name__}: {str(exc)[:200]}",
                    )
                )
    return build_report(str(old_root), str(new_root), changes)


def _compare_files(name: str, old_path: Path, new_path: Path) -> list[Change]:
    if old_path.read_bytes() == new_path.read_bytes():
        return []
    old_view, new_view = SchemaView(str(old_path)), SchemaView(str(new_path))
    return classify_views(old_view, new_view, prefix=name)


def classify_views(old: SchemaView, new: SchemaView, *, prefix: str) -> list[Change]:
    """The changes in the classes and enums that ``new`` defines itself, against ``old``."""
    out: list[Change] = []

    def add(cls: ChangeClass, code: str, path: str, detail: str, **flags: bool) -> None:
        out.append(Change(cls=cls, code=code, path=f"{prefix}:{path}", detail=detail, **flags))

    old_classes = old.all_classes(imports=False)
    new_classes = new.all_classes(imports=False)
    for cname in sorted(set(old_classes) | set(new_classes)):
        path = f"classes.{cname}"
        if cname not in old_classes:
            add("additive", "class_added", path, f"class {cname} added")
        elif cname not in new_classes:
            add("breaking", "class_removed", path, f"class {cname} removed")
        else:
            _class(cname, old, new, old_classes[cname], new_classes[cname], add)
    old_enums = old.all_enums(imports=False)
    new_enums = new.all_enums(imports=False)
    for ename in sorted(set(old_enums) | set(new_enums)):
        path = f"enums.{ename}"
        if ename not in old_enums:
            add("additive", "enum_added", path, f"enum {ename} added")
        elif ename not in new_enums:
            add("breaking", "enum_removed", path, f"enum {ename} removed")
        else:
            _enum(ename, old_enums[ename], new_enums[ename], add)
    return out


def _class(cname, old, new, was: ClassDefinition, now: ClassDefinition, add) -> None:  # noqa: ANN001
    path = f"classes.{cname}"
    if was.is_a != now.is_a:
        add("breaking", "is_a_changed", path, f"parent {was.is_a} became {now.is_a}")
    for tag in ("tl:table", _EVENT_TAG, "tl:record_types"):
        if _annotation(was, tag) != _annotation(now, tag):
            add(
                "breaking",
                "annotation_changed",
                f"{path}.{tag}",
                f"{tag} {_annotation(was, tag)} became {_annotation(now, tag)}",
            )
    payload = _annotation(now, _EVENT_TAG) is not None
    old_slots = {s.name: s for s in old.class_induced_slots(cname)}
    new_slots = {s.name: s for s in new.class_induced_slots(cname)}
    for sname in sorted(set(old_slots) | set(new_slots)):
        spath = f"{path}.{sname}"
        if sname not in old_slots:
            slot = new_slots[sname]
            if slot.required or slot.identifier:
                add(
                    "breaking" if payload else "constraining",
                    "slot_added_required",
                    spath,
                    f"required slot {sname} added" + (" to an event payload" if payload else ""),
                )
            else:
                add("additive", "slot_added", spath, f"slot {sname} added")
        elif sname not in new_slots:
            add("breaking", "slot_removed", spath, f"slot {sname} removed")
        else:
            _slot(spath, payload, old, new, old_slots[sname], new_slots[sname], add)
    was_keys = {str(k) for k in (was.unique_keys or {})}
    now_keys = {str(k) for k in (now.unique_keys or {})}
    for key in sorted(now_keys - was_keys):
        add(
            "constraining",
            "unique_key_added",
            f"{path}.unique_keys.{key}",
            f"unique key {key} added",
        )
    for key in sorted(was_keys - now_keys):
        add(
            "additive",
            "unique_key_removed",
            f"{path}.unique_keys.{key}",
            f"unique key {key} removed",
            relaxing=True,
        )
    if (was.description or "").strip() != (now.description or "").strip():
        add("additive", "description_changed", path, f"description of {cname} changed", review=True)


def _range(view: SchemaView, slot: SlotDefinition) -> str:
    default = view.schema.default_range if view.schema is not None else None
    return str(slot.range or default or "string")


def _slot(spath, payload, old, new, was: SlotDefinition, now: SlotDefinition, add) -> None:  # noqa: ANN001
    if _range(old, was) != _range(new, now):
        add(
            "breaking",
            "range_changed",
            spath,
            f"range {_range(old, was)} became {_range(new, now)}",
        )
    if bool(was.multivalued) != bool(now.multivalued):
        add("breaking", "multivalued_changed", spath, "multivalued changed")
    if bool(was.identifier) != bool(now.identifier):
        add("breaking", "identifier_changed", spath, "identifier changed")
    if not was.required and now.required:
        add(
            "breaking" if payload else "constraining",
            "required_added",
            spath,
            "the slot became required",
        )
    elif was.required and not now.required:
        add("additive", "required_dropped", spath, "the slot is no longer required", relaxing=True)
    for attr, code in (("minimum_value", "minimum"), ("maximum_value", "maximum")):
        before, after = getattr(was, attr), getattr(now, attr)
        if before == after:
            continue
        tighter = before is None or (
            after is not None and (after > before if attr == "minimum_value" else after < before)
        )
        if tighter:
            add(
                "constraining",
                f"{code}_tightened",
                f"{spath}.{code}",
                f"{code} {before} became {after}",
            )
        else:
            add(
                "additive",
                f"{code}_relaxed",
                f"{spath}.{code}",
                f"{code} {before} became {after}",
                relaxing=True,
            )
    if was.pattern != now.pattern:
        if now.pattern is None:
            add("additive", "pattern_dropped", f"{spath}.pattern", "pattern dropped", relaxing=True)
        else:
            add("constraining", "pattern_changed", f"{spath}.pattern", "pattern added or changed")
    if (was.description or "").strip() != (now.description or "").strip():
        add("additive", "description_changed", spath, "description changed", review=True)


def _enum(ename, was: EnumDefinition, now: EnumDefinition, add) -> None:  # noqa: ANN001
    old_values = {str(v) for v in (was.permissible_values or {})}
    new_values = {str(v) for v in (now.permissible_values or {})}
    for value in sorted(new_values - old_values):
        add("additive", "enum_value_added", f"enums.{ename}.{value}", f"value {value} added")
    for value in sorted(old_values - new_values):
        add("breaking", "enum_value_removed", f"enums.{ename}.{value}", f"value {value} removed")
